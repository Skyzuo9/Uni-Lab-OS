"""LayoutService — Layout Optimizer 单例入口。

检测器模式：
  - "mock": OBB SAT 碰撞 + 欧氏距离可达性（默认，无 ROS2 依赖）
  - "moveit": MoveIt2 FCL 碰撞 + IK 可达性（需 checker_bridge 初始化）
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Any

from .constraints import evaluate_default_hard_constraints
from .device_catalog import (
    create_devices_from_list,
    load_devices_from_assets,
    load_devices_from_registry,
    load_footprints,
    merge_device_lists,
)
from .intent_interpreter import InterpretResult, interpret_intents
from .lab_parser import parse_lab
from .mock_checkers import MockCollisionChecker, MockReachabilityChecker
from .models import Constraint, Intent
from .optimizer import optimize, snap_theta
from .seeders import resolve_seeder_params, seed_layout

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # Uni-Lab-OS 仓库根目录

UNI_LAB_ASSETS_DIR = Path(
    os.getenv("UNI_LAB_ASSETS_DIR", str(_REPO_ROOT.parent / "uni-lab-assets"))
)
UNI_LAB_OS_DEVICE_MESH_DIR = Path(
    os.getenv(
        "UNI_LAB_OS_DEVICE_MESH_DIR",
        str(_REPO_ROOT / "unilabos" / "device_mesh" / "devices"),
    )
)

_CONSUMABLE_KEYWORDS = {
    "plate", "well", "tube", "tip", "reservoir", "carrier", "nest",
    "adapter", "trough", "magnet_module", "magnet_plate", "rack", "lid",
    "seal", "cap", "vial", "flask", "dish", "block", "strip", "insert",
    "gasket", "pad", "grid_segment", "spacer", "diti_tray",
}
_DEVICE_KEYWORDS = {
    "reader", "handler", "hotel", "washer", "stacker", "sealer", "labeler",
    "centrifuge", "incubator", "shaker", "robot", "arm", "flex", "dispenser",
    "printer", "scanner", "analyzer", "fluorometer", "spectrophotometer",
    "thermocycler", "module",
}


def _is_standalone_device(device_id: str, bbox: tuple[float, float]) -> bool:
    mx = max(bbox[0], bbox[1])
    mn = min(bbox[0], bbox[1])
    if mx >= 0.30:
        return True
    if mx < 0.05:
        return False
    lower = device_id.lower()
    if mn < 0.03:
        return False
    is_consumable_name = any(kw in lower for kw in _CONSUMABLE_KEYWORDS)
    is_device_name = any(kw in lower for kw in _DEVICE_KEYWORDS)
    if is_consumable_name and not is_device_name:
        return False
    if is_device_name:
        return True
    return mx >= 0.15


class LayoutService:
    """Layout Optimizer 服务单例。"""

    _instance: LayoutService | None = None

    @classmethod
    def get_instance(cls) -> LayoutService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._checker_mode: str = os.getenv("LAYOUT_CHECKER_MODE", "mock")
        self._collision_checker: Any = None
        self._reachability_checker: Any = None
        self._device_cache: list[dict] | None = None
        self._init_checkers()

    # ------------------------------------------------------------------
    # 检测器管理
    # ------------------------------------------------------------------

    def _init_checkers(self) -> None:
        if self._checker_mode == "moveit":
            try:
                from .checker_bridge import CheckerBridge
                checkers = CheckerBridge.create_checkers()
                self._collision_checker = checkers["collision"]
                self._reachability_checker = checkers["reachability"]
                logger.info("LayoutService: MoveIt2 checkers initialized")
            except Exception as exc:
                logger.warning(
                    "LayoutService: MoveIt2 init failed (%s), falling back to mock", exc
                )
                self._checker_mode = "mock"
                self._collision_checker = MockCollisionChecker()
                self._reachability_checker = MockReachabilityChecker()
        else:
            self._collision_checker = MockCollisionChecker()
            self._reachability_checker = MockReachabilityChecker()
            logger.info("LayoutService: Mock checkers initialized")

    def set_checker_mode(self, mode: str, moveit2: Any = None) -> None:
        """切换检测器模式。moveit 模式需先由 CheckerBridge 完成初始化。"""
        self._checker_mode = mode
        self._init_checkers()

    def get_checker_status(self) -> dict:
        return {
            "mode": self._checker_mode,
            "collision_checker": type(self._collision_checker).__name__,
            "reachability_checker": type(self._reachability_checker).__name__,
        }

    # ------------------------------------------------------------------
    # 设备目录
    # ------------------------------------------------------------------

    def _build_device_list(self) -> list[dict]:
        if self._device_cache is not None:
            return self._device_cache

        footprints = load_footprints()
        registry = load_devices_from_registry(UNI_LAB_OS_DEVICE_MESH_DIR, footprints)
        assets = load_devices_from_assets(UNI_LAB_ASSETS_DIR / "data.json", footprints)
        merged = merge_device_lists(registry, assets)

        self._device_cache = [
            {
                "id": d.id,
                "name": d.name,
                "device_type": d.device_type,
                "source": d.source,
                "bbox": list(d.bbox),
                "height": d.height,
                "origin_offset": list(d.origin_offset),
                "openings": [
                    {"direction": list(o.direction), "label": o.label}
                    for o in d.openings
                ],
                "model_path": d.model_path,
                "model_type": d.model_type,
                "thumbnail_url": d.thumbnail_url,
                "is_standalone": _is_standalone_device(d.id, d.bbox),
            }
            for d in merged
        ]
        standalone = sum(1 for d in self._device_cache if d["is_standalone"])
        logger.info(
            "Built device catalog: %d devices (%d standalone)",
            len(self._device_cache), standalone,
        )
        return self._device_cache

    def get_devices(self, source: str = "all") -> list[dict]:
        devices = self._build_device_list()
        if source != "all":
            devices = [d for d in devices if d["source"] == source]
        return devices

    # ------------------------------------------------------------------
    # 意图解释
    # ------------------------------------------------------------------

    def interpret(self, intents_raw: list[dict]) -> InterpretResult:
        intents = [
            Intent(
                intent=i["intent"],
                params=i.get("params", {}),
                description=i.get("description", ""),
            )
            for i in intents_raw
        ]
        return interpret_intents(intents)

    # ------------------------------------------------------------------
    # 布局优化
    # ------------------------------------------------------------------

    def run_optimize(
        self,
        devices_raw: list[dict],
        lab_raw: dict,
        constraints_raw: list[dict],
        seeder: str = "compact_outward",
        seeder_overrides: dict | None = None,
        run_de: bool = True,
        workflow_edges: list[list[str]] | None = None,
        maxiter: int = 200,
        seed: int | None = None,
    ) -> dict:
        seeder_overrides = seeder_overrides or {}

        # Build id → uuid mappings
        id_to_catalog: dict[str, str] = {}
        id_to_uuid: dict[str, str] = {}
        for d in devices_raw:
            internal_id = d.get("uuid") or d["id"]
            id_to_catalog[internal_id] = d["id"]
            id_to_uuid[internal_id] = d.get("uuid") or d["id"]

        devices = create_devices_from_list(devices_raw)
        lab = parse_lab(lab_raw)
        constraints = [
            Constraint(
                type=c["type"],
                rule_name=c["rule_name"],
                params=c.get("params", {}),
                weight=c.get("weight", 1.0),
            )
            for c in constraints_raw
        ]

        # 1. Resolve seeder
        effective_seeder = seeder if seeder != "row_fallback" else "compact_outward"
        params = resolve_seeder_params(effective_seeder, seeder_overrides or None)

        # 2. Seed layout
        seed_placements = seed_layout(
            devices, lab, params,
            workflow_edges or None,
        )

        # 3. Auto-inject orientation soft constraints
        if run_de and seeder != "row_fallback" and seed_placements and params:
            orientation_mode = params.orientation_mode
            if orientation_mode != "none":
                constraints.append(Constraint(
                    type="soft",
                    rule_name="prefer_orientation_mode",
                    params={"mode": orientation_mode},
                    weight=seeder_overrides.get("orientation_weight", 5.0),
                ))
            align_weight = seeder_overrides.get("align_weight", 2.0)
            if align_weight > 0:
                constraints.append(Constraint(
                    type="soft",
                    rule_name="prefer_aligned",
                    weight=align_weight,
                ))

        # 4. Differential Evolution
        de_ran = False
        if run_de:
            result_placements = optimize(
                devices=devices,
                lab=lab,
                constraints=constraints,
                collision_checker=self._collision_checker,
                reachability_checker=self._reachability_checker,
                seed_placements=seed_placements,
                maxiter=maxiter,
                seed=seed,
            )
            de_ran = True
        else:
            result_placements = seed_placements

        # 5. θ snap post-processing
        result_placements = snap_theta(result_placements)

        # 6. Evaluate final cost
        final_cost = evaluate_default_hard_constraints(
            devices, result_placements, lab, self._collision_checker, graduated=False,
        )

        # 7. 同步最终布局到 MoveIt2 Planning Scene（moveit 模式专用）
        # DE 优化循环中 sync_to_scene=False，这里做最终一次性同步
        if self._checker_mode == "moveit":
            checker_placements = [
                {
                    "id": p.device_id,
                    "bbox": next(
                        (d.bbox for d in devices if d.id == p.device_id), (0.6, 0.4)
                    ),
                    "pos": (p.x, p.y, p.theta),
                }
                for p in result_placements
            ]
            try:
                self._collision_checker.sync_to_planning_scene(checker_placements)
            except Exception:
                logger.warning("Failed to sync final layout to MoveIt2", exc_info=True)

        return {
            "placements": [
                {
                    "device_id": id_to_catalog.get(p.device_id, p.device_id),
                    "uuid": id_to_uuid.get(p.device_id, p.device_id),
                    "position": {"x": round(p.x, 4), "y": round(p.y, 4), "z": 0.0},
                    "rotation": {"x": 0.0, "y": 0.0, "z": round(p.theta, 4)},
                }
                for p in result_placements
            ],
            "cost": final_cost,
            "success": not math.isinf(final_cost),
            "seeder_used": seeder,
            "de_ran": de_ran,
        }
