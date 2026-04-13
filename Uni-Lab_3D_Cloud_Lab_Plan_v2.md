# Uni-Lab 云端 3D 实验室搭建与运行演示规划 v2

> 本文档基于对 Uni-Lab OS 源码的完整分析（`unilabos/` 包结构、`ResourceVisualization`、`device_mesh/`、`workflow/`、`registry/`、`ros/`），结合 ROS2/MoveIt2/RViz2/ROSBridge2 的技术特性撰写，所有路径和类名均对应仓库实际代码。

---

## 一、现有基础盘点（不需要重新建设的部分）

在规划新建内容之前，必须先明确仓库里已经具备哪些能力：

### 1.1 已有的 3D 资产（`unilabos/device_mesh/`）

**机器人设备（有完整 Xacro + STL/DAE 网格）**

| 设备 | Xacro 路径 | 备注 |
|------|-----------|------|
| Elite CS 系列机械臂 | `devices/elite_robot/urdf/cs.urdf.xacro` | cs612/616/620/625/63/66，含 visual/collision 分离 |
| Opentrons OT-2 液体处理器 | `devices/opentrons_liquid_handler/macro_device.xacro` | 含移液臂 |
| SCARA 臂 + 滑轨 | `devices/arm_slider/macro_device.xacro` | 线性轴 + SCARA 组合 |
| Toyo XYZ 龙门架 | `devices/toyo_xyz/macro_device.xacro` | 三轴直线运动 |
| HPLC 分析站 | `devices/hplc_station/macro_device.xacro` | — |
| Thermo Orbitor RS2 酒店 | `devices/thermo_orbitor_rs2_hotel/macro_device.xacro` | 含 `meshes/hotel.stl` |
| 6-DOF 仿真机器人 | `devices/dummy2_robot/dummy2.xacro` | 开发测试用 |

**耗材资产（有 STL）**

96 孔板、高板、TipRack、Tecan 嵌套 TipRack、HPLC 板、试剂瓶、离心管等，均位于 `resources/*/`。

### 1.2 已有的可视化启动逻辑（`ResourceVisualization`）

`unilabos/device_mesh/resource_visalization.py` 中的 `ResourceVisualization` 类已经实现：
- 读取设备布局配置（`position.x/y/z`、`config.rotation`）
- 动态拼接各设备的 Xacro 宏为一个完整 URDF 字符串
- 通过 `LaunchService` 启动 `robot_state_publisher` + `rviz2` + `move_group`（可选）

**这是阶段一的直接起点**，不需要从零搭建，只需要扩展它的前端输出方向。

### 1.3 已有的工作流调度（`HostNode` + FastAPI）

```
用户 / 前端
    ↓ POST /api/job/add  {device_id, action, action_args}
HostNode（ros/nodes/presets/host_node.py）
    ↓ 发送 ROS2 Action Goal
/devices/{device_id}/{action_name}  Action Server
    ↓ 调用驱动类方法
设备执行 → 发布 status_types 到 ROS Topic
    ↓ GET /api/job/{job_id} 或 WebSocket /api/ws/device_status
前端轮询/推送获取结果
```

**每个设备已经有 ROS Topic 持续发布状态**（由 `PropertyPublisher` + `@topic` 装饰器实现），例如机械臂的 `arm_pose`。这些就是 3D 动态同步的数据源。

### 1.4 已有的 ROS2 消息体系（`unilabos_msgs/`）

约 80 个 `.action` 文件、`Resource.msg`（含 `geometry_msgs/Pose pose`）、`ResourceAdd/Update/Delete` 服务，已覆盖全部实验室操作语义。

---

## 二、总体架构设计

```
┌──────────────────────── Uni-Lab OS 云端 ───────────────────────────────┐
│                                                                         │
│   ┌─────────────────┐    ┌───────────────────────────────────────────┐ │
│   │   Web 前端       │    │              ROS2 Runtime                 │ │
│   │                 │    │                                           │ │
│   │  ┌───────────┐  │    │  robot_state_publisher (/robot_description│ │
│   │  │ 3D 视图    │◄─┼────┼──  /joint_states, /tf)                   │ │
│   │  │ ros3djs   │  │    │                                           │ │
│   │  │ Three.js  │  │    │  move_group (MoveIt2 PlanningScene)       │ │
│   │  └───────────┘  │    │    ├── CollisionObject 注册（各仪器）      │ │
│   │       ▲         │    │    └── /display_planned_path              │ │
│   │  WebSocket      │    │                                           │ │
│   └────────┬────────┘    │  ThrottlerNode                           │ │
│            │             │    ├── /joint_states   100Hz → 25Hz      │ │
│       ROSBridge2         │    ├── /tf             100Hz → 20Hz      │ │
│       (WebSocket:9090)   │    └── /planning_scene 事件驱动           │ │
│            │             │                                           │ │
│            └─────────────►  HostNode → /devices/{id}/{action}       │ │
│                          │  BaseROS2DeviceNode → PropertyPublisher  │ │
│   ┌─────────────────┐    │  ResourceVisualization（扩展）            │ │
│   │ FastAPI         │    └───────────────────────────────────────────┘ │
│   │ /api/job/add    │                                                   │
│   │ /api/ws/status  │    ┌───────────────────────────────────────────┐ │
│   │ /api/devices    │    │  AI 布局引擎（阶段三）                      │ │
│   └─────────────────┘    │  ConstraintSolver + ReachabilityMap       │ │
│                          └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 三、阶段一：云端手动搭建静态 3D 实验室

### 目标

用户在 Web 界面选择设备，拖放排布，点击"预览"后在浏览器内看到完整的 3D 实验室场景。

### 3.1 资产标准化（关键前置工作）

#### 3.1.1 模型零点约定

**所有设备 Xacro 宏的坐标原点统一规范**：

```
Z = 0：设备物理底面（落地面）
XY 原点：设备底面几何中心投影
+X 轴：设备正面朝向
```

目前 `macro_device.xacro` 通过 `${x/1000}`、`${y/1000}` 参数定位，已有基础。需要逐一检查现有资产的零点，不符合规范的用 `<origin xyz="..." rpy="..."/>` 偏移修正，**不要修改模型本身**。

#### 3.1.2 资产完整性检查脚本

```python
# scripts/check_assets.py
# 遍历 registry/devices/*.yaml，对每个有 model.mesh 的设备：
# 1. 检查对应 device_mesh/devices/{mesh}/ 是否存在 macro_device.xacro
# 2. 检查 meshes/ 下是否同时有 visual 和 collision 网格
# 3. 输出缺失设备清单，用于建模优先级排期

import yaml, os
from pathlib import Path

REGISTRY_DIR = "unilabos/registry/devices"
MESH_DIR = "unilabos/device_mesh/devices"

for yaml_file in Path(REGISTRY_DIR).glob("*.yaml"):
    data = yaml.safe_load(yaml_file.read_text())
    for device_id, cfg in data.items():
        mesh_name = cfg.get("model", {}).get("mesh")
        if mesh_name:
            xacro_path = Path(MESH_DIR) / mesh_name / "macro_device.xacro"
            collision_path = Path(MESH_DIR) / mesh_name / "meshes" / "collision"
            print(f"{'✅' if xacro_path.exists() else '❌'} {device_id}: {xacro_path}")
            print(f"  collision: {'✅' if collision_path.exists() else '⚠️ 未拆分'}")
```

#### 3.1.3 Visual / Collision 拆分判断标准

| 条件 | 处置 |
|------|------|
| 顶点数 < 5 万 且 MoveIt2 规划时间 < 500ms | 无需拆分，Visual 兼做 Collision |
| 顶点数 ≥ 5 万 或 规划时间 ≥ 500ms | 必须拆分：Visual 保留原模型，Collision 替换为简化凸包（Blender Convex Hull） |

验证规划时间：
```bash
ros2 topic echo /move_group/result | grep planning_time
```

#### 3.1.4 缺失设备的建模补充优先级

根据 `registry/devices/*.yaml` 中未挂载 `model.mesh` 的设备，按使用频率排序补充建模：

| 优先级 | 设备类别 | registry 文件 | 建模来源 |
|--------|---------|--------------|---------|
| P0 | 离心机 | `temperature.yaml` 等 | 厂商 STEP 文件 → Blender → USD/STL |
| P0 | 天平 | `balance.yaml` | 同上 |
| P1 | AGV | `robot_agv.yaml` | 同上 |
| P1 | 固体分散仪 | `solid_dispenser.yaml` | 同上 |
| P2 | 气体处理 | `gas_handler.yaml` | 同上 |

### 3.2 扩展 `ResourceVisualization` 支持 ROSBridge

**当前代码**（`resource_visalization.py`）只启动 RViz2。需要在 `create_launch_description()` 中增加 ROSBridge2 节点：

```python
# 在 create_launch_description() 末尾追加
from launch_ros.actions import Node as RosNode

rosbridge_node = RosNode(
    package='rosbridge_server',
    executable='rosbridge_websocket',
    name='rosbridge_websocket',
    parameters=[{
        'port': 9090,
        'address': '0.0.0.0',
        'ssl': False,
    }]
)

# ThrottlerNode（新建）
throttler_node = RosNode(
    package='unilabos',
    executable='throttler_node',   # 新建可执行入口
    name='throttler_node',
    parameters=[{
        'joint_state_rate': 25.0,  # Hz
        'tf_rate': 20.0,
    }]
)

ld.add_action(rosbridge_node)
ld.add_action(throttler_node)
```

### 3.3 ThrottlerNode 实现

新建 `unilabos/ros/nodes/throttler_node.py`：

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from tf2_msgs.msg import TFMessage

class ThrottlerNode(Node):
    """将高频 ROS Topic 降频后转发，保护前端浏览器性能。"""

    def __init__(self):
        super().__init__('throttler_node')
        js_rate  = self.declare_parameter('joint_state_rate', 25.0).value  # Hz
        tf_rate  = self.declare_parameter('tf_rate', 20.0).value

        # /joint_states: 原始 → 节流发布
        self._js_pub  = self.create_publisher(JointState, '/joint_states_throttled', 10)
        self._tf_pub  = self.create_publisher(TFMessage,  '/tf_throttled', 10)

        self.create_subscription(JointState, '/joint_states',
            lambda msg: setattr(self, '_last_js', msg), 10)
        self.create_subscription(TFMessage, '/tf',
            lambda msg: setattr(self, '_last_tf', msg), 10)

        self.create_timer(1.0 / js_rate, self._pub_js)
        self.create_timer(1.0 / tf_rate, self._pub_tf)

    def _pub_js(self):
        if hasattr(self, '_last_js'):
            self._js_pub.publish(self._last_js)

    def _pub_tf(self):
        if hasattr(self, '_last_tf'):
            self._tf_pub.publish(self._last_tf)
```

### 3.4 前端 3D 视图实现

**推荐技术栈**：`ros3djs` + `Three.js` + `ROSLIB.js`（均为纯 JS，无需打包工具，可直接集成进现有 Jinja2 模板）。

```html
<!-- 集成到 unilabos/app/web/templates/lab3d.html -->
<script src="https://cdn.jsdelivr.net/npm/roslib/build/roslib.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/ros3djs/build/ros3d.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three/build/three.min.js"></script>

<div id="urdf-viewer" style="width:100%;height:600px;"></div>

<script>
const ros = new ROSLIB.Ros({ url: 'ws://localhost:9090' });
const viewer = new ROS3D.Viewer({
    divID: 'urdf-viewer',
    width: 1200, height: 600,
    antialias: true,
    background: '#1a1a2e'
});

// 加载 URDF（robot_state_publisher 发布 /robot_description）
const urdfClient = new ROS3D.UrdfClient({
    ros, scene: viewer.scene,
    tfClient: new ROSLIB.TFClient({
        ros,
        fixedFrame: 'world',
        angularThres: 0.01,
        transThres: 0.001,
        rate: 20.0,       // 匹配 ThrottlerNode 的 tf_rate
        serverName: '/tf2_web_republisher'
    }),
    param: '/robot_description',
    path: '/static/meshes/',   // 静态文件服务托管 STL/DAE
    loader: ROS3D.COLLADA_LOADER
});

// 规划轨迹预览（阶段二）
const plannedPathTopic = new ROSLIB.Topic({
    ros,
    name: '/move_group/display_planned_path',
    messageType: 'moveit_msgs/DisplayTrajectory'
});
</script>
```

### 3.5 布局配置 API

在 `app/web/api.py` 新增端点，接收前端拖拽结果并触发 `ResourceVisualization` 重建：

```python
@router.post("/api/lab/layout")
async def update_layout(layout: LabLayoutRequest):
    """
    接收格式：
    {
      "devices": {
        "elite_arm_1": {
          "type": "device",
          "class": "robotic_arm.elite",
          "position": {"x": 500, "y": 0, "z": 0},  # 单位 mm
          "config": {"rotation": {"x": 0, "y": 0, "z": 0}}
        },
        ...
      }
    }
    """
    viz = ResourceVisualization(layout.devices, {})
    viz.launch()   # 重启 robot_state_publisher，前端自动刷新 URDF
    return {"status": "ok"}
```

---

## 四、阶段二：工作流 3D 动态同步

### 目标

Uni-Lab OS 下发工作流后，前端 3D 视图中机械臂实时动起来，并能预览 MoveIt2 规划的运动轨迹。

### 4.1 UniLab OS → ROS 数据流（填充 4.3.1 空节）

**已有基础**：`BaseROS2DeviceNode` 的 `PropertyPublisher` 已经在持续发布设备状态（如 `arm_pose`）到 ROS Topic。关键是把这些状态翻译成标准的 `/joint_states`。

```
Uni-Lab OS 工作流
    ↓ POST /api/job/add
    {device_id: "elite_arm_1", action: "move_pos_task", action_args: {command: "..."}}
HostNode.send_goal_to_device()
    ↓ ROS2 Action Goal → /devices/elite_arm_1/move_pos_task
BaseROS2DeviceNode（ActionServer）
    ↓ 驱动类执行动作
EliteRobot.arm_pose（@topic 装饰器属性）
    ↓ PropertyPublisher → /devices/elite_arm_1/arm_pose (String, 当前关节角 JSON)
    ↓
【新增】JointStateAdapterNode
    ↓ 订阅 /devices/elite_arm_1/arm_pose
    ↓ 解析 JSON → sensor_msgs/JointState
    ↓ 发布 /joint_states（robot_state_publisher 消费）
    ↓
robot_state_publisher → /tf（各连杆坐标系）
    ↓ ThrottlerNode（降频）
ROSBridge2（WebSocket）
    ↓
前端 ros3djs（驱动 URDF 动画）
```

**新建 `JointStateAdapterNode`**（`unilabos/ros/nodes/joint_state_adapter.py`）：

```python
class JointStateAdapterNode(Node):
    """将各设备的 arm_pose topic 适配为标准 /joint_states 消息。"""

    DEVICE_JOINT_MAP = {
        # device_id → (topic名, joint_names列表)
        "elite_arm_1": ("/devices/elite_arm_1/arm_pose",
                        ["joint1","joint2","joint3","joint4","joint5","joint6"]),
    }

    def __init__(self):
        super().__init__('joint_state_adapter')
        self._pub = self.create_publisher(JointState, '/joint_states', 10)
        for device_id, (topic, joints) in self.DEVICE_JOINT_MAP.items():
            self.create_subscription(String, topic,
                lambda msg, j=joints: self._on_pose(msg, j), 10)

    def _on_pose(self, msg: String, joint_names: list):
        import json
        positions = json.loads(msg.data)  # 根据实际格式解析
        js = JointState()
        js.header.stamp = self.get_clock().now().to_msg()
        js.name = joint_names
        js.position = positions
        self._pub.publish(js)
```

### 4.2 MoveIt2 PlanningScene 集成

将实验室所有设备注册为 `CollisionObject`，MoveIt2 全局避障自动生效：

```python
# unilabos/ros/nodes/planning_scene_manager.py
from moveit_msgs.msg import CollisionObject, PlanningScene
from shape_msgs.msg import SolidPrimitive
from geometry_msgs.msg import Pose

class PlanningSceneManager(Node):
    """将设备布局同步到 MoveIt2 PlanningScene，实现全局碰撞检测。"""

    def __init__(self):
        super().__init__('planning_scene_manager')
        self._pub = self.create_publisher(
            PlanningScene, '/planning_scene', 10)

    def add_device(self, device_id: str, mesh_path: str, pose: Pose):
        """将设备注册为 CollisionObject。"""
        co = CollisionObject()
        co.id = device_id
        co.header.frame_id = "world"
        # 使用设备的 collision mesh（STL）
        co.meshes = [load_mesh(mesh_path)]
        co.mesh_poses = [pose]
        co.operation = CollisionObject.ADD

        scene = PlanningScene()
        scene.world.collision_objects.append(co)
        scene.is_diff = True
        self._pub.publish(scene)

    def attach_consumable(self, arm_link: str, consumable_id: str):
        """耗材附着到机械臂末端（Attached Collision Object）。"""
        # 从 PlanningScene 的 CollisionObject 列表中移除
        # 添加到 AttachedCollisionObject，关联到 arm_link
        ...
```

**Attached Collision Object 完整流程**（以 96 孔板为例）：

```
1. 初始：plate_96 作为 CollisionObject 在工作台上
2. 机械臂移动到 grasp 帧 → 夹爪闭合
3. PlanningSceneManager.attach_consumable("panda_hand", "plate_96_1")
   → plate_96_1 从场景 CollisionObject 移除
   → 作为 AttachedCollisionObject 附着到 panda_hand
   → 后续所有规划自动考虑 plate_96_1 的体积
4. 机械臂移动到目标位置 → 夹爪张开
5. PlanningSceneManager.detach_consumable("plate_96_1", target_pose)
   → 重新注册为 CollisionObject 在新位置
```

### 4.3 ROS → 前端渲染（填充 4.3.2 空节）

**前端需要订阅的完整 Topic 列表**：

| Topic | 消息类型 | 用途 | 频率 |
|-------|---------|------|------|
| `/robot_description` | `std_msgs/String` | 加载 URDF，一次性 | 一次性 |
| `/joint_states_throttled` | `sensor_msgs/JointState` | 驱动机械臂关节动画 | 25 Hz |
| `/tf_throttled` | `tf2_msgs/TFMessage` | 更新各物体坐标系 | 20 Hz |
| `/planning_scene` | `moveit_msgs/PlanningScene` | 渲染设备轮廓/碰撞体 | 事件驱动 |
| `/move_group/display_planned_path` | `moveit_msgs/DisplayTrajectory` | 预览规划轨迹（动画回放） | 事件驱动 |
| `/api/ws/device_status` | JSON (FastAPI WS) | 设备状态指示（颜色/图标） | 1 Hz |

**轨迹预览实现**（前端 JS）：

```javascript
// 订阅 MoveIt2 规划好的轨迹，按时间戳回放动画
plannedPathTopic.subscribe(function(msg) {
    const trajectory = msg.trajectory[0].joint_trajectory;
    let frameIndex = 0;

    const animate = () => {
        if (frameIndex >= trajectory.points.length) return;
        const point = trajectory.points[frameIndex];
        // 更新 URDF viewer 中的关节角
        urdfClient.setJointValues(
            Object.fromEntries(
                trajectory.joint_names.map((name, i) =>
                    [name, point.positions[i]]
                )
            )
        );
        // 按实际时间步长播放
        const dt = frameIndex < trajectory.points.length - 1
            ? (trajectory.points[frameIndex+1].time_from_start.sec -
               point.time_from_start.sec) * 1000
            : 0;
        frameIndex++;
        setTimeout(animate, dt);
    };
    animate();
});
```

---

## 五、阶段三：AI 自动实验室布局排布

### 目标

用户选定设备列表和实验室尺寸后，AI 自动输出满足所有约束的最优布局方案。

### 5.1 约束体系设计

```python
# unilabos/layout/constraints.py

@dataclass
class LayoutConstraint:
    name: str
    penalty: float  # float('inf') = 硬约束；有限值 = 软约束代价

# ─── 硬约束（违反则方案无效）─────────────────────────────────────
HARD_CONSTRAINTS = [
    LayoutConstraint("pcr_contamination_isolation",   penalty=float('inf')),
    LayoutConstraint("balance_vibration_isolation",   penalty=float('inf')),
    LayoutConstraint("arm_kinematic_reachability",    penalty=float('inf')),
    LayoutConstraint("power_outlet_proximity",        penalty=float('inf')),
    LayoutConstraint("exhaust_fan_proximity",         penalty=float('inf')),
]

# ─── 软约束（优化目标）───────────────────────────────────────────
SOFT_CONSTRAINTS = [
    LayoutConstraint("minimize_transfer_distance",    penalty=1.0),
    LayoutConstraint("cable_routing_clearance",       penalty=0.5),
    LayoutConstraint("operator_walkway_clearance",    penalty=0.8),
]

# ─── 硬编码规则 API（对应原文档 4.4 节末尾）──────────────────────
def distance_less_than(device_a: str, device_b: str, dist_m: float) -> LayoutConstraint:
    """设备 A 和 B 的距离必须小于 dist_m 米。"""
    return LayoutConstraint(f"{device_a}_near_{device_b}", penalty=float('inf'))

def distance_greater_than(device_a: str, device_b: str, dist_m: float) -> LayoutConstraint:
    """设备 A 和 B 的距离必须大于 dist_m 米。"""
    return LayoutConstraint(f"{device_a}_far_from_{device_b}", penalty=float('inf'))
```

### 5.2 离线可达性地图生成

```python
# scripts/generate_reachability_map.py
# 依赖：Matterix / Isaac Sim（GPU 加速 IK 求解）或 IKFast（CPU）

"""
对每个机械臂配置：
1. 在实验室地面网格上枚举机器人底座候选位置 (x, y, θ)
2. 对每个候选位置，用 IK 求解器测试工作空间球内所有目标点
3. 生成体素地图：可达 = 1，不可达 = 0
4. 序列化为 .npz 文件
5. AI 排布时 O(1) 查表
"""

import numpy as np

def generate_reachability_map(robot_type: str, resolution_m: float = 0.05) -> np.ndarray:
    """
    返回形状 (X_GRID, Y_GRID, Z_GRID) 的布尔体素数组。
    True = 该点在机械臂工作空间内（从当前底座位置）。
    """
    # 使用 IKFast 或 Matterix/IsaacSim 的 DifferentialIK 批量求解
    ...

def check_reachability(robot_base: tuple, target_xyz: tuple,
                       voxel_map: np.ndarray, resolution: float) -> bool:
    """O(1) 查表：判断目标点是否可达。"""
    vx = int((target_xyz[0] - robot_base[0]) / resolution)
    vy = int((target_xyz[1] - robot_base[1]) / resolution)
    vz = int(target_xyz[2] / resolution)
    return bool(voxel_map[vx, vy, vz])
```

### 5.3 布局求解器（两阶段策略）

**阶段 3a（MVP）：2D 占用域投影 + Pensil AI**

适用于约束少、快速出方案的场景：

```
1. 对每个设备，取其 Xacro 模型的 AABB（轴对齐包围盒）的 XY 投影 → 矩形占用域
2. 将占用域 + 实验室平面图（含电源、排气位置）+ 设备列表发送给 Pensil AI
3. Pensil 输出 2D 布局 JSON
4. 自动验证：逐一检查所有硬约束（代码验证，不靠 AI）
5. 验证通过 → 输出；失败 → 高亮违反项，提示用户或触发阶段 3b
```

**阶段 3b（完整版）：约束满足求解器**

适用于约束多、Pensil 方案不可行的场景：

```python
# unilabos/layout/solver.py
from scipy.optimize import differential_evolution
import numpy as np

def cost_function(positions: np.ndarray, devices: list,
                  constraints: list, reachability_maps: dict) -> float:
    """
    positions: 展平的 (x1,y1,θ1, x2,y2,θ2, ...) 数组
    返回总代价（硬约束违反返回 inf）
    """
    layout = decode_positions(positions, devices)

    total_cost = 0.0
    for constraint in constraints:
        violation = evaluate_constraint(constraint, layout, reachability_maps)
        if constraint.penalty == float('inf') and violation > 0:
            return float('inf')   # 硬约束违反，方案直接淘汰
        total_cost += constraint.penalty * violation

    return total_cost

def solve_layout(devices: list, lab_bounds: tuple,
                 constraints: list) -> dict:
    """使用差分进化（全局优化）求解布局。"""
    bounds = [(0, lab_bounds[0]), (0, lab_bounds[1]), (0, 2*np.pi)] * len(devices)
    result = differential_evolution(
        cost_function, bounds,
        args=(devices, constraints, {}),
        maxiter=1000, tol=1e-6, seed=42
    )
    return decode_positions(result.x, devices)
```

**无解情况处理**：

```python
def solve_with_relaxation(devices, lab_bounds, constraints):
    """约束松弛策略：硬约束无解时，逐步降级为软约束并提示用户。"""
    hard = [c for c in constraints if c.penalty == float('inf')]
    soft = [c for c in constraints if c.penalty < float('inf')]

    result = solve_layout(devices, lab_bounds, hard + soft)
    if result is None:
        # 尝试逐一松弛最可能冲突的硬约束
        for i, hc in enumerate(hard):
            relaxed = hard[:i] + hard[i+1:] + soft
            result = solve_layout(devices, lab_bounds, relaxed)
            if result:
                return result, f"警告：无法满足约束 [{hc.name}]，已自动降级，请人工确认"
    return result, None
```

### 5.4 对接 `deploy_master` 设备筛选

```python
# 在 app/web/api.py 新增端点
@router.post("/api/layout/recommend")
async def recommend_devices(scene: SceneRequest):
    """
    根据用户选择的实验场景，从 registry 中推荐设备列表。
    对接 deploy_master 的设备筛选功能。
    """
    from unilabos.registry.registry import lab_registry
    # 从 registry 中查找支持该场景所需 action 的设备
    required_actions = SCENE_ACTION_MAP[scene.name]  # 如 PCR 需要 HeatChill + Centrifuge
    recommended = [
        device_id
        for device_id, cfg in lab_registry.device_type_registry.items()
        if any(a in cfg.get("action_value_mappings", {}) for a in required_actions)
    ]
    return {"devices": recommended}
```

---

## 六、关键技术细节补充

### 6.1 URDF 发布策略

Uni-Lab OS 的实验室可能有多台机器人，需要用**命名空间**隔离各自的 `/joint_states` 和 `/tf`，再合并到世界坐标系：

```xml
<!-- 每台设备的 Xacro 宏挂载在世界坐标系下的固定 frame -->
<joint name="world_to_elite_arm_1" type="fixed">
  <parent link="world"/>
  <child link="elite_arm_1/base_link"/>
  <origin xyz="0.5 0.0 0.0" rpy="0 0 0"/>  <!-- ResourceVisualization 填入位置 -->
</joint>
```

所有设备共享同一个 `robot_state_publisher`（发布合并 URDF），前端只需订阅一个 `/robot_description` 和一组 `/joint_states`。

### 6.2 前端 2D/3D 切换

```javascript
// 一键切换，照顾低带宽环境
let is3D = true;
document.getElementById('toggle-view').onclick = () => {
    is3D = !is3D;
    if (is3D) {
        viewer.renderer.setSize(1200, 600);
        // 重新订阅 /joint_states_throttled（25Hz）
        jointStateSub.subscribe(updateURDF);
    } else {
        // 切换到 SVG 2D 平面图（从 layout JSON 直接渲染，无需 ROS）
        render2DLayout(currentLayout);
        jointStateSub.unsubscribe();  // 停止 ROS 数据流，节省带宽
    }
};
```

### 6.3 Aliyun OSS 模型托管

`robot_arm.yaml` 中已有 `model.path: https://uni-lab.oss-cn-zhangjiakou.aliyuncs.com/...` 字段，说明云端模型存储路径已规划。前端的 `path: '/static/meshes/'` 应映射到 OSS：

```python
# app/web/api.py - 静态文件代理或重定向
@router.get("/static/meshes/{device}/{filename}")
async def serve_mesh(device: str, filename: str):
    oss_url = f"https://uni-lab.oss-cn-zhangjiakou.aliyuncs.com/meshes/{device}/{filename}"
    return RedirectResponse(url=oss_url)
```

---

## 七、实施路线图

### 阶段一（第 1-4 周）

| 周次 | 任务 | 交付物 | 验收标准 |
|------|------|--------|---------|
| 第 1 周 | 资产盘点脚本 + 模型零点规范化 | `scripts/check_assets.py` + 修正后的 Xacro | 所有已有设备零点符合规范 |
| 第 2 周 | `ResourceVisualization` 集成 ROSBridge2 + ThrottlerNode | `throttler_node.py` + 更新后的 launch | RViz2 和浏览器同时渲染同一场景 |
| 第 3 周 | 前端 3D 视图（ros3djs 集成到 Jinja2 模板） | `lab3d.html` + `POST /api/lab/layout` | 浏览器内显示 Elite 机械臂 + 实验台静态场景 |
| 第 4 周 | 优先补充缺失设备建模（P0：离心机、天平） | 新 Xacro + STL 文件 | 可视化场景中加入这两类设备 |

### 阶段二（第 5-8 周）

| 周次 | 任务 | 交付物 | 验收标准 |
|------|------|--------|---------|
| 第 5 周 | `JointStateAdapterNode` | `joint_state_adapter.py` | 机械臂执行动作时浏览器内实时跟随 |
| 第 6 周 | `PlanningSceneManager`（CollisionObject 注册） | `planning_scene_manager.py` | MoveIt2 规划路径自动绕开所有设备 |
| 第 7 周 | Attached Collision Object（耗材附着/释放） | 扩展 `PlanningSceneManager` | 机械臂抓取 96 孔板后碰撞体跟随移动 |
| 第 8 周 | 轨迹预览前端动画 + 性能调优 | 前端 JS 动画回放 | 工作流执行前可预览路径，帧率 ≥ 20fps |

### 阶段三（第 9-14 周）

| 周次 | 任务 | 交付物 | 验收标准 |
|------|------|--------|---------|
| 第 9-10 周 | 离线可达性地图生成（Elite CS 系列） | `scripts/generate_reachability_map.py` + `.npz` 文件 | 对任意底座位置可在 1ms 内查表 |
| 第 11 周 | 约束规则体系 + 硬编码规则 API | `layout/constraints.py` | 支持 `distance_less_than` / `distance_greater_than` |
| 第 12-13 周 | 布局求解器 MVP（Pensil + 验证层） | `layout/solver.py` + 验证器 | 输出布局方案，所有硬约束均通过验证 |
| 第 14 周 | 对接 `deploy_master` + 2D/3D 一键切换 | `POST /api/layout/recommend` | 选择场景后自动推荐设备并输出布局 |

---

## 八、各阶段验收指标

| 阶段 | 指标 | 目标值 |
|------|------|--------|
| 阶段一 | 场景加载时间（5台设备） | < 10 秒 |
| 阶段一 | 支持同时展示的最大设备数 | ≥ 15 台 |
| 阶段二 | 工作流下发 → 前端关节动画延迟 | < 150ms |
| 阶段二 | 前端渲染帧率（工作流执行中） | ≥ 20fps |
| 阶段二 | MoveIt2 规划时间（5台设备场景） | < 500ms |
| 阶段三 | AI 布局单次迭代时间 | < 5 秒 |
| 阶段三 | 可达性查表时间 | < 1ms |
| 阶段三 | 输出方案的硬约束满足率 | 100% |
