# 阶段二——已有代码基础汇总

> 本文档汇总 `uni-lab-3D-phase2.md` 中标注为 **[已有]** 或 **"已有初步实现"** 的功能模块在 Uni-Lab-OS 代码库中的具体位置。
>
> 生成时间：2026-03-17

---

## 目录

1. [BaseROS2DeviceNode + PropertyPublisher（设备状态发布）](#1-baseros2devicenode--propertypublisher)
2. [unilabos_msgs 消息体系（85 个 Action + Msg + Srv）](#2-unilabos_msgs-消息体系)
3. [HostNode + send_goal（ROS2 Action 调度）](#3-hostnode--send_goal)
4. [FastAPI 工作流接口（/api/job/add、/ws/device_status）](#4-fastapi-工作流接口)
5. [ResourceMeshManager + PlanningScene（耗材附着/释放初步实现）](#5-resourcemeshmanager--planningscene)
6. [MoveitInterface — 业务逻辑封装层（pick/place、FK/IK、资源 TF）](#6-moveitinterface--业务逻辑封装层)
7. [MoveIt2 底层 Python 接口（运动规划、碰撞管理、轨迹执行）](#7-moveit2-底层-python-接口)
8. [ResourceVisualization（动态 URDF/SRDF 生成、MoveIt2 全栈启动）](#8-resourcevisualization)
9. [完整数据链路示意](#9-完整数据链路示意)

---

## 1. BaseROS2DeviceNode + PropertyPublisher

> **文档原文**：*BaseROS2DeviceNode 的 PropertyPublisher 已在持续发布设备状态（如 arm_pose）到 ROS Topic [已有]*

### 文件位置

```
unilabos/ros/nodes/base_device_node.py
```

### PropertyPublisher 类（第 175–248 行）

定时从设备驱动读取属性值，发布到 ROS2 Topic。

```python
# 第 175-204 行
class PropertyPublisher:
    def __init__(self, node, name, get_method, msg_type, initial_period=5.0, ...):
        self.publisher_ = node.create_publisher(msg_type, f"{name}", qos)
        self.timer = node.create_timer(self.timer_period, self.publish_property)

    # 第 232-241 行：定时回调，读取属性并发布
    def publish_property(self):
        value = self.get_property()       # 调用 get_method() 从驱动获取值
        if value is not None:
            msg = convert_to_ros_msg(self.msg_type, value)
            self.publisher_.publish(msg)  # 发布到 ROS Topic
```

### BaseROS2DeviceNode 类（第 290–349 行）

每个设备实例化时自动创建 PropertyPublisher。

```python
# 第 310-313 行：节点命名空间
self.node_name = f'{device_id.split("/")[-1]}'
self.namespace = f"/devices/{device_id}"
Node.__init__(self, self.node_name, namespace=self.namespace)

# 第 327-336 行：遍历 _status_types 创建发布者
for attr_name, msg_type in self._status_types.items():
    self.create_ros_publisher(attr_name, msg_type)
```

### Topic 命名规则

```
/devices/{device_id}/{attr_name}

示例：
  /devices/elite_arm_1/arm_pose     → 机械臂关节位姿
  /devices/stirrer_1/status         → 搅拌器状态
  /devices/pump_1/volume            → 泵体积
```

### 关键要点

- 默认发布频率 **5.0 秒一次**（`initial_period=5.0`）
- 可通过 `change_frequency(period)` 动态调整
- 支持同步/异步 getter（`get_method` 可以是 coroutine）
- 消息类型自动转换：`convert_to_ros_msg(msg_type, value)`

---

## 2. unilabos_msgs 消息体系

> **文档原文**：*ROS2 消息体系（unilabos_msgs/，~80个 .action 文件、Resource.msg 含 geometry_msgs/Pose）已覆盖全部实验室操作语义 [已有]*

### 文件位置

```
unilabos_msgs/
├── action/   → 85 个 .action 文件
├── msg/      → 2 个 .msg 文件
└── srv/      → 7 个 .srv 文件
```

### Action 文件（85 个，覆盖所有实验室操作）

```
unilabos_msgs/action/
├── Add.action                  # 加液
├── AGVTransfer.action          # AGV 转运
├── Centrifuge.action           # 离心
├── Clean.action                # 清洗
├── CleanVessel.action          # 清洗容器
├── Dissolve.action             # 溶解
├── Dry.action                  # 干燥
├── Filter.action               # 过滤
├── FilterThrough.action        # 通过过滤
├── HeatChill.action            # 加热/冷却
├── MoveArmJoint.action         # 机械臂关节移动
├── RunColumn.action            # 色谱柱
├── SendCmd.action              # 通用命令发送
├── Stir.action                 # 搅拌
├── Transfer.action             # 液体转移
├── Wait.action                 # 等待
├── WashSolid.action            # 洗涤固体
│   ... 共 85 个
```

### Resource.msg（含 geometry_msgs/Pose）

```
unilabos_msgs/msg/Resource.msg
```

```
string id
string name
string sample_id
string[] children
string parent
string type
string category
geometry_msgs/Pose pose        ← 包含位姿信息，用于耗材 3D 定位
string config
string data
```

### Srv 文件（7 个，资源管理）

```
unilabos_msgs/srv/
├── ResourceAdd.srv            # 添加资源
├── ResourceDelete.srv         # 删除资源
├── ResourceGet.srv            # 获取资源
├── ResourceList.srv           # 列出资源
├── ResourceUpdate.srv         # 更新资源
├── SerialCommand.srv          # 串口命令
└── Stop.srv                   # 停止
```

---

## 3. HostNode + send_goal

> **文档原文**：*HostNode + FastAPI 工作流调度已有，含 /api/job/add、/api/ws/device_status 等接口*

### 文件位置

```
unilabos/ros/nodes/presets/host_node.py
```

### HostNode 类（第 83–174 行）

单例模式的中央调度节点，管理所有设备、资源、控制器。继承自 BaseROS2DeviceNode。

```python
# 第 83 行
class HostNode(BaseROS2DeviceNode):
    # 第 98-102 行：单例获取
    @classmethod
    def get_instance(cls, timeout=30):
        ...
```

### send_goal 方法（第 762–824 行）

核心调度方法：将 FastAPI 收到的任务请求转发为 ROS2 Action Goal。

```python
# 第 762-819 行
def send_goal(self, item, action_type, action_kwargs, sample_material, server_info=None):
    device_id = item.device_id
    action_name = item.action_name

    # 构建 action_id：/devices/{device_id}/{action_name}
    action_id = f"/devices/{device_id}/{action_name}"

    # 获取对应的 ActionClient
    action_client = self._action_clients[action_id]

    # 将参数转换为 ROS 消息
    goal_msg = convert_to_ros_msg(action_client._action_type.Goal(), action_kwargs)

    # 异步发送 Goal
    future = action_client.send_goal_async(
        goal_msg,
        feedback_callback=...,
    )
```

### property_callback（第 723–762 行）

订阅各设备的 PropertyPublisher Topic，接收状态更新，通过 `publish_device_status` 转发给 WebSocket 客户端。

```python
# 第 723 行
def property_callback(self, msg, device_id, property_name, msg_type):
    # 更新 device_status 字典
    # 转发到 WebSocket 客户端
```

### update_device_status_subscriptions（第 671–720 行）

自动发现并订阅 `/devices/...` 下的新 Topic。

---

## 4. FastAPI 工作流接口

### 文件位置

```
unilabos/app/web/api.py          ← 路由定义
unilabos/app/web/controller.py   ← 业务逻辑
```

### POST /api/v1/job/add（api.py 第 1312–1332 行）

创建任务，触发 ROS2 Action 执行。

```python
# api.py 第 1312 行
@api.post("/job/add", summary="Create job", response_model=JobAddResp)
def post_job_add(req: JobAddReq):
    data = job_add(req)  # 调用 controller.job_add()
    return JobAddResp(data=data)
```

controller.py 中的 `job_add()`（第 265–345 行）：
- 生成 job_id / task_id
- 获取 HostNode 单例
- 检查设备是否繁忙（`check_device_action_busy`）
- 创建 QueueItem
- 调用 `host_node.send_goal()` 发送 ROS2 Action Goal

### WebSocket /api/v1/ws/device_status（api.py 第 243–256 行）

实时推送设备状态给前端。

```python
# api.py 第 243 行
@api.websocket("/ws/device_status")
async def websocket_device_status(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    # 保持连接，由 broadcast_device_status() 推送数据
```

### broadcast_device_status（api.py 第 84–106 行）

每秒循环，获取 HostNode 的设备状态，推送给所有 WebSocket 客户端。

```python
# api.py 第 84 行
async def broadcast_device_status():
    while True:
        host_info = get_host_node_info()
        status_data = {
            "type": "device_status",
            "data": {
                "device_status": host_info["device_status"],
                "device_status_timestamps": host_info["device_status_timestamps"],
            },
        }
        for connection in active_connections:
            await connection.send_json(status_data)
        await asyncio.sleep(1)  # 1Hz 推送
```

### GET /api/v1/job/{id}/status（api.py 第 1305–1309 行）

查询任务执行状态。

### API 路由挂载（api.py 第 1335–1338 行）

```python
app.include_router(api, prefix="/api/v1", tags=["api"])
```

所有接口实际路径为 `/api/v1/...`。

---

## 5. ResourceMeshManager + PlanningScene

> **文档原文**：*如果不用支持本地 rviz 则云端 moveit2 就够，目前已有初步实现*

### 文件位置

```
unilabos/ros/nodes/presets/resource_mesh_manager.py   ← 核心实现
unilabos/devices/ros_dev/moveit2.py                   ← MoveIt2 底层封装
```

### ResourceMeshManager 类（resource_mesh_manager.py 第 28–112 行）

继承 BaseROS2DeviceNode，管理耗材 3D 网格、TF 变换、PlanningScene。

```python
# 第 28 行
class ResourceMeshManager(BaseROS2DeviceNode):
    def __init__(self, resource_model, resource_config, resource_tracker, ...):
        # 资源模型和配置
        self.resource_model = resource_model
        self.resource_config_dict = {item['uuid']: item for item in resource_config}
```

### 核心能力

| 能力 | 方法 | 行号 | 说明 |
|------|------|------|------|
| 获取当前 PlanningScene | `_get_planning_scene_service.call()` | 66–76 | 调用 `/get_planning_scene` 服务 |
| 更新 PlanningScene | `_apply_planning_scene_service.call()` | 79–89 | 调用 `/apply_planning_scene` 服务 |
| **tf_update Action** | `tf_update()` | **405–510** | 核心：接收 `{resource_id: target_parent}` 命令，执行 attach/detach |
| 添加碰撞网格 | `add_resource_collision_meshes()` | 514–520 | 将耗材注册为 CollisionObject |

### tf_update 方法详解（第 405–510 行）

这是**耗材附着/释放的核心实现**，是一个 ROS2 Action Server 回调：

```python
# 第 405 行
def tf_update(self, goal_handle):
    cmd_dict = json.loads(tf_update_msg.command)
    # cmd_dict 格式：{"plate_96_1": "ee_link", "tip_rack_1": "world"}

    for resource_id, target_parent in cmd_dict.items():
        # 1. 通过 TF 查找当前位姿变换
        transform = self.tf_buffer.lookup_transform(parent_id, resource_id, ...)

        # 2. 更新内部 TF 字典
        self.resource_tf_dict[resource_id] = {
            "parent": parent_id,
            "position": {...},
            "rotation": {...}
        }

        # 3. 操作 PlanningScene
        if target_parent == 'world':
            # 释放：从 attached 移除，添加回 world collision objects
            operation_attach = CollisionObject.REMOVE
            operation_world = CollisionObject.ADD
        else:
            # 附着：从 world 移除，attach 到指定 link
            operation_attach = CollisionObject.ADD
            operation_world = CollisionObject.REMOVE

        # 4. 构建 AttachedCollisionObject
        collision_object = AttachedCollisionObject(
            object=CollisionObject(id=resource_id, operation=operation_attach)
        )
        if target_parent != 'world':
            collision_object.link_name = target_parent

    # 5. 应用到 PlanningScene
    self._apply_planning_scene_service.call(req)
```

### 工作流程

```
API 请求 "机械臂抓取 plate_96_1"
  → HostNode.send_goal() 发送 tf_update Action
    → ResourceMeshManager.tf_update() 执行：
      1. TF lookup 获取当前位姿
      2. 从 world CollisionObject 移除 plate_96_1
      3. 作为 AttachedCollisionObject 附着到 ee_link
      4. ApplyPlanningScene 使 MoveIt2 感知附着物
      5. publish_resource_tf() 更新前端 TF 数据
```

---

## 6. MoveitInterface — 业务逻辑封装层

> **补充说明**：此节基于 `moveit2_integration_summary.md` 的深度分析补充。`MoveitInterface` 是连接实验室操作（pick/place）与 MoveIt2 运动规划的**核心中间层**，两份 Phase2 文档此前未涉及。

### 文件位置

```
unilabos/devices/ros_dev/moveit_interface.py    ← 385 行
```

### MoveitInterface 类

通过**组合**方式管理多个 `MoveIt2` 实例（每个 MoveGroup 一个），在其上构建实验室级操作。

```python
class MoveitInterface:
    _ros_node: BaseROS2DeviceNode    # ROS 2 节点引用（post_init 注入）
    tf_buffer: Buffer                # TF2 坐标变换缓冲区
    tf_listener: TransformListener   # TF2 变换监听器
```

### 两阶段初始化

**阶段一：`__init__`（纯数据，不依赖 ROS 2）**
- 加载 `device_mesh/devices/{moveit_type}/config/move_group.json`
- 记录预定义关节位姿查找表 `joint_poses`

**阶段二：`post_init(ros_node)`（ROS 2 依赖）**
- 为每个 Move Group 创建 `MoveIt2` 实例，关节名/link 名/group 名自动加 `{device_id}_` 前缀
- 启动定时器，通过 Topic 自动发现 `tf_update` Action Server

### 核心方法

| 方法 | 作用 | 调用链 |
|------|------|--------|
| `pick_and_place(cmd)` | 完整抓取/放置工作流 | FK → IK → moveit_task/moveit_joint_task → resource_manager |
| `set_position(cmd)` | 笛卡尔空间直接位姿控制 | → `moveit_task()` → `MoveIt2.move_to_pose()` |
| `set_status(cmd)` | 预定义关节配置切换（如 home 位） | → `moveit_joint_task()` → `MoveIt2.move_to_configuration()` |
| `resource_manager(resource, parent)` | 资源 TF 父链接更新 | → `SendCmd` Action → `ResourceMeshManager.tf_update()` |
| `moveit_task(...)` | 底层笛卡尔运动封装 | → `MoveIt2.move_to_pose()`，含重试逻辑 |
| `moveit_joint_task(...)` | 底层关节运动封装 | → `MoveIt2.move_to_configuration()`，含重试逻辑 |

### pick_and_place 完整流程（以含 lift_height 的 pick 为例）

```
pick_and_place(command_json)
  │
  ├── 1. FK 计算：joint_positions → 末端位姿
  ├── 2. IK 计算：抬升后位姿 → 安全关节角（含约束）
  │
  └── 执行动作序列：
      Step 0: moveit_joint_task → IK 关节角 [自由空间规划]
      Step 1: moveit_task → 抬升位上方 [笛卡尔直线]
      Step 2: moveit_task → 目标位置 (FK 位姿) [笛卡尔直线]
      Step 3: resource_manager(resource, ee_link)  ← 附着
      Step 4: moveit_task → 抬升 (z + lift_height) [笛卡尔直线]
      Step 5: moveit_task → 水平移开 (x + x_distance) [笛卡尔直线]
```

### 与第 5 节 ResourceMeshManager 的关系

`MoveitInterface.resource_manager()` 是 `ResourceMeshManager.tf_update()` 的**上游调用方**：

```
MoveitInterface.pick_and_place()
  → resource_manager("beaker_1", "tool0")
    → SendCmd Action {command: '{"beaker_1": "tool0"}'}
      → ResourceMeshManager.tf_update()
        → PlanningScene attach/detach
        → publish_resource_tf() → 前端
```

### 注册表中的接入方式

通过设备 class 名中的 `moveit.` 标识自动接入：

```yaml
# 注册表示例
robotic_arm.SCARA_with_slider.moveit.virtual:
  class:
    module: unilabos.devices.ros_dev.moveit_interface:MoveitInterface
    action_value_mappings:
      pick_and_place: ...    # SendCmd Action
      set_position: ...      # SendCmd Action
      set_status: ...        # SendCmd Action
```

---

## 7. MoveIt2 底层 Python 接口

> **补充说明**：`moveit2.py` 是整个运动控制的基础，提供对 MoveIt2 ROS 2 接口的完整 Python 封装。

### 文件位置

```
unilabos/devices/ros_dev/moveit2.py    ← ~2443 行
```

### MoveIt2 类——ROS 2 通信拓扑

| 类型 | 名称 | 用途 |
|------|------|------|
| **Subscriber** | `/joint_states` | 实时获取关节状态（BEST_EFFORT QoS） |
| **Action Client** | `/move_action` | 一体化规划+执行 |
| **Action Client** | `/execute_trajectory` | 独立轨迹执行 |
| **Service Client** | `/plan_kinematic_path` | 关节/笛卡尔运动规划 |
| **Service Client** | `/compute_cartesian_path` | 笛卡尔路径规划（直线插补） |
| **Service Client** | `/compute_fk` | 正运动学计算 |
| **Service Client** | `/compute_ik` | 逆运动学计算 |
| **Service Client** | `/get_planning_scene` | 获取当前规划场景 |
| **Service Client** | `/apply_planning_scene` | 应用修改后的规划场景 |
| **Publisher** | `/collision_object` | 发布碰撞物体 |
| **Publisher** | `/attached_collision_object` | 发布附着碰撞物体 |

### 运动规划与执行

两种执行模式：
- **MoveGroup Action 模式**（`use_move_group_action=True`）：规划+执行合并，由 MoveIt2 内部管理
- **Plan + Execute 模式**：先 Service 规划，再 ExecuteTrajectory Action 执行

关键方法：`move_to_pose()`、`move_to_configuration()`、`plan()`、`execute()`、`wait_until_executed()`、`cancel_execution()`

### 碰撞场景管理（完整 API）

| 方法 | 说明 |
|------|------|
| `add_collision_box/sphere/cylinder/cone/mesh()` | 添加各类碰撞体 |
| `move_collision()` | 移动已有碰撞体 |
| `remove_collision_object()` | 移除碰撞体 |
| `attach_collision_object()` | 将碰撞体附着到 link |
| `detach_collision_object()` | 从 link 分离碰撞体 |
| `allow_collisions()` | 修改 Allowed Collision Matrix |
| `clear_all_collision_objects()` | 清空所有碰撞物体 |

### 运动学服务

- **正运动学 (FK)**：`compute_fk()` — 关节角 → 末端位姿
- **逆运动学 (IK)**：`compute_ik()` — 目标位姿 → 关节角（支持约束和避碰）

### 状态管理

通过 `MoveIt2State` 枚举和 `threading.Lock` 实现线程安全的状态机：`IDLE` → `REQUESTING` → `EXECUTING` → `IDLE`。配合 `ignore_new_calls_while_executing` 防止运动冲突。

---

## 8. ResourceVisualization

> **补充说明**：此节基于 `moveit2_integration_summary.md` 大幅扩充。`ResourceVisualization` 不仅是"启动 RViz"，它是整个 3D 场景的**核心构建器**，负责动态 URDF/SRDF 生成和 MoveIt2 全栈启动。

### 文件位置

```
unilabos/device_mesh/resource_visalization.py    ← 429 行
```

> 注意：文件名有拼写错误（visalization → visualization）

### ResourceVisualization 类（第 38–56 行）

根据实验室设备/资源注册表配置，**动态生成**完整的 URDF 和 SRDF，并启动 MoveIt2 所需的全部 ROS 2 节点。

### 注册表 `model` 字段——3D 模型加载的入口

注册表 YAML 中的 `model` 字段驱动整个 3D 加载流程：

```yaml
model:
  mesh: arm_slider                    # 模型文件夹名 → device_mesh/devices/arm_slider/
  path: https://...macro_device.xacro # OSS 远程下载地址
  type: device                        # 决定 ResourceVisualization 的处理逻辑
```

### 两种模型类型的处理路径

| 对比项 | `type: device`（动态设备） | `type: resource`（静态资源） |
|--------|--------------------------|----------------------------|
| **模型格式** | xacro 宏（参数化 URDF） | STL 静态 mesh |
| **加载方式** | xacro include → 嵌入全局 URDF 运动链 | 记录路径 → 后续作为碰撞体添加 |
| **是否有关节** | 是（prismatic/revolute） | 否（纯静态） |
| **支持 MoveIt** | 是（class 名含 `moveit.` 时触发） | 否 |
| **存放目录** | `device_mesh/devices/{mesh}/` | `device_mesh/resources/{mesh}` |
| **实际示例** | arm_slider, toyo_xyz, elite_robot | 微孔板, tip rack, 试管架 |

### MoveIt 设备的额外配置（`config/` 目录）

当设备 class 名包含 `moveit.` 时，`ResourceVisualization` 额外加载：

```
device_mesh/devices/arm_slider/
├── macro_device.xacro                 ← URDF 运动链
├── joint_limit.yaml                   ← 关节物理限制
├── meshes/                            ← 3D 网格
└── config/                            ← ★ MoveIt 设备独有
    ├── macro.ros2_control.xacro       ← ros2_control 硬件接口
    ├── macro.srdf.xacro               ← SRDF（Move Group + 碰撞矩阵）
    ├── move_group.json                ← MoveitInterface 使用的配置
    ├── ros2_controllers.yaml          ← 控制器定义
    ├── moveit_controllers.yaml        ← MoveIt ↔ 控制器映射
    ├── kinematics.yaml                ← 运动学求解器（LMA）
    ├── joint_limits.yaml              ← MoveIt 关节限制
    ├── initial_positions.yaml         ← 仿真初始位置
    ├── pilz_cartesian_limits.yaml     ← Pilz 笛卡尔限制
    └── moveit_planners.yaml           ← 规划器列表（OMPL）
```

### moveit_init()——多设备配置合并

对每个 MoveIt 设备加载控制器/运动学配置，**所有关节名和控制器名加上设备 ID 前缀**，合并到全局配置中。这是多设备共存的关键。

### create_launch_description（第 319–392 行）

启动以下 ROS2 节点：

| 节点 | 包 | 作用 |
|------|-----|------|
| `ros2_control_node` | `controller_manager` | ros2_control 硬件管理器 |
| `spawner` (per controller) | `controller_manager` | 激活各 JointTrajectoryController |
| **`spawner` (joint_state_broadcaster)** | `controller_manager` | **★ 广播关节状态到 `/joint_states`** |
| `robot_state_publisher` | `robot_state_publisher` | 根据 URDF + `/joint_states` 发布 `/tf` |
| `move_group` | `moveit_ros_move_group` | MoveIt2 核心节点 |
| `rviz2`（可选） | `rviz2` | 3D 可视化 |

> **关键发现**：`joint_state_broadcaster` 已经在将 ros2_control 的关节状态发布到 `/joint_states`，`robot_state_publisher` 已经在据此发布 `/tf`。**对于 MoveIt 设备，`/joint_states` → `/tf` 的链路已经完整，无需额外的 JointStateAdapterNode**。

### 从注册表到 MoveIt2 的完整链路

```
注册表 YAML
│  model.mesh = "arm_slider", model.type = "device"
│  class 含 "moveit."
▼
ResourceVisualization.__init__()
│  xacro include → URDF + SRDF + ros2_control
▼
ResourceVisualization.moveit_init()
│  加载 ros2_controllers / moveit_controllers / kinematics（带前缀合并）
▼
ResourceVisualization.create_launch_description()
│  启动 ros2_control_node → controller spawners → joint_state_broadcaster
│  启动 robot_state_publisher → /tf
│  启动 move_group → MoveIt2 规划服务
▼
MoveitInterface.post_init()
│  读取 move_group.json → 创建 MoveIt2 实例 → 等待 tf_update
▼
运行时: pick_and_place / set_position / set_status
```

---

## 9. 完整数据链路示意

文档描述的完整数据链路，及各部分在代码中的位置。

> **重要修正**：原文档将所有设备统一标注为需要 JointStateAdapterNode。实际上 MoveIt 设备和非 MoveIt 设备的 `/joint_states` 来源不同，需要区分两条路径。

### 链路 A：MoveIt 设备的关节状态链路（✅ 已有，无需新开发）

```
用户操作
  │
  ▼
POST /api/v1/job/add               ← api.py:1312
  │
  ▼
controller.job_add()               ← controller.py:265
  │
  ▼
HostNode.send_goal()               ← host_node.py:762
  │
  ▼
MoveitInterface (ActionServer)     ← moveit_interface.py
  │  pick_and_place / set_position / set_status
  │  通过 MoveIt2 实例规划+执行运动
  ▼
ros2_control_node                  ← resource_visalization.py 启动
  │  执行 JointTrajectoryController
  │  更新关节状态
  ▼
joint_state_broadcaster            ← resource_visalization.py 启动  ✅ 已有
  │  发布 /joint_states (sensor_msgs/JointState)
  ▼
robot_state_publisher              ← resource_visalization.py 启动  ✅ 已有
  │  /joint_states → /tf
  ▼
Foxglove Bridge (ws://0.0.0.0:8765)
  │
  ▼
前端 ros-bridge.js → urdf-scene.js ← lab3d-phase2/*.js ✅ 已完成
```

### 链路 B：非 MoveIt 设备的关节状态链路（需 JointStateAdapterNode）

```
非 MoveIt 设备（搅拌器、泵、液体处理器等）
  │  PropertyPublisher 发布状态
  ▼
/devices/{id}/{attr}               ← base_device_node.py:196
  │  例如 /devices/stirrer_1/status（5秒/次，自定义 msg_type）
  │
  ▼
  ┌─── 【待开发】JointStateAdapterNode ───────────────┐
  │  仅服务于非 MoveIt 设备                             │
  │  订阅 /devices/+/arm_pose 等自定义话题              │
  │  转换为标准 sensor_msgs/JointState                 │
  │  发布到 /joint_states                              │
  │  优先级降低：MoveIt 设备已不需要此节点                │
  └───────────────────────────────────────────────────┘
  │
  ▼
/joint_states → robot_state_publisher → /tf → 前端
```

### 链路 C：耗材附着/释放链路（✅ 已有）

```
MoveitInterface.pick_and_place()   ← moveit_interface.py
  │  在抓取/放置步骤中调用 resource_manager()
  ▼
resource_manager(resource, parent) ← moveit_interface.py
  │  SendCmd Action: {"beaker_1": "tool0"}
  ▼
ResourceMeshManager.tf_update()    ← resource_mesh_manager.py:405
  │  1. TF lookup 获取位姿
  │  2. 操作 PlanningScene (attach/detach)
  │  3. ApplyPlanningScene
  ▼
publish_resource_tf()              ← resource_mesh_manager.py:245 (50Hz)
  │  发布到 /devices/resource_mesh_manager/resource_pose
  ▼
前端 resource-tracker.js           ← lab3d-phase2/resource-tracker.js ✅ 已完成
```

### 链路 D：MoveIt2 轨迹规划预览（✅ 已有）

```
MoveitInterface.moveit_task()      ← moveit_interface.py
  │  MoveIt2.move_to_pose()
  ▼
move_group 节点                    ← resource_visalization.py 启动
  │  规划完成后发布
  ▼
/move_group/display_planned_path
  │
  ▼
前端 trajectory-player.js         ← lab3d-phase2/trajectory-player.js ✅ 已完成
```

### 链路 E：设备状态 WebSocket（✅ 已有）

```
HostNode.property_callback()       ← host_node.py:723
  │  接收 PropertyPublisher 数据
  │  更新 device_status 字典
  ▼
broadcast_device_status()          ← api.py:84
  │  每秒推送一次
  ▼
WebSocket /api/v1/ws/device_status ← api.py:243
  │
  ▼
前端 status-overlay.js             ← lab3d-phase2/status-overlay.js ✅ 已完成
```

---

## 附：文件索引速查表

| 组件 | 文件路径 | 关键行号 |
|------|----------|----------|
| PropertyPublisher | `unilabos/ros/nodes/base_device_node.py` | 175–248 |
| BaseROS2DeviceNode | `unilabos/ros/nodes/base_device_node.py` | 290–349 |
| HostNode | `unilabos/ros/nodes/presets/host_node.py` | 83–174 |
| HostNode.send_goal | `unilabos/ros/nodes/presets/host_node.py` | 762–824 |
| HostNode.property_callback | `unilabos/ros/nodes/presets/host_node.py` | 723–762 |
| POST /job/add | `unilabos/app/web/api.py` | 1312–1332 |
| WS /ws/device_status | `unilabos/app/web/api.py` | 243–256 |
| broadcast_device_status | `unilabos/app/web/api.py` | 84–106 |
| job_add | `unilabos/app/web/controller.py` | 265–345 |
| ResourceMeshManager | `unilabos/ros/nodes/presets/resource_mesh_manager.py` | 28–112 |
| tf_update (attach/detach) | `unilabos/ros/nodes/presets/resource_mesh_manager.py` | 405–510 |
| add_resource_collision_meshes | `unilabos/ros/nodes/presets/resource_mesh_manager.py` | 514–520 |
| **MoveitInterface** | `unilabos/devices/ros_dev/moveit_interface.py` | 全文 385 行 |
| MoveitInterface.pick_and_place | `unilabos/devices/ros_dev/moveit_interface.py` | 191–350 |
| MoveitInterface.resource_manager | `unilabos/devices/ros_dev/moveit_interface.py` | 96–112 |
| MoveitInterface.moveit_task | `unilabos/devices/ros_dev/moveit_interface.py` | 113–145 |
| **MoveIt2**（底层接口） | `unilabos/devices/ros_dev/moveit2.py` | 全文 ~2443 行 |
| MoveIt2.move_to_pose | `unilabos/devices/ros_dev/moveit2.py` | 规划+执行 |
| MoveIt2.compute_fk/ik | `unilabos/devices/ros_dev/moveit2.py` | FK/IK 服务 |
| MoveIt2 碰撞管理 | `unilabos/devices/ros_dev/moveit2.py` | add/attach/detach/remove |
| ResourceVisualization | `unilabos/device_mesh/resource_visalization.py` | 38–429 |
| ResourceVisualization.moveit_init | `unilabos/device_mesh/resource_visalization.py` | 控制器/运动学配置合并 |
| create_launch_description | `unilabos/device_mesh/resource_visalization.py` | 319–392 |
| Resource.msg | `unilabos_msgs/msg/Resource.msg` | 1–11 |
| Action 定义（85 个） | `unilabos_msgs/action/*.action` | — |
| Msg 定义（2 个） | `unilabos_msgs/msg/Resource.msg, State.msg` | — |
| Srv 定义（7 个） | `unilabos_msgs/srv/*.srv` | — |
