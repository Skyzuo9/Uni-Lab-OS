# Uni-Lab 云端 3D 实验室——阶段二分步实施指南
# 工作流 3D 模拟同步

> **阶段二目标**：在浏览器中看到**实验室运行过程的实时 3D 动画**——工作流下发后，机械臂移动、耗材被抓取搬运、设备状态变色，全部同步反映在 3D 场景中；执行前还可预览规划轨迹。
>
> **阶段一已交付**：静态 3D 场景渲染、设备拖拽布局、OBB 碰撞检测、`/api/v1/urdf` + `/meshes` 接口、Foxglove Bridge 连接
>
> **总工期估算**：约 8-12 个工作日  

---

## 现有代码盘点（阶段二视角）

在开始之前，必须清楚哪些已经有了、哪些需要新建。以下是基于源码的逐项审计：

| 能力 | 状态 | 源码位置 | 说明 |
|------|------|----------|------|
| Elite Robot 直接发布 `/joint_states` | ✅ 已有 | `devices/arm/elite_robot.py:21,177-184` | 每次 `get_actual_joint_positions()` 时发布，但非定时 |
| `PropertyPublisher` 5s 定时发布 | ✅ 已有 | `ros/nodes/base_device_node.py:175-204` | 支持 `change_frequency()` 动态改频 |
| `ResourceMeshManager` 耗材 TF 广播 | ✅ 已有 | `ros/nodes/presets/resource_mesh_manager.py:93-94,289-371` | `resource_pose` 话题，50Hz 检测变化并发布 JSON |
| `ResourceMeshManager` attach/detach | ✅ 已有 | `resource_mesh_manager.py:405-499` | `tf_update` Action Server，完整的 PlanningScene 操作 |
| `JointRepublisher`（JointState → JSON） | ✅ 已有 | `ros/nodes/presets/joint_republisher.py` | 订阅 `/joint_states` 发布 JSON 到 `joint_state_repub` |
| `/ws/device_status` WebSocket | ✅ 已有 | `app/web/api.py:84-109,243-256` | 1Hz 推送设备状态 JSON |
| `move_group` MoveIt2 启动 | ✅ 已有 | `device_mesh/resource_visalization.py:336-371` | OMPL 规划管线，PlanningScene 发布 |
| `JointStateAdapterNode`（高频补发） | ❌ 需新建 | — | 为非 ros2_control 设备补充 50Hz 关节状态 |
| 轨迹预览前端 | ❌ 需新建 | — | 订阅 `DisplayTrajectory`，时间轴回放 |
| 耗材动画前端对接 | ❌ 需新建 | — | 订阅 `resource_pose`，更新 Three.js 场景 |
| 设备状态着色前端 | ❌ 需新建 | — | 订阅 `/ws/device_status`，颜色映射 |

---

## 整体路线图

```
Step 0  阶段一完成度验证                 ─── 0.5天
Step 1  Elite Robot 高频关节状态发布     ─── 1天    ← 动画基础
Step 2  前端实时关节动画                 ─── 2天    ← 核心视觉效果
Step 3  耗材附着/释放前端动画            ─── 2天    ← 搬运流程可视化
Step 4  设备状态实时着色                 ─── 1天
Step 5  轨迹预览播放器                   ─── 2.5天  ← 规划可视化
Step 6  端到端工作流演示验证             ─── 1天
```

> **关键依赖链**：Step 1 → Step 2（关节动画）→ Step 3（耗材动画需要关节驱动 TF）  
> Step 4 与 Step 2 可并行；Step 5 在 Step 2 完成后开始

---

## Step 0：阶段一完成度验证

在开始阶段二之前，逐项确认阶段一的交付物：

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS

# 启动系统（web 模式）
python -m unilabos \
    --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
    --visual web \
    --port 8002

# ── 以下在另一个终端执行 ──
conda activate unilab

# 检查 1: URDF 接口
curl -s http://localhost:8002/api/v1/urdf | head -3
# 预期: <?xml version="1.0"?><robot name="full_dev">...

# 检查 2: 无 file:// 路径
curl -s http://localhost:8002/api/v1/urdf | grep -c "file://"
# 预期: 0

# 检查 3: STL 文件可 HTTP 访问
curl -sI http://localhost:8002/meshes/devices/arm_slider/meshes/arm_slideway.STL | head -1
# 预期: HTTP/1.1 200 OK

# 检查 4: Foxglove Bridge 端口
timeout 3 ros2 run foxglove_bridge foxglove_bridge 2>&1 | grep -i "listen"
# 预期: Listening on port 8765（如已在系统内启动则端口已占用，也算通过）

# 检查 5: ROS2 话题
ros2 topic list | grep -E "/tf|/joint_states|/robot_description"
# 预期: 至少出现 /tf、/tf_static、/robot_description

# 检查 6: /lab3d 页面（浏览器手动验证）
# 访问 http://localhost:8002/lab3d，3D 场景应正常渲染

# 检查 7: PlanningScene 碰撞物体
ros2 service call /get_planning_scene moveit_msgs/srv/GetPlanningScene "{}" | grep "collision_objects" | head -3
# 预期: 有碰撞物体条目
```

> 如果任何检查失败，需先回到 `Uni-Lab-3D-Phase1-Guide.md` 补完对应步骤。

---

## Step 1：Elite Robot 高频关节状态发布（1 天）

### 1.1 问题分析

当前 `EliteRobot.get_actual_joint_positions()`（`devices/arm/elite_robot.py:177`）在每次调用时同步发布 `/joint_states`，但这个方法**只在 `modbus_task()` 执行动作时被循环调用**（第 134 行 `while` 循环内，约 10Hz），**空闲状态下无人调用，频率为 0**。

前端动画需要至少 20Hz 的稳定 `/joint_states` 数据流，否则模型静止不动或跳帧。

### 1.2 方案选择

| 方案 | 优点 | 缺点 |
|------|------|------|
| A: 在 EliteRobot 内加 50Hz 定时器 | 改动最小（3 行代码） | 侵入设备驱动层，空闲时每秒 50 次 TCP 请求 |
| B: 新建 JointStateAdapterNode 订阅 PropertyPublisher 转发 | 解耦 | PropertyPublisher 默认 5s，需要先改频率 |
| **C: 新建独立定时器节点，直接调用设备驱动 API** | **解耦 + 频率可控 + 不双重发布** | 需要持有设备驱动引用 |

**选择方案 A**（最小改动优先），在 Elite Robot 空闲时也定时轮询关节角。

### 1.3 修改 `elite_robot.py`

**文件**：`unilabos/devices/arm/elite_robot.py`

在 `__init__` 末尾添加定时器，仅在连接成功时启用：

```python
# ── 在 __init__ 末尾（约第 36 行之后）添加 ──

# 高频关节状态定时发布（50Hz，供前端 3D 动画使用）
self._joint_poll_rate = 20.0  # Hz，Elite SDK TCP 建议不超过 50Hz
self._joint_poll_timer = self.node.create_timer(
    1.0 / self._joint_poll_rate,
    self._poll_joint_state
)
self._last_joint_positions = None

def _poll_joint_state(self):
    """定时轮询关节角并发布，避免只在动作执行时才有数据"""
    try:
        response = self.send_command("req 1 get_actual_joint_positions()\n")
        joint_positions = self.parse_success_response(response)
        if joint_positions:
            self._last_joint_positions = joint_positions
            self.joint_state_msg.header.stamp = self.node.get_clock().now().to_msg()
            self.joint_state_msg.position = joint_positions
            self.joint_state_pub.publish(self.joint_state_msg)
    except Exception:
        pass  # TCP 断连时静默跳过，不影响主流程
```

同时给 `joint_state_msg` 加上 `header.stamp`，这是 `robot_state_publisher` 正确处理 TF 时序的要求：

```python
# ── 修改 __init__ 中 joint_state_msg 初始化（约第 12 行） ──
# 修改前：
self.joint_state_msg = JointState()

# 修改后：
from std_msgs.msg import Header
self.joint_state_msg = JointState()
self.joint_state_msg.header = Header()
```

### 1.4 去除 `modbus_task` 中的冗余调用

`modbus_task()` 第 134 行的 `self.get_actual_joint_positions()` 现在由定时器覆盖，但保留无害（最多是多发一次）。如果 Elite SDK 不支持并发 TCP 请求，则需要加锁：

```python
# ── 在 __init__ 中添加锁 ──
import threading
self._tcp_lock = threading.Lock()

# ── 修改 send_command ──
def send_command(self, command):
    with self._tcp_lock:
        self.sock.sendall(command.encode('utf-8'))
        response = self.sock.recv(1024).decode('utf-8')
    return response
```

### 1.5 对非 Elite 设备的处理

对于通过 `PropertyPublisher` 发布关节状态的其他设备（如 `arm_slider` 等 ros2_control 设备），不需要任何改动——它们已经有 `joint_state_broadcaster` 以 100Hz 发布 `/joint_states`。

对于其他无 ros2_control 的自定义设备，在对应驱动类中复制同样的定时器模式即可。

### 1.6 验证

```bash
# 启动系统后（Elite Robot 已连接或使用 mock 模式），检查 /joint_states 频率
ros2 topic hz /joint_states
# 预期: average rate: 20.0Hz（如有 arm_slider 等设备会更高，混合后应 >= 20Hz）

# 检查关节名称
ros2 topic echo /joint_states --once | grep "name"
# 预期: 包含 elite_xxx_shoulder_pan_joint 等 6 个关节
```

---

## Step 2：前端实时关节动画（2 天）

### 2.1 数据流架构

```
EliteRobot 20Hz → /joint_states → robot_state_publisher → /tf
arm_slider 100Hz → /joint_states ─┘                        │
                                                            ▼
                                    Foxglove Bridge ws://8765
                                                            │
                                          throttle_rate=40ms (≈25Hz)
                                                            ▼
                                        前端 ros-bridge.js 订阅 /tf
                                                            │
                                                            ▼
                                        urdf-scene.js 更新关节角
```

**关键设计决策**：

- **不使用独立 ThrottlerNode**：Foxglove Bridge / ROSBridge 均支持订阅参数内置降频
- **不降频 `/tf_static`**：latched 话题，仅在首次连接时传输一次
- **`/tf`（动态）降频到 25Hz**：前端动画足够流畅，保护浏览器性能

### 2.2 修改 `ros-bridge.js`：添加 `/joint_states` 订阅

在阶段一创建的 `ros-bridge.js` 中扩展：

```javascript
// ── 新增：订阅 /joint_states（Foxglove WebSocket 协议） ──

export class RosBridge {
    constructor(url = 'ws://localhost:8765') {
        this.url = url;
        this.ws = null;
        this.callbacks = {};
        this._channelMap = {};
    }

    connect() {
        this.ws = new WebSocket(this.url, ['foxglove.websocket.v1']);
        this.ws.binaryType = 'arraybuffer';

        this.ws.onopen = () => {
            console.log('[RosBridge] 已连接', this.url);
            this._subscribe('/joint_states', 'sensor_msgs/msg/JointState', 40);
            this._subscribe('/tf', 'tf2_msgs/msg/TFMessage', 40);
        };

        this.ws.onmessage = (event) => {
            if (typeof event.data === 'string') {
                const msg = JSON.parse(event.data);
                this._handleServerMessage(msg);
            } else {
                this._handleBinaryMessage(event.data);
            }
        };
    }

    _subscribe(topic, type, throttleMs = 0) {
        // Foxglove 协议：先 advertise channel，再 subscribe
        // 具体实现取决于 Foxglove WebSocket 版本
        // 此处为简化示意，实际使用 @foxglove/ws-protocol 库
    }

    on(topic, callback) {
        if (!this.callbacks[topic]) this.callbacks[topic] = [];
        this.callbacks[topic].push(callback);
    }

    _dispatch(topic, data) {
        (this.callbacks[topic] || []).forEach(cb => cb(data));
    }
}
```

### 2.3 修改 `urdf-scene.js`：驱动关节旋转

在阶段一创建的 `urdf-scene.js` 中添加关节更新逻辑：

```javascript
// ── 新增方法：接收 /joint_states 更新 URDF 关节角 ──

/**
 * 更新 URDF 模型的关节角度。
 * urdf-loader 加载后的 robot 对象暴露 .joints 属性，
 * 每个 joint 有 .setJointValue(angle) 方法。
 *
 * @param {Object} jointState - { name: string[], position: number[] }
 */
export function updateJointState(robot, jointState) {
    if (!robot || !robot.joints) return;

    const { name, position } = jointState;
    for (let i = 0; i < name.length; i++) {
        const joint = robot.joints[name[i]];
        if (joint) {
            joint.setJointValue(position[i]);
        }
    }
}

// 在 main.js 中连接：
// rosBridge.on('/joint_states', (msg) => {
//     updateJointState(robot, msg);
// });
```

### 2.4 修改 `main.js`：组合关节动画

```javascript
import { createScene, loadURDF, updateJointState } from './urdf-scene.js';
import { RosBridge } from './ros-bridge.js';

const scene = createScene(document.getElementById('canvas-3d'));
const bridge = new RosBridge('ws://' + window.location.hostname + ':8765');

// 加载 URDF
const robot = await loadURDF('/api/v1/urdf');
scene.add(robot);

// 连接 ROS Bridge
bridge.connect();

// 关节状态实时更新（阶段二核心）
bridge.on('/joint_states', (msg) => {
    updateJointState(robot, msg);
});

// 渲染循环
function animate() {
    requestAnimationFrame(animate);
    scene.render();
}
animate();
```

### 2.5 验证

```
测试用例：
1. 启动系统（带 Elite Robot 或 arm_slider）
2. 通过 POST /api/job/add 下发一个简单动作（如机械臂归零）
3. 浏览器打开 /lab3d
4. 观察机械臂模型是否跟随真实/仿真关节角运动

验收标准：
- 机械臂模型 20fps 以上流畅运动
- 从动作下发到前端可见动画，延迟 < 200ms
- 空闲状态下模型静止（不抖动）
```

---

## Step 3：耗材附着/释放前端动画（2 天）

### 3.1 后端现状——已有实现，无需修改

`ResourceMeshManager` 已完整实现耗材生命周期：

```
初始状态: 96 孔板作为 CollisionObject 在工作台上
    ↓ tf_update Action（command: {"plate_96_1": "elite_arm_tool0"}）
抓取:    从 PlanningScene 移除 → 附着到末端执行器 link
    ↓ robot_state_publisher 自动更新 TF（板跟随末端移动）
搬运中:  MoveIt2 规划自动考虑附着物体积（避障）
    ↓ tf_update Action（command: {"plate_96_1": "world"}）
释放:    从末端分离 → 重新注册为 CollisionObject 到新位置
```

`resource_pose` 话题（`resource_mesh_manager.py:93`）以 50Hz 检测并发布耗材位姿变化的 JSON：

```json
{
    "plate_96_1": {
        "position": {"x": 0.5, "y": 0.3, "z": 0.8},
        "rotation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
    }
}
```

### 3.2 前端新增：耗材位姿订阅

**文件**：`unilabos/app/web/static/lab3d/resource-tracker.js`（新建）

```javascript
/**
 * 耗材位姿追踪器。
 * 订阅 resource_pose 话题，在 Three.js 场景中
 * 实时更新耗材 mesh 的位置和旋转。
 */

export class ResourceTracker {
    constructor(scene, rosBridge) {
        this.scene = scene;
        this.bridge = rosBridge;
        this.resourceMeshes = new Map();
    }

    /**
     * 初始化耗材 mesh 并开始订阅。
     * @param {Object} resourceList - 从 /api/v1/urdf 解析出的耗材列表
     */
    init(resourceList) {
        // 为每个耗材在场景中标记可追踪的 mesh
        resourceList.forEach(res => {
            const mesh = this.scene.getObjectByName(res.id);
            if (mesh) {
                this.resourceMeshes.set(res.id, mesh);
            }
        });

        // 订阅 resource_pose 话题
        this.bridge.on('resource_pose', (msg) => {
            this._onResourcePoseUpdate(msg);
        });
    }

    _onResourcePoseUpdate(msg) {
        let changes;
        try {
            // resource_pose 是 std_msgs/String，data 字段为 JSON
            changes = typeof msg.data === 'string'
                ? JSON.parse(msg.data)
                : msg;
        } catch (e) {
            return;
        }

        for (const [resourceId, pose] of Object.entries(changes)) {
            const mesh = this.resourceMeshes.get(resourceId);
            if (!mesh) continue;

            if (pose.position) {
                mesh.position.set(
                    pose.position.x,
                    pose.position.y,
                    pose.position.z
                );
            }
            if (pose.rotation) {
                mesh.quaternion.set(
                    pose.rotation.x,
                    pose.rotation.y,
                    pose.rotation.z,
                    pose.rotation.w
                );
            }
        }
    }
}
```

### 3.3 附着视觉反馈

当耗材从工作台转移到末端执行器时，需要视觉提示：

```javascript
// 在 _onResourcePoseUpdate 中添加视觉反馈
_onResourcePoseUpdate(msg) {
    // ...（前面的位姿更新逻辑）

    for (const [resourceId, pose] of Object.entries(changes)) {
        const mesh = this.resourceMeshes.get(resourceId);
        if (!mesh) continue;

        // 附着状态检测：parent 不是 world 说明被抓取
        const isAttached = pose.parent && pose.parent !== 'world';

        // 视觉反馈：被抓取时半透明蓝色边框
        if (mesh.userData._outlineMesh) {
            mesh.userData._outlineMesh.visible = isAttached;
        }
    }
}
```

### 3.4 验证

```
测试用例：
1. graph JSON 中包含 arm_slider + plate_96
2. 启动系统，/lab3d 显示板在工作台上
3. 通过 ROS2 Action 发送 tf_update：{"plate_96_1": "arm_slider_tool0"}
4. 观察板是否从工作台飞到机械臂末端
5. 再发送 tf_update：{"plate_96_1": "world"}
6. 观察板是否回到场景中某个位置

验证命令（模拟 tf_update Action）：
ros2 action send_goal /tf_update unilabos_msgs/action/SendCmd \
    "{command: '{\"plate_96_1\": \"arm_slider_tool0\"}'}"
```

---

## Step 4：设备状态实时着色（1 天）

### 4.1 后端现状——已有实现

`/ws/device_status`（`api.py:243`）每秒推送所有设备状态：

```json
{
    "type": "device_status",
    "data": {
        "device_status": {
            "arm_slider": "idle",
            "elite_arm_1": "running",
            "thermo_orbitor": "error"
        },
        "device_status_timestamps": { ... }
    }
}
```

### 4.2 前端新增：状态着色模块

**文件**：`unilabos/app/web/static/lab3d/status-overlay.js`（新建）

```javascript
/**
 * 设备状态着色叠加层。
 * 通过 FastAPI WebSocket 接收设备状态，
 * 根据状态改变对应设备 mesh 的材质颜色/透明度。
 */

const STATUS_COLORS = {
    idle:      0x888888,  // 灰色
    running:   0x2196F3,  // 蓝色
    completed: 0x4CAF50,  // 绿色
    error:     0xF44336,  // 红色
    warning:   0xFF9800,  // 橙色
};

export class StatusOverlay {
    constructor(scene) {
        this.scene = scene;
        this.ws = null;
        this.deviceMeshes = new Map();
        this._originalMaterials = new Map();
    }

    init(deviceList) {
        deviceList.forEach(dev => {
            const mesh = this.scene.getObjectByName(dev.id);
            if (mesh) {
                this.deviceMeshes.set(dev.id, mesh);
                this._originalMaterials.set(dev.id, mesh.material?.clone());
            }
        });

        this._connectWebSocket();
    }

    _connectWebSocket() {
        const wsUrl = `ws://${window.location.host}/api/v1/ws/device_status`;
        this.ws = new WebSocket(wsUrl);

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'device_status') {
                    this._applyStatusColors(msg.data.device_status);
                }
            } catch (e) { /* ignore */ }
        };

        this.ws.onclose = () => {
            setTimeout(() => this._connectWebSocket(), 3000);
        };
    }

    _applyStatusColors(statusMap) {
        for (const [deviceId, status] of Object.entries(statusMap)) {
            const mesh = this.deviceMeshes.get(deviceId);
            if (!mesh) continue;

            const color = STATUS_COLORS[status] || STATUS_COLORS.idle;

            mesh.traverse(child => {
                if (child.isMesh && child.material) {
                    child.material = child.material.clone();
                    child.material.emissive?.setHex(color);
                    child.material.emissiveIntensity = (status === 'idle') ? 0 : 0.3;
                }
            });
        }
    }
}
```

### 4.3 集成到 `main.js`

```javascript
import { StatusOverlay } from './status-overlay.js';

const statusOverlay = new StatusOverlay(scene);
statusOverlay.init(deviceList);
```

### 4.4 验证

```
1. 下发工作流（POST /api/job/add），使某个设备变为 running
2. 观察 /lab3d 中该设备变蓝
3. 工作流完成后变绿
4. 模拟异常（停止设备）观察变红
```

---

## Step 5：轨迹预览播放器（2.5 天）

### 5.1 数据源

MoveIt2 `move_group` 在规划成功后会发布 `/move_group/display_planned_path`（类型：`moveit_msgs/msg/DisplayTrajectory`）。消息结构：

```
DisplayTrajectory
  └─ trajectory[]                    # 可能有多段
       └─ joint_trajectory           # JointTrajectory
            ├─ joint_names[]         # ["shoulder_pan_joint", ...]
            └─ points[]              # JointTrajectoryPoint
                 ├─ positions[]      # [1.57, -0.8, ...]  弧度
                 ├─ velocities[]     # （可选）
                 └─ time_from_start  # Duration {sec, nanosec}
```

### 5.2 前端新增：轨迹播放器

**文件**：`unilabos/app/web/static/lab3d/trajectory-player.js`（新建）

```javascript
/**
 * 轨迹预览播放器。
 * 订阅 MoveIt2 规划轨迹，提供播放/暂停/进度条控制，
 * 逐帧更新 URDF 关节角实现动画预览。
 */

import { updateJointState } from './urdf-scene.js';

export class TrajectoryPlayer {
    constructor(robot, uiContainer) {
        this.robot = robot;
        this.trajectory = null;
        this.isPlaying = false;
        this.playbackSpeed = 1.0;
        this._startTime = 0;
        this._animFrameId = null;

        this._buildUI(uiContainer);
    }

    /**
     * 接收 DisplayTrajectory 消息并准备播放。
     */
    loadTrajectory(displayTrajectory) {
        if (!displayTrajectory.trajectory ||
            displayTrajectory.trajectory.length === 0) return;

        // 取第一段轨迹
        const jt = displayTrajectory.trajectory[0].joint_trajectory;
        if (!jt || !jt.points || jt.points.length === 0) return;

        this.trajectory = {
            jointNames: jt.joint_names,
            points: jt.points.map(pt => ({
                positions: pt.positions,
                timeFromStart: pt.time_from_start.sec
                    + pt.time_from_start.nanosec * 1e-9,
            })),
        };

        const totalTime = this.trajectory.points[
            this.trajectory.points.length - 1
        ].timeFromStart;

        this._updateUI(totalTime);
        console.log(`[TrajectoryPlayer] 已加载轨迹，${this.trajectory.points.length} 个路点，总时长 ${totalTime.toFixed(2)}s`);
    }

    play() {
        if (!this.trajectory) return;
        this.isPlaying = true;
        this._startTime = performance.now();
        this._playbackLoop();
    }

    pause() {
        this.isPlaying = false;
        if (this._animFrameId) {
            cancelAnimationFrame(this._animFrameId);
        }
    }

    _playbackLoop() {
        if (!this.isPlaying) return;

        const elapsed = (performance.now() - this._startTime) / 1000
            * this.playbackSpeed;
        const totalTime = this.trajectory.points[
            this.trajectory.points.length - 1
        ].timeFromStart;

        if (elapsed >= totalTime) {
            // 播放结束，应用最后一帧
            this._applyFrame(this.trajectory.points.length - 1);
            this.isPlaying = false;
            return;
        }

        // 找到当前时间点对应的两个相邻路点，做线性插值
        const { index, alpha } = this._findSegment(elapsed);
        this._applyInterpolated(index, alpha);

        this._animFrameId = requestAnimationFrame(() => this._playbackLoop());
    }

    _findSegment(time) {
        const pts = this.trajectory.points;
        for (let i = 0; i < pts.length - 1; i++) {
            if (time >= pts[i].timeFromStart && time < pts[i + 1].timeFromStart) {
                const segDuration = pts[i + 1].timeFromStart - pts[i].timeFromStart;
                const alpha = (time - pts[i].timeFromStart) / segDuration;
                return { index: i, alpha };
            }
        }
        return { index: pts.length - 1, alpha: 0 };
    }

    _applyInterpolated(index, alpha) {
        const pts = this.trajectory.points;
        const p0 = pts[index].positions;
        const p1 = pts[Math.min(index + 1, pts.length - 1)].positions;

        const interpolated = p0.map((v, i) => v + (p1[i] - v) * alpha);

        updateJointState(this.robot, {
            name: this.trajectory.jointNames,
            position: interpolated,
        });
    }

    _applyFrame(index) {
        updateJointState(this.robot, {
            name: this.trajectory.jointNames,
            position: this.trajectory.points[index].positions,
        });
    }

    _buildUI(container) {
        // 创建播放控制面板（播放/暂停按钮 + 进度条 + 速度选择）
        const panel = document.createElement('div');
        panel.id = 'trajectory-panel';
        panel.innerHTML = `
            <div style="background:rgba(0,0,0,0.7);color:#fff;padding:8px;border-radius:6px;display:none" id="traj-controls">
                <span>轨迹预览</span>
                <button id="traj-play">▶ 播放</button>
                <button id="traj-pause">⏸ 暂停</button>
                <select id="traj-speed">
                    <option value="0.25">0.25x</option>
                    <option value="0.5">0.5x</option>
                    <option value="1" selected>1x</option>
                    <option value="2">2x</option>
                </select>
                <span id="traj-duration"></span>
            </div>
        `;
        container.appendChild(panel);

        panel.querySelector('#traj-play')?.addEventListener('click', () => this.play());
        panel.querySelector('#traj-pause')?.addEventListener('click', () => this.pause());
        panel.querySelector('#traj-speed')?.addEventListener('change', (e) => {
            this.playbackSpeed = parseFloat(e.target.value);
        });
    }

    _updateUI(totalTime) {
        const ctrl = document.getElementById('traj-controls');
        if (ctrl) {
            ctrl.style.display = 'flex';
            ctrl.querySelector('#traj-duration').textContent =
                `${totalTime.toFixed(1)}s`;
        }
    }
}
```

### 5.3 订阅轨迹话题

在 `main.js` 中：

```javascript
import { TrajectoryPlayer } from './trajectory-player.js';

const trajectoryPlayer = new TrajectoryPlayer(robot, document.body);

// 通过 Foxglove Bridge 订阅 display_planned_path
bridge.on('/move_group/display_planned_path', (msg) => {
    trajectoryPlayer.loadTrajectory(msg);
});
```

### 5.4 触发轨迹规划（测试用）

```bash
# 使用 MoveIt2 命令行触发一次规划（不执行）
ros2 action send_goal /move_group/plan moveit_msgs/action/MoveGroup \
    "{planning_options: {plan_only: true}}"

# 或通过 Python 脚本
python -c "
from moveit_py import MoveItPy
# ...（MoveIt2 Python API 规划示例）
"
```

### 5.5 验证

```
1. 触发 MoveIt2 规划
2. /lab3d 中出现"轨迹预览"控制面板
3. 点击播放，机械臂按规划路径预演
4. 调整速度到 0.5x/2x，动画速度对应变化
5. 未执行前用户可反复预览
```

---

## Step 6：端到端工作流演示验证（1 天）

### 6.1 完整数据流确认

```
用户 POST /api/job/add（"将 plate_96 从工作台搬到 HPLC"）
    ↓
HostNode → ROS2 Action Goal → EliteRobot.modbus_task_cmd("lh2hplc")
    ↓
EliteRobot._poll_joint_state() → /joint_states (20Hz)
    ↓
robot_state_publisher → /tf（机械臂关节 TF）
    ↓
ResourceMeshManager.tf_update() → 耗材附着 → resource_pose（50Hz）
    ↓
Foxglove Bridge → ws://8765
    ↓
前端 ros-bridge.js → urdf-scene.js（关节动画）
                    → resource-tracker.js（耗材跟随）
                    → status-overlay.js（设备变蓝）
```

### 6.2 验收测试清单

| 测试项 | 操作 | 预期结果 |
|--------|------|----------|
| 关节动画 | POST 一个机械臂移动任务 | 前端模型同步运动，帧率 ≥ 20fps |
| 耗材跟随 | 机械臂抓取 96 孔板 | 板从工作台飞到末端执行器 |
| 耗材释放 | 机械臂释放板到新位置 | 板脱离末端，出现在新坐标 |
| 设备着色 | 任务执行中 | 活动设备变蓝色 |
| 任务完成 | 任务结束 | 设备变灰/绿色 |
| 轨迹预览 | 规划一个运动 | 出现播放面板，可预览 |
| 延迟 | 任务下发到前端可见 | < 200ms |
| 多设备 | 5 台设备同时工作 | 各自动画互不干扰 |
| 异常恢复 | 断开 WS 后重连 | 自动恢复数据流 |

### 6.3 性能指标

```bash
# 测量前端帧率（在浏览器控制台）
# F12 → Console 输入：
let frames = 0;
const start = performance.now();
function countFrame() { frames++; requestAnimationFrame(countFrame); }
requestAnimationFrame(countFrame);
setTimeout(() => {
    const fps = frames / ((performance.now() - start) / 1000);
    console.log(`FPS: ${fps.toFixed(1)}`);
}, 5000);
# 预期: >= 20fps（5 台设备场景）
```

```bash
# 测量 /joint_states 到前端的延迟
# 在 ros-bridge.js 中记录接收时间戳，与 msg.header.stamp 比较
# 差值应 < 150ms
```

---

## 附录 A：文件改动速查表

| 文件 | 改动类型 | 步骤 |
|------|----------|------|
| `unilabos/devices/arm/elite_robot.py` | 新增 `_poll_joint_state` 定时器 + TCP 锁 | Step 1 |
| `unilabos/app/web/static/lab3d/ros-bridge.js` | 扩展 Foxglove 订阅逻辑 | Step 2 |
| `unilabos/app/web/static/lab3d/urdf-scene.js` | 新增 `updateJointState()` | Step 2 |
| `unilabos/app/web/static/lab3d/main.js` | 组合关节/耗材/状态/轨迹模块 | Step 2-5 |
| `unilabos/app/web/static/lab3d/resource-tracker.js` | **新建**：耗材位姿追踪 | Step 3 |
| `unilabos/app/web/static/lab3d/status-overlay.js` | **新建**：设备状态着色 | Step 4 |
| `unilabos/app/web/static/lab3d/trajectory-player.js` | **新建**：轨迹预览播放器 | Step 5 |

**后端无新建文件**——阶段二的后端能力已由现有代码覆盖，仅需对 `elite_robot.py` 做小幅修改。

---

## 附录 B：与阶段一原始 Phase 2 文档的差异对照

| 原文档描述 | 本指南修正 | 原因 |
|-----------|-----------|------|
| 新建 JointStateAdapterNode 订阅 PropertyPublisher | 在 EliteRobot 内加 20Hz 定时器 | EliteRobot 已有 `/joint_states` publisher，Adapter 会双重发布 |
| 新建 ThrottlerNode 降频 | 删除，使用 Foxglove/ROSBridge 内置 throttle_rate | 无需额外节点 |
| 耗材附着与释放 [待开发] | 改为 [后端已有，需前端对接] | `ResourceMeshManager.tf_update()` 已完整实现 |
| 订阅 PropertyPublisher 作为数据源 | 直接使用 EliteRobot 的 `/joint_states` | PropertyPublisher 默认 5s，不适合动画 |
| `/ws/3d_status` WebSocket 未提及衔接 | 明确使用 Foxglove Bridge 统一通道 | 避免维护两套 WebSocket |
| 轨迹预览"一句话带过" | 独立 Step，含完整插值播放器实现 | 实际复杂度需 2.5 天 |
| 缺少阶段一前置检查 | 新增 Step 0 验证清单 | 防止在不完整基础上开发 |

---

*文档版本：v1.0（2026-03-17）*  
*基于 `elite_robot.py`、`resource_mesh_manager.py`、`joint_republisher.py`、`base_device_node.py`、`api.py` 实际源码编写*
