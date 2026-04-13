# Uni-Lab CAD 实现指南

> **目标**：将 Matterix（Isaac Sim 仿真框架）与 Uni-Lab-OS（实验室操作系统）的物理图谱、工作流系统打通，构建一个"实验室设计与仿真验证平台"——允许用户在虚拟环境中设计实验室布局、编排工作流，并在真机部署前完成碰撞检测、可达性分析和流体风险预判。

---

## 一、架构全景

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Uni-Lab CAD 系统边界                                │
│                                                                       │
│  ┌────────────────────┐    ┌─────────────────────────────────────┐   │
│  │   Uni-Lab-OS 侧     │    │          Matterix 侧                │   │
│  │                    │    │                                     │   │
│  │  physical_graph    │    │  MatterixBaseEnvCfg                 │   │
│  │  (nodes + links    │───→│  (articulated_assets + objects      │   │
│  │   JSON)            │    │   + particle_systems + workflows)   │   │
│  │                    │    │                                     │   │
│  │  protocol_workflow │    │  StateMachine                       │   │
│  │  (action 序列 JSON) │───→│  (PrimitiveAction 序列)             │   │
│  │                    │    │                                     │   │
│  │  ResourceTreeSet   │    │  SceneData                          │   │
│  │  (labware 状态树)   │←───│  (RigidObjectData / frames)        │   │
│  └─────────┬──────────┘    └──────────────┬──────────────────────┘   │
│            │                              │                           │
│  ┌─────────▼──────────────────────────────▼──────────────────────┐   │
│  │                     Bridge Layer（核心桥接层）                   │   │
│  │                                                               │   │
│  │  asset_mapper.py      scene_builder.py    workflow_translator │   │
│  │  （设备类→USD资产）    （graph JSON→EnvCfg）   （动作序列转换）  │   │
│  └──────────────────────────────┬────────────────────────────────┘   │
│                                 │                                     │
│  ┌──────────────────────────────▼────────────────────────────────┐   │
│  │                     Validation Engine                          │   │
│  │   reachability_checker  collision_checker  fluid_risk_checker  │   │
│  └──────────────────────────────┬────────────────────────────────┘   │
│                                 │                                     │
│  ┌──────────────────────────────▼────────────────────────────────┐   │
│  │             FastAPI CAD Routes + Web UI                        │   │
│  │    /api/v1/cad/validate   /api/v1/cad/assets   /cad           │   │
│  └───────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 二、前置条件

### 2.1 两个系统的安装

| 系统 | 必须版本 | 安装文档 |
|---|---|---|
| Isaac Sim | 5.0.0 | `MatterixREPRODUCTION_GUIDE.md` |
| Isaac Lab | 2.3.0 | 同上 |
| Matterix | main 分支 | `MatterixREADME.md` |
| Uni-Lab-OS | main 分支 | `README.md` |
| ROS2 | Humble | Uni-Lab-OS 依赖 |
| Python | 3.11 | 两者共同要求 |

### 2.2 环境变量

```bash
# Matterix 资产路径（必须设置，否则 USD 找不到）
export MATTERIX_PATH=/path/to/Matterix

# ROS2 环境
source /opt/ros/humble/setup.bash
source install/setup.bash

# Isaac Lab conda 环境
conda activate matterix
```

### 2.3 项目目录结构

在 Uni-Lab-OS 根目录下创建新子包：

```
Uni-Lab-OS/
├── unilabos/                    # 现有代码
├── unilabos_msgs/               # 现有 ROS2 消息
└── uni_lab_cad/                 # 新建：Uni-Lab CAD 子系统
    ├── __init__.py
    ├── bridge/
    │   ├── __init__.py
    │   ├── asset_mapper.py      # 设备注册表类 → Matterix USD 资产配置
    │   ├── scene_builder.py     # physical graph JSON → MatterixBaseEnvCfg
    │   └── workflow_translator.py  # Uni-Lab 动作序列 → matterix_sm 序列
    ├── sim/
    │   ├── __init__.py
    │   ├── cad_env_cfg.py       # 动态 EnvCfg 构造器
    │   └── validators/
    │       ├── __init__.py
    │       ├── reachability.py  # 可达性检验
    │       ├── collision.py     # 碰撞检测
    │       └── fluid_risk.py    # 流体溢出风险
    ├── api/
    │   ├── __init__.py
    │   ├── cad_routes.py        # FastAPI 路由
    │   └── models.py            # Pydantic 请求/响应模型
    └── ui/
        ├── templates/
        │   └── cad.html
        └── static/
            ├── cad.js
            └── cad.css
```

---

## 三、第一阶段：Bridge Layer（桥接层）

这是整个系统的核心，需要最先实现。

### 3.1 资产映射表（`bridge/asset_mapper.py`）

**任务**：将 Uni-Lab-OS 的设备注册表类名（如 `virtual_stirrer`、`robot_arm`）映射到 Matterix 的资产配置类。

**关键数据来源**：
- Uni-Lab-OS 设备注册表：`unilabos/registry/devices/*.yaml`，每个 YAML 的顶层键即 `class` 字段的合法值
- Matterix 资产配置：`matterix_assets` 包中的 `FRANKA_PANDA_HIGH_PD_IK_CFG`、`BEAKER_500ML_INST_CFG`、`TABLE_THORLABS_75X90_INST_Cfg` 等

```python
# uni_lab_cad/bridge/asset_mapper.py

from __future__ import annotations
from dataclasses import replace
from typing import Literal

# Matterix 资产配置导入
from matterix_assets.robots.franka_arms import (
    FRANKA_PANDA_HIGH_PD_IK_CFG,
    FRANKA_ROBOTI2F85_INST_CFG,
)
from matterix_assets.labware.beakers import BEAKER_500ML_INST_CFG
from matterix_assets.infrastructure.tables import (
    TABLE_THORLABS_75X90_INST_Cfg,
    TABLE_SEATTLE_INST_Cfg,
)
from matterix_assets.asset_cfgs import (
    MatterixRigidObjectCfg,
    MatterixArticulationCfg,
    MatterixStaticObjectCfg,
)

# 坐标缩放：Uni-Lab-OS 画布像素坐标 → Isaac Sim 世界坐标（米）
# Uni-Lab-OS 的 position.x/y 是画布像素坐标，需要缩放
CANVAS_TO_WORLD_SCALE = 0.01  # 100 px = 1 m（根据实际画布尺寸调整）

AssetCategory = Literal["robot", "container", "static", "unknown"]

# ─── 主映射表 ───────────────────────────────────────────────────────────────
# 键：Uni-Lab-OS registry YAML 的顶层设备类名
# 值：对应的 Matterix 资产配置实例（未设置 pos，由 scene_builder 填入）
DEVICE_CLASS_TO_MATTERIX_CFG: dict[str, MatterixArticulationCfg | MatterixRigidObjectCfg | MatterixStaticObjectCfg | None] = {
    # ── 机器人臂 ──
    "robot_arm":               FRANKA_PANDA_HIGH_PD_IK_CFG,
    "elite_robot":             FRANKA_PANDA_HIGH_PD_IK_CFG,   # 暂用 Franka 占位
    "franka_arm":              FRANKA_PANDA_HIGH_PD_IK_CFG,

    # ── 工作站（映射为实验桌） ──
    "workstation":             TABLE_THORLABS_75X90_INST_Cfg,
    "post_process":            TABLE_THORLABS_75X90_INST_Cfg,

    # ── 设备（暂无 USD，映射为桌子占位，后续替换） ──
    "virtual_stirrer":         TABLE_SEATTLE_INST_Cfg,
    "virtual_centrifuge":      TABLE_SEATTLE_INST_Cfg,
    "virtual_heatchill":       TABLE_SEATTLE_INST_Cfg,
    "liquid_handler":          TABLE_THORLABS_75X90_INST_Cfg,
    "hplc":                    TABLE_SEATTLE_INST_Cfg,
    "balance":                 TABLE_SEATTLE_INST_Cfg,

    # ── 容器/耗材 ──
    "container":               BEAKER_500ML_INST_CFG,
    "flask":                   BEAKER_500ML_INST_CFG,
    "vial":                    BEAKER_500ML_INST_CFG,
    "well_plate":              None,  # TODO: 需要添加 well plate USD 资产
}


def get_asset_category(cfg) -> AssetCategory:
    """判断资产类别，用于决定放入 articulated_assets 还是 objects"""
    if isinstance(cfg, MatterixArticulationCfg):
        return "robot"
    elif isinstance(cfg, MatterixRigidObjectCfg):
        return "container"
    elif isinstance(cfg, MatterixStaticObjectCfg):
        return "static"
    return "unknown"


def resolve_asset_cfg(
    device_class: str,
    position_2d: dict,           # {"x": float, "y": float, "z": float}
    env_floor_z: float = 0.0,
) -> tuple[AssetCategory, MatterixArticulationCfg | MatterixRigidObjectCfg | MatterixStaticObjectCfg] | None:
    """
    将 Uni-Lab-OS 设备节点转换为带有世界坐标 pos 的 Matterix 资产配置。

    返回 None 表示该设备类型无对应 Matterix 资产，跳过。
    """
    base_cfg = DEVICE_CLASS_TO_MATTERIX_CFG.get(device_class)
    if base_cfg is None:
        return None

    # 坐标转换：画布 2D → Isaac Sim 3D
    world_x = position_2d.get("x", 0.0) * CANVAS_TO_WORLD_SCALE
    world_y = position_2d.get("y", 0.0) * CANVAS_TO_WORLD_SCALE
    world_z = env_floor_z

    cfg_with_pos = replace(base_cfg, pos=(world_x, world_y, world_z))
    return get_asset_category(cfg_with_pos), cfg_with_pos
```

---

### 3.2 场景构造器（`bridge/scene_builder.py`）

**任务**：读取 Uni-Lab-OS 的 physical setup graph JSON，输出一个完整的 `MatterixBaseEnvCfg`。

**数据流**：
```
stirteststation.json (nodes + links)
  → read_node_link_json()  [unilabos/resources/graphio.py]
  → nx.Graph, ResourceTreeSet
  → 遍历节点 → resolve_asset_cfg()
  → MatterixBaseEnvCfg(articulated_assets=..., objects=...)
```

**关键格式对照**：

| Uni-Lab-OS graph 节点字段 | 用途 | 映射到 Matterix |
|---|---|---|
| `id` | 设备唯一 ID | `articulated_assets`/`objects` 的字典键 |
| `class` | 设备注册类名 | `DEVICE_CLASS_TO_MATTERIX_CFG` 的查找键 |
| `type` | `"device"` / `"container"` | 辅助判断资产类型 |
| `position.x/y` | 画布坐标 | Isaac Sim `pos=(x,y,z)` |
| `config` | 构造参数 | 部分字段（如 `max_volume`）可写入资产的 `frames` |

```python
# uni_lab_cad/bridge/scene_builder.py

from __future__ import annotations
import logging
from isaaclab.utils import configclass
from matterix.envs import MatterixBaseEnvCfg
from matterix_sm.robot_action_spaces import FRANKA_IK_ACTION_SPACE

# Uni-Lab-OS 工具
from unilabos.resources.graphio import read_node_link_json

from .asset_mapper import resolve_asset_cfg

logger = logging.getLogger(__name__)


@configclass
class DynamicEnvCfg(MatterixBaseEnvCfg):
    """
    动态构造的 MatterixBaseEnvCfg。
    不能在类定义时填充 articulated_assets / objects，
    因为 @configclass 装饰器不支持运行时动态类。
    通过 build_env_cfg_from_graph() 工厂函数填充。
    """
    env_spacing: float = 5.0
    num_envs: int = 1


def build_env_cfg_from_graph(
    graph_json_path: str,
    robot_override: str | None = None,
) -> DynamicEnvCfg:
    """
    从 Uni-Lab-OS physical graph JSON 构造 Matterix 仿真环境配置。

    Args:
        graph_json_path: 指向 node-link JSON 文件的路径。
        robot_override:  如果设置，强制将所有 robot 类型节点替换为此 Matterix 资产名。

    Returns:
        填充了 articulated_assets 和 objects 的 DynamicEnvCfg 实例。
    """
    graph, resource_tree, _links = read_node_link_json(graph_json_path)

    articulated_assets: dict = {}
    objects: dict = {}
    skipped: list[str] = []

    for node_id, node_data in graph.nodes(data=True):
        device_class = node_data.get("class") or node_data.get("type", "")
        position = node_data.get("position") or {"x": 0.0, "y": 0.0, "z": 0.0}

        result = resolve_asset_cfg(device_class, position)
        if result is None:
            skipped.append(f"{node_id} ({device_class})")
            continue

        category, cfg = result
        if category == "robot":
            articulated_assets[node_id] = cfg
        else:
            objects[node_id] = cfg

    if skipped:
        logger.warning("以下设备没有对应 Matterix 资产，已跳过：%s", skipped)

    cfg = DynamicEnvCfg()
    cfg.articulated_assets = articulated_assets
    cfg.objects = objects
    return cfg
```

---

### 3.3 工作流翻译器（`bridge/workflow_translator.py`）

**任务**：将 Uni-Lab-OS 的协议工作流动作列表翻译为 `matterix_sm` 的 `ActionBaseCfg` 序列。

**Uni-Lab-OS 工作流格式**（`workflow_translator` 的输入）：
```json
{
  "workflow": [
    {"action": "Transfer", "action_args": {"from_vessel": "beaker_A", "to_vessel": "beaker_B", "volume": 50.0}},
    {"action": "HeatChill", "action_args": {"vessel": "reactor", "temp": 60.0, "time": "30 min", "stir": true}},
    {"action": "Stir", "action_args": {"vessel": "reactor", "stir_speed": 500.0, "stir_time": 600.0}}
  ]
}
```

**翻译规则**（每条 Uni-Lab-OS 动作 → 若干 matterix_sm 原语动作）：

| Uni-Lab-OS action | matterix_sm 等价序列 |
|---|---|
| `Transfer` | `PickObjectCfg(from_vessel)` → `MoveToFrameCfg(to_vessel, "above_pour")` → `OpenGripperCfg` → `MoveRelativeCfg(return_home)` |
| `LiquidHandlerTransfer` | 与 Transfer 相同，但机器人换成液体处理机械臂 |
| `HeatChill` | `MoveToFrameCfg(vessel, "place")` → `OpenGripperCfg` （放置到加热板，设备状态由 Uni-Lab-OS 侧控制） |
| `AddSolid` | `PickObjectCfg(solid_container)` → `MoveToFrameCfg(target, "above_pour")` → `OpenGripperCfg` |
| `Centrifuge` / `Stir` | 无机械臂动作（纯设备操作，仿真中只验证时序） |

```python
# uni_lab_cad/bridge/workflow_translator.py

from __future__ import annotations
from dataclasses import dataclass

from matterix_sm import (
    PickObjectCfg,
    MoveToFrameCfg,
    MoveRelativeCfg,
    OpenGripperCfg,
    CloseGripperCfg,
)
from matterix_sm.action_base import ActionBaseCfg
from matterix_sm.robot_action_spaces import FRANKA_IK_ACTION_SPACE


@dataclass
class TranslationResult:
    actions: list[ActionBaseCfg]
    warnings: list[str]          # 翻译过程中产生的警告（如缺少帧定义）


# ─── 各动作翻译函数 ─────────────────────────────────────────────────────────

def _translate_transfer(args: dict, robot_name: str) -> TranslationResult:
    """
    Uni-Lab-OS Transfer → Pick source beaker → Move over target → Open gripper
    
    必须确保：
    - from_vessel 对应的 Matterix 资产定义了 "pre_grasp", "grasp", "post_grasp" 帧
    - to_vessel 对应的 Matterix 资产定义了 "above_pour" 帧（需在 asset_mapper 中添加）
    """
    from_vessel = args.get("from_vessel", "")
    to_vessel = args.get("to_vessel", "")
    warnings = []

    if not from_vessel or not to_vessel:
        warnings.append(f"Transfer 动作缺少 from_vessel 或 to_vessel 字段")

    actions = [
        PickObjectCfg(
            description=f"拾取 {from_vessel}",
            object=from_vessel,
            agent_assets=robot_name,
            action_space_info=FRANKA_IK_ACTION_SPACE,
        ),
        MoveToFrameCfg(
            description=f"移至 {to_vessel} 上方倾倒位",
            object=to_vessel,
            frame="above_pour",          # 需要在 target 资产配置的 frames 中定义
            agent_assets=robot_name,
            action_space_info=FRANKA_IK_ACTION_SPACE,
        ),
        OpenGripperCfg(
            description="松开/倾倒",
            agent_assets=robot_name,
        ),
        MoveRelativeCfg(
            description="回退安全距离",
            position_offset=(0.0, 0.0, 0.15),
            agent_assets=robot_name,
        ),
    ]
    return TranslationResult(actions=actions, warnings=warnings)


def _translate_add_solid(args: dict, robot_name: str) -> TranslationResult:
    """AddSolid → 拾取固体容器 → 移到目标上方 → 打开夹爪倾倒"""
    solid_source = args.get("solid", args.get("vessel", ""))
    target = args.get("to_vessel", "")
    actions = [
        PickObjectCfg(
            description=f"拾取固体容器 {solid_source}",
            object=solid_source,
            agent_assets=robot_name,
            action_space_info=FRANKA_IK_ACTION_SPACE,
        ),
        MoveToFrameCfg(
            description=f"移到 {target} 上方",
            object=target,
            frame="above_pour",
            agent_assets=robot_name,
            action_space_info=FRANKA_IK_ACTION_SPACE,
        ),
        OpenGripperCfg(agent_assets=robot_name),
        MoveRelativeCfg(position_offset=(0.0, 0.0, 0.2), agent_assets=robot_name),
    ]
    return TranslationResult(actions=actions, warnings=[])


def _translate_device_only(action_name: str) -> TranslationResult:
    """
    纯设备动作（HeatChill、Stir、Centrifuge 等），无机械臂动作。
    仿真中仅做时序标记，不产生机械臂运动。
    """
    return TranslationResult(
        actions=[],
        warnings=[f"{action_name} 是纯设备动作，仿真中跳过机械臂运动，仅验证时序"],
    )


# ─── 动作名称到翻译函数的路由表 ─────────────────────────────────────────────

_TRANSLATORS = {
    "Transfer":                  _translate_transfer,
    "LiquidHandlerTransfer":     _translate_transfer,
    "Add":                       _translate_transfer,
    "AddSolid":                  _translate_add_solid,
    "SolidDispenseAddPowderTube": _translate_add_solid,
    # 纯设备动作，不生成机械臂动作序列
    "HeatChill":     lambda a, r: _translate_device_only("HeatChill"),
    "HeatChillStart":lambda a, r: _translate_device_only("HeatChillStart"),
    "Stir":          lambda a, r: _translate_device_only("Stir"),
    "StartStir":     lambda a, r: _translate_device_only("StartStir"),
    "Centrifuge":    lambda a, r: _translate_device_only("Centrifuge"),
    "Evaporate":     lambda a, r: _translate_device_only("Evaporate"),
    "Wait":          lambda a, r: _translate_device_only("Wait"),
}


def translate_workflow(
    workflow_json: dict,
    robot_name: str = "robot",
) -> TranslationResult:
    """
    将 Uni-Lab-OS 协议工作流 JSON 翻译为 matterix_sm 动作序列。

    Args:
        workflow_json: {"workflow": [{"action": str, "action_args": dict}, ...]}
        robot_name:    目标机器人在 articulated_assets 中的键名。

    Returns:
        TranslationResult，含完整动作序列和所有警告。
    """
    steps: list[dict] = workflow_json.get("workflow", [])
    all_actions: list[ActionBaseCfg] = []
    all_warnings: list[str] = []

    for i, step in enumerate(steps):
        action_name = step.get("action", "")
        action_args = step.get("action_args", {})

        translator = _TRANSLATORS.get(action_name)
        if translator is None:
            all_warnings.append(
                f"步骤 {i+1}: 未知动作类型 '{action_name}'，已跳过"
            )
            continue

        result = translator(action_args, robot_name)
        all_actions.extend(result.actions)
        all_warnings.extend([f"步骤 {i+1} ({action_name}): {w}" for w in result.warnings])

    return TranslationResult(actions=all_actions, warnings=all_warnings)
```

---

## 四、第二阶段：Validation Engine（仿真验证引擎）

### 4.1 可达性检验（`sim/validators/reachability.py`）

**原理**：对场景中每个带 `frames` 的刚体对象，令机械臂逐一尝试移动到每个操作帧。如果 `StateMachine` 在 timeout 内到达目标，则标记为可达。

**依赖的 Matterix 内部接口**：
- `MatterixBaseEnv`（`matterix.envs`）
- `StateMachine`（`matterix_sm`）
- `MoveToFrameCfg`（`matterix_sm`）
- `SceneData.rigid_objects[name].frames`（`matterix_sm.scene_data`）

```python
# uni_lab_cad/sim/validators/reachability.py

from __future__ import annotations
from dataclasses import dataclass, field

import torch

from matterix.envs import MatterixBaseEnv, MatterixBaseEnvCfg
from matterix_sm import StateMachine, MoveToFrameCfg
from matterix_sm.robot_action_spaces import FRANKA_IK_ACTION_SPACE
from matterix_assets.asset_cfgs import MatterixRigidObjectCfg


@dataclass
class FrameReachability:
    robot: str
    object: str
    frame: str
    reachable: bool
    reached_pos_error: float | None   # 到达时的位置误差（米），None 表示超时
    timeout_steps: int                # 达到结论所用的仿真步数


@dataclass
class ReachabilityReport:
    results: list[FrameReachability] = field(default_factory=list)

    @property
    def all_reachable(self) -> bool:
        return all(r.reachable for r in self.results)

    def unreachable_frames(self) -> list[FrameReachability]:
        return [r for r in self.results if not r.reachable]

    def to_dict(self) -> dict:
        return {
            "all_reachable": self.all_reachable,
            "total_checks": len(self.results),
            "passed": sum(1 for r in self.results if r.reachable),
            "failed": len(self.unreachable_frames()),
            "details": [
                {
                    "robot": r.robot,
                    "object": r.object,
                    "frame": r.frame,
                    "reachable": r.reachable,
                    "pos_error_m": r.reached_pos_error,
                }
                for r in self.results
            ],
        }


def check_reachability(
    env_cfg: MatterixBaseEnvCfg,
    timeout_steps: int = 300,         # 每个目标帧最多跑 300 步（约 5 秒 @60Hz）
    position_threshold: float = 0.02, # 到达判定阈值（米）
) -> ReachabilityReport:
    """
    逐一检验场景中每个带 frames 的刚体对象的操作帧是否可达。

    注意：
    - 此函数会实际启动 Isaac Sim，需要 GPU 和 Isaac Sim 环境
    - 每次调用完成后会关闭 env，但 Isaac Sim 进程保持运行
    - 建议在独立进程中调用（通过 subprocess 或 multiprocessing）
    """
    # 收集所有需要检验的 (robot, object, frame) 三元组
    checks: list[tuple[str, str, str]] = []
    for robot_name in env_cfg.articulated_assets:
        for obj_name, obj_cfg in env_cfg.objects.items():
            if isinstance(obj_cfg, MatterixRigidObjectCfg) and obj_cfg.frames:
                for frame_name in obj_cfg.frames:
                    checks.append((robot_name, obj_name, frame_name))

    if not checks:
        return ReachabilityReport()

    # 启动仿真环境
    env = MatterixBaseEnv(env_cfg, render_mode=None)
    obs, _ = env.reset()

    report = ReachabilityReport()

    for robot_name, obj_name, frame_name in checks:
        # 重置场景
        obs, _ = env.reset()

        # 构建单步移动动作
        sm = StateMachine(
            num_envs=env_cfg.num_envs,
            dt=env_cfg.dt,
            device=str(obs["policy"].device) if hasattr(obs, "__getitem__") else "cuda",
        )
        move_action = MoveToFrameCfg(
            object=obj_name,
            frame=frame_name,
            agent_assets=robot_name,
            action_space_info=FRANKA_IK_ACTION_SPACE,
            timeout=timeout_steps * env_cfg.dt,
        )
        sm.set_action_sequence([move_action])

        # 运行直到完成或超时
        reached = False
        pos_error = None
        steps_used = 0

        for step in range(timeout_steps):
            action_dict = sm.step(obs)
            # action_dict 形如 {"robot": tensor(num_envs, action_dim)}
            action_tensor = list(action_dict.values())[0] if action_dict else torch.zeros(1, 8)
            obs, _, terminated, truncated, info = env.step(action_tensor)

            status_list = sm.get_status()
            steps_used = step + 1

            # 检查是否所有环境都完成了这个动作
            if status_list and all(s.get("done", False) for s in status_list):
                # 从 obs 中读取 EE 位置误差
                # obs 键格式："{robot_name}__{obs_name}"
                ee_pos_key = f"{robot_name}__ee_world_pos"
                frame_key = f"{obj_name}__{frame_name}_frame"
                if ee_pos_key in obs and frame_key in obs:
                    ee_pos = obs[ee_pos_key][:, :3]   # (num_envs, 3)
                    target_pos = obs[frame_key][:, :3]
                    pos_error = float((ee_pos - target_pos).norm(dim=-1).mean().item())
                    reached = pos_error < position_threshold
                else:
                    reached = True  # 无法计算误差时默认认为成功
                break

        report.results.append(FrameReachability(
            robot=robot_name,
            object=obj_name,
            frame=frame_name,
            reachable=reached,
            reached_pos_error=pos_error,
            timeout_steps=steps_used,
        ))

    env.close()
    return report
```

---

### 4.2 工作流碰撞检测（`sim/validators/collision.py`）

**原理**：将翻译后的 `matterix_sm` 动作序列实际执行一遍，记录每一步的碰撞接触力。

```python
# uni_lab_cad/sim/validators/collision.py

from __future__ import annotations
from dataclasses import dataclass, field

from matterix.envs import MatterixBaseEnv, MatterixBaseEnvCfg
from matterix_sm import StateMachine
from matterix_sm.action_base import ActionBaseCfg


@dataclass
class CollisionEvent:
    step: int
    object_a: str
    object_b: str
    contact_force_n: float   # 接触力（牛顿）


@dataclass
class CollisionReport:
    events: list[CollisionEvent] = field(default_factory=list)
    workflow_completed: bool = False
    completion_steps: int = 0

    @property
    def has_collision(self) -> bool:
        return len(self.events) > 0

    def to_dict(self) -> dict:
        return {
            "has_collision": self.has_collision,
            "collision_count": len(self.events),
            "workflow_completed": self.workflow_completed,
            "completion_steps": self.completion_steps,
            "events": [
                {
                    "step": e.step,
                    "object_a": e.object_a,
                    "object_b": e.object_b,
                    "contact_force_n": e.contact_force_n,
                }
                for e in self.events
            ],
        }


def check_collision(
    env_cfg: MatterixBaseEnvCfg,
    action_sequence: list[ActionBaseCfg],
    max_steps: int = 3000,
    collision_force_threshold: float = 5.0,  # 超过 5N 视为碰撞
) -> CollisionReport:
    """
    执行翻译后的 matterix_sm 动作序列，记录碰撞事件。

    Isaac Sim 的 contact sensor 需要在资产配置中通过
    `activate_contact_sensors=True` 启用，否则无法检测接触力。
    """
    import torch

    env = MatterixBaseEnv(env_cfg, render_mode=None)
    obs, _ = env.reset()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    sm = StateMachine(num_envs=env_cfg.num_envs, dt=env_cfg.dt, device=device)
    sm.set_action_sequence(action_sequence)

    report = CollisionReport()

    for step in range(max_steps):
        action_dict = sm.step(obs)
        if not action_dict:
            break

        action_tensor = list(action_dict.values())[0]
        obs, _, terminated, truncated, info = env.step(action_tensor)

        # ── 检查场景中注册了 contact sensor 的资产 ──
        # Isaac Lab 将接触力存入 obs["policy"] 的 force_data 条目
        for asset_name in env_cfg.articulated_assets:
            force_key = f"{asset_name}__force_data"
            if force_key in obs:
                force_tensor = obs[force_key]  # (num_envs, num_bodies, 3)
                max_force = float(force_tensor.norm(dim=-1).max().item())
                if max_force > collision_force_threshold:
                    report.events.append(CollisionEvent(
                        step=step,
                        object_a=asset_name,
                        object_b="unknown",
                        contact_force_n=max_force,
                    ))

        # 检查动作序列是否全部完成
        status_list = sm.get_status()
        if status_list and all(s.get("done", False) for s in status_list):
            report.workflow_completed = True
            report.completion_steps = step + 1
            break

        if terminated.any() or truncated.any():
            break

    env.close()
    return report
```

---

### 4.3 流体风险检测（`sim/validators/fluid_risk.py`）

**原理**：在启用 `FluidCfg` 粒子系统的环境中，检测流体粒子是否超出容器边界（溢出）。

**注意**：启用粒子系统后 Isaac Sim 强制切换 CPU Pipeline，速度会明显降低，仅在用户明确请求时启用。

```python
# uni_lab_cad/sim/validators/fluid_risk.py

from __future__ import annotations
from dataclasses import dataclass, field

from matterix.envs import MatterixBaseEnv, MatterixBaseEnvCfg
from matterix_sm import StateMachine
from matterix_sm.action_base import ActionBaseCfg
from matterix.particle_cfg import FluidCfg
from matterix_assets.asset_cfgs import MatterixRigidObjectCfg


@dataclass
class FluidSpillEvent:
    step: int
    fluid_name: str
    spilled_particles: int       # 溢出粒子数量
    spill_fraction: float        # 溢出比例（0~1）


@dataclass
class FluidRiskReport:
    events: list[FluidSpillEvent] = field(default_factory=list)

    @property
    def max_spill_fraction(self) -> float:
        return max((e.spill_fraction for e in self.events), default=0.0)

    def to_dict(self) -> dict:
        return {
            "spill_detected": len(self.events) > 0,
            "max_spill_fraction": self.max_spill_fraction,
            "events": [
                {
                    "step": e.step,
                    "fluid": e.fluid_name,
                    "spilled_particles": e.spilled_particles,
                    "spill_fraction": round(e.spill_fraction, 3),
                }
                for e in self.events
            ],
        }


def check_fluid_risk(
    env_cfg: MatterixBaseEnvCfg,
    action_sequence: list[ActionBaseCfg],
    max_steps: int = 500,              # 粒子仿真较慢，步数设小
    spill_z_threshold: float = -0.01,  # 低于地面 1cm 视为溢出
    check_interval: int = 50,          # 每 50 步检查一次
) -> FluidRiskReport:
    """
    启用流体粒子系统，检测工作流执行中的液体溢出风险。

    要求 env_cfg.particle_systems 中已配置 FluidCfg。
    如果没有粒子系统配置，返回空报告。
    """
    if not env_cfg.particle_systems:
        return FluidRiskReport()

    import torch

    env = MatterixBaseEnv(env_cfg, render_mode=None)
    obs, _ = env.reset()

    device = "cpu"  # 粒子系统强制 CPU
    sm = StateMachine(num_envs=env_cfg.num_envs, dt=env_cfg.dt, device=device)
    sm.set_action_sequence(action_sequence)

    report = FluidRiskReport()

    for step in range(max_steps):
        action_dict = sm.step(obs)
        if not action_dict:
            break
        action_tensor = list(action_dict.values())[0]
        obs, _, terminated, truncated, _ = env.step(action_tensor)

        # 每 check_interval 步检查一次粒子位置
        if step % check_interval == 0:
            for fluid_name, fluid_cfg in env_cfg.particle_systems.items():
                if not isinstance(fluid_cfg, FluidCfg):
                    continue
                # 通过 env 的粒子管理器获取当前粒子坐标
                # env.particle_manager 是 matterix 内部的 Particles 实例
                if hasattr(env, "particle_manager") and env.particle_manager:
                    particle_data = env.particle_manager.get_current_pos_vel(env_ids=[0])
                    if 0 in particle_data:
                        positions, _ = particle_data[0]
                        if positions is not None and len(positions) > 0:
                            total = len(positions)
                            spilled = int((positions[:, 2] < spill_z_threshold).sum().item())
                            if spilled > 0:
                                report.events.append(FluidSpillEvent(
                                    step=step,
                                    fluid_name=fluid_name,
                                    spilled_particles=spilled,
                                    spill_fraction=spilled / total,
                                ))

        status_list = sm.get_status()
        if status_list and all(s.get("done", False) for s in status_list):
            break
        if terminated.any() or truncated.any():
            break

    env.close()
    return report
```

---

## 五、第三阶段：API Layer（接口层）

### 5.1 Pydantic 模型（`api/models.py`）

```python
# uni_lab_cad/api/models.py

from pydantic import BaseModel, Field
from typing import Any


class CadValidateRequest(BaseModel):
    """POST /api/v1/cad/validate 的请求体"""
    graph_json: dict = Field(
        description="Uni-Lab-OS physical setup graph，格式为 node-link JSON (nodes + links)"
    )
    workflow_json: dict = Field(
        default={"workflow": []},
        description="Uni-Lab-OS 协议工作流，格式为 {'workflow': [{'action': str, 'action_args': dict}]}"
    )
    robot_name: str = Field(
        default="robot",
        description="工作流中执行机械臂动作的设备 ID（必须在 graph_json.nodes 中存在）"
    )
    checks: list[str] = Field(
        default=["reachability", "collision"],
        description="要执行的检查类型。可选值：reachability, collision, fluid_risk"
    )


class CadValidateResponse(BaseModel):
    """POST /api/v1/cad/validate 的响应体"""
    job_id: str
    status: str = "queued"   # queued | running | done | failed


class CadValidateResult(BaseModel):
    """GET /api/v1/cad/validate/{job_id} 的响应体"""
    job_id: str
    status: str              # running | done | failed
    warnings: list[str]
    reachability: dict | None = None
    collision: dict | None = None
    fluid_risk: dict | None = None
    error: str | None = None


class AssetInfo(BaseModel):
    name: str
    display_name: str
    category: str            # robot | container | static
    matterix_cfg_class: str  # 对应的 Matterix 配置类名
    has_usd: bool            # 是否有 USD 文件（False 表示使用占位资产）
    frames: list[str]        # 该资产定义的操控帧名称
```

---

### 5.2 FastAPI 路由（`api/cad_routes.py`）

此文件需要挂载到 Uni-Lab-OS 的现有 FastAPI 实例（`unilabos/app/web/server.py`）。

```python
# uni_lab_cad/api/cad_routes.py

from __future__ import annotations
import asyncio
import json
import tempfile
import os
from uuid import uuid4
from concurrent.futures import ProcessPoolExecutor

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .models import (
    CadValidateRequest,
    CadValidateResponse,
    CadValidateResult,
    AssetInfo,
)
from ..bridge.asset_mapper import DEVICE_CLASS_TO_MATTERIX_CFG, get_asset_category
from ..bridge.scene_builder import build_env_cfg_from_graph
from ..bridge.workflow_translator import translate_workflow

cad_router = APIRouter(prefix="/api/v1/cad", tags=["Uni-Lab CAD"])

# ─── 任务状态存储（生产环境建议换成 Redis） ─────────────────────────────────
_validation_jobs: dict[str, dict] = {}
_executor = ProcessPoolExecutor(max_workers=1)  # 一次只跑一个 Isaac Sim 进程


# ─── 核心验证逻辑（在独立进程中运行） ────────────────────────────────────────

def _run_validation_in_process(
    graph_json: dict,
    workflow_json: dict,
    robot_name: str,
    checks: list[str],
) -> dict:
    """
    在独立进程中运行 Matterix 仿真验证。
    返回序列化后的结果字典。
    
    此函数在 ProcessPoolExecutor 中运行，不能使用 async/await。
    Isaac Sim 必须在单独进程中初始化，不能与 FastAPI 共用同一进程。
    """
    result = {"warnings": [], "reachability": None, "collision": None, "fluid_risk": None}
    
    try:
        # 将 graph_json 写到临时文件（build_env_cfg_from_graph 需要文件路径）
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(graph_json, f)
            tmp_path = f.name

        try:
            env_cfg = build_env_cfg_from_graph(tmp_path, robot_override=None)
        finally:
            os.unlink(tmp_path)

        translation = translate_workflow(workflow_json, robot_name=robot_name)
        result["warnings"].extend(translation.warnings)

        if "reachability" in checks:
            from ..sim.validators.reachability import check_reachability
            report = check_reachability(env_cfg)
            result["reachability"] = report.to_dict()

        if "collision" in checks and translation.actions:
            from ..sim.validators.collision import check_collision
            report = check_collision(env_cfg, translation.actions)
            result["collision"] = report.to_dict()

        if "fluid_risk" in checks and translation.actions:
            from ..sim.validators.fluid_risk import check_fluid_risk
            report = check_fluid_risk(env_cfg, translation.actions)
            result["fluid_risk"] = report.to_dict()

    except Exception as e:
        result["error"] = str(e)

    return result


# ─── API 路由 ─────────────────────────────────────────────────────────────

@cad_router.post("/validate", response_model=CadValidateResponse)
async def submit_validation(req: CadValidateRequest):
    """
    提交一个实验室设计验证任务。
    Isaac Sim 初始化需要约 30-60 秒，任务在后台异步运行。
    通过 GET /api/v1/cad/validate/{job_id} 轮询结果。
    """
    job_id = str(uuid4())
    _validation_jobs[job_id] = {"status": "running", "result": None}

    loop = asyncio.get_event_loop()

    async def _run():
        try:
            result = await loop.run_in_executor(
                _executor,
                _run_validation_in_process,
                req.graph_json,
                req.workflow_json,
                req.robot_name,
                req.checks,
            )
            _validation_jobs[job_id] = {"status": "done", "result": result}
        except Exception as e:
            _validation_jobs[job_id] = {"status": "failed", "result": {"error": str(e)}}

    asyncio.create_task(_run())
    return CadValidateResponse(job_id=job_id)


@cad_router.get("/validate/{job_id}", response_model=CadValidateResult)
async def get_validation_result(job_id: str):
    """轮询验证任务结果"""
    job = _validation_jobs.get(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"detail": "任务不存在"})

    if job["status"] == "running":
        return CadValidateResult(job_id=job_id, status="running", warnings=[])

    result = job["result"] or {}
    return CadValidateResult(
        job_id=job_id,
        status=job["status"],
        warnings=result.get("warnings", []),
        reachability=result.get("reachability"),
        collision=result.get("collision"),
        fluid_risk=result.get("fluid_risk"),
        error=result.get("error"),
    )


@cad_router.get("/assets", response_model=list[AssetInfo])
async def list_available_assets():
    """
    列出 Matterix 资产库中所有可用资产，
    供前端 CAD 画布的资产面板展示。
    """
    assets = []
    for device_class, cfg in DEVICE_CLASS_TO_MATTERIX_CFG.items():
        if cfg is None:
            continue
        category = get_asset_category(cfg)
        frames = list(getattr(cfg, "frames", {}).keys())
        assets.append(AssetInfo(
            name=device_class,
            display_name=device_class.replace("_", " ").title(),
            category=category,
            matterix_cfg_class=type(cfg).__name__,
            has_usd=bool(getattr(cfg, "usd_path", None)),
            frames=frames,
        ))
    return assets


@cad_router.get("/assets/{device_class}/frames")
async def get_asset_frames(device_class: str):
    """返回指定资产的操控帧定义（用于前端渲染帧标注）"""
    cfg = DEVICE_CLASS_TO_MATTERIX_CFG.get(device_class)
    if cfg is None:
        return JSONResponse(status_code=404, content={"detail": "资产不存在"})
    return {"device_class": device_class, "frames": getattr(cfg, "frames", {})}
```

### 5.3 挂载到 Uni-Lab-OS（修改 `server.py`）

在 `unilabos/app/web/server.py` 中添加：

```python
# 在 create_app() 函数中添加以下内容：
from uni_lab_cad.api.cad_routes import cad_router

def create_app():
    app = FastAPI(title="Uni-Lab-OS", ...)
    app.include_router(cad_router)          # ← 新增
    # ... 其余路由
    return app
```

---

## 六、第四阶段：Web UI（前端）

### 6.1 三区布局设计

```
┌──────────────────────────────────────────────────────────────────┐
│  Uni-Lab CAD                                    [验证] [导出] [部署]│
├───────────────┬──────────────────────────────┬───────────────────┤
│  资产面板       │       CAD 画布（主区）          │   属性面板 / 结果    │
│               │                              │                   │
│ ▶ 机器人       │  ┌──────┐  ┌──────┐         │  选中：beaker_A    │
│   Franka      │  │robot │  │table │         │  ─────────────    │
│               │  └──┬───┘  └──────┘         │  类型: container  │
│ ▶ 桌子         │     │            ┌──────┐    │  帧:              │
│   Thorlabs    │     └────────────│beaker│    │   · pre_grasp    │
│   Seattle     │                  └──────┘    │   · grasp        │
│               │                              │   · post_grasp   │
│ ▶ 容器         │  工作流时序（底部）:            │                   │
│   Beaker 500  │  [Pick beaker_A][Move→B][Open]│  验证结果:        │
│               │                              │  ✅ 可达性: 通过   │
│               │                              │  ⚠️ 碰撞: 1 处    │
└───────────────┴──────────────────────────────┴───────────────────┘
```

### 6.2 关键 JavaScript 功能（`ui/static/cad.js`）

前端核心逻辑需实现以下功能：

```javascript
// uni_lab_cad/ui/static/cad.js

// 1. 从 Uni-Lab-OS 物理图谱 WebSocket 实时加载设备位置
// 使用现有的 /api/v1/ws/device_status WebSocket
const ws = new WebSocket(`ws://${location.host}/api/v1/ws/device_status`);
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "device_status") {
        updateDevicePositions(msg.data.device_status);
    }
};

// 2. 提交验证任务并轮询结果
async function runValidation(graphJson, workflowJson) {
    const resp = await fetch("/api/v1/cad/validate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            graph_json: graphJson,
            workflow_json: workflowJson,
            checks: ["reachability", "collision"],
        }),
    });
    const {job_id} = await resp.json();

    // 轮询，直到状态变为 done 或 failed
    return new Promise((resolve) => {
        const poll = setInterval(async () => {
            const r = await fetch(`/api/v1/cad/validate/${job_id}`).then(r => r.json());
            if (r.status === "done" || r.status === "failed") {
                clearInterval(poll);
                resolve(r);
            }
        }, 3000);  // 每 3 秒轮询一次
    });
}

// 3. 将验证结果可视化叠加到画布
function renderValidationOverlay(result) {
    if (result.reachability) {
        result.reachability.details.forEach(detail => {
            const deviceNode = findDeviceNode(detail.object);
            if (deviceNode) {
                deviceNode.setColor(detail.reachable ? "green" : "red");
                deviceNode.setTooltip(
                    detail.reachable
                        ? `可达（误差 ${(detail.pos_error_m * 100).toFixed(1)} cm）`
                        : `不可达：${detail.frame} 帧超出机械臂工作空间`
                );
            }
        });
    }
}
```

---

## 七、数据流全景图

以一次完整的"设计→验证→部署"为例，展示数据在各模块间的流转：

```
用户操作                          数据格式                    处理模块
────────────────────────────────────────────────────────────────────

① 导入实验室图谱
   stirteststation.json     →  node-link JSON              read_node_link_json()
   (nodes + links)              (id, class, position,       [unilabos/resources/graphio.py]
                                config, data)

② 构建仿真场景
   node-link JSON           →  DynamicEnvCfg               build_env_cfg_from_graph()
   (class="virtual_stirrer")    (articulated_assets={},     [bridge/scene_builder.py]
                                 objects={},
                                 particle_systems={})

③ 导入工作流
   {"workflow": [           →  ActionBaseCfg 序列           translate_workflow()
     {"action":"Transfer",      [PickObjectCfg,             [bridge/workflow_translator.py]
      "action_args":{...}}]}     MoveToFrameCfg,
                                 OpenGripperCfg, ...]

④ 运行可达性检验
   DynamicEnvCfg            →  ReachabilityReport           check_reachability()
   (objects 带 frames)          {results: [                 [sim/validators/reachability.py]
                                  {robot, object, frame,
                                   reachable, pos_error}]}

⑤ 运行碰撞检测
   EnvCfg + Action 序列     →  CollisionReport              check_collision()
                                {events: [{step,            [sim/validators/collision.py]
                                  object_a, contact_force}]}

⑥ 返回前端可视化
   Pydantic CadValidateResult → JSON                        FastAPI /api/v1/cad/validate
   → 画布颜色叠加 + 告警列表

⑦ 一键部署到真实实验室
   验证通过的 workflow_json  →  Uni-Lab-OS 工作流 API        POST /api/v1/workflow/upload
                                (Bohrium 云端执行)           [unilabos/workflow/wf_utils.py]
```

---

## 八、已知限制与 TODO

### 8.1 Matterix 暂未开源的能力（需等待或自行实现）

| 功能 | 状态 | 影响 |
|---|---|---|
| 设备功能仿真（加热板、离心机）| 未开源 | `HeatChill`、`Stir` 等只能验证时序，不能验证设备行为 |
| 化学反应动力学 | 未开源 | 无法仿真反应进度 |
| OT-2 移液机器人 | 未开源 | 液体处理机械臂目前用 Franka 占位 |

### 8.2 需要扩展的 Matterix 资产

下列 Uni-Lab-OS 设备类型目前没有对应的 USD 资产，需要自行建模并添加到 `matterix_assets`：

| 设备类型 | 优先级 | 建议来源 |
|---|---|---|
| 加热搅拌板（heaterstirrer）| 高 | Thorlabs / GrabCAD 免费模型 |
| 微量移液枪头（tip）| 高 | 简单圆柱体 USD |
| 96 孔板（well_plate）| 高 | OpenBiofab 开源模型 |
| HPLC 系统 | 中 | 仪器厂商 3D 文件 |
| 离心机 | 中 | GrabCAD |

添加新资产步骤：
1. 将 USD 文件放入 `$MATTERIX_PATH/source/matterix_assets/data/` 对应子目录
2. 在 `matterix_assets` 包中创建对应的 `MatterixStaticObjectCfg` 或 `MatterixRigidObjectCfg` 子类
3. 在 `DEVICE_CLASS_TO_MATTERIX_CFG` 中添加映射

### 8.3 坐标系对齐

Uni-Lab-OS 的画布坐标（2D 像素）与 Isaac Sim 的世界坐标（3D 米）需要仔细对齐：

- `CANVAS_TO_WORLD_SCALE = 0.01`（初始值，需根据实际画布标定）
- `env_floor_z`（桌面高度）需与实际实验桌高度匹配（Thorlabs 桌高约 0.9 m）
- 坐标原点：建议将机械臂 base link 设为画布坐标原点

### 8.4 Isaac Sim 进程隔离

Isaac Sim 必须在**独立进程**中运行，不能与 FastAPI 共用同一 Python 进程：

- 使用 `ProcessPoolExecutor`（本文档方案）
- 或使用 `subprocess.Popen` 调用独立脚本
- 或使用 Omniverse Extension 方式，通过 HTTP/RPC 与 FastAPI 通信

---

## 九、分阶段开发计划

```
Week 1-2：Bridge Layer
├── 实现 asset_mapper.py：完成 15+ 设备类的映射
├── 实现 scene_builder.py：能正确读取 stirteststation.json
└── 实现 workflow_translator.py：支持 Transfer、HeatChill、Stir

Week 3-4：Validation Engine
├── 实现 reachability.py：可检验任意 (robot, object, frame) 三元组
├── 实现 collision.py：能检测接触力超阈值事件
└── 端到端测试：使用 Matterix-Test-Beakers-Franka-v1 任务验证

Week 5-6：API Layer
├── 实现 cad_routes.py 全部路由
├── 挂载到 Uni-Lab-OS FastAPI 实例
└── 用 stirteststation.json + 简单 Transfer 工作流做集成测试

Week 7-8：Web UI
├── 实现 CAD 画布（基于 React Flow 或 D3.js）
├── 资产面板 + 拖拽放置
└── 验证结果可视化叠加

Week 9+：资产扩充 + 优化
├── 添加加热搅拌板、96 孔板 USD 资产
├── 性能优化（预热 Isaac Sim 进程、批量检验）
└── 与 Bohrium 云端的一键部署集成
```

---

## 十、快速开始（最小可验证版本）

完成 Bridge Layer 后，可以用以下命令验证整个链路：

```python
# scripts/test_cad_bridge.py
# 在 conda matterix 环境中运行（需要 Isaac Sim）

from uni_lab_cad.bridge.scene_builder import build_env_cfg_from_graph
from uni_lab_cad.bridge.workflow_translator import translate_workflow
from uni_lab_cad.sim.validators.reachability import check_reachability

# 使用 Uni-Lab-OS 自带的测试图谱
GRAPH_JSON = "unilabos/test/experiments/mock_protocol/stirteststation.json"
WORKFLOW_JSON = {
    "workflow": [
        {"action": "Transfer", "action_args": {
            "from_vessel": "reactor",
            "to_vessel": "reactor",
            "volume": 50.0,
        }}
    ]
}

# Step 1: 构建仿真场景
env_cfg = build_env_cfg_from_graph(GRAPH_JSON)
print(f"场景包含 {len(env_cfg.articulated_assets)} 个机器人, {len(env_cfg.objects)} 个对象")

# Step 2: 翻译工作流
translation = translate_workflow(WORKFLOW_JSON, robot_name="robot")
print(f"翻译出 {len(translation.actions)} 个动作，{len(translation.warnings)} 个警告")
for w in translation.warnings:
    print(f"  ⚠️  {w}")

# Step 3: 可达性检验（会启动 Isaac Sim，耗时约 1-2 分钟）
print("正在启动 Isaac Sim 进行可达性检验...")
report = check_reachability(env_cfg)
print(f"可达性检验完成：{report.to_dict()}")
```

运行方式：
```bash
conda activate matterix
cd /path/to/Uni-Lab-OS
python scripts/test_cad_bridge.py
```

---

*文档生成日期：2026-03-14*  
*基于 Matterix（matterix_sm、matterix_assets、matterix_tasks、matterix 四个包的实际源码）*  
*与 Uni-Lab-OS（unilabos/resources/graphio.py、unilabos/registry/、unilabos/ros/ 等实际源码）整理*
