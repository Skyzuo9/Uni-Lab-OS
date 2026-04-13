# Matterix 仓库介绍

## 项目定位

**Matterix** 是一个**多尺度、GPU 加速的化学实验室机器人仿真框架**，用于构建高保真化学实验室数字孪生，加速实验工作流开发。

- **开源协议**：BSD-3-Clause（允许商用、允许闭源修改，保留版权声明即可）
- **依赖平台**：NVIDIA Isaac Sim 5.0 + Isaac Lab 2.3
- **支持系统**：Linux 64 / Windows 64
- **Python 版本**：3.11

---

## 核心能力

| 能力 | 说明 |
|------|------|
| 多尺度物理仿真 | 刚体、软体、液体（流体粒子）、粉末（固体粒子）、热传导（规划中）、化学动力学（规划中） |
| 数字孪生设计 | 湿实验室场景，可快速搭建含多机械臂、多器皿的环境 |
| 工作流自动化 | 层级式状态机编排机器人动作序列，极低代码量实现 Pick/Place 等任务 |
| RL/IL 支持 | 兼容 RL Games、RSL-RL、SKRL、Stable-Baselines3；内置 HDF5 数据录制 |
| 真实机器人部署 | 通过 ROS2 接口将仿真工作流部署到真实机器人 |

---

## 四个核心包

```
source/
├── matterix_sm/         # 状态机：动作编排（可独立于 Isaac Lab 使用）
├── matterix_assets/     # 资产库：机器人、器皿、基础设施的 USD + 配置
├── matterix_tasks/      # 任务/环境定义（RL 训练、工作流测试）
└── matterix/            # 核心框架：粒子系统、MDP 环境、观测管理器
```

---

## 资产系统

### 三类资产基类

| 基类 | 用途 | 对应 Isaac Lab 类 |
|------|------|------------------|
| `MatterixRigidObjectCfg` | 刚体可抓取物（如烧杯） | `RigidObjectCfg` |
| `MatterixStaticObjectCfg` | 静态场景物体（如桌子） | `AssetBaseCfg` |
| `MatterixArticulationCfg` | 关节型机构（如机械臂） | `ArticulationCfg` |

### 当前已开源的具体资产

**实验室器皿（Labware）**

| 配置类 | 说明 |
|--------|------|
| `BEAKER_500ML_CFG` | 500 mL 硼硅玻璃烧杯 |
| `BEAKER_500ML_INST_CFG` | 同上，可多实例化版本 |

**机器人（Robots）**

| 配置类 | 说明 |
|--------|------|
| `FRANKA_PANDA_CFG` | Franka Panda（标准 PD） |
| `FRANKA_PANDA_HIGH_PD_CFG` | Franka Panda（高刚度 PD） |
| `FRANKA_PANDA_HIGH_PD_IK_CFG` | Franka Panda（高 PD + 笛卡尔 IK） |
| `FRANKA_ROBOTI2F85_INST_CFG` | Franka + Robotiq 2F85 夹爪 |
| `FRANKA_ROBOTIQ2F85_INST_HIGH_PD_CFG` | 同上，高 PD |

**基础设施（Infrastructure）**

| 配置类 | 说明 |
|--------|------|
| `TABLE_THORLABS_75X90_INST_Cfg` | Thorlabs 75×90 cm 实验桌 |
| `TABLE_THORLABS_75X90_Cfg` | 同上，非实例化版 |
| `TABLE_SEATTLE_INST_Cfg` | Seattle 实验桌（来自 Isaac Nucleus） |

### 操控帧（Frames）—— 资产的语义核心

每个资产可定义**命名坐标系**，在物体自身坐标系下描述操控位置：

```python
frames = {
    "pre_grasp": (0.0, 0.0, 0.04),   # 接近点（高 4cm）
    "grasp":     (0.0, 0.0, 0.0),    # 夹取点
    "post_grasp":(0.0, 0.0, 0.05),   # 抬升点（高 5cm）
}
```

状态机通过 `(object名, frame名)` 引用目标位姿，实现语义化操控，无需硬编码坐标。

### 资产文件格式与位置

| 格式 | 说明 |
|------|------|
| `.usd` | USD 二进制场景文件 |
| `.usda` | USD ASCII 文本文件（便于版本管理） |

实际模型文件存放在 `source/matterix_assets/data/`（Git 子模块，需单独拉取）：

```
data/
├── labware/beaker500ml/          # 烧杯 USD
├── robots/franka/franka-robotiq85/  # Franka+Robotiq 机器人 USD
└── infrastructure/tables/        # 桌子 USD
```

---

## 状态机与工作流

### 层级结构

```
StateMachine
└── CompositionalAction（如 PickObject）
    └── PrimitiveAction（如 MoveToFrame / OpenGripper / CloseGripper）
```

### 已实现的原语动作

| 动作 | 说明 |
|------|------|
| `Move` / `MoveToPose` | 移动末端到绝对位姿 |
| `MoveToFrame` | 移动末端到物体的命名帧 |
| `MoveRelative` | 相对当前位置移动 |
| `OpenGripper` / `CloseGripper` | 夹爪控制 |

### 已实现的组合动作

| 动作 | 内部序列 |
|------|---------|
| `PickObject` | OpenGripper → MoveToFrame(pre_grasp) → MoveToFrame(grasp) → CloseGripper → MoveRelative(post_grasp) |

---

## 粒子系统

| 系统 | 配置类 | 关键参数 |
|------|--------|---------|
| 流体 | `FluidCfg` / `FineGrainedFluidCfg` | 粘度、表面张力、内聚力、透明材质、等值面渲染 |
| 粉末 | `PowderCfg` / `FinePowderCfg` | 摩擦、粘度、不透明材质 |

> 注意：粒子系统启用后强制使用 CPU，不支持 GPU Pipeline，仿真速度会明显下降。

---

## 开源能力边界

### 完全支持

- 搭建多机器人 + 多器皿 + 多桌子的实验室仿真场景
- 编排任意工作流（Pick/Place/Move 等）
- 并行多环境向量化执行（GPU 加速）
- 流体 / 粉末粒子系统仿真
- HDF5 数据录制（用于模仿学习）
- RL 训练（4 大主流框架）
- 自定义新资产（提供 USD + 继承配置基类）

### 暂未开源 / 不支持

| 能力 | 状态 |
|------|------|
| 化学反应动力学 | README 提及，代码中未实现 |
| 热传导仿真 | README 提及，代码中未实现 |
| 设备功能（离心机、加热板等） | 未开源 |
| OT-2 移液机器人完整配置 | 仅文档提及，配置类未写 |
| RL Reward 函数 | 框架支持，具体奖励需用户自定义 |

---

## BSD-3-Clause 协议要点

| 行为 | 是否允许 |
|------|---------|
| 商业使用 | ✅ 允许 |
| 修改代码 | ✅ 允许 |
| 闭源分发 | ✅ 允许 |
| 去掉版权声明 | ❌ 不允许 |
| 用原项目名背书自己产品 | ❌ 不允许 |
| 出问题找原作者索赔 | ❌ 不支持（AS IS） |
