# Layout Optimizer × Uni-Lab-OS 集成执行方案

**日期**: 2026-03-26  
**目标**: 将 layout_optimizer 以 Uni-Lab-OS 原生模块的方式集成，使用真实 MoveIt2 碰撞检测与 IK 可达性替代 Mock 实现  

---

## 0. 核心架构决策

### 现状

```
layout_optimizer (独立 FastAPI :8000)          Uni-Lab-OS (FastAPI :8002 + ROS2)
┌──────────────────────────┐                  ┌───────────────────────────────┐
│  server.py               │                  │  app/web/server.py            │
│  MockCollisionChecker    │   ← 完全隔离 →    │  HostNode + registered_devices│
│  MockReachabilityChecker │                  │  MoveIt2 (move_group)         │
└──────────────────────────┘                  │  ResourceMeshManager          │
                                              └───────────────────────────────┘
```

### 目标架构

```
Uni-Lab-OS 进程 (FastAPI :8002 + ROS2 + Layout Optimizer)
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  app/web/api.py                                             │
│    /api/v1/layout/interpret     ← 新增路由                   │
│    /api/v1/layout/optimize                                  │
│    /api/v1/layout/schema                                    │
│         │                                                   │
│         ▼ (同进程调用)                                       │
│  unilabos/services/layout_optimizer/   ← 新增模块            │
│    ├── __init__.py                                          │
│    ├── service.py          ← LayoutService 单例              │
│    ├── checker_bridge.py   ← MoveIt2 桥接层                  │
│    └── (核心算法文件从 handover 移入)                          │
│         │                                                   │
│         ▼ (同进程读取)                                       │
│  registered_devices → MoveitInterface → MoveIt2 实例         │
│  ResourceMeshManager → PlanningScene 同步                    │
│                                                             │
│  ROS2 层                                                    │
│    move_group 节点 ← /compute_ik, /get_planning_scene       │
│    robot_state_publisher ← TF                               │
│    ros2_control ← 关节控制                                   │
└─────────────────────────────────────────────────────────────┘
```

**关键决策**:  
layout_optimizer 不再作为独立 FastAPI 服务，而是作为 Uni-Lab-OS 的**同进程模块**集成。  
理由：Uni-Lab-OS 的 FastAPI 和 ROS2 节点运行在同一进程中，API handler 通过 `HostNode` 单例和 `registered_devices` 字典直接读取 ROS2 节点状态。Layout optimizer 需要 MoveIt2 实例，最高效的方式是同进程访问。

---

## 1. 模块结构设计

### 1.1 在 Uni-Lab-OS 中新建模块

```
unilabos/
├── services/                          ← 新建目录（服务层）
│   └── layout_optimizer/
│       ├── __init__.py
│       ├── service.py                 ← LayoutService: 对外入口单例
│       ├── checker_bridge.py          ← CheckerBridge: 从 ROS2 获取 MoveIt2 实例
│       ├── models.py                  ← 搬入（Device, Lab, Placement, Constraint, Intent）
│       ├── obb.py                     ← 搬入（OBB 几何计算，无修改）
│       ├── constraints.py             ← 搬入（约束评估，无修改）
│       ├── optimizer.py               ← 搬入 + 修改（去 pencil 依赖，改默认 checker 来源）
│       ├── seeders.py                 ← 搬入（力导向种子布局）
│       ├── intent_interpreter.py      ← 搬入（意图翻译，无修改）
│       ├── device_catalog.py          ← 搬入 + 修改（接入 Uni-Lab-OS registry）
│       ├── footprints.json            ← 搬入（499 设备离线数据）
│       └── voxel_maps/                ← 新建目录（存放预计算可达性体素图 .npz）
```

### 1.2 在 web 层注册路由

```
unilabos/app/web/
├── api.py                             ← 新增 layout_router 路由注册
└── routers/
    └── layout.py                      ← 新建（/api/v1/layout/* 路由定义）
```

### 1.3 在 registry 层注册能力

```
unilabos/registry/
└── services/
    └── layout_optimizer.yaml          ← 新建（描述 service 能力和配置）
```

---

## 2. 分阶段实施计划

### Phase 1: 模块搬迁 + Mock 模式可用（2 天）

> 目标：layout_optimizer 的全部功能在 Uni-Lab-OS 进程内可用，行为与独立运行完全一致

#### 2.1 创建模块目录

```bash
mkdir -p unilabos/services/layout_optimizer
mkdir -p unilabos/services/layout_optimizer/voxel_maps
mkdir -p unilabos/app/web/routers
```

#### 2.2 搬迁核心文件（直接复制，不修改算法逻辑）

| 源文件 (handover) | 目标文件 (Uni-Lab-OS) | 修改 |
|---|---|---|
| `models.py` | `services/layout_optimizer/models.py` | 无 |
| `obb.py` | `services/layout_optimizer/obb.py` | 无 |
| `constraints.py` | `services/layout_optimizer/constraints.py` | 修改 import 路径 |
| `seeders.py` | `services/layout_optimizer/seeders.py` | 修改 import 路径 |
| `intent_interpreter.py` | `services/layout_optimizer/intent_interpreter.py` | 修改 import 路径 |
| `mock_checkers.py` | `services/layout_optimizer/mock_checkers.py` | 修改 import 路径 |
| `interfaces.py` | `services/layout_optimizer/interfaces.py` | 无 |
| `device_catalog.py` | `services/layout_optimizer/device_catalog.py` | 修改 import 路径 |
| `footprints.json` | `services/layout_optimizer/footprints.json` | 无 |

#### 2.3 修改 optimizer.py — 去除 pencil 依赖

```python
# 修改前（handover）
from .pencil_integration import generate_initial_layout

# 修改后
# pencil_integration 已移除，使用 seeders.py 替代
# seed_placements 由调用方（service.py）通过 seeders 生成后传入
```

#### 2.4 创建 service.py — LayoutService 单例

```python
"""Layout Optimizer 服务入口。

以单例模式提供 interpret / optimize / devices 功能。
Checker 模式由 set_checker_mode() 控制：
  - "mock": 使用 OBB SAT + 欧氏距离（默认，无 ROS 依赖）
  - "moveit": 使用 MoveIt2 碰撞检测 + IK 可达性
"""

class LayoutService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._checker_mode = "mock"
        self._collision_checker = None
        self._reachability_checker = None
        self._init_checkers()

    def set_checker_mode(self, mode, moveit2=None):
        """切换检测器模式。moveit 模式需传入 MoveIt2 实例。"""
        ...

    def interpret(self, intents):
        """将语义意图翻译为约束列表。"""
        ...

    def optimize(self, devices, lab, constraints, ...):
        """运行布局优化。"""
        ...

    def get_devices(self, source="all"):
        """获取设备目录。"""
        ...
```

#### 2.5 创建 layout.py 路由 — 挂载到 /api/v1/layout

```python
"""Layout Optimizer API 路由。

路由挂载到 /api/v1/layout/，与 Uni-Lab-OS 的 API 体系统一。
"""
from fastapi import APIRouter

layout_router = APIRouter(prefix="/layout", tags=["layout"])

@layout_router.post("/interpret")
async def interpret(request: InterpretRequest):
    service = LayoutService.get_instance()
    return service.interpret(request.intents)

@layout_router.post("/optimize")
async def optimize(request: OptimizeRequest):
    service = LayoutService.get_instance()
    return service.optimize(...)

@layout_router.get("/schema")
async def schema():
    ...

@layout_router.get("/devices")
async def devices(source: str = "all"):
    ...
```

#### 2.6 在 api.py 中注册路由

```python
# unilabos/app/web/api.py — setup_api_routes 函数中新增：
from unilabos.app.web.routers.layout import layout_router
api.include_router(layout_router)
```

#### 2.7 验收标准

- [ ] `unilab` 启动后 `curl http://localhost:8002/api/v1/layout/schema` 返回 10 种意图
- [ ] `POST /api/v1/layout/interpret` 与原 handover 行为一致
- [ ] `POST /api/v1/layout/optimize` (mock 模式) 与原 handover 行为一致
- [ ] 原 193 个测试全部通过（import 路径适配后）

---

### Phase 2: MoveIt2 碰撞检测集成（3 天）

> 目标：优化结果同步到 MoveIt2 Planning Scene，使运动规划感知设备布局

#### 2.8 创建 checker_bridge.py — MoveIt2 桥接层

```python
"""从 Uni-Lab-OS 的 registered_devices 中发现并桥接 MoveIt2 实例。

该模块是 layout_optimizer 与 Uni-Lab-OS ROS2 层的唯一接触点。
所有 ROS2 依赖都封装在此，layout_optimizer 其余代码保持 ROS-free。
"""

class CheckerBridge:
    """发现 MoveIt2 实例，创建真实检测器。"""

    @staticmethod
    def discover_moveit2_instances():
        """从 registered_devices 中找到所有 MoveitInterface 设备。

        遍历 Uni-Lab-OS 的 registered_devices 字典，
        找到 driver_instance 是 MoveitInterface 的设备，
        提取其 moveit2 字典中的 MoveIt2 实例。

        Returns:
            dict[str, MoveIt2]: {device_id: MoveIt2 实例}
        """
        from unilabos.ros.nodes.base_device_node import registered_devices

        moveit2_instances = {}
        for device_id, device_info in registered_devices.items():
            node = device_info.get("node")
            if node and hasattr(node, 'driver_instance'):
                driver = node.driver_instance
                if hasattr(driver, 'moveit2'):
                    for group_name, m2 in driver.moveit2.items():
                        key = f"{device_id}_{group_name}"
                        moveit2_instances[key] = m2
        return moveit2_instances

    @staticmethod
    def discover_resource_mesh_manager():
        """找到 ResourceMeshManager 节点实例。

        用于将优化结果同步到 Planning Scene。
        """
        from unilabos.ros.nodes.base_device_node import registered_devices
        for device_id, device_info in registered_devices.items():
            node = device_info.get("node")
            if hasattr(node, 'add_resource_collision_meshes'):
                return node
        return None

    @classmethod
    def create_checkers(cls, primary_arm_id=None):
        """创建真实检测器。

        Args:
            primary_arm_id: 首选机械臂 ID（用于可达性检测的 compute_ik）。
                           若为 None，取第一个发现的 MoveIt2 实例。
        Returns:
            (collision_checker, reachability_checker)
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
```

#### 2.9 修改 ros_checkers.py — 碰撞检测双模式

DE 优化器迭代频次极高（~100K 次 cost function 调用），不能每次都走 ROS service。设计如下：

```
                    DE 优化循环中（~100K 调用/次优化）
                    ┌─────────────────────────────────┐
cost_function() ──→ │  python-fcl 直接碰撞检测          │  ← 纯 Python，无 ROS
                    │  或 OBB SAT 回退                  │
                    └─────────────────────────────────┘

                    最终评估 + 场景同步（1 次/次优化）
                    ┌─────────────────────────────────┐
final_eval() ─────→ │  _sync_collision_objects()       │  ← 发布到 /collision_object
                    │  + binary pass/fail 评估          │
                    └─────────────────────────────────┘
```

修改 `MoveItCollisionChecker`：增加 `sync_only()` 方法供最终同步使用，`check()` 时可选是否同步。

```python
class MoveItCollisionChecker:
    def __init__(self, moveit2, *, default_height=0.4,
                 sync_to_scene=True, sync_on_check=False):
        ...
        self._sync_on_check = sync_on_check  # DE 循环中设为 False

    def check(self, placements):
        if self._sync_on_check:
            self._sync_collision_objects(placements)
        if self._fcl_available:
            return self._check_with_fcl(placements)
        return self._check_with_obb(placements)

    def sync_to_planning_scene(self, placements):
        """最终布局确定后，一次性同步到 MoveIt2。"""
        self._sync_collision_objects(placements)
```

#### 2.10 修改 service.py — optimize 流程加入 sync

```python
def optimize(self, ...):
    ...
    result_placements = optimizer.optimize(...)
    result_placements = optimizer.snap_theta(result_placements)

    # 最终结果同步到 MoveIt2 Planning Scene
    if self._checker_mode == "moveit":
        checker_placements = self._to_checker_format(devices, result_placements)
        self._collision_checker.sync_to_planning_scene(checker_placements)

    return result_placements
```

#### 2.11 验收标准

- [ ] `LAYOUT_CHECKER_MODE=moveit` 启动时自动发现 MoveIt2 实例
- [ ] DE 优化速度不受影响（python-fcl/OBB in loop）
- [ ] 优化完成后 RViz 中可看到设备碰撞盒在正确位置
- [ ] `move_group` 节点的 Planning Scene 包含最新布局

---

### Phase 3: IK 可达性检测集成（3 天）

> 目标：用真实 IK 替代欧氏距离判断，确保优化结果中机械臂真的能到达目标

#### 2.12 实时 IK — 最终验证

修改 `service.py`：optimize 完成后用 `compute_ik` 验证每条 reachability 约束：

```python
def _verify_reachability(self, placements, constraints):
    """用真实 IK 验证可达性约束。

    仅在最终评估时调用（不在 DE 循环中），
    因为 compute_ik 是 ROS service 调用（~5ms/次）。

    Returns:
        list[dict]: 失败的约束列表，含 arm_id, target_device_id, reason
    """
    failures = []
    for c in constraints:
        if c.rule_name != "reachability":
            continue
        arm_id = c.params["arm_id"]
        target_id = c.params["target_device_id"]
        arm_p = next((p for p in placements if p.device_id == arm_id), None)
        target_p = next((p for p in placements if p.device_id == target_id), None)
        if not arm_p or not target_p:
            continue

        arm_pose = {"x": arm_p.x, "y": arm_p.y, "theta": arm_p.theta}
        target = {"x": target_p.x, "y": target_p.y, "z": 0.0}
        if not self._reachability_checker.is_reachable(arm_id, arm_pose, target):
            failures.append({
                "arm_id": arm_id,
                "target_device_id": target_id,
                "reason": "IK solver found no solution",
            })
    return failures
```

#### 2.13 响应格式扩展

`/api/v1/layout/optimize` 响应新增 `reachability_verification` 字段：

```json
{
  "placements": [...],
  "cost": 0.0,
  "success": true,
  "seeder_used": "compact_outward",
  "de_ran": true,
  "reachability_verification": {
    "mode": "moveit_ik",
    "all_passed": true,
    "failures": [],
    "checked_count": 4
  }
}
```

#### 2.14 验收标准

- [ ] 可达性约束用 `/compute_ik` 验证而非欧氏距离
- [ ] 返回中包含真实 IK 验证结果
- [ ] 未知机械臂（无 MoveIt2 配置）优雅降级到 Mock

---

### Phase 4: 预计算可达性体素图（3 天）

> 目标：将 IK 调用结果离线预计算为 O(1) 查表，DE 循环可用

#### 2.15 创建 precompute_reachability.py 离线工具

```python
"""离线生成可达性体素图 (.npz)。

用法：
    # 需要 ROS2 + move_group 运行中
    python -m unilabos.services.layout_optimizer.precompute_reachability \
        --arm-id arm_slider_arm \
        --resolution 0.02 \
        --reach-estimate 1.5 \
        --output voxel_maps/arm_slider_arm.npz

工作原理：
    1. 在机械臂基坐标系中按 resolution 步长网格化 3D 空间
    2. 对每个网格点调用 moveit2.compute_ik()
    3. 记录可达 (True) / 不可达 (False)
    4. 保存为 .npz (grid, origin, resolution)

预计耗时：
    resolution=0.02, reach=1.5 → 150×150×75 = ~1.7M 点
    @5ms/点 → ~2.3 小时 (可多线程加速)

精度 vs 速度权衡：
    resolution=0.01 → 高精度 (1cm) → ~13.5M 点 → ~19 小时
    resolution=0.02 → 中精度 (2cm) → ~1.7M 点 → ~2.3 小时  ← 推荐
    resolution=0.05 → 低精度 (5cm) → ~54K 点 → ~4.5 分钟
"""
```

#### 2.16 集成体素图到 DE 循环

当 `voxel_maps/` 目录下存在对应 arm_id 的 `.npz` 文件时，`IKFastReachabilityChecker` 自动加载，DE 循环中使用 O(1) 查表替代欧氏距离：

```
优化循环可达性检测优先级：
  1. 体素图命中 → O(1) 查表 → 精确 ✓ 快速 ✓
  2. 体素图未命中 → compute_ik() → 精确 ✓ 慢 ✗ (仅最终验证用)
  3. 无 MoveIt2 → Mock 欧氏距离 → 不精确 ✗ 快速 ✓
```

#### 2.17 验收标准

- [ ] 离线工具可为 arm_slider 生成 .npz 体素图
- [ ] DE 循环使用体素图进行 O(1) 可达性查询
- [ ] 优化速度与 Mock 模式差距 < 20%
- [ ] 体素查询结果与实时 IK 一致性 > 95%

---

### Phase 5: 设备目录统一 + LLM 联调（2 天）

> 目标：layout_optimizer 的设备信息从 Uni-Lab-OS registry 获取，不再依赖独立的 footprints.json

#### 2.18 device_catalog.py 适配 registry

```python
def load_devices_from_registry_live():
    """从 Uni-Lab-OS 运行时 registry 加载设备信息。

    优先级：
    1. 当前场景设备 (registered_devices) — 实时在线设备
    2. lab_registry.device_type_registry — 全量注册设备
    3. footprints.json — 离线兜底数据
    """
    from unilabos.ros.nodes.base_device_node import registered_devices
    from unilabos.registry.registry import lab_registry

    devices = []
    for device_id, device_info in registered_devices.items():
        # 从 registry 获取 model.mesh → device_mesh 配置
        # 从 footprints.json 补充 bbox/openings
        ...
    return devices
```

#### 2.19 LLM Skill 适配

更新 `layout_intent_translator.md`，调整 API 端点：

```diff
- POST /interpret
+ POST /api/v1/layout/interpret

- GET /interpret/schema
+ GET /api/v1/layout/schema

- POST /optimize
+ POST /api/v1/layout/optimize

- GET /devices
+ GET /api/v1/layout/devices
```

#### 2.20 验收标准

- [ ] `GET /api/v1/layout/devices` 返回当前场景在线设备 + registry 全量设备
- [ ] LLM Skill 文档适配新端点
- [ ] 端到端测试：NL → interpret → optimize → 场景更新

---

## 3. 文件修改清单

### 新建文件

| 文件 | 用途 |
|---|---|
| `unilabos/services/__init__.py` | 服务层包 |
| `unilabos/services/layout_optimizer/__init__.py` | 模块入口，导出 LayoutService |
| `unilabos/services/layout_optimizer/service.py` | LayoutService 单例 |
| `unilabos/services/layout_optimizer/checker_bridge.py` | MoveIt2 发现与桥接 |
| `unilabos/services/layout_optimizer/ros_checkers.py` | MoveIt2 碰撞+可达性适配器（从 handover 搬入+改进） |
| `unilabos/services/layout_optimizer/precompute_reachability.py` | 离线体素生成工具 |
| `unilabos/app/web/routers/__init__.py` | 路由包 |
| `unilabos/app/web/routers/layout.py` | Layout API 路由 |
| `unilabos/services/layout_optimizer/models.py` | 数据模型（搬入） |
| `unilabos/services/layout_optimizer/obb.py` | OBB 几何（搬入） |
| `unilabos/services/layout_optimizer/constraints.py` | 约束评估（搬入） |
| `unilabos/services/layout_optimizer/optimizer.py` | DE 优化器（搬入+修改） |
| `unilabos/services/layout_optimizer/seeders.py` | 种子布局（搬入） |
| `unilabos/services/layout_optimizer/intent_interpreter.py` | 意图翻译（搬入） |
| `unilabos/services/layout_optimizer/mock_checkers.py` | Mock 检测器（搬入） |
| `unilabos/services/layout_optimizer/interfaces.py` | Protocol 定义（搬入） |
| `unilabos/services/layout_optimizer/device_catalog.py` | 设备目录（搬入+修改） |
| `unilabos/services/layout_optimizer/footprints.json` | 离线设备数据（搬入） |

### 修改文件

| 文件 | 修改内容 |
|---|---|
| `unilabos/app/web/api.py` | `setup_api_routes` 中新增 `api.include_router(layout_router)` |
| `unilabos/app/web/server.py` | （可能）初始化 LayoutService |
| `setup.py` 或 `MANIFEST.in` | 包含新模块的数据文件（footprints.json, voxel_maps/） |

---

## 4. 检测器模式对比

| 维度 | Mock 模式 | MoveIt 模式 (Phase 2-4) |
|---|---|---|
| **碰撞检测 (DE循环)** | OBB SAT (O(n²), ~0.01ms) | python-fcl 直接 (O(n²), ~0.05ms) |
| **碰撞检测 (最终)** | 同上 | 同上 + sync_to_planning_scene |
| **可达性 (DE循环)** | 欧氏距离 (O(1), ~0.001ms) | 体素图查表 (O(1), ~0.005ms) |
| **可达性 (最终验证)** | 同上 | compute_ik (ROS, ~5ms) |
| **边界检测** | AABB 计算 | 同 Mock（几何计算无需 ROS） |
| **ROS2 依赖** | 无 | 需要 move_group 运行 |
| **精度** | 低（2D 简化） | 高（真实 3D 碰撞 + IK） |
| **环境变量** | `LAYOUT_CHECKER_MODE=mock` | `LAYOUT_CHECKER_MODE=moveit` |

---

## 5. 依赖管理

### 新增 Python 依赖

```yaml
# conda 或 pip
scipy>=1.10          # DE 优化器（原有）
numpy>=1.24          # 数值计算（原有）
pydantic>=2.0        # 数据验证（Uni-Lab-OS 已有）
python-fcl>=0.7      # 可选：精确碰撞检测（Phase 2）
```

### ROS2 依赖（Phase 2+，Uni-Lab-OS 已配置）

```yaml
ros-humble-moveit            # MoveIt2 核心
ros-humble-moveit-msgs       # MoveIt2 消息类型
```

### 不需要新增

- `fastapi`, `uvicorn` — Uni-Lab-OS 已有
- `anthropic` — 仅 LLM 测试需要

---

## 6. 测试策略

### Phase 1 测试

将原 handover 的 193 个测试迁移到 `unilabos/services/layout_optimizer/tests/`，修改 import 路径。所有测试应在无 ROS2 环境下通过。

### Phase 2-3 新增测试

| 测试文件 | 内容 |
|---|---|
| `test_checker_bridge.py` | Mock registered_devices，验证 MoveIt2 发现逻辑 |
| `test_integration_moveit.py` | 需 ROS2 环境，端到端 interpret → optimize → PlanningScene 验证 |
| `test_api_routes.py` | FastAPI TestClient 测试 `/api/v1/layout/*` 路由 |

### 测试运行方式

```bash
# 无 ROS2 环境（CI/本地开发）
pytest unilabos/services/layout_optimizer/tests/ -v -k "not moveit"

# 有 ROS2 + MoveIt2 环境
LAYOUT_CHECKER_MODE=moveit pytest unilabos/services/layout_optimizer/tests/ -v
```

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| MoveIt2 实例尚未初始化时 API 被调用 | 返回空/错误 | LayoutService 启动时检测，moveit 模式不可用时自动降级到 mock 并记录 warning |
| DE 优化中引入 ROS 调用导致性能暴跌 | 优化耗时从 ~5s 变为 ~50min | 严格隔离：DE 循环内只用本地计算（fcl/OBB + 体素/欧氏），ROS 调用仅在最终验证 |
| python-fcl 安装困难 | 回退到 OBB SAT | ros_checkers.py 已有 OBB 回退逻辑，性能和精度足够 |
| 体素图生成耗时过长 | 阻塞部署 | 先用 resolution=0.05 快速生成（~5min），后续用 0.02 替换 |
| 设备 ID 命名不一致 | 约束匹配失败 | checker_bridge.py 中做 ID 映射层 |
| move_group 节点崩溃 | 碰撞同步失败 | _sync_collision_objects 已有 try/except，不影响优化结果 |

---

## 8. 里程碑时间线

```
Day 1-2:  Phase 1 — 模块搬迁 + Mock 模式
          ✓ 核心文件搬入 Uni-Lab-OS
          ✓ API 路由注册
          ✓ 测试通过

Day 3-5:  Phase 2 — MoveIt2 碰撞检测集成
          ✓ checker_bridge.py 发现 MoveIt2
          ✓ 最终布局同步到 PlanningScene
          ✓ RViz 可视化验证

Day 6-8:  Phase 3 — IK 可达性集成
          ✓ 最终验证用 compute_ik
          ✓ 响应包含 IK 验证结果
          ✓ 降级策略完善

Day 9-11: Phase 4 — 预计算体素图
          ✓ 离线工具生成 .npz
          ✓ DE 循环使用体素查表
          ✓ 性能基准测试

Day 12-13: Phase 5 — 设备目录统一 + LLM 联调
          ✓ 接入 Uni-Lab-OS registry
          ✓ LLM Skill 端点适配
          ✓ 端到端验收
```

---

## 9. API 端点变更对照表

| 原 handover 端点 | 新 Uni-Lab-OS 端点 | 变化 |
|---|---|---|
| `GET /health` | `GET /api/v1/layout/health` | 路径前缀 |
| `GET /devices` | `GET /api/v1/layout/devices` | 路径前缀 + 可选接入 registry |
| `POST /interpret` | `POST /api/v1/layout/interpret` | 路径前缀 |
| `GET /interpret/schema` | `GET /api/v1/layout/schema` | 路径简化 |
| `POST /optimize` | `POST /api/v1/layout/optimize` | 路径前缀 + 响应增加 reachability_verification |
| (无) | `GET /api/v1/layout/checker_status` | 新增：返回当前检测器模式和可用性 |

---

## 10. Quick Start（集成后）

```bash
# 1. 仅 Mock 模式（无 ROS2）
unilab --visual disable
# → http://localhost:8002/api/v1/layout/schema

# 2. MoveIt 模式（需 ROS2 + move_group）
LAYOUT_CHECKER_MODE=moveit unilab --visual enable
# → http://localhost:8002/api/v1/layout/checker_status
# → {"mode": "moveit", "collision": "fcl", "reachability": "voxel+ik", "arms": ["arm_slider_arm"]}

# 3. 生成体素图（离线，需 move_group 运行）
python -m unilabos.services.layout_optimizer.precompute_reachability \
    --arm-id arm_slider_arm --resolution 0.02
```
