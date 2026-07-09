"""机械臂可达工作空间生成器 — 几何探测 + URDF 关节限位 + 解析计算。

速度策略（< 1 秒）：
  1. 用 4 次 compute_fk 探测连杆长度和基座偏移
  2. 从 URDF 自动获取各关节真实上下限（滑轨行程 + 旋转范围）
  3. 在关节空间 (slider × j1 × j2) 全范围解析生成可达点（零额外 ROS 调用）
  4. 完全避免 compute_ik（无 error -31）
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Joint limits: read from URDF via ROS2
# ---------------------------------------------------------------------------

def _get_joint_limits(moveit2):
    """从 URDF 获取各关节的上下限位。

    依次尝试：moveit2 内部 URDF → 节点参数 → subprocess ros2 param get。
    Returns: {joint_name: (lower, upper)} 或 None。
    """
    import xml.etree.ElementTree as ET

    urdf_str = None

    # ① pymoveit2 内部属性
    for attr in ("_robot_description",
                 "_MoveIt2__robot_description",
                 "robot_description"):
        val = getattr(moveit2, attr, None)
        if isinstance(val, str) and "<robot" in val:
            urdf_str = val
            logger.info("Got URDF from moveit2.%s (%d chars)", attr, len(val))
            break

    # ② 节点参数
    if urdf_str is None:
        node = getattr(moveit2, "_node", None)
        if node is not None:
            try:
                try:
                    node.declare_parameter("robot_description", "")
                except Exception:
                    pass
                val = node.get_parameter("robot_description") \
                          .get_parameter_value().string_value
                if val and "<robot" in val:
                    urdf_str = val
                    logger.info("Got URDF from node parameter (%d chars)", len(val))
            except Exception as e:
                logger.debug("node param failed: %s", e)

    # ③ subprocess
    if urdf_str is None:
        import subprocess
        for target in ("/move_group", "/robot_state_publisher"):
            try:
                r = subprocess.run(
                    ["ros2", "param", "get", target, "robot_description"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and "<robot" in r.stdout:
                    idx = r.stdout.find("<robot")
                    if idx >= 0:
                        urdf_str = r.stdout[idx:]
                        logger.info("Got URDF from %s (%d chars)", target, len(urdf_str))
                        break
            except Exception:
                pass

    if not urdf_str:
        logger.warning("Could not retrieve URDF — joint limits unavailable, using fallback ranges")
        return None

    # 解析 XML
    try:
        start = urdf_str.find("<robot")
        end = urdf_str.rfind("</robot>")
        if start >= 0 and end > start:
            urdf_str = urdf_str[start : end + len("</robot>")]
        root = ET.fromstring(urdf_str)
    except ET.ParseError as e:
        logger.warning("URDF parse error: %s", e)
        return None

    limits = {}
    for joint_elem in root.findall(".//joint"):
        jtype = joint_elem.get("type", "")
        if jtype in ("fixed", "floating"):
            continue
        name = joint_elem.get("name", "")
        limit_elem = joint_elem.find("limit")
        if limit_elem is not None:
            lo = float(limit_elem.get("lower", "0"))
            hi = float(limit_elem.get("upper", "0"))
            if lo != hi:
                limits[name] = (lo, hi)

    result = {}
    for jn in moveit2.joint_names:
        if jn in limits:
            result[jn] = limits[jn]
            logger.info("  Joint limit: %-30s [%+.4f, %+.4f]", jn, *limits[jn])
        else:
            logger.warning("  Joint limit: %-30s NOT FOUND in URDF", jn)

    return result if result else None


# ---------------------------------------------------------------------------
# Geometry discovery: ~4 FK calls → learn arm dimensions
# ---------------------------------------------------------------------------

def _discover_arm_geometry(moveit2):
    """用少量 FK 调用探测机械臂的几何参数 + 从 URDF 读取关节限位。"""
    n_joints = len(moveit2.joint_names)
    zeros = [0.0] * n_joints

    def fk_at(joint_vals):
        try:
            r = moveit2.compute_fk(joint_state=joint_vals)
            if r is None:
                return None
            p = r.pose.position
            return [p.x, p.y, p.z]
        except Exception as e:
            logger.warning("FK probe failed: %s", e)
            return None

    p0 = fk_at(zeros)
    if p0 is None:
        logger.error("FK at zero-state failed, cannot discover geometry")
        return None
    logger.info("FK probe [0]: all-zero → (%.4f, %.4f, %.4f)", *p0)

    delta_j1 = 0.3
    j1_state = list(zeros)
    j1_state[1] = delta_j1
    p1 = fk_at(j1_state)
    if p1 is None:
        return None
    logger.info("FK probe [1]: j1=%.2f → (%.4f, %.4f, %.4f)", delta_j1, *p1)

    delta_j2 = 0.3
    j2_state = list(zeros)
    j2_state[2] = delta_j2
    p2 = fk_at(j2_state)
    if p2 is None:
        return None
    logger.info("FK probe [2]: j2=%.2f → (%.4f, %.4f, %.4f)", delta_j2, *p2)

    slider_state = list(zeros)
    slider_state[0] = 0.1
    ps = fk_at(slider_state)
    if ps is None:
        return None
    logger.info("FK probe [3]: slider=0.1 → (%.4f, %.4f, %.4f)", *ps)

    p0, p1, p2, ps = np.array(p0), np.array(p1), np.array(p2), np.array(ps)
    slider_diff = ps - p0
    if abs(slider_diff[2]) > abs(slider_diff[0]) and abs(slider_diff[2]) > abs(slider_diff[1]):
        slider_axis = "z"
    elif abs(slider_diff[0]) > abs(slider_diff[1]):
        slider_axis = "x"
    else:
        slider_axis = "y"
    logger.info("Slider axis: %s (diff=%.4f,%.4f,%.4f)", slider_axis, *slider_diff)

    reach_at_zero = math.sqrt(p0[0]**2 + p0[1]**2)
    angle_at_zero = math.atan2(p0[1], p0[0])

    d_j2 = np.linalg.norm(p2[:2] - p0[:2])
    L_total = reach_at_zero
    L2_approx = d_j2 / (2 * math.sin(abs(delta_j2) / 2)) if abs(delta_j2) > 0.01 else L_total * 0.4
    L1_approx = L_total - L2_approx

    if L1_approx < 0.02:
        L1_approx = L_total * 0.5
        L2_approx = L_total * 0.5

    current_pos = []
    if moveit2.joint_state is not None and hasattr(moveit2.joint_state, 'position'):
        current_pos = list(moveit2.joint_state.position)
    slider_pos = current_pos[0] if current_pos else 0.0

    base_angle = angle_at_zero

    geo = {
        "base_offset": [0.0, 0.0, float(p0[2])],
        "base_angle": float(base_angle),
        "link1": float(abs(L1_approx)),
        "link2": float(abs(L2_approx)),
        "total_reach": float(L_total),
        "slider_axis": slider_axis,
        "slider_delta_per_unit": float(np.linalg.norm(slider_diff) / 0.1),
        "home_z": float(p0[2]),
        "slider_pos": float(slider_pos),
        "joint_names": list(moveit2.joint_names),
    }

    limits = _get_joint_limits(moveit2)
    geo["joint_limits"] = limits or {}

    logger.info("Discovered geometry: L1=%.4f, L2=%.4f, total=%.4f, base_angle=%.2f°, slider=%s, limits=%d joints",
                geo["link1"], geo["link2"], geo["total_reach"],
                math.degrees(base_angle), slider_axis, len(geo["joint_limits"]))
    return geo


# ---------------------------------------------------------------------------
# Analytical workspace: joint-space parametrization
# ---------------------------------------------------------------------------

def _analytical_workspace(geo, *, resolution=0.03, n_j1=72, n_j2=36):
    """从关节限位 + 连杆长度解析生成完整 3D 工作空间。

    使用关节空间参数化 (slider × j1 × j2) 而非极坐标，
    以正确处理旋转受限的情况。纯数学，零 ROS 调用。
    """
    L1 = geo["link1"]
    L2 = geo["link2"]
    base_angle = geo.get("base_angle", 0.0)
    home_z = geo["home_z"]
    slider_axis = geo["slider_axis"]
    slider_delta = geo["slider_delta_per_unit"]
    slider_pos = geo.get("slider_pos", 0.0)
    limits = geo.get("joint_limits", {})
    jnames = geo.get("joint_names", [])

    if jnames and jnames[0] in limits:
        s_lo, s_hi = limits[jnames[0]]
    else:
        s_lo, s_hi = max(slider_pos - 0.2, 0.0), slider_pos + 0.2

    if len(jnames) > 1 and jnames[1] in limits:
        j1_lo, j1_hi = limits[jnames[1]]
    else:
        j1_lo, j1_hi = -math.pi, math.pi

    if len(jnames) > 2 and jnames[2] in limits:
        j2_lo, j2_hi = limits[jnames[2]]
    else:
        j2_lo, j2_hi = -math.pi, math.pi

    n_slider = max(3, int((s_hi - s_lo) / 0.05) + 1)
    slider_vals = np.linspace(s_lo, s_hi, n_slider)
    j1_vals = np.linspace(j1_lo, j1_hi, n_j1)
    j2_vals = np.linspace(j2_lo, j2_hi, n_j2)

    t0 = time.time()
    seen = set()
    points = []
    inv_res = 1.0 / resolution

    for sv in slider_vals:
        if slider_axis == "z":
            dz = (sv - slider_pos) * slider_delta
            dx = 0.0
        elif slider_axis == "x":
            dx = (sv - slider_pos) * slider_delta
            dz = 0.0
        else:
            dx, dz = 0.0, 0.0
        z = round(home_z + dz, 4)

        for j1 in j1_vals:
            a1 = base_angle + j1
            arm1_x = L1 * math.cos(a1)
            arm1_y = L1 * math.sin(a1)
            for j2 in j2_vals:
                a12 = a1 + j2
                x = arm1_x + L2 * math.cos(a12) + dx
                y = arm1_y + L2 * math.sin(a12)
                gx = round(round(x * inv_res) / inv_res, 4)
                gy = round(round(y * inv_res) / inv_res, 4)
                key = (gx, gy, z)
                if key not in seen:
                    seen.add(key)
                    points.append([gx, gy, z])

    elapsed = time.time() - t0
    logger.info(
        "Analytical workspace: %d unique pts in %.3fs "
        "(slider=[%.3f,%.3f] j1=[%.1f°,%.1f°] j2=[%.1f°,%.1f°])",
        len(points), elapsed, s_lo, s_hi,
        math.degrees(j1_lo), math.degrees(j1_hi),
        math.degrees(j2_lo), math.degrees(j2_hi),
    )
    return points


def _analytical_workspace_at_z(geo, z_target, *, resolution=0.03, n_j1=90, n_j2=45):
    """在指定 Z 高度生成 2D 可达轮廓（关节空间参数化）。"""
    L1 = geo["link1"]
    L2 = geo["link2"]
    base_angle = geo.get("base_angle", 0.0)
    slider_axis = geo["slider_axis"]
    slider_delta = geo["slider_delta_per_unit"]
    slider_pos = geo.get("slider_pos", 0.0)
    limits = geo.get("joint_limits", {})
    jnames = geo.get("joint_names", [])

    if len(jnames) > 1 and jnames[1] in limits:
        j1_lo, j1_hi = limits[jnames[1]]
    else:
        j1_lo, j1_hi = -math.pi, math.pi
    if len(jnames) > 2 and jnames[2] in limits:
        j2_lo, j2_hi = limits[jnames[2]]
    else:
        j2_lo, j2_hi = -math.pi, math.pi

    j1_vals = np.linspace(j1_lo, j1_hi, n_j1)
    j2_vals = np.linspace(j2_lo, j2_hi, n_j2)

    if slider_axis != "z":
        if jnames and jnames[0] in limits:
            s_lo, s_hi = limits[jnames[0]]
        else:
            s_lo, s_hi = max(slider_pos - 0.2, 0.0), slider_pos + 0.2
        n_sv = max(3, int((s_hi - s_lo) / 0.05) + 1)
        slider_vals = np.linspace(s_lo, s_hi, n_sv)
    else:
        slider_vals = [0.0]

    seen = set()
    points = []
    inv_res = 1.0 / resolution

    for sv in slider_vals:
        dx = (sv - slider_pos) * slider_delta if slider_axis == "x" else 0.0
        for j1 in j1_vals:
            a1 = base_angle + j1
            arm1_x = L1 * math.cos(a1)
            arm1_y = L1 * math.sin(a1)
            for j2 in j2_vals:
                a12 = a1 + j2
                x = arm1_x + L2 * math.cos(a12) + dx
                y = arm1_y + L2 * math.sin(a12)
                gx = round(round(x * inv_res) / inv_res, 4)
                gy = round(round(y * inv_res) / inv_res, 4)
                key = (gx, gy)
                if key not in seen:
                    seen.add(key)
                    points.append([gx, gy])

    return points


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_workspace(
    arm_id: str,
    arm_pose: dict,
    moveit2_instance: Any,
    *,
    resolution: float = 0.05,
    reach_estimate: float = 0.5,
    z_min: float = 0.0,
    z_max: float = 0.6,
    max_points: int = 50000,
    ee_quat: tuple | None = None,
    multi_pose: bool = True,
    voxel_maps: dict | None = None,
) -> dict:
    """生成 3D 可达工作空间点云。"""
    if voxel_maps and arm_id in voxel_maps:
        return _from_voxel_map(arm_id, arm_pose, voxel_maps[arm_id], resolution, max_points)

    if moveit2_instance is None:
        raise RuntimeError(f"No MoveIt2 instance for arm '{arm_id}'.")

    cx, cy = arm_pose["x"], arm_pose["y"]
    theta = arm_pose.get("theta", 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    t0 = time.time()
    geo = _discover_arm_geometry(moveit2_instance)
    if geo is None:
        raise RuntimeError(f"Cannot discover geometry for arm '{arm_id}'")

    local_points = _analytical_workspace(geo, resolution=resolution)
    if len(local_points) > max_points:
        step = max(1, len(local_points) // max_points)
        local_points = local_points[::step]

    world_points = []
    for lx, ly, lz in local_points:
        wx = cx + lx * cos_t - ly * sin_t
        wy = cy + lx * sin_t + ly * cos_t
        world_points.append([round(wx, 4), round(wy, 4), round(lz, 4)])

    elapsed = time.time() - t0
    bounds = _compute_bounds(world_points)
    return {
        "arm_id": arm_id, "source": "analytical_fk",
        "method": "geometry_discovery + URDF limits + analytical",
        "geometry": geo,
        "resolution": round(resolution, 4), "arm_pose": arm_pose,
        "points": world_points, "bounds": bounds,
        "stats": {
            "total_points": len(world_points),
            "reachable_points": len(world_points),
            "reachable_ratio": 1.0,
            "compute_time_s": round(elapsed, 2),
        },
    }


def generate_workspace_slices(
    arm_id: str,
    arm_pose: dict,
    moveit2_instance: Any,
    *,
    z_values: list[float] | None = None,
    resolution: float = 0.04,
    reach_estimate: float = 0.5,
    ee_quat: tuple | None = None,
    multi_pose: bool = True,
    voxel_maps: dict | None = None,
) -> dict:
    """生成水平截面。"""
    cx, cy = arm_pose["x"], arm_pose["y"]
    theta = arm_pose.get("theta", 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    if voxel_maps and arm_id in voxel_maps:
        if z_values is None:
            z_values = [0.05, 0.15, 0.25, 0.35, 0.45]
        return _slices_from_voxel_map(arm_id, arm_pose, voxel_maps[arm_id], z_values, resolution)

    if moveit2_instance is None:
        raise RuntimeError(f"No MoveIt2 instance for arm '{arm_id}'.")

    t0 = time.time()
    geo = _discover_arm_geometry(moveit2_instance)
    if geo is None:
        raise RuntimeError(f"Cannot discover geometry for arm '{arm_id}'")

    if z_values is None:
        fk_z = geo["home_z"]
        slider_axis = geo["slider_axis"]

        if slider_axis == "z":
            jnames = geo.get("joint_names", [])
            lim = geo.get("joint_limits", {})
            sp = geo.get("slider_pos", 0.0)
            sd = geo["slider_delta_per_unit"]
            if jnames and jnames[0] in lim:
                s_lo, s_hi = lim[jnames[0]]
            else:
                s_lo, s_hi = max(sp - 0.2, 0.0), sp + 0.2
            z_lo = fk_z + (s_lo - sp) * sd
            z_hi = fk_z + (s_hi - sp) * sd
            if z_lo > z_hi:
                z_lo, z_hi = z_hi, z_lo
            n_slices = min(12, max(5, int((z_hi - z_lo) / 0.03) + 1))
            z_values = [round(z, 4) for z in np.linspace(z_lo, z_hi, n_slices)]
            logger.info("Z range from slider limits: [%.3f, %.3f] → %d slices", z_lo, z_hi, n_slices)
        else:
            z_values = [round(fk_z + dz, 3) for dz in [-0.10, -0.05, 0.0, 0.05, 0.10]]

    slices = []
    total_reachable = 0
    for z in z_values:
        local_pts = _analytical_workspace_at_z(geo, z, resolution=resolution)
        world_pts = []
        for lx, ly in local_pts:
            wx = cx + lx * cos_t - ly * sin_t
            wy = cy + lx * sin_t + ly * cos_t
            world_pts.append([round(wx, 4), round(wy, 4)])
        total_reachable += len(world_pts)
        contour = _extract_contour(world_pts)
        slices.append({"z": round(z, 4), "contour": contour, "reachable_count": len(world_pts)})
        logger.info("  z=%.3f: %d reachable points", z, len(world_pts))

    elapsed = time.time() - t0
    logger.info("Slices done: %d total reachable in %.3fs", total_reachable, elapsed)
    return {
        "arm_id": arm_id, "source": "analytical_fk",
        "method": "geometry_discovery + URDF limits + analytical",
        "geometry": geo,
        "arm_pose": arm_pose, "slices": slices,
        "stats": {
            "reachable_points": total_reachable,
            "compute_time_s": round(elapsed, 2),
        },
    }


# ---------------------------------------------------------------------------
# Voxel map loaders
# ---------------------------------------------------------------------------

def _from_voxel_map(arm_id, arm_pose, voxel_map, resolution, max_points):
    vm = voxel_map
    step = max(1, int(resolution / vm.resolution))
    cx, cy = arm_pose["x"], arm_pose["y"]
    theta = arm_pose.get("theta", 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    points = []
    for ix in range(0, vm.grid.shape[0], step):
        for iy in range(0, vm.grid.shape[1], step):
            for iz in range(0, vm.grid.shape[2], step):
                if not vm.grid[ix, iy, iz]:
                    continue
                lx = vm.origin[0] + ix * vm.resolution
                ly = vm.origin[1] + iy * vm.resolution
                lz = vm.origin[2] + iz * vm.resolution
                wx = cx + lx * cos_t - ly * sin_t
                wy = cy + lx * sin_t + ly * cos_t
                points.append([round(wx, 4), round(wy, 4), round(lz, 4)])
                if len(points) >= max_points:
                    break
            if len(points) >= max_points:
                break
        if len(points) >= max_points:
            break
    bounds = _compute_bounds(points)
    return {
        "arm_id": arm_id, "source": "voxel_map",
        "resolution": round(resolution, 4), "arm_pose": arm_pose,
        "points": points, "bounds": bounds,
        "stats": {"total_points": len(points), "compute_time_s": 0.0},
    }


def _slices_from_voxel_map(arm_id, arm_pose, voxel_map, z_values, resolution):
    vm = voxel_map
    cx, cy = arm_pose["x"], arm_pose["y"]
    theta = arm_pose.get("theta", 0.0)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    slices = []
    for z in z_values:
        iz = int(round((z - vm.origin[2]) / vm.resolution))
        if iz < 0 or iz >= vm.grid.shape[2]:
            slices.append({"z": round(z, 4), "contour": [], "reachable_count": 0})
            continue
        pts = []
        step = max(1, int(resolution / vm.resolution))
        for ix in range(0, vm.grid.shape[0], step):
            for iy in range(0, vm.grid.shape[1], step):
                if not vm.grid[ix, iy, iz]:
                    continue
                lx = vm.origin[0] + ix * vm.resolution
                ly = vm.origin[1] + iy * vm.resolution
                wx = cx + lx * cos_t - ly * sin_t
                wy = cy + lx * sin_t + ly * cos_t
                pts.append([round(wx, 4), round(wy, 4)])
        contour = _extract_contour(pts)
        slices.append({"z": round(z, 4), "contour": contour, "reachable_count": len(pts)})
    return {
        "arm_id": arm_id, "source": "voxel_map",
        "arm_pose": arm_pose, "slices": slices, "stats": {"compute_time_s": 0.0},
    }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _extract_contour(points_2d):
    if len(points_2d) < 3:
        return points_2d
    try:
        from scipy.spatial import ConvexHull
        arr = np.array(points_2d)
        hull = ConvexHull(arr)
        contour = arr[hull.vertices].tolist()
        contour.append(contour[0])
        return [[round(x, 4), round(y, 4)] for x, y in contour]
    except Exception:
        return points_2d


def _compute_bounds(points):
    if not points:
        return {"min": [0, 0, 0], "max": [0, 0, 0]}
    arr = np.array(points)
    return {"min": arr.min(axis=0).round(4).tolist(), "max": arr.max(axis=0).round(4).tolist()}
