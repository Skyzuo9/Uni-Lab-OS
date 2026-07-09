#!/usr/bin/env python3
"""
使用几何近似生成可达性体素图（不需要 MoveIt2 运行）。

适用于 arm_slider（Elite CS612 + 导轨）和 dummy2_robot。
体素图格式与 ros_checkers.py IKFastReachabilityChecker._load_voxel_maps() 兼容。

运行：
    python3 scripts/generate_voxel_map_geometric.py
"""
import math
import numpy as np
from pathlib import Path


def generate_arm_voxel_map(
    arm_id: str,
    arm_reach: float,
    inner_dead_zone: float,
    z_min: float,
    z_max: float,
    resolution: float = 0.05,
    output_dir: Path = None,
):
    """生成球环形可达性体素图（6-DOF 机械臂的几何近似）。"""
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "unilabos" / "services" / "layout_optimizer" / "voxel_maps"
    output_dir.mkdir(parents=True, exist_ok=True)

    half_r = arm_reach
    origin = np.array([-half_r, -half_r, z_min])

    nx = int(2 * half_r / resolution) + 1
    ny = int(2 * half_r / resolution) + 1
    nz = int((z_max - z_min) / resolution) + 1

    grid = np.zeros((nx, ny, nz), dtype=bool)

    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                x = origin[0] + ix * resolution
                y = origin[1] + iy * resolution
                z = origin[2] + iz * resolution
                r_xy = math.sqrt(x**2 + y**2)
                if inner_dead_zone < r_xy < arm_reach and z_min <= z <= z_max:
                    grid[ix, iy, iz] = True

    out_path = output_dir / f"{arm_id}.npz"
    np.savez_compressed(
        str(out_path),
        grid=grid,
        origin=origin,
        resolution=np.float64(resolution),
    )
    total = int(grid.sum())
    print(f"[{arm_id}] shape={grid.shape}, reachable_voxels={total}, file={out_path}")


if __name__ == "__main__":
    # arm_slider (Elite CS612, 臂展 1.304m)
    generate_arm_voxel_map(
        arm_id="arm_slider_arm",
        arm_reach=1.304,
        inner_dead_zone=0.1,
        z_min=-0.1,
        z_max=1.2,
        resolution=0.05,
    )

    # dummy2_robot (仿真机器人, 臂展约 0.8m)
    generate_arm_voxel_map(
        arm_id="dummy2_arm_arm",
        arm_reach=0.8,
        inner_dead_zone=0.05,
        z_min=0.0,
        z_max=0.9,
        resolution=0.05,
    )

    print("All voxel maps generated.")
