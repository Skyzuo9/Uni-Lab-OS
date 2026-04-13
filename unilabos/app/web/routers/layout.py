"""Layout Optimizer API 路由。

挂载到 /api/v1/layout/，与 Uni-Lab-OS 的 API 体系统一。

端点：
  GET  /api/v1/layout/health          — 健康检查
  GET  /api/v1/layout/checker_status  — 检测器模式
  GET  /api/v1/layout/schema          — 可用意图类型规范
  GET  /api/v1/layout/devices         — 设备目录
  POST /api/v1/layout/interpret       — 语义意图 → 约束列表
  POST /api/v1/layout/optimize        — 约束 → 最优布局
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

layout_router = APIRouter(prefix="/layout", tags=["layout"])


# ---------- Pydantic 请求/响应模型 ----------


class IntentSpec(BaseModel):
    intent: str
    params: dict = {}
    description: str = ""


class TranslationEntry(BaseModel):
    source_intent: str
    source_description: str
    source_params: dict
    generated_constraints: List[dict]
    explanation: str
    confidence: str = "high"


class InterpretRequest(BaseModel):
    intents: List[IntentSpec]


class InterpretResponse(BaseModel):
    constraints: List[dict]
    translations: List[TranslationEntry]
    workflow_edges: List[List[str]]
    errors: List[str]


class DeviceSpec(BaseModel):
    id: str
    name: str = ""
    size: Optional[List[float]] = None
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
    obstacles: List[dict] = []


class OptimizeRequest(BaseModel):
    devices: List[DeviceSpec]
    lab: LabSpec
    constraints: List[ConstraintSpec] = []
    seeder: str = "compact_outward"
    seeder_overrides: dict = {}
    run_de: bool = True
    workflow_edges: List[List[str]] = []
    maxiter: int = 200
    seed: Optional[int] = None


# ---------- 路由定义 ----------


def _get_service():
    from unilabos.services.layout_optimizer import LayoutService
    return LayoutService.get_instance()


@layout_router.get("/health")
async def layout_health():
    """Layout optimizer 健康检查。"""
    return {"status": "ok", "module": "layout_optimizer"}


@layout_router.get("/checker_status")
async def checker_status():
    """返回当前检测器模式（mock / moveit）。"""
    return _get_service().get_checker_status()


@layout_router.get("/schema")
async def intent_schema():
    """返回可用意图类型及其参数规范，供 LLM agent 发现和使用。"""
    return {
        "description": "Layout optimizer intent schema. LLM agents should translate user requests into these intents.",
        "intents": {
            "reachable_by": {
                "description": "Robot arm must be able to reach all target devices",
                "params": {
                    "arm": {"type": "string", "required": True, "description": "Device ID of robot arm"},
                    "targets": {"type": "list[string]", "required": True, "description": "Device IDs the arm must reach"},
                },
                "generates": "hard reachability constraint per target",
            },
            "close_together": {
                "description": "Group of devices should be placed near each other",
                "params": {
                    "devices": {"type": "list[string]", "required": True},
                    "priority": {"type": "string", "required": False, "default": "medium", "enum": ["low", "medium", "high"]},
                },
                "generates": "soft minimize_distance for each pair",
            },
            "far_apart": {
                "description": "Devices should be placed far from each other",
                "params": {
                    "devices": {"type": "list[string]", "required": True},
                    "priority": {"type": "string", "required": False, "default": "medium", "enum": ["low", "medium", "high"]},
                },
                "generates": "soft maximize_distance for each pair",
            },
            "max_distance": {
                "description": "Two devices must be within a maximum distance",
                "params": {
                    "device_a": {"type": "string", "required": True},
                    "device_b": {"type": "string", "required": True},
                    "distance": {"type": "float", "required": True, "description": "Max edge-to-edge distance in meters"},
                },
                "generates": "hard distance_less_than",
            },
            "min_distance": {
                "description": "Two devices must be at least a minimum distance apart",
                "params": {
                    "device_a": {"type": "string", "required": True},
                    "device_b": {"type": "string", "required": True},
                    "distance": {"type": "float", "required": True, "description": "Min edge-to-edge distance in meters"},
                },
                "generates": "hard distance_greater_than",
            },
            "min_spacing": {
                "description": "Minimum gap between all device pairs",
                "params": {
                    "min_gap": {"type": "float", "required": False, "default": 0.3},
                },
                "generates": "hard min_spacing",
            },
            "workflow_hint": {
                "description": "Consecutive devices in workflow should be near each other",
                "params": {
                    "workflow": {"type": "string", "required": False},
                    "devices": {"type": "list[string]", "required": True},
                },
                "generates": "soft minimize_distance for consecutive pairs + workflow_edges",
            },
            "face_outward": {
                "description": "Devices should face outward from lab center",
                "params": {},
                "generates": "soft prefer_orientation_mode outward",
            },
            "face_inward": {
                "description": "Devices should face inward toward lab center",
                "params": {},
                "generates": "soft prefer_orientation_mode inward",
            },
            "align_cardinal": {
                "description": "Devices should align to cardinal directions (0/90/180/270°)",
                "params": {},
                "generates": "soft prefer_aligned",
            },
        },
    }


@layout_router.get("/devices")
async def list_devices(source: str = "all"):
    """返回设备目录。?source=registry|assets|all"""
    return _get_service().get_devices(source)


@layout_router.post("/interpret", response_model=InterpretResponse)
async def run_interpret(request: InterpretRequest):
    """将语义化意图翻译为约束列表。"""
    logger.info("Layout interpret: %d intents", len(request.intents))
    service = _get_service()

    intents_raw = [
        {"intent": i.intent, "params": i.params, "description": i.description}
        for i in request.intents
    ]
    result = service.interpret(intents_raw)

    return InterpretResponse(
        constraints=[
            {"type": c.type, "rule_name": c.rule_name, "params": c.params, "weight": c.weight}
            for c in result.constraints
        ],
        translations=[
            TranslationEntry(
                source_intent=t["source_intent"],
                source_description=t.get("source_description", ""),
                source_params=t.get("source_params", {}),
                generated_constraints=t["generated_constraints"],
                explanation=t["explanation"],
                confidence=t.get("confidence", "high"),
            )
            for t in result.translations
        ],
        workflow_edges=result.workflow_edges,
        errors=result.errors,
    )


@layout_router.post("/optimize")
async def run_optimize(request: OptimizeRequest):
    """接收设备列表+约束，返回最优布局方案。"""
    logger.info(
        "Layout optimize: %d devices, lab %.1f×%.1f, %d constraints, seeder=%s, run_de=%s",
        len(request.devices),
        request.lab.width,
        request.lab.depth,
        len(request.constraints),
        request.seeder,
        request.run_de,
    )
    service = _get_service()

    try:
        result = service.run_optimize(
            devices_raw=[d.model_dump() for d in request.devices],
            lab_raw=request.lab.model_dump(),
            constraints_raw=[c.model_dump() for c in request.constraints],
            seeder=request.seeder,
            seeder_overrides=request.seeder_overrides,
            run_de=request.run_de,
            workflow_edges=request.workflow_edges or None,
            maxiter=request.maxiter,
            seed=request.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result
