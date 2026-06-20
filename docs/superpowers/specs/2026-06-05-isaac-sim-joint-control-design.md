# Isaac Sim 内置关节控制面板设计

## 背景

目标是在 UniLabOS edge 端以 managed 模式启动 Isaac Sim 后，直接在 Isaac Sim 窗口内显示一个手动控制面板，用于控制 `/home/ubuntu/lab4090/assets/horizon_v2_import/isaac/MVPpkushengke.usd` 中的可动关节。

本设计采用推荐路线：Isaac worker 内置 UI，并让 UI 和 RPC 共用同一套控制核心。这样既能在 RustDesk 里直接拖拽控制，也能保留 UniLabOS edge / workflow 后续通过 RPC 调用同一能力的路径。

## 当前事实

当前 Phase A managed 模式已经具备：

- `unilabos.app.main` 可通过 `--isaac_managed` 启动 Isaac worker。
- Isaac worker 可加载 USD 场景并提供 `/health`、`/rpc`。
- 当前 worker 已支持 `get_observation`、`set_command`、`get_joint_states`、`render` 等基础 RPC。
- 当前 worker 里的 `set_command` 只是记录 joint state，不会真正驱动 USD/PhysX 关节。

已在 4090 上扫描到 `MVPpkushengke.usd` 的可控关节如下：

| Joint | Type | UI 控制 |
| --- | --- | --- |
| `/World/HOR_Horizon_V2_1_2508_13/joints/arm0_joint` | `PhysicsPrismaticJoint` | slider/input |
| `/World/HOR_Horizon_V2_1_2508_13/joints/arm1_joint` | `PhysicsRevoluteJoint` | slider/input |
| `/World/HOR_Horizon_V2_1_2508_13/joints/arm2_joint` | `PhysicsRevoluteJoint` | slider/input |
| `/World/HOR_Horizon_V2_1_2508_13/joints/arm3_joint` | `PhysicsRevoluteJoint` | slider/input |
| `/World/HOR_Horizon_V2_1_2508_13/joints/left_joint` | `PhysicsPrismaticJoint` | slider/input |
| `/World/HOR_Horizon_V2_1_2508_13/joints/right_joint` | `PhysicsPrismaticJoint` | slider/input |
| `/World/HOR_Horizon_V2_1_2508_13/joints/gate_joint` | `PhysicsRevoluteJoint` | slider/input |

固定关节不进入第一版控制面板：

- `arm_joint`
- `box_joint`
- `root_joint`

## 用户目标

第一版需要同时实现三件事：

1. 改变 Isaac Sim 中 USD 关节位置。
2. 对目标动作做轨迹规划。
3. 在 Isaac 内做碰撞安全检查；不安全则拒绝执行。

用户明确不希望第一版用浏览器 Web UI，控制窗口应在 Isaac Sim 内部。

## 范围

### 第一版包含

- Isaac Sim 内置窗口：`UniLab Joint Control`。
- 自动识别或配置目标 USD 中的可动关节。
- 每个可动关节提供 slider、数值输入、当前值、目标值。
- `Plan`：从当前关节位置到目标位置生成插值轨迹。
- `Check`：在 Isaac 中逐步预演轨迹并检测碰撞。
- `Execute`：只有安全检查通过后才执行轨迹。
- `Stop`：中断当前执行。
- `Reset Targets`：目标值恢复到当前关节值。
- RPC 提供与 UI 共用的能力，供 UniLabOS edge 后续调用。

### 第一版不包含

- 自动避障重规划。
- 真实硬件控制。
- 复杂任务编排或实验协议绑定。
- 云端可视化拖拽界面。
- 多机器人、多 USD 场景的通用资产管理。

## 总体架构

```text
UniLabOS edge
  -> managed Isaac worker
       -> IsaacController
       -> JointControlService
            -> JointRegistry
            -> TrajectoryPlanner
            -> CollisionChecker
            -> TrajectoryExecutor
       -> Isaac 内置 UI: UniLab Joint Control
       -> HTTP RPC: /rpc
```

核心原则：

- UI 不直接操作 USD 关节，而是调用 `JointControlService`。
- RPC 也调用同一个 `JointControlService`。
- 所有安全检查在 `JointControlService` 内统一执行。
- 如果碰撞检测能力不可用，系统必须失败关闭，不允许默认放行。

## 组件设计

### JointRegistry

职责：

- 从当前 USD stage 中发现可控关节。
- 过滤固定关节。
- 提取 joint path、joint name、joint type、drive axis、当前 target、单位、软限位。
- 对 `MVPpkushengke.usd` 提供显式 allowlist，避免把无关 joint 放进 UI。

第一版默认 allowlist：

```python
[
    "arm0_joint",
    "arm1_joint",
    "arm2_joint",
    "arm3_joint",
    "left_joint",
    "right_joint",
    "gate_joint",
]
```

单位策略：

- UI 显示使用直觉单位：
  - Revolute: degree
  - Prismatic: scene unit，默认按 meter 标注
- RPC 内部保存 `unit` 字段，避免调用方猜测。
- 4090 实测显示，`MVPpkushengke.usd` 中 revolute joint 的 `physics:lowerLimit` / `physics:upperLimit`
  是角度制。例如 `arm1_joint` 的限位为 `-114.591552734375` 到 `114.591552734375`，
  对应约 `-2 rad` 到 `2 rad`；`gate_joint` 上限为 `89.9543685913086`，对应约 `90 deg`。
- 因此第一版对这个 USD 的写入策略是：
  - Revolute UI 输入 degree，直接写入 angular DriveAPI `targetPosition`。
  - Prismatic UI 输入 meter，直接写入 linear DriveAPI `targetPosition`。
  - 如果后续使用 Isaac articulation runtime API 读取到 radians，则只在该 API 边界做 rad/deg 转换，
    不改变 UI/RPC 的外部单位。

需要加入一个 4090 单位 smoke：

1. 打开 `MVPpkushengke.usd`。
2. 对 `arm1_joint` 写入 `targetPosition=10.0`。
3. 推进仿真若干步。
4. 断言 USD drive target 仍为 `10.0`，并且 `arm1_Link` 位姿发生可观测变化。
5. 重置为 `0.0`。

### JointControlService

职责：

- 提供关节状态查询。
- 接收目标关节位置。
- 调用轨迹规划。
- 调用碰撞检查。
- 调用轨迹执行。
- 维护当前状态、最后一次计划、最后一次失败原因。

核心方法：

```python
list_joints() -> list[JointSpec]
get_joint_state() -> JointState
plan_joint_targets(targets: dict[str, float], options: PlanOptions) -> TrajectoryPlan
check_trajectory(plan_id: str) -> CollisionCheckResult
execute_trajectory(plan_id: str) -> ExecutionResult
stop_motion() -> None
```

### TrajectoryPlanner

第一版采用线性插值规划：

- 输入：当前关节位置、目标关节位置、最大步长、最大速度、最大轨迹步数。
- 输出：离散 waypoint 列表。
- 每个 waypoint 是 `{joint_name: target_value}`。

默认约束：

- Revolute joint 每步最大角度变化可配置，默认保守。
- Prismatic joint 每步最大线性变化可配置，默认保守。
- 超过最大步数时拒绝计划，而不是生成过长阻塞任务。

这不是自动避障规划器；它负责生成一条待检查的候选轨迹。

### CollisionChecker

第一版为 B 版安全能力：Isaac 碰撞检测版。

4090 上的 Isaac Sim 5.1 API 探针结果：

- `omni.physx.get_physx_simulation_interface()` 可用。
- `IPhysxSimulation` 暴露：
  - `get_contact_report`
  - `get_full_contact_report`
  - `subscribe_contact_report_events`
  - `subscribe_full_contact_report_events`
- `omni.physx.get_physx_scene_query_interface()` 可用，暴露 `overlap_*`、`raycast_*`、`sweep_*`
  查询方法。

第一版采用 contact report 作为主路径，scene query 作为补充诊断路径：

- 主路径：在检查和执行期间订阅 contact report，逐步推进仿真后读取 contact event。
- 补充路径：在需要定位或验证几何重叠时使用 scene query 的 overlap/sweep 方法。
- 如果 contact report 初始化失败、订阅失败或返回格式无法解析，按 `collision_check_unavailable` 处理，
  不允许执行轨迹。

流程：

1. 保存当前关节 drive target 和仿真状态。
2. 对轨迹中的每个 waypoint：
   - 写入关节 drive target。
   - 推进 Isaac 仿真若干小步。
   - 查询 PhysX/Isaac 接触信息。
   - 判断是否存在不允许的接触。
3. 如果发现碰撞，立即停止检查并返回：
   - `safe=false`
   - 碰撞 waypoint index
   - 相关 body / prim path
   - 失败原因
4. 检查结束后恢复到检查前状态。

安全策略：

- 不允许静默忽略碰撞 API 异常。
- 如果无法读取碰撞结果，返回 `collision_check_unavailable`。
- 第一版允许配置忽略列表，例如固定底座自接触、已知合理接触。
- 默认策略偏保守，宁可拒绝，也不误放行。

### TrajectoryExecutor

职责：

- 只执行已经通过检查的 `plan_id`。
- 按 waypoint 顺序写入 joint drive target。
- 每步推进 Isaac 仿真。
- 更新 UI 状态。
- 支持中断。

执行规则：

- 未检查的计划不能执行。
- 检查失败的计划不能执行。
- 执行中如果出现异常或新增碰撞，立即停止并返回失败。
- 同一时间只允许一个执行任务。

### Isaac 内置 UI

窗口名称：`UniLab Joint Control`

第一版布局：

```text
Scene: MVPpkushengke.usd
Status: Ready / Planning / Checking / Executing / Failed

[Joint table]
Joint        Current     Target      Slider        Type
arm0_joint   0.000       0.120       [------]      prismatic
arm1_joint   0.0 deg     20.0 deg    [------]      revolute
gate_joint   0.0 deg     15.0 deg    [------]      revolute

[Plan] [Check] [Execute] [Stop] [Reset Targets]

Last result:
safe=false, collision at step 12, prim=/World/HOR_Horizon_V2_1_2508_13/link_arm3
```

UI 行为：

- 拖动 slider 只改变目标值，不直接执行。
- 点击 `Plan` 生成轨迹。
- 点击 `Check` 执行碰撞检查。
- 只有 `Check` 通过后 `Execute` 按钮可用。
- 失败原因直接显示在面板中。

### RPC 设计

worker `/rpc` 新增操作：

```json
{"op": "list_joint_controls", "args": {}}
{"op": "get_joint_control_state", "args": {}}
{"op": "plan_joint_targets", "args": {"targets": {"arm1_joint": 20.0}, "options": {}}}
{"op": "check_joint_plan", "args": {"plan_id": "plan_20260605_0001" }}
{"op": "execute_joint_plan", "args": {"plan_id": "plan_20260605_0001" }}
{"op": "stop_joint_motion", "args": {}}
```

返回值保留结构化错误：

```json
{
  "ok": false,
  "code": "collision_detected",
  "message": "Trajectory collides at waypoint 12",
  "details": {
    "waypoint_index": 12,
    "joint_targets": {"arm1_joint": 18.0},
    "contacts": [
      {
        "body0": "/World/HOR_Horizon_V2_1_2508_13/link_arm3",
        "body1": "/World/HOR_Horizon_V2_1_2508_13/base"
      }
    ]
  }
}
```

### UniLabOS edge 集成

edge 不直接负责 UI 或碰撞检查。edge 的职责仍是：

- managed 启动 Isaac worker。
- 把 `physics_endpoint` 指向 worker。
- 后续可通过 `IsaacBridgeBackend` 调用 joint RPC。

需要扩展 `IsaacBridgeBackend`：

```python
list_joint_controls() -> list[dict]
get_joint_control_state() -> dict
plan_joint_targets(targets: dict[str, float], options: dict | None = None) -> dict
check_joint_plan(plan_id: str) -> dict
execute_joint_plan(plan_id: str) -> dict
stop_joint_motion()
```

这样后续 UniLabOS workflow 可以复用同一条控制链路。

## 错误处理

常见错误和处理：

| 错误 | 行为 |
| --- | --- |
| 目标 joint 不存在 | 拒绝计划 |
| 目标超出限位 | 拒绝计划 |
| 碰撞检查 API 不可用 | 拒绝执行 |
| 轨迹中途碰撞 | 停止检查或执行 |
| 正在执行时再次执行 | 返回 busy |
| Isaac stage 未加载 | UI 显示 not ready，RPC 返回 stage_not_loaded |
| worker 关闭 | edge 由 managed 清理进程 |

## 测试策略

### 本地单元测试

不依赖 Isaac：

- joint allowlist 过滤。
- 轨迹插值。
- 限位检查。
- plan/check/execute 状态机。
- RPC 编解码。
- `IsaacBridgeBackend` 新方法。

### Isaac worker fake 测试

使用 fake controller：

- UI 不直接测渲染，只测 service 行为。
- 碰撞检查 fake 返回 safe/unsafe。
- 确认 unsafe plan 不能 execute。
- 确认 stop 能中断执行状态。

### 4090 集成测试

在 Ubuntu 4090 上运行：

- managed 启动 non-headless Isaac worker。
- 打开 `MVPpkushengke.usd`。
- `/health` 返回 OK。
- `list_joint_controls` 返回 7 个可控 joint。
- 给一个小角度目标，plan/check/execute 成功。
- 给一个人工构造的不安全目标，check 返回失败。
- RustDesk 中可见 `UniLab Joint Control` 面板。

## 分阶段实施

### 阶段 1: JointControlService 骨架

- 添加 joint spec/state/plan 数据模型。
- 添加 joint discovery allowlist。
- 添加 trajectory planner。
- 添加 fake collision checker。
- 添加 worker RPC。

验收：

- 测试不依赖 Isaac 全部通过。
- 通过 RPC 能列出 joint、生成 plan、拒绝未检查执行。

### 阶段 2: Isaac 真实关节写入

- 在 worker 内通过 USD/Isaac API 读取 joint drive。
- 写入 `targetPosition`。
- 确认 slider 目标能改变 Isaac 中的机构姿态。

验收：

- 在 4090 上可通过 RPC 改变一个小幅关节目标。
- `get_joint_control_state` 能看到当前值变化。

### 阶段 3: Isaac 碰撞检查

- 实现逐 waypoint 预演。
- 接入 PhysX/Isaac 接触读取。
- 增加忽略列表。
- 检查失败时恢复原状态。

验收：

- 安全目标通过。
- 不安全目标拒绝并给出结构化错误。
- 碰撞 API 不可用时 fail closed。

### 阶段 4: Isaac 内置 UI

- 添加 `UniLab Joint Control` 窗口。
- 接入 JointControlService。
- 实现 slider、Plan、Check、Execute、Stop、Reset。

验收：

- managed non-headless 启动后，Isaac Sim 内可见面板。
- 用户可通过 RustDesk 拖动目标并执行安全轨迹。

## 启动方式

第一版继续沿用 managed 启动命令，只新增一个开关以启用内置控制面板：

```bash
python -m unilabos.app.main \
  --physics isaac \
  --physics_scene /home/ubuntu/lab4090/assets/horizon_v2_import/isaac/MVPpkushengke.usd \
  --isaac_managed \
  --no_isaac_headless \
  --isaac_joint_control_ui
```

后续可加：

```bash
--isaac_joint_allowlist docs/demo/mvppkushengke_joints.yaml
--isaac_collision_ignore docs/demo/mvppkushengke_collision_ignore.yaml
```

## 验收定义

认为第一版完成，需要同时满足：

- UniLabOS edge 能 managed 启动 Isaac Sim GUI。
- Isaac Sim 内显示 `UniLab Joint Control` 面板。
- 面板列出 7 个目标关节。
- 用户拖动目标不会直接运动，必须经过 Plan/Check/Execute。
- 安全轨迹能执行并改变关节位置。
- 碰撞轨迹不能执行，并显示失败原因。
- RPC 与 UI 共用同一套控制核心。
- 测试覆盖 service、RPC、bridge 和 4090 smoke。

## 未决风险

- `MVPpkushengke.usd` 的 drive targetPosition 单位已完成初步实测：revolute 采用 degree，
  prismatic 采用 meter。剩余工作是把该结论固化为 4090 smoke 测试，避免后续 Isaac API 调用边界误用 radians。
- Isaac/PhysX 接触读取 API 已完成初步探针：优先使用 `IPhysxSimulation` 的 contact report API，
  scene query 作为补充。剩余工作是在真实轨迹检查中验证 contact event 的 body/prim path 映射。
- 多个 Isaac worker 同时运行会争用 GPU 和 Kit 缓存，集成测试应使用独立端口并避免同时开多个重负载 GUI。
- 用户已确认碰撞体资产完整，因此资产完整性不再作为第一版风险；实现仍保留 fail-closed 策略。
