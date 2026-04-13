# Uni-Lab 3D 阶段二——开发者实操指南
# 工作流 3D 模拟同步（独立开发版）

> **你的角色**：负责阶段二全部开发  
> **阶段一**：由其他队友并行开发中，尚未完成  
> **你的开发机**：Ubuntu 22.04 + RTX 4090 + Driver 580 + CUDA 13.0  
> **已配置完成**：conda `unilab` 环境 / ROS2 Humble / MoveIt2 / foxglove_bridge / rosbridge_server / Node.js 20 / unilabos 0.10.18  
> **项目目录**：`~/workspace/Uni-Lab-OS`

---

## 开发策略

阶段一（静态 3D 渲染、/api/v1/urdf 等接口）尚未完成，但**阶段二的大部分工作可以独立进行**：

```
你可以立即开始的：                       需要阶段一完成后集成的：
──────────────────────                 ──────────────────────────
✅ Step 1: EliteRobot 高频发布改造       ❌ Step 2.3: 集成到 /lab3d 页面
✅ Step 2.1-2.2: 前端 JS 模块独立开发    ❌ Step 3.3: 耗材 mesh 关联 URDF
✅ Step 3.1-3.2: resource-tracker.js    ❌ Step 6: 端到端演示
✅ Step 4: status-overlay.js
✅ Step 5: trajectory-player.js
✅ 自建独立测试页面验证各模块
```

---

## 目录

```
Step 1   后端：Elite Robot 高频关节发布        ─── 第 1 天
Step 2   前端：关节动画模块 + 独立测试页        ─── 第 2-3 天
Step 3   前端：耗材跟随动画模块                ─── 第 4-5 天
Step 4   前端：设备状态着色模块                ─── 第 5 天（半天）
Step 5   前端：轨迹预览播放器                  ─── 第 6-7 天
Step 6   与阶段一集成 + 端到端验证              ─── 第 8 天（待队友交付后）
```

---

## Step 1：后端——Elite Robot 高频关节发布

### 1.0 理解当前代码

先读懂你要改的文件：

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS

# 查看 Elite Robot 驱动
cat unilabos/devices/arm/elite_robot.py
```

**当前问题**：`get_actual_joint_positions()` 只在 `modbus_task()` 执行动作时被调用（约 10Hz），空闲时频率为 0。前端动画需要稳定 20Hz。

### 1.1 修改 `elite_robot.py`

```bash
cd ~/workspace/Uni-Lab-OS
```

打开 `unilabos/devices/arm/elite_robot.py`，做以下修改：

**第一处：在文件顶部添加 threading 导入**

在第 3 行 `import time` 之后添加：

```python
import threading
```

**第二处：在 `__init__` 末尾（约第 36 行之后）添加定时器和锁**

```python
        # ── 阶段二新增：高频关节状态定时发布（供前端 3D 动画） ──
        self._tcp_lock = threading.Lock()
        self._joint_poll_rate = 20.0  # Hz
        self._joint_poll_timer = self.node.create_timer(
            1.0 / self._joint_poll_rate,
            self._poll_joint_state
        )

    def _poll_joint_state(self):
        """20Hz 定时轮询关节角并发布到 /joint_states"""
        try:
            positions = self.get_actual_joint_positions()
        except Exception:
            pass
```

**第三处：给 `send_command` 加锁**

将原来的 `send_command` 方法（约第 148 行）替换为：

```python
    def send_command(self, command):
        with self._tcp_lock:
            self.sock.sendall(command.encode('utf-8'))
            response = self.sock.recv(1024).decode('utf-8')
        return response
```

**第四处：给 `joint_state_msg` 加时间戳**

将 `get_actual_joint_positions` 方法（约第 177 行）中的发布部分补上 header.stamp：

```python
    def get_actual_joint_positions(self):
        response = self.send_command(f"req 1 get_actual_joint_positions()\n")
        joint_positions = self.parse_success_response(response)
        if joint_positions:
            self.joint_state_msg.header.stamp = self.node.get_clock().now().to_msg()
            self.joint_state_msg.position = joint_positions
            self.joint_state_pub.publish(self.joint_state_msg)
            return joint_positions
        return None
```

同时在 `__init__` 中给 `joint_state_msg` 加上 header 初始化（约第 12 行之后）：

```python
        from std_msgs.msg import Header
        self.joint_state_msg = JointState()
        self.joint_state_msg.header = Header()
```

### 1.2 验证（不需要真实 Elite Robot）

在没有真实 Elite 机械臂的情况下，可以用 ROS2 命令验证 `/joint_states` 话题链路是否通畅：

```bash
conda activate unilab

# 终端 1：用 stirteststation 测试图谱启动系统（arm_slider 有 joint_state_broadcaster）
python -m unilabos \
    --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
    --visual rviz \
    --port 8002

# 终端 2：检查 /joint_states 话题
conda activate unilab
ros2 topic hz /joint_states
# 预期：arm_slider 的 joint_state_broadcaster 应产生数据

ros2 topic echo /joint_states --once
# 预期：看到关节名和位置数组
```

> **注意**：Elite Robot 的代码修改只有在**连接真实设备**时才能完整测试。目前先确保代码编译无误。

### 1.3 代码检查（无需设备）

```bash
cd ~/workspace/Uni-Lab-OS
python -c "
from unilabos.devices.arm.elite_robot import EliteRobot
import inspect
source = inspect.getsource(EliteRobot)
assert '_poll_joint_state' in source, '缺少定时器方法'
assert '_tcp_lock' in source, '缺少 TCP 锁'
assert 'header.stamp' in source, '缺少时间戳'
print('✓ elite_robot.py 修改验证通过')
"
```

---

## Step 2：前端——关节动画模块 + 独立测试页

### 2.0 创建独立开发目录

阶段一的 `/lab3d` 页面还不存在，你先建一个**独立的前端开发环境**，后续再合并：

```bash
cd ~/workspace/Uni-Lab-OS

# 创建阶段二前端开发目录
mkdir -p unilabos/app/web/static/lab3d-phase2
cd unilabos/app/web/static/lab3d-phase2

# 初始化 npm 项目
npm init -y

# 安装依赖
npm install three urdf-loader @foxglove/ws-protocol roslib

# 安装开发服务器
npm install --save-dev vite
```

### 2.1 创建 `urdf-scene.js`——Three.js 场景 + 关节更新

```bash
cat > urdf-scene.js << 'JSEOF'
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import URDFLoader from 'urdf-loader';

let scene, camera, renderer, controls, robot;

export function createScene(container) {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x263238);

    camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.01, 100);
    camera.position.set(2, 2, 3);

    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);

    controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0.5, 0);
    controls.update();

    // 灯光
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);

    // 地面网格
    const grid = new THREE.GridHelper(10, 20, 0x444444, 0x333333);
    scene.add(grid);

    // 坐标轴
    scene.add(new THREE.AxesHelper(1));

    window.addEventListener('resize', () => {
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    });

    return scene;
}

/**
 * 加载 URDF 并添加到场景。
 * @param {string} urdfUrl - URDF 文件的 URL（如 /api/v1/urdf）
 * @param {string} meshBaseUrl - 网格文件基础 URL（如 /meshes/）
 * @returns {Promise<Object>} 加载完成的 robot 对象
 */
export function loadURDF(urdfUrl, meshBaseUrl = '') {
    return new Promise((resolve, reject) => {
        fetch(urdfUrl)
            .then(res => res.text())
            .then(urdfContent => {
                const loader = new URDFLoader();
                loader.parseVisual = true;
                loader.packages = '';
                loader.workingPath = meshBaseUrl;

                const result = loader.parse(urdfContent);
                robot = result;
                scene.add(robot);
                resolve(robot);
            })
            .catch(reject);
    });
}

/**
 * 阶段二核心：用 /joint_states 数据更新 URDF 关节角。
 * urdf-loader 的 robot.joints 是 { jointName: URDFJoint } 的 Map，
 * 每个 URDFJoint 有 .setJointValue(angle) 方法。
 */
export function updateJointState(jointState) {
    if (!robot || !robot.joints) return;

    const { name, position } = jointState;
    for (let i = 0; i < name.length; i++) {
        const joint = robot.joints[name[i]];
        if (joint) {
            joint.setJointValue(position[i]);
        }
    }
}

/**
 * 获取场景中所有设备 mesh 名称列表
 */
export function getDeviceMeshNames() {
    const names = [];
    if (robot) {
        robot.traverse(child => {
            if (child.name) names.push(child.name);
        });
    }
    return names;
}

export function getRobot() { return robot; }
export function getScene() { return scene; }

export function animate() {
    requestAnimationFrame(animate);
    controls?.update();
    renderer?.render(scene, camera);
}
JSEOF
```

### 2.2 创建 `ros-bridge.js`——Foxglove WebSocket 客户端

```bash
cat > ros-bridge.js << 'JSEOF'
/**
 * ROS Bridge 模块（阶段二）。
 * 通过 Foxglove Bridge WebSocket 订阅 ROS2 话题。
 * 
 * 支持的话题：
 * - /joint_states (sensor_msgs/JointState)
 * - /tf (tf2_msgs/TFMessage)
 * - resource_pose (std_msgs/String)
 * - /move_group/display_planned_path (moveit_msgs/DisplayTrajectory)
 */

export class RosBridge {
    constructor(foxgloveUrl = 'ws://localhost:8765') {
        this.url = foxgloveUrl;
        this.ws = null;
        this.callbacks = {};
        this.connected = false;
        this._reconnectTimer = null;
    }

    connect() {
        console.log('[RosBridge] 正在连接', this.url);
        
        try {
            this.ws = new WebSocket(this.url, ['foxglove.websocket.v1']);
        } catch (e) {
            console.error('[RosBridge] WebSocket 创建失败:', e);
            this._scheduleReconnect();
            return;
        }

        this.ws.binaryType = 'arraybuffer';

        this.ws.onopen = () => {
            console.log('[RosBridge] ✓ 已连接');
            this.connected = true;
        };

        this.ws.onmessage = (event) => {
            if (typeof event.data === 'string') {
                try {
                    const msg = JSON.parse(event.data);
                    this._handleServerMessage(msg);
                } catch (e) { /* ignore */ }
            }
        };

        this.ws.onclose = () => {
            console.log('[RosBridge] 连接断开，5s 后重连');
            this.connected = false;
            this._scheduleReconnect();
        };

        this.ws.onerror = (e) => {
            console.error('[RosBridge] 错误:', e);
        };
    }

    _scheduleReconnect() {
        if (this._reconnectTimer) return;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
        }, 5000);
    }

    _handleServerMessage(msg) {
        // Foxglove WebSocket 协议：serverInfo, advertise, etc.
        if (msg.op === 'advertise') {
            // 收到可用 channel 列表后，订阅我们需要的话题
            this._subscribeToKnownTopics(msg.channels || []);
        }
    }

    _subscribeToKnownTopics(channels) {
        const topicsWeWant = [
            '/joint_states',
            '/tf',
            'resource_pose',
            '/move_group/display_planned_path',
        ];

        for (const ch of channels) {
            if (topicsWeWant.includes(ch.topic)) {
                const subMsg = JSON.stringify({
                    op: 'subscribe',
                    subscriptions: [{
                        id: ch.id,
                        channelId: ch.id,
                    }],
                });
                this.ws.send(subMsg);
                console.log(`[RosBridge] 已订阅 ${ch.topic}`);
            }
        }
    }

    /**
     * 注册话题回调。
     * @param {string} topic - 话题名
     * @param {Function} callback - 回调函数，参数为解析后的消息对象
     */
    on(topic, callback) {
        if (!this.callbacks[topic]) this.callbacks[topic] = [];
        this.callbacks[topic].push(callback);
    }

    _dispatch(topic, data) {
        (this.callbacks[topic] || []).forEach(cb => {
            try { cb(data); } catch (e) { console.error(e); }
        });
    }

    disconnect() {
        if (this.ws) this.ws.close();
    }
}
JSEOF
```

### 2.3 创建独立测试页 `dev-test.html`

这个页面**不依赖阶段一的 /lab3d 页面**，你可以用它独立验证所有阶段二模块：

```bash
cat > dev-test.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>Uni-Lab 3D Phase 2 独立测试</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #1e1e1e; color: #eee; font-family: monospace; overflow: hidden; }
        #canvas-container { width: 75vw; height: 100vh; float: left; }
        #info-panel {
            width: 25vw; height: 100vh; float: right;
            background: #2d2d2d; padding: 16px; overflow-y: auto;
            border-left: 1px solid #444;
        }
        h3 { color: #4fc3f7; margin: 12px 0 6px; }
        .status { padding: 4px 8px; margin: 2px 0; border-radius: 3px; font-size: 13px; }
        .ok { background: #2e7d32; }
        .warn { background: #f57f17; color: #000; }
        .err { background: #c62828; }
        .pending { background: #555; }
        button { background: #4fc3f7; border: none; padding: 6px 16px; cursor: pointer; margin: 4px; border-radius: 4px; }
        button:hover { background: #81d4fa; }
        #log { font-size: 11px; max-height: 300px; overflow-y: auto; background: #1a1a1a; padding: 8px; margin-top: 8px; }
    </style>
</head>
<body>
    <div id="canvas-container"></div>
    <div id="info-panel">
        <h2>Phase 2 模块测试</h2>

        <h3>连接状态</h3>
        <div id="status-foxglove" class="status pending">Foxglove Bridge: 未连接</div>
        <div id="status-joint" class="status pending">/joint_states: 无数据</div>
        <div id="status-resource" class="status pending">resource_pose: 无数据</div>
        <div id="status-device" class="status pending">/ws/device_status: 未连接</div>
        <div id="status-traj" class="status pending">轨迹预览: 无数据</div>

        <h3>操作</h3>
        <button onclick="testJointPublish()">模拟 /joint_states</button>
        <button onclick="testResourcePose()">模拟耗材移动</button>
        <button onclick="testDeviceStatus()">模拟设备状态变更</button>
        <button onclick="testTrajectory()">模拟轨迹播放</button>

        <h3>URDF 加载</h3>
        <div>
            <input id="urdf-url" value="http://localhost:8002/api/v1/urdf" style="width: 90%; padding: 4px;">
            <button onclick="loadUrdfFromUrl()">加载</button>
        </div>

        <h3>日志</h3>
        <div id="log"></div>
    </div>

    <script type="module">
        import { createScene, loadURDF, updateJointState, animate } from './urdf-scene.js';
        import { RosBridge } from './ros-bridge.js';

        const log = (msg) => {
            const el = document.getElementById('log');
            const time = new Date().toLocaleTimeString();
            el.innerHTML = `[${time}] ${msg}\n` + el.innerHTML;
            if (el.childNodes.length > 200) el.innerHTML = el.innerHTML.slice(0, 5000);
        };

        // 初始化场景
        const scene = createScene(document.getElementById('canvas-container'));
        animate();
        log('Three.js 场景已初始化');

        // 连接 Foxglove Bridge
        const bridge = new RosBridge('ws://' + window.location.hostname + ':8765');
        bridge.connect();

        bridge.on('/joint_states', (msg) => {
            updateJointState(msg);
            const el = document.getElementById('status-joint');
            el.className = 'status ok';
            el.textContent = `/joint_states: ${msg.name?.length || 0} 个关节`;
        });

        // 定时检查连接状态
        setInterval(() => {
            const el = document.getElementById('status-foxglove');
            if (bridge.connected) {
                el.className = 'status ok';
                el.textContent = 'Foxglove Bridge: ✓ 已连接';
            } else {
                el.className = 'status err';
                el.textContent = 'Foxglove Bridge: ✗ 未连接';
            }
        }, 2000);

        // 模拟函数挂到 window 上
        window.testJointPublish = () => {
            const mockMsg = {
                name: ['joint_1', 'joint_2', 'joint_3'],
                position: [Math.random() * 3.14, Math.random() * 3.14, Math.random() * 3.14],
            };
            updateJointState(mockMsg);
            log('模拟 joint_states 已发送');
        };

        window.testResourcePose = () => {
            log('模拟 resource_pose（需 resource-tracker.js 集成后测试）');
        };

        window.testDeviceStatus = () => {
            log('模拟 device_status（需 status-overlay.js 集成后测试）');
        };

        window.testTrajectory = () => {
            log('模拟轨迹播放（需 trajectory-player.js 集成后测试）');
        };

        window.loadUrdfFromUrl = () => {
            const url = document.getElementById('urdf-url').value;
            log(`正在加载 URDF: ${url}`);
            loadURDF(url, url.replace('/api/v1/urdf', '/meshes/'))
                .then(() => log('✓ URDF 加载成功'))
                .catch(e => log('✗ URDF 加载失败: ' + e.message));
        };
    </script>
</body>
</html>
HTMLEOF
```

### 2.4 配置 Vite 开发服务器

```bash
cat > vite.config.js << 'JSEOF'
import { defineConfig } from 'vite';

export default defineConfig({
    root: '.',
    server: {
        port: 3000,
        open: '/dev-test.html',
        proxy: {
            '/api': 'http://localhost:8002',
            '/meshes': 'http://localhost:8002',
        },
    },
});
JSEOF
```

### 2.5 启动独立开发环境

```bash
# 终端 1：启动 Uni-Lab-OS 后端（提供 ROS2 话题数据）
conda activate unilab
cd ~/workspace/Uni-Lab-OS
python -m unilabos \
    --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
    --visual rviz \
    --port 8002

# 终端 2：启动 Foxglove Bridge（如果系统没有自动启动的话）
conda activate unilab
ros2 run foxglove_bridge foxglove_bridge --ros-args -p port:=8765

# 终端 3：启动前端开发服务器
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d-phase2
npx vite

# 浏览器打开 http://localhost:3000/dev-test.html
# 应看到 Three.js 场景 + 右侧测试面板
# 如果 Foxglove 连接成功，状态指示变绿
```

---

## Step 3：前端——耗材跟随动画模块

### 3.1 创建 `resource-tracker.js`

```bash
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d-phase2

cat > resource-tracker.js << 'JSEOF'
import * as THREE from 'three';

/**
 * 耗材位姿追踪器。
 * 后端 ResourceMeshManager 已经：
 * 1. 实现了 tf_update Action（attach/detach 到 PlanningScene）
 * 2. 以 50Hz 发布 resource_pose 话题（JSON 格式位姿变化）
 * 
 * 本模块只需订阅该话题，更新 Three.js mesh 位置。
 */
export class ResourceTracker {
    constructor(scene, rosBridge) {
        this.scene = scene;
        this.bridge = rosBridge;
        this.meshes = new Map();      // resourceId → THREE.Mesh
        this.attachState = new Map();  // resourceId → parentFrame
    }

    /**
     * 注册可追踪的耗材。
     * 在 URDF 加载后调用，从 scene 中查找对应 mesh。
     */
    registerResources(resourceIds) {
        for (const id of resourceIds) {
            const obj = this.scene.getObjectByName(id);
            if (obj) {
                this.meshes.set(id, obj);
            }
        }
        console.log(`[ResourceTracker] 已注册 ${this.meshes.size} 个耗材`);
    }

    /**
     * 开始监听 resource_pose 话题。
     */
    startListening() {
        this.bridge.on('resource_pose', (msg) => {
            let changes;
            try {
                changes = typeof msg.data === 'string' ? JSON.parse(msg.data) : msg;
            } catch (e) { return; }

            this._applyPoseChanges(changes);
        });
    }

    _applyPoseChanges(changes) {
        for (const [resourceId, poseOrParent] of Object.entries(changes)) {
            const mesh = this.meshes.get(resourceId);
            if (!mesh) continue;

            // resource_pose 有两种格式：
            // 1. resource_pose 模式: { position: {x,y,z}, rotation: {x,y,z,w} }
            // 2. resource_status 模式: 直接是 parent_frame 字符串
            if (typeof poseOrParent === 'object' && poseOrParent.position) {
                const p = poseOrParent.position;
                const r = poseOrParent.rotation;
                mesh.position.set(p.x, p.y, p.z);
                if (r) mesh.quaternion.set(r.x, r.y, r.z, r.w);
            }

            // 附着状态追踪（用于视觉反馈）
            if (typeof poseOrParent === 'string') {
                const wasAttached = this.attachState.get(resourceId) !== 'world';
                const isAttached = poseOrParent !== 'world';
                this.attachState.set(resourceId, poseOrParent);

                if (isAttached !== wasAttached) {
                    this._setAttachHighlight(mesh, isAttached);
                }
            }
        }
    }

    _setAttachHighlight(mesh, isAttached) {
        mesh.traverse(child => {
            if (child.isMesh && child.material) {
                if (isAttached) {
                    child.material = child.material.clone();
                    child.material.emissive = new THREE.Color(0x2196F3);
                    child.material.emissiveIntensity = 0.3;
                    child.material.transparent = true;
                    child.material.opacity = 0.85;
                } else {
                    child.material.emissiveIntensity = 0;
                    child.material.transparent = false;
                    child.material.opacity = 1.0;
                }
            }
        });
    }
}
JSEOF
```

### 3.2 验证（独立测试页）

在 `dev-test.html` 的 `<script type="module">` 中添加：

```javascript
import { ResourceTracker } from './resource-tracker.js';

const resourceTracker = new ResourceTracker(scene, bridge);
// 阶段一完成后，从 URDF 解析耗材列表；现在先手动注册
// resourceTracker.registerResources(['plate_96_1', 'tip_rack_1']);
resourceTracker.startListening();

window.testResourcePose = () => {
    // 模拟一次耗材位姿变更
    resourceTracker._applyPoseChanges({
        'plate_96_1': {
            position: { x: Math.random(), y: 0.5, z: Math.random() },
            rotation: { x: 0, y: 0, z: 0, w: 1 },
        }
    });
    log('✓ 模拟 resource_pose 已应用');
};
```

---

## Step 4：前端——设备状态着色模块

### 4.1 创建 `status-overlay.js`

```bash
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d-phase2

cat > status-overlay.js << 'JSEOF'
import * as THREE from 'three';

/**
 * 设备状态实时着色。
 * 订阅 FastAPI /ws/device_status WebSocket（已有，1Hz 推送）。
 * 根据状态改变设备 mesh 的发光颜色。
 */

const STATUS_COLORS = {
    idle:       0x888888,
    running:    0x2196F3,
    completed:  0x4CAF50,
    error:      0xF44336,
    warning:    0xFF9800,
};

export class StatusOverlay {
    constructor(scene) {
        this.scene = scene;
        this.ws = null;
        this.deviceMeshes = new Map();
    }

    registerDevices(deviceIds) {
        for (const id of deviceIds) {
            const mesh = this.scene.getObjectByName(id);
            if (mesh) this.deviceMeshes.set(id, mesh);
        }
        console.log(`[StatusOverlay] 已注册 ${this.deviceMeshes.size} 个设备`);
    }

    connectWebSocket(baseUrl = '') {
        const host = baseUrl || window.location.host;
        const wsUrl = `ws://${host}/api/v1/ws/device_status`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'device_status') {
                    this._apply(msg.data.device_status);
                }
            } catch (e) { /* ignore */ }
        };

        this.ws.onclose = () => {
            setTimeout(() => this.connectWebSocket(baseUrl), 3000);
        };
    }

    _apply(statusMap) {
        for (const [deviceId, status] of Object.entries(statusMap)) {
            const mesh = this.deviceMeshes.get(deviceId);
            if (!mesh) continue;

            const color = STATUS_COLORS[status] || STATUS_COLORS.idle;
            const intensity = (status === 'idle') ? 0 : 0.3;

            mesh.traverse(child => {
                if (child.isMesh && child.material) {
                    child.material = child.material.clone();
                    if (child.material.emissive) {
                        child.material.emissive.setHex(color);
                        child.material.emissiveIntensity = intensity;
                    }
                }
            });
        }
    }

    /** 手动设置状态（测试用） */
    setStatus(deviceId, status) {
        this._apply({ [deviceId]: status });
    }
}
JSEOF
```

---

## Step 5：前端——轨迹预览播放器

### 5.1 创建 `trajectory-player.js`

```bash
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d-phase2

cat > trajectory-player.js << 'JSEOF'
import { updateJointState } from './urdf-scene.js';

/**
 * MoveIt2 轨迹预览播放器。
 * 订阅 /move_group/display_planned_path (DisplayTrajectory)，
 * 按时间戳线性插值逐帧回放规划动画。
 */
export class TrajectoryPlayer {
    constructor(robot, container) {
        this.robot = robot;
        this.trajectory = null;
        this.isPlaying = false;
        this.playbackSpeed = 1.0;
        this._startTime = 0;
        this._animFrameId = null;

        this._buildUI(container);
    }

    loadTrajectory(displayTrajectory) {
        const trajs = displayTrajectory.trajectory;
        if (!trajs || trajs.length === 0) return;

        const jt = trajs[0].joint_trajectory;
        if (!jt || !jt.points || jt.points.length === 0) return;

        this.trajectory = {
            jointNames: jt.joint_names,
            points: jt.points.map(pt => ({
                positions: pt.positions,
                timeFromStart: (pt.time_from_start?.sec || 0)
                    + (pt.time_from_start?.nanosec || 0) * 1e-9,
            })),
        };

        const total = this.trajectory.points.at(-1).timeFromStart;
        this._showPanel(total);
        console.log(`[TrajectoryPlayer] 加载 ${this.trajectory.points.length} 个路点，${total.toFixed(2)}s`);
    }

    /** 手动加载轨迹数据（测试用） */
    loadFromRawPoints(jointNames, points) {
        this.trajectory = { jointNames, points };
        this._showPanel(points.at(-1).timeFromStart);
    }

    play() {
        if (!this.trajectory) return;
        this.isPlaying = true;
        this._startTime = performance.now();
        this._loop();
        this._updateBtn(true);
    }

    pause() {
        this.isPlaying = false;
        if (this._animFrameId) cancelAnimationFrame(this._animFrameId);
        this._updateBtn(false);
    }

    _loop() {
        if (!this.isPlaying) return;

        const elapsed = (performance.now() - this._startTime) / 1000 * this.playbackSpeed;
        const total = this.trajectory.points.at(-1).timeFromStart;

        if (elapsed >= total) {
            this._applyFrame(this.trajectory.points.length - 1);
            this.pause();
            return;
        }

        const { index, alpha } = this._findSegment(elapsed);
        this._applyInterpolated(index, alpha);
        this._animFrameId = requestAnimationFrame(() => this._loop());
    }

    _findSegment(time) {
        const pts = this.trajectory.points;
        for (let i = 0; i < pts.length - 1; i++) {
            if (time >= pts[i].timeFromStart && time < pts[i + 1].timeFromStart) {
                const dur = pts[i + 1].timeFromStart - pts[i].timeFromStart;
                return { index: i, alpha: (time - pts[i].timeFromStart) / dur };
            }
        }
        return { index: pts.length - 1, alpha: 0 };
    }

    _applyInterpolated(index, alpha) {
        const pts = this.trajectory.points;
        const p0 = pts[index].positions;
        const p1 = pts[Math.min(index + 1, pts.length - 1)].positions;
        const interp = p0.map((v, i) => v + (p1[i] - v) * alpha);
        updateJointState({ name: this.trajectory.jointNames, position: interp });
    }

    _applyFrame(idx) {
        updateJointState({
            name: this.trajectory.jointNames,
            position: this.trajectory.points[idx].positions,
        });
    }

    _buildUI(container) {
        const div = document.createElement('div');
        div.id = 'traj-panel';
        div.style.cssText = 'position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.85);color:#fff;padding:10px 20px;border-radius:8px;display:none;align-items:center;gap:10px;z-index:100;font-family:monospace;';
        div.innerHTML = `
            <span style="color:#4fc3f7;font-weight:bold;">轨迹预览</span>
            <button id="traj-play-btn" style="padding:4px 12px;cursor:pointer;border:none;border-radius:4px;background:#4fc3f7;">▶ 播放</button>
            <select id="traj-speed" style="padding:2px;">
                <option value="0.25">0.25x</option>
                <option value="0.5">0.5x</option>
                <option value="1" selected>1x</option>
                <option value="2">2x</option>
            </select>
            <span id="traj-info"></span>
        `;
        container.appendChild(div);

        div.querySelector('#traj-play-btn')?.addEventListener('click', () => {
            this.isPlaying ? this.pause() : this.play();
        });
        div.querySelector('#traj-speed')?.addEventListener('change', (e) => {
            this.playbackSpeed = parseFloat(e.target.value);
        });
    }

    _showPanel(totalTime) {
        const panel = document.getElementById('traj-panel');
        if (panel) {
            panel.style.display = 'flex';
            panel.querySelector('#traj-info').textContent = `${totalTime.toFixed(1)}s`;
        }
    }

    _updateBtn(playing) {
        const btn = document.getElementById('traj-play-btn');
        if (btn) btn.textContent = playing ? '⏸ 暂停' : '▶ 播放';
    }
}
JSEOF
```

### 5.2 在测试页集成轨迹播放器

在 `dev-test.html` 的 `testTrajectory` 函数中模拟轨迹数据：

```javascript
import { TrajectoryPlayer } from './trajectory-player.js';

// robot 变量在 loadURDF 后才有，这里先存引用
let trajectoryPlayer = null;

// 在 loadUrdfFromUrl 成功回调中初始化：
// trajectoryPlayer = new TrajectoryPlayer(robot, document.body);

window.testTrajectory = () => {
    if (!trajectoryPlayer) {
        log('请先加载 URDF');
        return;
    }
    // 模拟一个 3 关节、5 个路点的轨迹
    trajectoryPlayer.loadFromRawPoints(
        ['joint_1', 'joint_2', 'joint_3'],
        [
            { positions: [0, 0, 0],    timeFromStart: 0 },
            { positions: [0.5, -0.3, 0.2], timeFromStart: 1 },
            { positions: [1.0, -0.6, 0.5], timeFromStart: 2 },
            { positions: [1.2, -0.8, 0.8], timeFromStart: 3 },
            { positions: [0, 0, 0],    timeFromStart: 4 },
        ]
    );
    trajectoryPlayer.play();
    log('✓ 模拟轨迹开始播放');
};
```

---

## Step 6：与阶段一集成

**在你队友完成阶段一后**，执行以下合并步骤：

### 6.1 将模块文件复制到阶段一目录

```bash
# 假设队友的阶段一代码放在 static/lab3d/ 目录下
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static

# 复制阶段二模块到阶段一目录
cp lab3d-phase2/ros-bridge.js      lab3d/
cp lab3d-phase2/resource-tracker.js lab3d/
cp lab3d-phase2/status-overlay.js   lab3d/
cp lab3d-phase2/trajectory-player.js lab3d/
```

### 6.2 将阶段二逻辑集成到 `main.js`

在队友的 `main.js` 中添加：

```javascript
// ── 阶段二模块导入 ──
import { RosBridge } from './ros-bridge.js';
import { ResourceTracker } from './resource-tracker.js';
import { StatusOverlay } from './status-overlay.js';
import { TrajectoryPlayer } from './trajectory-player.js';

// ── 初始化阶段二模块（在 URDF 加载成功后） ──

// 1. Foxglove Bridge 连接 + 关节动画
const bridge = new RosBridge('ws://' + window.location.hostname + ':8765');
bridge.connect();
bridge.on('/joint_states', (msg) => updateJointState(msg));

// 2. 耗材跟随
const resourceTracker = new ResourceTracker(scene, bridge);
resourceTracker.registerResources(resourceIds); // 从 URDF 解析
resourceTracker.startListening();

// 3. 设备状态着色
const statusOverlay = new StatusOverlay(scene);
statusOverlay.registerDevices(deviceIds);
statusOverlay.connectWebSocket();

// 4. 轨迹预览
const trajectoryPlayer = new TrajectoryPlayer(robot, document.body);
bridge.on('/move_group/display_planned_path', (msg) => {
    trajectoryPlayer.loadTrajectory(msg);
});
```

### 6.3 后端修改合入

确保 `elite_robot.py` 的修改已合入主分支：
- `_poll_joint_state` 定时器
- `_tcp_lock` 线程锁
- `header.stamp` 时间戳

---

## 文件清单

开发完成后，你产出的所有文件：

```
~/workspace/Uni-Lab-OS/
├── unilabos/
│   ├── devices/arm/
│   │   └── elite_robot.py                    # 修改：+定时器 +锁 +时间戳
│   └── app/web/static/lab3d-phase2/          # 阶段二独立开发目录
│       ├── package.json
│       ├── vite.config.js
│       ├── dev-test.html                     # 独立测试页
│       ├── urdf-scene.js                     # Three.js 场景 + 关节更新
│       ├── ros-bridge.js                     # Foxglove WebSocket 客户端
│       ├── resource-tracker.js               # 耗材位姿追踪
│       ├── status-overlay.js                 # 设备状态着色
│       └── trajectory-player.js              # 轨迹预览播放器
└── Uni-Lab-3D-Phase2-Dev-Guide.md            # 本文档
```

**后端改动**：仅 1 个文件（`elite_robot.py`）  
**前端新建**：5 个 JS 模块 + 1 个测试 HTML + 配置文件  
**无需阶段一交付即可完成的工作**：上述全部  
**需要阶段一后集成**：复制 JS 文件到 `lab3d/` 目录 + 在 `main.js` 中导入

---

*文档版本：v1.0（2026-03-17）*  
*开发机：Ubuntu 22.04 + RTX 4090 + conda unilab 环境*
