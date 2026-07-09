"""Layout Optimizer 服务入口。

以单例模式提供 interpret / optimize / devices 功能。
Checker 模式由 set_checker_mode() 控制：
  - "mock": 使用 OBB SAT + 欧氏距离（默认，无 ROS 依赖）
  - "moveit": 使用 MoveIt2 碰撞检测 + IK 可达性
"""

from __future__ import annotations

import logging
import math
import os
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
from .models import Constraint, Device, Intent, Lab, Placement
from .optimizer import optimize, snap_theta
from .seeders import resolve_seeder_params, seed_layout

logger = logging.getLogger(__name__)

class LayoutService:
    """Layout Optimizer 服务单例。"""

    _instance: LayoutService | None = None

    @classmethod
    def get_instance(cls) -> LayoutService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._checker_mode = os.getenv("LAYOUT_CHECKER_MODE", "mock")
        self._collision_checker: Any = None
        self._reachability_checker: Any = None
        self._device_cache: list[dict] | None = None
        self._init_checkers()

    def _init_checkers(self):
        from .mock_checkers import MockCollisionChecker, MockReachabilityChecker
        if self._checker_mode == "moveit":
            try:
                from .checker_bridge import CheckerBridge
                self._collision_checker, self._reachability_checker = CheckerBridge.create_checkers()
                logger.info("Layout checkers: MoveIt2 mode")
                return
            except Exception as e:
                logger.warning("MoveIt2 checkers unavailable (%s), falling back to mock", e)
                self._checker_mode = "mock"
        self._collision_checker = MockCollisionChecker()
        self._reachability_checker = MockReachabilityChecker()
        logger.info("Layout checkers: Mock mode")

    def set_checker_mode(self, mode: str, **kwargs: Any) -> None:
        self._checker_mode = mode
        self._init_checkers()

    def get_checker_status(self) -> dict:
        return {
            "mode": self._checker_mode,
            "collision_checker": type(self._collision_checker).__name__,
            "reachability_checker": type(self._reachability_checker).__name__,
        }

    # --- interpret ---

    def interpret(self, intents: list[dict]) -> dict:
        intent_objs = [
            Intent(
                intent=i.get("intent", ""),
                params=i.get("params", {}),
                description=i.get("description", ""),
            )
            for i in intents
        ]
        result: InterpretResult = interpret_intents(intent_objs)
        return {
            "constraints": [
                {"type": c.type, "rule_name": c.rule_name, "params": c.params, "weight": c.weight}
                for c in result.constraints
            ],
            "translations": result.translations,
            "workflow_edges": result.workflow_edges,
            "errors": result.errors,
        }

    # --- optimize ---

    def run_optimize(
        self,
        devices_raw: list[dict],
        lab_raw: dict,
        constraints_raw: list[dict] | None = None,
        seeder: str = "compact_outward",
        seeder_overrides: dict | None = None,
        run_de: bool = True,
        workflow_edges: list[list[str]] | None = None,
        maxiter: int = 200,
        seed: int | None = None,
    ) -> dict:
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
                type=c["type"], rule_name=c["rule_name"],
                params=c.get("params", {}), weight=c.get("weight", 1.0),
            )
            for c in (constraints_raw or [])
        ]

        try:
            params = resolve_seeder_params(seeder, seeder_overrides)
        except ValueError as e:
            return {"error": str(e), "success": False}

        seed_placements = seed_layout(devices, lab, params, workflow_edges)

        if run_de and seeder != "row_fallback" and seed_placements:
            orientation_mode = params.orientation_mode if params else "none"
            if orientation_mode != "none":
                constraints.append(Constraint(
                    type="soft", rule_name="prefer_orientation_mode",
                    params={"mode": orientation_mode},
                    weight=(seeder_overrides or {}).get("orientation_weight", 5.0),
                ))
            align_weight = (seeder_overrides or {}).get("align_weight", 2.0)
            if align_weight > 0:
                constraints.append(Constraint(
                    type="soft", rule_name="prefer_aligned", weight=align_weight,
                ))

        de_ran = False
        if run_de:
            result_placements = optimize(
                devices=devices, lab=lab, constraints=constraints,
                collision_checker=self._collision_checker,
                seed_placements=seed_placements,
                maxiter=maxiter, seed=seed,
            )
            de_ran = True
        else:
            result_placements = seed_placements

        result_placements = snap_theta(result_placements)

        if self._checker_mode == "moveit" and hasattr(self._collision_checker, "sync_to_planning_scene"):
            try:
                self._collision_checker.sync_to_planning_scene(result_placements)
            except Exception as e:
                logger.warning("Failed to sync to planning scene: %s", e)

        final_cost = evaluate_default_hard_constraints(
            devices, result_placements, lab, self._collision_checker, graduated=False,
        )

        response = {
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

        if self._checker_mode == "moveit":
            response["reachability_verification"] = self._verify_reachability(
                result_placements, constraints
            )

        return response

    def _verify_reachability(self, placements: list[Placement], constraints: list[Constraint]) -> dict:
        failures = []
        checked = 0
        for c in constraints:
            if c.rule_name != "reachability":
                continue
            checked += 1
            arm_id = c.params.get("arm_id", "")
            target_id = c.params.get("target_device_id", "")
            arm_p = next((p for p in placements if p.device_id == arm_id), None)
            target_p = next((p for p in placements if p.device_id == target_id), None)
            if not arm_p or not target_p:
                continue
            if self._reachability_checker and hasattr(self._reachability_checker, "is_reachable"):
                arm_pose = {"x": arm_p.x, "y": arm_p.y, "theta": arm_p.theta}
                target = {"x": target_p.x, "y": target_p.y, "z": 0.0}
                if not self._reachability_checker.is_reachable(arm_id, arm_pose, target):
                    failures.append({
                        "arm_id": arm_id, "target_device_id": target_id,
                        "reason": "IK solver found no solution",
                    })
        return {
            "mode": "moveit_ik" if self._checker_mode == "moveit" else "mock_euclidean",
            "all_passed": len(failures) == 0,
            "failures": failures,
            "checked_count": checked,
        }

    # --- devices ---

    def get_devices(self, source: str = "all") -> list[dict]:
        if self._device_cache is None:
            footprints = load_footprints()
            from pathlib import Path
            device_mesh_dir = Path(os.getenv(
                "UNI_LAB_OS_DEVICE_MESH_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "device_mesh" / "devices"),
            ))
            registry = load_devices_from_registry(device_mesh_dir, footprints)
            # assets data.json path — skip if not configured
            assets_dir = os.getenv("UNI_LAB_ASSETS_DIR", "")
            if assets_dir:
                data_json = Path(assets_dir) / "data.json"
                assets = load_devices_from_assets(data_json, footprints)
            else:
                assets = []
            merged = merge_device_lists(registry, assets)
            self._device_cache = [
                {
                    "id": d.id, "name": d.name, "device_type": d.device_type,
                    "source": d.source,
                    "bbox": list(d.bbox), "height": d.height,
                    "origin_offset": list(d.origin_offset),
                    "openings": [{"direction": list(o.direction), "label": o.label} for o in d.openings],
                    "model_path": d.model_path, "model_type": d.model_type,
                "is_standalone": _is_standalone_device(d.id, d.bbox),
                    "thumbnail_url": d.thumbnail_url,
                }
                for d in merged
            ]
        devices = self._device_cache
        if source != "all":
            devices = [d for d in devices if d["source"] == source]
        return devices

    # --- schema ---

    @staticmethod
    def get_schema() -> dict:
        return {
            "description": "Layout optimizer intent schema.",
            "intents": {
                "reachable_by": {
                    "description": "Robot arm must be able to reach all target devices",
                    "params": {
                        "arm": {"type": "string", "required": True},
                        "targets": {"type": "list[string]", "required": True},
                    },
                },
                "close_together": {
                    "description": "Group of devices should be placed near each other",
                    "params": {
                        "devices": {"type": "list[string]", "required": True},
                        "priority": {"type": "string", "required": False, "default": "medium"},
                    },
                },
                "far_apart": {
                    "description": "Devices should be placed far from each other",
                    "params": {
                        "devices": {"type": "list[string]", "required": True},
                        "priority": {"type": "string", "required": False, "default": "medium"},
                    },
                },
                "max_distance": {
                    "description": "Two devices must be within a maximum distance",
                    "params": {
                        "device_a": {"type": "string", "required": True},
                        "device_b": {"type": "string", "required": True},
                        "distance": {"type": "float", "required": True},
                    },
                },
                "min_distance": {
                    "description": "Two devices must be at least a minimum distance apart",
                    "params": {
                        "device_a": {"type": "string", "required": True},
                        "device_b": {"type": "string", "required": True},
                        "distance": {"type": "float", "required": True},
                    },
                },
                "min_spacing": {
                    "description": "Minimum gap between all device pairs",
                    "params": {"min_gap": {"type": "float", "required": False, "default": 0.3}},
                },
                "workflow_hint": {
                    "description": "Workflow step order — consecutive devices should be near each other",
                    "params": {
                        "workflow": {"type": "string", "required": False},
                        "devices": {"type": "list[string]", "required": True},
                    },
                },
                "face_outward": {"description": "Devices should face outward from lab center", "params": {}},
                "face_inward": {"description": "Devices should face inward toward lab center", "params": {}},
                "align_cardinal": {"description": "Devices should align to cardinal directions", "params": {}},
            },
        }
