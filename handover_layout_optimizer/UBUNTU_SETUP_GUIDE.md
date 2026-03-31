# Layout Optimizer × Uni-Lab-OS 集成：Ubuntu 操作指南

**目标系统**: Ubuntu 22.04.5 LTS (Jammy)  
**生成日期**: 2026-03-26  
**操作方式**: 远程桌面终端逐步执行

---

## 系统现状摘要

| 项目 | 值 |
|---|---|
| Uni-Lab-OS 源码 | `/home/ubuntu/workspace/Uni-Lab-OS/` |
| handover 源码 | `/home/ubuntu/Desktop/handover_layout_optimizer/` |
| Conda 环境 | `unilab` (Python 3.11, miniforge3) |
| unilabos 版本 | 0.10.18 (editable install) |
| ROS2 | rclpy 3.3.16 已安装，ros2 CLI 未安装 |
| MoveIt2 | 仅 moveit_msgs/moveit_configs_utils，核心未安装 |
| 缺失包 | scipy, python-fcl |

---

## Phase 0：环境准备

### Step 0.1：激活 conda 环境

后续所有操作都在 `unilab` conda 环境中执行。打开终端：

```bash
conda activate unilab
```

### Step 0.2：安装缺失的 Python 依赖

```bash
# scipy — DE 优化器核心依赖
pip install "scipy>=1.10"

# 验证
python -c "import scipy; print('scipy', scipy.__version__)"
```

### Step 0.3：安装 ROS2 CLI 工具（Phase 2+ 需要）

```bash
# 检查当前 robostack channel 配置
conda config --show channels

# 安装 ROS2 CLI（如果上面没有 robostack-staging，先添加）
conda install -c robostack-staging ros-humble-ros2cli ros-humble-ros-base -y

# 验证
ros2 --version
```

> 如果 conda install 报冲突，尝试：
> ```bash
> mamba install -c robostack-staging ros-humble-ros2cli ros-humble-ros-base -y
> ```
> 如果 `mamba` 不可用：`conda install mamba -n base -c conda-forge -y`

### Step 0.4：安装 MoveIt2（Phase 2+ 需要）

```bash
conda install -c robostack-staging ros-humble-moveit -y

# 验证
python -c "from moveit_msgs.msg import CollisionObject; print('MoveIt2 msgs OK')"
```

> 如果安装失败，可以跳过此步，Phase 1（Mock 模式）不需要 MoveIt2。

### Step 0.5：安装 python-fcl（可选，Phase 2 精确碰撞检测）

```bash
pip install python-fcl

# 验证
python -c "import fcl; print('python-fcl OK')" 2>/dev/null || echo "fcl not available, will use OBB fallback"
```

### Step 0.6：验证环境

```bash
python -c "
import scipy; print('scipy', scipy.__version__)
import numpy; print('numpy', numpy.__version__)
import fastapi; print('fastapi', fastapi.__version__)
import pydantic; print('pydantic', pydantic.__version__)
import rclpy; print('rclpy OK')
import unilabos; print('unilabos', unilabos.__version__)
print('--- All core dependencies OK ---')
"
```

---

## Phase 1：模块搬迁 + Mock 模式可用

> 目标：layout_optimizer 全部功能在 Uni-Lab-OS 进程内可用，行为与独立运行一致

### Step 1.1：创建目录结构

```bash
cd /home/ubuntu/workspace/Uni-Lab-OS

# 创建 services 包
mkdir -p unilabos/services/layout_optimizer/voxel_maps

# 创建 __init__.py 使其成为 Python 包
touch unilabos/services/__init__.py

# 创建路由目录
mkdir -p unilabos/app/web/routers
touch unilabos/app/web/routers/__init__.py
```

验证：

```bash
ls -la unilabos/services/layout_optimizer/
# 应该看到 voxel_maps/ 目录
```

### Step 1.2：复制核心文件（不修改）

```bash
HANDOVER=/home/ubuntu/Desktop/handover_layout_optimizer
TARGET=unilabos/services/layout_optimizer

# 无需修改的文件
cp "$HANDOVER/models.py"       "$TARGET/models.py"
cp "$HANDOVER/obb.py"          "$TARGET/obb.py"
cp "$HANDOVER/interfaces.py"   "$TARGET/interfaces.py"
cp "$HANDOVER/lab_parser.py"   "$TARGET/lab_parser.py"
cp "$HANDOVER/footprints.json" "$TARGET/footprints.json"
cp "$HANDOVER/ros_checkers.py" "$TARGET/ros_checkers.py"

echo "核心文件复制完成"
ls -la "$TARGET"
```

### Step 1.3：复制并修复 import 路径的文件

以下文件使用了 `from layout_optimizer.xxx import` 绝对导入，需要改为相对导入 `from .xxx import`。

#### 1.3.1 constraints.py（已是相对导入，直接复制）

```bash
cp "$HANDOVER/constraints.py" "$TARGET/constraints.py"
```

#### 1.3.2 device_catalog.py（已是相对导入，直接复制）

```bash
cp "$HANDOVER/device_catalog.py" "$TARGET/device_catalog.py"
```

#### 1.3.3 intent_interpreter.py（需修复导入）

```bash
cp "$HANDOVER/intent_interpreter.py" "$TARGET/intent_interpreter.py"

# 修复：from layout_optimizer.models → from .models
sed -i 's/from layout_optimizer\.models/from .models/g' "$TARGET/intent_interpreter.py"

# 验证修复
head -15 "$TARGET/intent_interpreter.py"
```

#### 1.3.4 mock_checkers.py（需修复导入）

```bash
cp "$HANDOVER/mock_checkers.py" "$TARGET/mock_checkers.py"

# 修复：from layout_optimizer.obb → from .obb
sed -i 's/from layout_optimizer\.obb/from .obb/g' "$TARGET/mock_checkers.py"

# 验证修复
head -15 "$TARGET/mock_checkers.py"
```

#### 1.3.5 seeders.py（需修复导入 + 移除 pencil_integration）

```bash
cp "$HANDOVER/seeders.py" "$TARGET/seeders.py"

# 修复绝对导入
sed -i 's/from layout_optimizer\.models/from .models/g' "$TARGET/seeders.py"
sed -i 's/from layout_optimizer\.obb/from .obb/g' "$TARGET/seeders.py"
```

现在需要手动修复 `seeders.py` 中的 `pencil_integration` 引用。打开文件编辑：

```bash
nano "$TARGET/seeders.py"
```

找到第 78-80 行（`seed_layout` 函数中）：

```python
    if params is None:
        from layout_optimizer.pencil_integration import generate_fallback
        return generate_fallback(devices, lab)
```

替换为：

```python
    if params is None:
        return _row_fallback(devices, lab)
```

然后在文件末尾（`_resolve_collisions` 函数之后）添加：

```python


def _row_fallback(devices: list[Device], lab: Lab) -> list[Placement]:
    """简单行列布局回退方案，替代已移除的 pencil_integration。"""
    if not devices:
        return []
    cols = max(1, int(math.ceil(math.sqrt(len(devices)))))
    rows_count = max(1, math.ceil(len(devices) / cols))
    margin = 0.3
    placements = []
    for i, dev in enumerate(devices):
        row, col = divmod(i, cols)
        x = margin + (col + 0.5) * (lab.width - 2 * margin) / cols
        y = margin + (row + 0.5) * (lab.depth - 2 * margin) / rows_count
        x = min(max(x, dev.bbox[0] / 2), lab.width - dev.bbox[0] / 2)
        y = min(max(y, dev.bbox[1] / 2), lab.depth - dev.bbox[1] / 2)
        placements.append(Placement(device_id=dev.id, x=x, y=y, theta=0.0))
    return placements
```

保存退出（Ctrl+O, Enter, Ctrl+X）。

#### 1.3.6 optimizer.py（需移除 pencil_integration）

```bash
cp "$HANDOVER/optimizer.py" "$TARGET/optimizer.py"
```

打开文件编辑：

```bash
nano "$TARGET/optimizer.py"
```

**修改 1**：删除第 20 行的 pencil_integration 导入：

```python
# 删除这一行：
from .pencil_integration import generate_initial_layout
```

**修改 2**：替换第 78-79 行的 fallback 逻辑：

找到：

```python
    # 生成种子个体
    if seed_placements is None:
        seed_placements = generate_initial_layout(devices, lab)
```

替换为：

```python
    # 生成种子个体（调用方应通过 seeders.seed_layout 提供）
    if seed_placements is None:
        from .seeders import seed_layout, PRESETS
        seed_placements = seed_layout(devices, lab, PRESETS["compact_outward"])
```

保存退出。

### Step 1.4：创建模块 `__init__.py`

```bash
cat > "$TARGET/__init__.py" << 'PYEOF'
"""Layout Optimizer — Uni-Lab-OS 集成模块。

以同进程模块方式提供实验室布局自动优化功能。
Mock 模式无 ROS 依赖；MoveIt 模式需要 ROS2 + MoveIt2。
"""

from .models import Constraint, Device, Lab, Opening, Placement
from .optimizer import optimize

__all__ = ["Device", "Lab", "Opening", "Placement", "Constraint", "optimize"]
PYEOF
```

### Step 1.5：创建 `service.py` — LayoutService 单例

```bash
cat > "$TARGET/service.py" << 'PYEOF'
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

    def _init_checkers(self) -> None:
        if self._checker_mode == "moveit":
            try:
                from .checker_bridge import CheckerBridge
                self._collision_checker, self._reachability_checker = (
                    CheckerBridge.create_checkers()
                )
                logger.info("Layout checkers: MoveIt2 mode")
            except Exception as e:
                logger.warning("MoveIt2 checkers unavailable (%s), falling back to mock", e)
                self._checker_mode = "mock"
                self._collision_checker = MockCollisionChecker()
                self._reachability_checker = MockReachabilityChecker()
        else:
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
            assets = load_devices_from_assets(None, footprints)
            merged = merge_device_lists(registry, assets)
            self._device_cache = [
                {
                    "id": d.id, "name": d.name, "device_type": d.device_type,
                    "source": d.source,
                    "bbox": list(d.bbox), "height": d.height,
                    "origin_offset": list(d.origin_offset),
                    "openings": [{"direction": list(o.direction), "label": o.label} for o in d.openings],
                    "model_path": d.model_path, "model_type": d.model_type,
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
PYEOF
```

### Step 1.6：创建 API 路由 `layout.py`

```bash
cat > unilabos/app/web/routers/layout.py << 'PYEOF'
"""Layout Optimizer API 路由。

挂载到 /api/v1/layout/，与 Uni-Lab-OS API 体系统一。
"""

from __future__ import annotations

import logging
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
PYEOF
```

### Step 1.7：在 `api.py` 中注册路由

```bash
cd /home/ubuntu/workspace/Uni-Lab-OS
```

需要在 `unilabos/app/web/api.py` 的 `setup_api_routes` 函数中添加 layout_router。

打开文件编辑：

```bash
nano unilabos/app/web/api.py
```

找到文件末尾的 `setup_api_routes` 函数（大约第 1335 行）：

```python
def setup_api_routes(app):
    """设置API路由"""
    app.include_router(admin, prefix="/admin/v1", tags=["admin"])
    app.include_router(api, prefix="/api/v1", tags=["api"])
```

修改为：

```python
def setup_api_routes(app):
    """设置API路由"""
    app.include_router(admin, prefix="/admin/v1", tags=["admin"])
    app.include_router(api, prefix="/api/v1", tags=["api"])

    # Layout Optimizer 路由
    try:
        from unilabos.app.web.routers.layout import layout_router
        app.include_router(layout_router, prefix="/api/v1", tags=["layout"])
    except ImportError as e:
        import logging
        logging.getLogger(__name__).warning("Layout optimizer routes not loaded: %s", e)
```

保存退出。

### Step 1.8：验证模块可导入

```bash
cd /home/ubuntu/workspace/Uni-Lab-OS
conda activate unilab

# 测试基础导入
python -c "
from unilabos.services.layout_optimizer.models import Device, Lab, Placement, Constraint
print('models OK')

from unilabos.services.layout_optimizer.obb import obb_corners, obb_overlap
print('obb OK')

from unilabos.services.layout_optimizer.constraints import evaluate_constraints
print('constraints OK')

from unilabos.services.layout_optimizer.mock_checkers import MockCollisionChecker
print('mock_checkers OK')

from unilabos.services.layout_optimizer.seeders import seed_layout, resolve_seeder_params
print('seeders OK')

from unilabos.services.layout_optimizer.intent_interpreter import interpret_intents
print('intent_interpreter OK')

from unilabos.services.layout_optimizer.optimizer import optimize
print('optimizer OK')

from unilabos.services.layout_optimizer.service import LayoutService
print('service OK')

print('--- All imports OK ---')
"
```

> **排错**：如果某个 import 报 `ModuleNotFoundError`，检查错误消息指向的文件，修复其中的 `from layout_optimizer.xxx` 为 `from .xxx`。

### Step 1.9：运行快速功能测试

```bash
python -c "
from unilabos.services.layout_optimizer.service import LayoutService

svc = LayoutService.get_instance()

# 测试 schema
schema = svc.get_schema()
print(f'Schema intents: {len(schema[\"intents\"])} types')

# 测试 interpret
result = svc.interpret([
    {'intent': 'close_together', 'params': {'devices': ['dev_a', 'dev_b']}}
])
print(f'Interpret: {len(result[\"constraints\"])} constraints generated')

# 测试 optimize (mock mode)
opt_result = svc.run_optimize(
    devices_raw=[
        {'id': 'device_1', 'name': 'Centrifuge', 'size': [0.4, 0.4]},
        {'id': 'device_2', 'name': 'Vortex', 'size': [0.2, 0.2]},
    ],
    lab_raw={'width': 3.0, 'depth': 2.0},
    maxiter=50,
)
print(f'Optimize: success={opt_result[\"success\"]}, {len(opt_result[\"placements\"])} placements')

print('--- Functional tests PASSED ---')
"
```

### Step 1.10：启动 Uni-Lab-OS 并验证 API

```bash
conda activate unilab

# 以 simple 模式启动（不需要 ROS2）
unilab --backend simple --visual disable --skip_env_check --disable_browser
```

打开**另一个终端窗口**，测试 API：

```bash
# 测试 health
curl -s http://localhost:8002/api/v1/layout/health
# 期望：{"status":"ok"}

# 测试 schema
curl -s http://localhost:8002/api/v1/layout/schema | python3 -m json.tool | head -20
# 期望：看到 10 种意图定义

# 测试 interpret
curl -s -X POST http://localhost:8002/api/v1/layout/interpret \
  -H "Content-Type: application/json" \
  -d '{"intents": [{"intent": "close_together", "params": {"devices": ["dev_a", "dev_b"]}}]}'
# 期望：返回 constraints + translations

# 测试 optimize
curl -s -X POST http://localhost:8002/api/v1/layout/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "devices": [
      {"id": "centrifuge_1", "name": "Centrifuge", "size": [0.4, 0.4]},
      {"id": "vortex_1", "name": "Vortex Mixer", "size": [0.2, 0.2]}
    ],
    "lab": {"width": 3.0, "depth": 2.0},
    "maxiter": 50
  }' | python3 -m json.tool
# 期望：返回 placements + cost + success=true

# 测试 checker_status
curl -s http://localhost:8002/api/v1/layout/checker_status
# 期望：{"mode":"mock","collision_checker":"MockCollisionChecker","reachability_checker":"MockReachabilityChecker"}

echo "--- Phase 1 验收完成 ---"
```

Ctrl+C 停止 unilab 服务。

### Step 1.11：迁移测试文件

```bash
HANDOVER=/home/ubuntu/Desktop/handover_layout_optimizer
TARGET=unilabos/services/layout_optimizer

# 复制测试目录
cp -r "$HANDOVER/tests" "$TARGET/tests"

# 创建 __init__.py
touch "$TARGET/tests/__init__.py"

# 修复测试中的导入路径
cd /home/ubuntu/workspace/Uni-Lab-OS

# 批量替换测试文件中的 import
for f in "$TARGET"/tests/test_*.py; do
    # layout_optimizer.xxx → unilabos.services.layout_optimizer.xxx
    sed -i 's/from layout_optimizer\./from unilabos.services.layout_optimizer./g' "$f"
    sed -i 's/import layout_optimizer\./import unilabos.services.layout_optimizer./g' "$f"
    # 也处理 from layout_optimizer import
    sed -i 's/from layout_optimizer import/from unilabos.services.layout_optimizer import/g' "$f"
    echo "Fixed: $f"
done

# 运行测试（跳过需要 ROS2/LLM 的测试）
pip install pytest httpx -q
pytest "$TARGET/tests/" -v -k "not ros_checkers and not llm_skill" --tb=short 2>&1 | tail -30
```

> 部分测试可能因 `pencil_integration` 或路径问题失败，需要逐个修复。关键是 `test_optimizer.py`、`test_constraints.py`、`test_obb.py`、`test_mock_checkers.py`、`test_seeders.py` 通过。

---

## Phase 2：MoveIt2 碰撞检测集成

> 前提：Phase 0 中 ROS2 CLI 和 MoveIt2 已安装成功

### Step 2.1：创建 `checker_bridge.py`

```bash
cd /home/ubuntu/workspace/Uni-Lab-OS
TARGET=unilabos/services/layout_optimizer

cat > "$TARGET/checker_bridge.py" << 'PYEOF'
"""从 Uni-Lab-OS 的 registered_devices 中发现并桥接 MoveIt2 实例。

该模块是 layout_optimizer 与 Uni-Lab-OS ROS2 层的唯一接触点。
所有 ROS2 依赖都封装在此，layout_optimizer 其余代码保持 ROS-free。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CheckerBridge:
    """发现 MoveIt2 实例，创建真实检测器。"""

    @staticmethod
    def discover_moveit2_instances() -> dict[str, Any]:
        """从 registered_devices 中找到所有 MoveitInterface 设备。"""
        try:
            from unilabos.ros.nodes.base_device_node import registered_devices
        except ImportError:
            logger.warning("Cannot import registered_devices (ROS2 not available)")
            return {}

        moveit2_instances: dict[str, Any] = {}
        for device_id, device_info in registered_devices.items():
            node = device_info.get("node")
            if node and hasattr(node, "driver_instance"):
                driver = node.driver_instance
                if hasattr(driver, "moveit2"):
                    for group_name, m2 in driver.moveit2.items():
                        key = f"{device_id}_{group_name}"
                        moveit2_instances[key] = m2
        logger.info("Discovered %d MoveIt2 instances: %s",
                     len(moveit2_instances), list(moveit2_instances.keys()))
        return moveit2_instances

    @staticmethod
    def discover_resource_mesh_manager() -> Any | None:
        """找到 ResourceMeshManager 节点实例。"""
        try:
            from unilabos.ros.nodes.base_device_node import registered_devices
        except ImportError:
            return None

        for device_id, device_info in registered_devices.items():
            node = device_info.get("node")
            if hasattr(node, "add_resource_collision_meshes"):
                return node
        return None

    @classmethod
    def create_checkers(cls, primary_arm_id: str | None = None) -> tuple[Any, Any]:
        """创建真实检测器。

        Returns:
            (collision_checker, reachability_checker)

        Raises:
            RuntimeError: 如果没有找到 MoveIt2 实例
        """
        instances = cls.discover_moveit2_instances()
        if not instances:
            raise RuntimeError("No MoveIt2 instances found in registered_devices")

        if primary_arm_id and primary_arm_id in instances:
            moveit2 = instances[primary_arm_id]
        else:
            moveit2 = next(iter(instances.values()))

        from .ros_checkers import MoveItCollisionChecker, IKFastReachabilityChecker
        collision = MoveItCollisionChecker(moveit2, sync_to_scene=True)
        reachability = IKFastReachabilityChecker(
            moveit2,
            voxel_dir=Path(__file__).parent / "voxel_maps",
        )
        return collision, reachability
PYEOF
```

### Step 2.2：验证 MoveIt2 模式（需要 ROS2 运行）

```bash
# 以 ros 模式启动（需要完整 ROS2 环境）
LAYOUT_CHECKER_MODE=moveit unilab --backend ros --visual disable --skip_env_check --disable_browser
```

在另一个终端：

```bash
curl -s http://localhost:8002/api/v1/layout/checker_status
# 如果 MoveIt2 实例可用：{"mode":"moveit",...}
# 如果降级：{"mode":"mock",...}（检查 unilab 终端的 warning 日志）
```

---

## Phase 3：IK 可达性检测集成

Phase 3 的代码已经内嵌在 Step 1.5 创建的 `service.py` 中（`_verify_reachability` 方法）。当 `LAYOUT_CHECKER_MODE=moveit` 时，优化完成后会自动用 `compute_ik` 验证可达性约束，结果包含在 optimize 响应的 `reachability_verification` 字段中。

只需确认：

```bash
# MoveIt 模式下运行 optimize
curl -s -X POST http://localhost:8002/api/v1/layout/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "devices": [
      {"id": "arm_slider_arm", "name": "Robot Arm", "size": [0.3, 0.3], "device_type": "articulation"},
      {"id": "centrifuge_1", "name": "Centrifuge", "size": [0.4, 0.4]}
    ],
    "lab": {"width": 3.0, "depth": 2.0},
    "constraints": [
      {"type": "hard", "rule_name": "reachability", "params": {"arm_id": "arm_slider_arm", "target_device_id": "centrifuge_1"}}
    ],
    "maxiter": 50
  }' | python3 -m json.tool
# 期望：响应中包含 "reachability_verification" 字段
```

---

## Phase 4：预计算可达性体素图

### Step 4.1：创建离线预计算工具

```bash
TARGET=unilabos/services/layout_optimizer

cat > "$TARGET/precompute_reachability.py" << 'PYEOF'
"""离线生成可达性体素图 (.npz)。

用法（需要 ROS2 + move_group 运行中）：
    python -m unilabos.services.layout_optimizer.precompute_reachability \
        --arm-id arm_slider_arm \
        --resolution 0.02 \
        --reach-estimate 1.5 \
        --output voxel_maps/arm_slider_arm.npz
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
    """生成可达性体素图。"""
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

    return {
        "grid": grid,
        "origin": origin,
        "resolution": resolution,
    }


def save_voxel_map(data: dict, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(str(output_path), **data)
    logger.info("Saved voxel map to %s (%.1f MB)", output_path,
                output_path.stat().st_size / 1e6)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Precompute reachability voxel map")
    parser.add_argument("--arm-id", required=True, help="Arm device ID in registered_devices")
    parser.add_argument("--resolution", type=float, default=0.05, help="Grid resolution in meters")
    parser.add_argument("--reach-estimate", type=float, default=1.5, help="Estimated max reach in meters")
    parser.add_argument("--output", default=None, help="Output .npz path")
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
PYEOF
```

### Step 4.2：生成体素图（需要 move_group 运行）

```bash
# 先用低精度快速测试
python -m unilabos.services.layout_optimizer.precompute_reachability \
    --arm-id arm_slider_arm \
    --resolution 0.05 \
    --reach-estimate 1.5

# 生产用高精度（约 2 小时）
# python -m unilabos.services.layout_optimizer.precompute_reachability \
#     --arm-id arm_slider_arm \
#     --resolution 0.02 \
#     --reach-estimate 1.5
```

---

## Phase 5：设备目录统一 + LLM 联调

### Step 5.1：复制 LLM Skill 文档

```bash
HANDOVER=/home/ubuntu/Desktop/handover_layout_optimizer
TARGET=unilabos/services/layout_optimizer

mkdir -p "$TARGET/llm_skill"
cp "$HANDOVER/llm_skill/layout_intent_translator.md" "$TARGET/llm_skill/"
```

### Step 5.2：更新 LLM Skill 中的 API 端点

```bash
sed -i 's|POST /interpret|POST /api/v1/layout/interpret|g' "$TARGET/llm_skill/layout_intent_translator.md"
sed -i 's|GET /interpret/schema|GET /api/v1/layout/schema|g' "$TARGET/llm_skill/layout_intent_translator.md"
sed -i 's|POST /optimize|POST /api/v1/layout/optimize|g' "$TARGET/llm_skill/layout_intent_translator.md"
sed -i 's|GET /devices|GET /api/v1/layout/devices|g' "$TARGET/llm_skill/layout_intent_translator.md"
```

### Step 5.3：端到端验收

```bash
# 启动 unilab
conda activate unilab
unilab --backend simple --visual disable --skip_env_check --disable_browser &

# 等待启动
sleep 10

# 完整流程测试：interpret → optimize
echo "=== Step 1: Schema ==="
curl -s http://localhost:8002/api/v1/layout/schema | python3 -m json.tool | head -5

echo "=== Step 2: Interpret ==="
curl -s -X POST http://localhost:8002/api/v1/layout/interpret \
  -H "Content-Type: application/json" \
  -d '{
    "intents": [
      {"intent": "reachable_by", "params": {"arm": "arm_slider_arm", "targets": ["centrifuge_1", "pcr_1"]}},
      {"intent": "close_together", "params": {"devices": ["pcr_1", "centrifuge_1"], "priority": "high"}},
      {"intent": "workflow_hint", "params": {"workflow": "pcr", "devices": ["pcr_1", "centrifuge_1"]}}
    ]
  }' | python3 -m json.tool

echo "=== Step 3: Optimize ==="
curl -s -X POST http://localhost:8002/api/v1/layout/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "devices": [
      {"id": "arm_slider_arm", "name": "Robot Arm", "size": [0.3, 0.3], "device_type": "articulation"},
      {"id": "centrifuge_1", "name": "Centrifuge", "size": [0.4, 0.4]},
      {"id": "pcr_1", "name": "PCR Machine", "size": [0.35, 0.25]}
    ],
    "lab": {"width": 4.0, "depth": 3.0},
    "constraints": [
      {"type": "hard", "rule_name": "reachability", "params": {"arm_id": "arm_slider_arm", "target_device_id": "centrifuge_1", "max_reach": 1.2}},
      {"type": "hard", "rule_name": "reachability", "params": {"arm_id": "arm_slider_arm", "target_device_id": "pcr_1", "max_reach": 1.2}},
      {"type": "soft", "rule_name": "minimize_distance", "params": {"device_a": "pcr_1", "device_b": "centrifuge_1"}, "weight": 8.0}
    ],
    "maxiter": 100
  }' | python3 -m json.tool

echo "=== Step 4: Checker Status ==="
curl -s http://localhost:8002/api/v1/layout/checker_status | python3 -m json.tool

echo "=== Phase 5 端到端验收完成 ==="

# 停止 unilab
kill %1
```

---

## 文件清单总结

执行完所有 Phase 后，以下文件应存在于 Uni-Lab-OS 项目中：

```
unilabos/
├── services/
│   ├── __init__.py                              ← Phase 1 创建
│   └── layout_optimizer/
│       ├── __init__.py                          ← Phase 1 创建
│       ├── service.py                           ← Phase 1 创建
│       ├── checker_bridge.py                    ← Phase 2 创建
│       ├── precompute_reachability.py           ← Phase 4 创建
│       ├── models.py                            ← Phase 1 从 handover 复制
│       ├── obb.py                               ← Phase 1 从 handover 复制
│       ├── interfaces.py                        ← Phase 1 从 handover 复制
│       ├── lab_parser.py                        ← Phase 1 从 handover 复制
│       ├── constraints.py                       ← Phase 1 从 handover 复制
│       ├── optimizer.py                         ← Phase 1 从 handover 复制 + 修改
│       ├── seeders.py                           ← Phase 1 从 handover 复制 + 修改
│       ├── intent_interpreter.py                ← Phase 1 从 handover 复制 + 修改
│       ├── mock_checkers.py                     ← Phase 1 从 handover 复制 + 修改
│       ├── device_catalog.py                    ← Phase 1 从 handover 复制
│       ├── ros_checkers.py                      ← Phase 1 从 handover 复制
│       ├── footprints.json                      ← Phase 1 从 handover 复制
│       ├── llm_skill/
│       │   └── layout_intent_translator.md      ← Phase 5 从 handover 复制 + 修改
│       ├── voxel_maps/                          ← Phase 4 存放 .npz 文件
│       └── tests/                               ← Phase 1 从 handover 复制 + 修改
│           ├── __init__.py
│           ├── fixtures/
│           │   ├── sample_devices.json
│           │   └── sample_lab.json
│           ├── test_constraints.py
│           ├── test_device_catalog.py
│           ├── test_intent_interpreter.py
│           ├── test_mock_checkers.py
│           ├── test_obb.py
│           ├── test_optimizer.py
│           ├── test_seeders.py
│           └── ...
├── app/
│   └── web/
│       ├── api.py                               ← Phase 1 修改（添加 layout_router）
│       └── routers/
│           ├── __init__.py                      ← Phase 1 创建
│           └── layout.py                        ← Phase 1 创建
```

---

## 常见问题排查

### Q: `from .pencil_integration import ...` 报错
检查 `optimizer.py` 和 `seeders.py` 是否已按 Step 1.3.5 和 1.3.6 修改。

### Q: `from layout_optimizer.xxx` 报 ModuleNotFoundError
该文件的导入还没改为相对导入。运行：
```bash
grep -rn "from layout_optimizer\." unilabos/services/layout_optimizer/ --include="*.py"
```
将所有匹配结果改为 `from .xxx`。

### Q: unilab 启动后没有 `/api/v1/layout/*` 路由
检查 `api.py` 中是否正确添加了 `layout_router` 注册代码。查看 unilab 启动日志有无 warning。

### Q: scipy 版本冲突
```bash
pip install --force-reinstall "scipy>=1.10"
```

### Q: ROS2/MoveIt2 安装失败
Phase 1（Mock 模式）不需要 ROS2。可以先完成 Phase 1，ROS2 问题后续解决。设置：
```bash
export LAYOUT_CHECKER_MODE=mock
```

---

## API 端点速查

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/layout/health` | GET | 健康检查 |
| `/api/v1/layout/schema` | GET | 意图类型规范（LLM 用） |
| `/api/v1/layout/devices` | GET | 设备目录（?source=all/registry/assets） |
| `/api/v1/layout/checker_status` | GET | 当前检测器模式和状态 |
| `/api/v1/layout/interpret` | POST | 语义意图 → 约束列表 |
| `/api/v1/layout/optimize` | POST | 设备+约束 → 最优布局 |
