"""离线生成可达性体素图 (.npz)。

用法（需要 ROS2 + move_group 运行中）：
    python3 -m unilabos.services.layout_optimizer.precompute_reachability \
        --arm-id arm_slider_arm \
        --resolution 0.05 \
        --reach-estimate 1.5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def precompute_voxel_map(
    moveit2_instance,
    resolution: float = 0.02,
    reach_estimate: float = 1.5,
    z_min: float = 0.0,
    z_max: float = 0.6,
) -> dict:
    half_r = reach_estimate
    nx = int(2 * half_r / resolution) + 1
    ny = int(2 * half_r / resolution) + 1
    nz = int((z_max - z_min) / resolution) + 1
    total = nx * ny * nz

    logger.info("Grid: %d x %d x %d = %d points (resolution=%.3f)", nx, ny, nz, total, resolution)

    grid = np.zeros((nx, ny, nz), dtype=np.bool_)
    origin = np.array([-half_r, -half_r, z_min])

    checked = 0
    reachable_count = 0
    t0 = time.time()

    for ix in range(nx):
        for iy in range(ny):
            for iz in range(nz):
                x = origin[0] + ix * resolution
                y = origin[1] + iy * resolution
                z = origin[2] + iz * resolution

                try:
                    ik_result = moveit2_instance.compute_ik(
                        position=[x, y, z],
                        quat_xyzw=[0, 0, 0, 1],
                    )
                    if ik_result is not None:
                        grid[ix, iy, iz] = True
                        reachable_count += 1
                except Exception:
                    pass

                checked += 1
                if checked % 10000 == 0:
                    elapsed = time.time() - t0
                    rate = checked / elapsed if elapsed > 0 else 0
                    eta = (total - checked) / rate if rate > 0 else float("inf")
                    logger.info(
                        "Progress: %d/%d (%.1f%%) — reachable: %d — ETA: %.0fs",
                        checked, total, 100 * checked / total, reachable_count, eta,
                    )

    elapsed = time.time() - t0
    logger.info("Done: %d/%d reachable (%.1f%%) in %.1fs", reachable_count, total,
                100 * reachable_count / total, elapsed)

    return {"grid": grid, "origin": origin, "resolution": resolution}


def save_voxel_map(data: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(output_path), **data)
    logger.info("Saved voxel map to %s (%.1f MB)", output_path,
                output_path.stat().st_size / 1e6)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Precompute reachability voxel map")
    parser.add_argument("--arm-id", required=True)
    parser.add_argument("--resolution", type=float, default=0.05)
    parser.add_argument("--reach-estimate", type=float, default=1.5)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    output = args.output or str(
        Path(__file__).parent / "voxel_maps" / f"{args.arm_id}.npz"
    )

    from .checker_bridge import CheckerBridge
    instances = CheckerBridge.discover_moveit2_instances()
    if args.arm_id not in instances:
        logger.error("Arm '%s' not found. Available: %s", args.arm_id, list(instances.keys()))
        sys.exit(1)

    moveit2 = instances[args.arm_id]
    data = precompute_voxel_map(moveit2, args.resolution, args.reach_estimate)
    save_voxel_map(data, output)


if __name__ == "__main__":
    main()
