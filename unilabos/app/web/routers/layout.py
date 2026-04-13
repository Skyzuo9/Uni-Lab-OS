"""Layout Optimizer API 路由。

挂载到 /api/v1/layout/，与 Uni-Lab-OS API 体系统一。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

layout_router = APIRouter(prefix="/layout", tags=["layout"])


# --- Request / Response models ---

class IntentSpec(BaseModel):
    intent: str
    params: dict = {}
    description: str = ""

class InterpretRequest(BaseModel):
    intents: list[IntentSpec]

class DeviceSpec(BaseModel):
    id: str
    name: str = ""
    size: list[float] | None = None
    device_type: str = "static"
    uuid: str = ""

class ConstraintSpec(BaseModel):
    type: str
    rule_name: str
    params: dict = {}
    weight: float = 1.0

class LabSpec(BaseModel):
    width: float
    depth: float
    obstacles: list[dict] = []

class OptimizeRequest(BaseModel):
    devices: list[DeviceSpec]
    lab: LabSpec
    constraints: list[ConstraintSpec] = []
    seeder: str = "compact_outward"
    seeder_overrides: dict = {}
    run_de: bool = True
    workflow_edges: list[list[str]] = []
    maxiter: int = 200
    seed: int | None = None


# --- Helper ---

def _get_service():
    from unilabos.services.layout_optimizer.service import LayoutService
    return LayoutService.get_instance()


# --- Routes ---

@layout_router.get("/health")
async def health():
    return {"status": "ok"}

@layout_router.get("/station_file")
async def get_station_file(path: str):
    """Load a station JSON file by absolute path."""
    import os, json
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    try:
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        with open(path, "r") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@layout_router.get("/schema")
async def schema():
    return _get_service().get_schema()


@layout_router.get("/checker_status")
async def checker_status():
    return _get_service().get_checker_status()


@layout_router.get("/devices")
async def devices(source: str = "all"):
    return _get_service().get_devices(source)


@layout_router.post("/interpret")
async def interpret(request: InterpretRequest):
    intents = [i.model_dump() for i in request.intents]
    return _get_service().interpret(intents)


@layout_router.post("/optimize")
async def optimize(request: OptimizeRequest):
    return _get_service().run_optimize(
        devices_raw=[d.model_dump() for d in request.devices],
        lab_raw=request.lab.model_dump(),
        constraints_raw=[c.model_dump() for c in request.constraints],
        seeder=request.seeder,
        seeder_overrides=request.seeder_overrides,
        run_de=request.run_de,
        workflow_edges=request.workflow_edges,
        maxiter=request.maxiter,
        seed=request.seed,
    )


# --- Demo page ---

@layout_router.get("/demo", include_in_schema=False)
async def demo_page():
    from fastapi.responses import FileResponse
    from pathlib import Path
    demo_dir = Path(__file__).resolve().parent.parent.parent.parent / "services" / "layout_optimizer" / "demo"
    for name in ("lab3d_integrated.html", "layout_demo.html"):
        f = demo_dir / name
        if f.exists():
            return FileResponse(str(f), media_type="text/html")
    return {"error": "demo page not found", "expected": str(demo_dir)}


# --- Serve local JS libraries ---
@layout_router.get("/demo/lib/{filename:path}", include_in_schema=False)
async def serve_demo_lib(filename: str):
    from fastapi.responses import FileResponse
    from pathlib import Path
    lib_dir = Path("/home/ubuntu/workspace/Uni-Lab-OS/unilabos/services/layout_optimizer/demo/lib")
    file_path = (lib_dir / filename).resolve()
    if not str(file_path).startswith(str(lib_dir)):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path), media_type="application/javascript")
    from fastapi.responses import JSONResponse
    return JSONResponse({"error": "not found", "tried": str(file_path)}, status_code=404)


# --- Mesh serving routes (3D model STL files) ---

@layout_router.get("/mesh_manifest")
async def mesh_manifest():
    """Return the mesh manifest JSON for 3D device rendering."""
    import json as _json
    manifest_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "services", "layout_optimizer", "demo", "mesh_manifest.json"
    )
    manifest_path = os.path.abspath(manifest_path)
    if not os.path.isfile(manifest_path):
        raise HTTPException(status_code=404, detail="mesh_manifest.json not found")
    from fastapi.responses import FileResponse
    return FileResponse(manifest_path, media_type="application/json")


@layout_router.get("/meshes/{device_id}/{filename:path}")
async def serve_device_mesh(device_id: str, filename: str):
    """Serve STL mesh files from device_mesh/devices/{device_id}/meshes/{filename}."""
    from fastapi.responses import FileResponse
    mesh_dir = "/home/ubuntu/workspace/Uni-Lab-OS/unilabos/device_mesh/devices"
    file_path = os.path.join(mesh_dir, device_id, "meshes", filename)
    file_path = os.path.abspath(file_path)
    if not file_path.startswith(os.path.abspath(mesh_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Mesh file not found: {device_id}/meshes/{filename}")
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    media_type = "application/octet-stream"
    if ext == "stl":
        media_type = "application/sla"
    return FileResponse(file_path, media_type=media_type)


# --- Workspace 路由（MoveIt2 IK 驱动）---


@layout_router.get("/workspace/{arm_id}")
async def get_workspace(
    arm_id: str,
    x: float = 0.0,
    y: float = 0.0,
    theta: float = 0.0,
    resolution: float = 0.05,
    mode: str = "points",
    reach_estimate: float = 0.5,
    z_min: float = 0.0,
    z_max: float = 0.6,
    max_points: int = 30000,
    multi_pose: bool = True,
):
    """获取机械臂可达工作空间（MoveIt2 IK 计算）。"""
    from unilabos.services.layout_optimizer.workspace import (
        generate_workspace,
        generate_workspace_slices,
    )

    svc = _get_service()
    arm_pose = {"x": x, "y": y, "theta": theta}

    moveit2 = None
    if svc._checker_mode == "moveit" and hasattr(svc, "_reachability_checker"):
        rc = svc._reachability_checker
        if hasattr(rc, "_moveit2"):
            moveit2 = rc._moveit2

    if moveit2 is None:
        try:
            from unilabos.services.layout_optimizer.checker_bridge import CheckerBridge
            instances = CheckerBridge.discover_moveit2_instances()
            for key, inst in instances.items():
                if arm_id in key:
                    moveit2 = inst
                    break
            if moveit2 is None and instances:
                moveit2 = next(iter(instances.values()))
        except Exception:
            pass

    voxel_maps = None
    if hasattr(svc, "_reachability_checker") and hasattr(svc._reachability_checker, "_voxel_maps"):
        voxel_maps = svc._reachability_checker._voxel_maps
    # Fallback: load voxel maps directly from disk (no MoveIt2 needed)
    if not voxel_maps:
        try:
            import numpy as _npvx
            from pathlib import Path as _PVX
            _vdir = _PVX(__file__).parent.parent.parent / "services" / "layout_optimizer" / "voxel_maps"
            if _vdir.is_dir():
                _vm_dict = {}
                for _nf in _vdir.glob("*.npz"):
                    _dat = _npvx.load(str(_nf))
                    class _VMx:
                        grid = _dat["grid"] if "grid" in _dat else _npvx.zeros((1,1,1), bool)
                        origin = list(_dat["origin"]) if "origin" in _dat else [0.0,0.0,0.0]
                        resolution = float(_dat["resolution"]) if "resolution" in _dat else 0.05
                    _vm_dict[_nf.stem] = _VMx()
                if _vm_dict:
                    voxel_maps = _vm_dict
        except Exception as _fe2:
            pass

    # Fuzzy match arm_id → voxel map key (e.g. arm_slider → arm_slider_arm)
    if voxel_maps and arm_id not in voxel_maps:
        for _vk in voxel_maps:
            if _vk.startswith(arm_id):
                arm_id = _vk; break

    # Inline voxel fallback: no MoveIt2 needed
    if not voxel_maps and moveit2 is None:
        try:
            import numpy as _npv2
            from pathlib import Path as _Pv2
            import math as _mv2
            _vdir2 = _Pv2(__file__).parent.parent.parent.parent / "services" / 'layout_optimizer' / 'voxel_maps'
            for _nf2 in _vdir2.glob('*.npz'):
                if not _nf2.stem.startswith(arm_id): continue
                _dat2 = _npv2.load(str(_nf2))
                _grid2 = _dat2['grid']
                _orig2 = list(_dat2['origin'].flat)
                _res2 = float(_dat2['resolution'])
                _step2 = max(1, int(resolution / _res2))
                cx2, cy2 = arm_pose['x'], arm_pose['y']
                _ct, _st = _mv2.cos(arm_pose.get('theta',0)), _mv2.sin(arm_pose.get('theta',0))
                _pts2 = []
                for _ix in range(0, _grid2.shape[0], _step2):
                    for _iy in range(0, _grid2.shape[1], _step2):
                        for _iz in range(0, _grid2.shape[2], _step2):
                            if not _grid2[_ix,_iy,_iz]: continue
                            lx = _orig2[0]+_ix*_res2; ly = _orig2[1]+_iy*_res2; lz = _orig2[2]+_iz*_res2
                            _pts2.append([round(cx2+lx*_ct-ly*_st,4), round(cy2+lx*_st+ly*_ct,4), round(lz,4)])
                            if len(_pts2)>=max_points: break
                        if len(_pts2)>=max_points: break
                    if len(_pts2)>=max_points: break
                if _pts2: return {'arm_id':_nf2.stem,'source':'voxel_map','resolution':resolution,'arm_pose':arm_pose,'points':_pts2,'stats':{'total_points':len(_pts2)}}
        except Exception: pass

    try:
        if mode == "slices":
            return generate_workspace_slices(
                arm_id=arm_id, arm_pose=arm_pose, moveit2_instance=moveit2,
                resolution=resolution, reach_estimate=reach_estimate,
                multi_pose=multi_pose, voxel_maps=voxel_maps,
            )
        return generate_workspace(
            arm_id=arm_id, arm_pose=arm_pose, moveit2_instance=moveit2,
            resolution=resolution, reach_estimate=reach_estimate,
            z_min=z_min, z_max=z_max, max_points=max_points,
            multi_pose=multi_pose, voxel_maps=voxel_maps,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))





@layout_router.get("/ik/{arm_id}")
async def solve_ik(
    arm_id: str,
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.3,
):
    """IK 求解：检查目标 (x,y,z) 可达性，返回近似关节角（基于 voxel map + 解析模型）。"""
    import math as _math
    import numpy as _np_ik
    from pathlib import Path as _PIK

    _vdir_ik = _PIK(__file__).parent.parent.parent.parent / "services" / "layout_optimizer" / "voxel_maps"
    _voxel_data = None
    _voxel_stem = None
    for _nf in _vdir_ik.glob("*.npz"):
        if _nf.stem.startswith(arm_id):
            _voxel_data = _np_ik.load(str(_nf))
            _voxel_stem = _nf.stem
            break

    if _voxel_data is None:
        raise HTTPException(status_code=404, detail=f"No voxel map for arm '{arm_id}'")

    _grid = _voxel_data["grid"]
    _orig = list(_voxel_data["origin"].flat)
    _res = float(_voxel_data["resolution"])

    def _in_voxel(px, py, pz):
        ix = round((px - _orig[0]) / _res)
        iy = round((py - _orig[1]) / _res)
        iz = round((pz - _orig[2]) / _res)
        if 0 <= ix < _grid.shape[0] and 0 <= iy < _grid.shape[1] and 0 <= iz < _grid.shape[2]:
            return bool(_grid[ix, iy, iz])
        return False

    _reachable = _in_voxel(x, y, z)

    # Find nearest reachable point if target not reachable
    _nearest = None
    if not _reachable:
        _best_dist = 1e9
        _search_r = 3
        ix0 = round((x - _orig[0]) / _res)
        iy0 = round((y - _orig[1]) / _res)
        iz0 = round((z - _orig[2]) / _res)
        for _di in range(-_search_r, _search_r+1):
            for _dj in range(-_search_r, _search_r+1):
                for _dk in range(-_search_r, _search_r+1):
                    ni, nj, nk = ix0+_di, iy0+_dj, iz0+_dk
                    if not (0 <= ni < _grid.shape[0] and 0 <= nj < _grid.shape[1] and 0 <= nk < _grid.shape[2]):
                        continue
                    if _grid[ni, nj, nk]:
                        nx = _orig[0] + ni*_res
                        ny = _orig[1] + nj*_res
                        nz = _orig[2] + nk*_res
                        d = (nx-x)**2 + (ny-y)**2 + (nz-z)**2
                        if d < _best_dist:
                            _best_dist = d; _nearest = (nx, ny, nz)

    # Use actual or nearest reachable point for IK
    _tx, _ty, _tz = (x, y, z) if _reachable else (_nearest or (x, y, z))

    # Workspace bounds from voxel map
    _x_min, _x_max = float(_orig[0]), float(_orig[0] + _grid.shape[0]*_res)
    _y_min, _y_max = float(_orig[1]), float(_orig[1] + _grid.shape[1]*_res)
    _z_min, _z_max = float(_orig[2]), float(_orig[2] + _grid.shape[2]*_res)

    def _clamp(v, lo, hi): return max(lo, min(hi, v))
    def _norm(v, lo, hi): return (v - lo) / (hi - lo) if hi > lo else 0.0

    # Simplified analytical IK for arm_slider (SCARA-like on linear rail)
    # arm_base_joint (prismatic 0→1.5): slider along rail, maps to X
    _x_n = _norm(_tx, _x_min, _x_max)
    _slider = _clamp(_x_n * 1.5, 0.0, 1.5)

    # arm_link_1_joint (prismatic 0→0.6): vertical lift, maps to Z
    _z_n = _norm(_tz, _z_min, _z_max)
    _lift = _clamp(_z_n * 0.6, 0.0, 0.6)

    # arm_link_2_joint (revolute ±1.658): rotation, maps to Y
    _y_n = _ty / max(abs(_y_min), abs(_y_max), 0.01)
    _rot2 = _clamp(_y_n * 1.4, -1.658, 1.658)

    # arm_link_3_joint (revolute ±3.4): wrist compensation
    _rot3 = _clamp(-_rot2 * 0.6, -3.4, 3.4)

    _joint_names = [
        f"{arm_id}_arm_base_joint",
        f"{arm_id}_arm_link_1_joint",
        f"{arm_id}_arm_link_2_joint",
        f"{arm_id}_arm_link_3_joint",
        f"{arm_id}_gripper_right_joint",
        f"{arm_id}_gripper_left_joint",
    ]
    _joint_values = [_slider, _lift, _rot2, _rot3, 0.015, 0.015]

    return {
        "arm_id": _voxel_stem,
        "reachable": _reachable,
        "nearest_reachable": list(_nearest) if _nearest and not _reachable else None,
        "target": {"x": x, "y": y, "z": z},
        "used_point": {"x": _tx, "y": _ty, "z": _tz},
        "joint_names": _joint_names,
        "joint_values": _joint_values,
        "joints": dict(zip(_joint_names, _joint_values)),
    }

@layout_router.get("/urdf")
async def get_urdf(station_path: str = "", positions: str = ""):
    """Generate URDF from station JSON for Three.js URDF Loader. Reads YAML directly, no lab_registry dependency."""
    import json as _json
    import yaml as _yaml
    import xacro as _xacro
    from lxml import etree as _etree
    from pathlib import Path as _Path

    _this_dir = _Path(__file__).parent
    _project_root = (_this_dir / ".." / ".." / "..").resolve()
    _registry_dir = _project_root / "registry" / "devices"
    _mesh_base = _project_root / "device_mesh"

    _device_types: dict = {}
    if _registry_dir.exists():
        for _yf in _registry_dir.glob("*.yaml"):
            try:
                _data = _yaml.safe_load(_yf.read_text(encoding="utf-8")) or {}
                if isinstance(_data, dict):
                    _device_types.update(_data)
            except Exception:
                pass

    _station_data: dict = {}
    if station_path:
        try:
            _station_data = _json.loads(_Path(station_path).read_text(encoding="utf-8"))
        except Exception as _e:
            raise HTTPException(status_code=400, detail=f"Cannot read station file: {_e}")

    # Apply optional positions override (from frontend current state)
    if positions:
        try:
            import json as _pos_json
            _pos_override = _pos_json.loads(positions)
            for _node in _station_data.get("nodes", []):
                _nid = _node.get("id", "")
                if _nid in _pos_override:
                    _node["position"] = _pos_override[_nid]
        except Exception:
            pass

    _XACRO_NS = "http://ros.org/wiki/xacro"
    _urdf_template = (
        '<?xml version="1.0" ?>'
        '<robot name="full_dev" xmlns:xacro="http://ros.org/wiki/xacro">'
        '<link name="world"/>'
        '</robot>'
    )
    _root = _etree.fromstring(_urdf_template.encode())

    _device_count = 0
    for _node in _station_data.get("nodes", []):
        _ntype = _node.get("type", "device")
        _cls = _node.get("class", "")
        if _ntype != "device" or not _cls:
            continue

        _model_cfg: dict = {}
        if _cls in _device_types and "model" in _device_types[_cls]:
            _model_cfg = _device_types[_cls]["model"]

        _mesh_name = _model_cfg.get("mesh", "") if _model_cfg.get("type") == "device" else ""

        _pos = _node.get("position", {})
        _px = float(_pos.get("x", 0)) / 1000.0
        _py = float(_pos.get("y", 0)) / 1000.0
        _pz = float(_pos.get("z", 0)) / 1000.0
        if "pose" in _node and _node["pose"]:
            _pose_pos = _node["pose"].get("position", {})
            if _pose_pos:
                _px = float(_pose_pos.get("x", _px * 1000.0)) / 1000.0
                _py = float(_pose_pos.get("y", _py * 1000.0)) / 1000.0
                _pz = float(_pose_pos.get("z", _pz * 1000.0)) / 1000.0

        if not _mesh_name:
            _dev_id = _node.get("id", "unknown")
            _link = _etree.SubElement(_root, "link")
            _link.set("name", f"{_dev_id}_device_link")
            _vis = _etree.SubElement(_link, "visual")
            _geom = _etree.SubElement(_vis, "geometry")
            _box = _etree.SubElement(_geom, "box")
            _box.set("size", "0.3 0.3 0.3")
            _joint = _etree.SubElement(_root, "joint")
            _joint.set("name", f"{_dev_id}_joint")
            _joint.set("type", "fixed")
            _origin = _etree.SubElement(_joint, "origin")
            _origin.set("xyz", f"{_px} {_py} {_pz}")
            _origin.set("rpy", "0 0 0")
            _parent = _etree.SubElement(_joint, "parent")
            _parent.set("link", "world")
            _child = _etree.SubElement(_joint, "child")
            _child.set("link", f"{_dev_id}_device_link")
            _device_count += 1
            continue

        _macro_file = str(_mesh_base / "devices" / _mesh_name / "macro_device.xacro")
        if not _Path(_macro_file).exists():
            continue

        _inc = _etree.SubElement(_root, f"{{{_XACRO_NS}}}include")
        _inc.set("filename", _macro_file)
        _dev_elem = _etree.SubElement(_root, f"{{{_XACRO_NS}}}{_mesh_name}")
        _dev_elem.set("parent_link", "world")
        _dev_elem.set("mesh_path", str(_mesh_base))
        _dev_elem.set("device_name", _node.get("id", "dev") + "_")
        _dev_elem.set("station_name", "")
        _dev_elem.set("x", str(_px))
        _dev_elem.set("y", str(_py))
        _dev_elem.set("z", str(_pz))
        _rot = _node.get("config", {}).get("rotation", {})
        _dev_elem.set("rx", str(float(_rot.get("x", 0))))
        _dev_elem.set("ry", str(float(_rot.get("y", 0))))
        _dev_elem.set("r", str(float(_rot.get("z", 0))))
        for _k, _v in _node.get("config", {}).get("device_config", {}).items():
            _dev_elem.set(_k, str(_v))
        _device_count += 1

    try:
        _xml_str = _etree.tostring(_root, encoding="unicode")
        _doc = _xacro.parse(_xml_str)
        _xacro.process_doc(_doc)
        _urdf_str = _doc.toxml()
    except Exception as _e:
        raise HTTPException(status_code=500, detail=f"xacro processing failed: {_e}")

    _mesh_base_str = str(_mesh_base)
    _urdf_str = _urdf_str.replace(f"file://{_mesh_base_str}/", "")
    _urdf_str = _urdf_str.replace(f"{_mesh_base_str}/", "")

    return {"urdf": _urdf_str, "device_count": _device_count}

@layout_router.get("/workspace_diag/{arm_id}")
async def workspace_diag(arm_id: str):
    """诊断端点：获取 FK 真实姿态 + 测试 IK 可行性。"""
    import math
    svc = _get_service()
    result = {"arm_id": arm_id, "steps": []}

    # 1. 寻找 MoveIt2 实例
    moveit2 = None
    if svc._checker_mode == "moveit" and hasattr(svc, "_reachability_checker"):
        rc = svc._reachability_checker
        if hasattr(rc, "_moveit2"):
            moveit2 = rc._moveit2
    if moveit2 is None:
        try:
            from unilabos.services.layout_optimizer.checker_bridge import CheckerBridge
            instances = CheckerBridge.discover_moveit2_instances()
            result["steps"].append({"step": "discover", "instances": list(instances.keys())})
            for key, inst in instances.items():
                if arm_id in key:
                    moveit2 = inst
                    break
            if moveit2 is None and instances:
                moveit2 = next(iter(instances.values()))
        except Exception as e:
            result["steps"].append({"step": "discover", "error": str(e)})
    if moveit2 is None:
        result["error"] = "No MoveIt2 instance found"
        return result

    result["steps"].append({"step": "moveit2_found", "ok": True})

    # 2. 调用 compute_fk
    try:
        fk_result = moveit2.compute_fk()
        if fk_result is not None:
            p = fk_result.pose.position
            o = fk_result.pose.orientation
            reach = math.sqrt(p.x**2 + p.y**2)
            result["fk"] = {
                "position": {"x": round(p.x, 4), "y": round(p.y, 4), "z": round(p.z, 4)},
                "orientation_xyzw": [round(o.x, 4), round(o.y, 4), round(o.z, 4), round(o.w, 4)],
                "horizontal_reach": round(reach, 4),
                "frame": fk_result.header.frame_id,
            }
        else:
            result["fk"] = {"error": "compute_fk returned None"}
    except Exception as e:
        result["fk"] = {"error": str(e)}

    # 3. 测试 IK（用 FK 返回的姿态 + 多个候选）
    fk_quat = None
    fk_pos = None
    if "orientation_xyzw" in result.get("fk", {}):
        fk_quat = result["fk"]["orientation_xyzw"]
        fk_pos = [result["fk"]["position"]["x"],
                   result["fk"]["position"]["y"],
                   result["fk"]["position"]["z"]]

    test_quats = [
        ("identity", [0, 0, 0, 1]),
        ("rot_x_180", [1, 0, 0, 0]),
        ("rot_y_180", [0, 1, 0, 0]),
        ("rot_z_180", [0, 0, 1, 0]),
        ("rot_x_90", [0.707, 0, 0, 0.707]),
        ("rot_y_90", [0, 0.707, 0, 0.707]),
        ("rot_z_90", [0, 0, 0.707, 0.707]),
    ]
    if fk_quat:
        test_quats.insert(0, ("fk_quat", fk_quat))

    # 测试位置：用 FK 的真实位置 + 小偏移
    test_positions = []
    if fk_pos:
        test_positions.append(("fk_pos_exact", fk_pos))
        test_positions.append(("fk_pos_dx+0.05", [fk_pos[0]+0.05, fk_pos[1], fk_pos[2]]))
        test_positions.append(("fk_pos_dy+0.05", [fk_pos[0], fk_pos[1]+0.05, fk_pos[2]]))
    for r in [0.1, 0.2, 0.3, 0.5]:
        test_positions.append((f"r={r}_z=0.1", [r, 0, 0.1]))
        test_positions.append((f"r={r}_z=0.2", [0, r, 0.2]))

    ik_results = []
    for q_name, q_val in test_quats:
        for p_name, p_val in test_positions[:5]:
            try:
                ik = moveit2.compute_ik(position=p_val, quat_xyzw=q_val)
                ok = ik is not None
            except Exception as e:
                ok = False
            ik_results.append({
                "quat": q_name, "pos": p_name,
                "quat_val": q_val, "pos_val": [round(v,3) for v in p_val],
                "success": ok,
            })
            if ok:
                break
        if any(r["success"] for r in ik_results):
            break

    result["ik_tests"] = ik_results
    result["any_ik_success"] = any(r["success"] for r in ik_results)

    # 4. joint info
    try:
        result["joint_names"] = list(moveit2.joint_names) if hasattr(moveit2, "joint_names") else "N/A"
        if moveit2.joint_state is not None:
            js = moveit2.joint_state
            result["current_joint_state"] = {
                "names": list(js.name) if hasattr(js, "name") else [],
                "positions": list(js.position) if hasattr(js, "position") else [],
            }
        else:
            result["current_joint_state"] = "None (not yet received)"
    except Exception as e:
        result["joint_info_error"] = str(e)

    return result
