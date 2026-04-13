# Uni-Lab 云端 3D 实验室搭建与运行演示——修订规划

> **文档说明**：本文档在 `Uni-lab-os-3D-3.17new.md` 原始规划基础上，结合对 Uni-Lab-OS 代码库（`unilabos/device_mesh/`、`unilabos/ros/`、`unilabos/app/`）的深度审查和对 RViz2/ROSBridge2 开源生态的验证，对技术细节和实现路径进行了全面修订。**已标注每项任务的真实起点状态（已有 / 已有待接入 / 待开发）**，避免重复建设。

---

## 1. 背景与目标

自动化实验室规模化建设和工作流编排过程中，涉及大量对多设备精准空间布局、机械臂动态路径预留以及复杂作业流直观验证的需求。

Uni-Lab 云端 3D 实验室搭建与可视化运行方案实现以下三个目标：

- **设备尺寸自动化获取与 AI 智能排布**：确保仪器规格与实验室空间精准匹配，通过 AI 辅助设计实现建设方案的快速迭代与低成本试错。
- **全流程动作仿真与物理碰撞预检**：提供直观的设备运行可视化方法，在实机操作前排除工作流中的逻辑错误与空间冲突。
- **直观 3D 方案展示与开源生态构建**：以直观的视觉效果增强客户信任并促成合作，通过降低技术门槛打造开源自动化实验室生态。

---

## 2. 现有代码基础盘点（修订前的常见误解）

> ⚠️ **重要**：原规划文档大量标注「待开发」的功能，经代码审查后发现已有完整实现，必须先准确摸清家底再排期，避免重复建设。

### 2.1 已完整实现、可直接使用


| 模块                            | 文件位置                                        | 关键能力                                                               |
| ----------------------------- | ------------------------------------------- | ------------------------------------------------------------------ |
| **动态 URDF 生成**                | `device_mesh/resource_visalization.py`      | 读取 graph JSON → `lxml` + `xacro` 拼接多设备 URDF，自动处理命名空间               |
| **MoveIt2 全集成**               | `ResourceVisualization.moveit_init()`       | 合并多设备 SRDF、ros2_controllers.yaml、kinematics.yaml                   |
| **ROS2 启动描述**                 | `create_launch_description()`               | 自动启动 robot_state_publisher、move_group、ros2_control、RViz2           |
| **MoveIt PlanningScene**      | `device_mesh/resource_mesh_manager.py`      | `/collision_object`、`/planning_scene`、`/apply_planning_scene` 全部接通 |
| **Attached Collision Object** | `ResourceMeshManager.tf_update()`           | attach/detach 完整流程，机械臂抓取耗材时自动跟随                                    |
| **资源 TF 广播（50Hz）**            | `ResourceMeshManager.publish_resource_tf()` | 所有 labware 位置实时广播到 `/tf`                                           |
| **JointState 转 JSON**         | `ros/nodes/presets/joint_republisher.py`    | 订阅 `/joint_states` → 发布 JSON 字符串到 `joint_state_repub` topic        |
| **ROSBridge 包已安装**            | `scripts/unilabos-linux-64.yaml`            | `ros-humble-rosbridge-server` 已作为 conda 依赖安装                       |


### 2.2 已有但尚未接入完整流程（「最后一公里」问题）


| 缺口                              | 所需工作量     | 说明                                        |
| ------------------------------- | --------- | ----------------------------------------- |
| ROSBridge 启动代码                  | **0.5 天** | `create_launch_description()` 中追加 3 行节点定义 |
| FastAPI 网格文件静态路由                | **0.5 天** | `app.mount("/meshes", StaticFiles(...))`  |
| URDF 中 `file://` → HTTP URL 替换  | **0.5 天** | 新增 `get_web_urdf(base_url)` 方法            |
| `/api/v1/urdf` 接口               | **0.5 天** | 返回当前实验室的 web 可用 URDF                      |
| `JointRepublisher` 接入 WebSocket | **1 天**   | 已发布 JSON 字符串，需接入 FastAPI WebSocket 通道     |


### 2.3 已有 3D 资产清单

**设备模型**（`device_mesh/devices/`）：


| 设备                         | STL 文件                              | MoveIt2 配置 | 说明                                  |
| -------------------------- | ----------------------------------- | ---------- | ----------------------------------- |
| `arm_slider`               | 8 个 STL（滑轨+4轴臂+夹爪）                  | ✅ 完整       | SRDF + controllers + kinematics     |
| `dummy2_robot`             | base + J1-J6 + camera               | ✅ 完整       | 调试/测试用                              |
| `elite_robot`              | CS63/66/612/616/620/625 各变体 DAE+STL | 🔶 部分      | 只有 ros2_control，缺 SRDF 和 kinematics |
| `toyo_xyz`                 | 13 个 STL（龙门架）                       | ✅ 完整       |                                     |
| `slide_w140`               | 4 个 STL                             | ❌          |                                     |
| `hplc_station`             | STL 存在                              | ❌          |                                     |
| `thermo_orbitor_rs2_hotel` | `hotel.stl` + `hotel.glb`           | ❌          | **GLB 可直接用 Three.js 加载**            |
| `opentrons_liquid_handler` | 4 个 STL + FBX                       | ❌          |                                     |


**耗材模型**（`device_mesh/resources/`）：plate_96、plate_96_high、hplc_plate、tube、bottle、tip、tiprack_96_high、tiprack_box 等。部分附带 `.glb`（tecan_nested_tip_rack、generic_labware_tube_10_75）。

### 2.4 真正需要新建的能力


| 功能                               | 实际状态                             |
| -------------------------------- | -------------------------------- |
| 浏览器端 Three.js URDF 渲染            | ❌ 待开发                            |
| 前端拖拽布局交互                         | ❌ 待开发                            |
| JointStateAdapterNode（真实设备高频关节角） | ❌ 待开发（注意频率问题，见 §4.1）             |
| 动态生成 `.rviz` 配置                  | ❌ 待开发（现有 view_robot.rviz 硬编码链接名） |
| 碰撞网格凸包简化（Blender 批处理）            | ❌ 待开发                            |
| AI 布局模块                          | ❌ 待开发                            |
| 离线可达性地图                          | ❌ 待开发                            |


---

## 3. 时间节点与阶段划分

阶段 a 为主要目标优先完成，b 为进阶目标。阶段二、三在时间上可并行推进。

- **阶段一：支持云端手动搭建静态 3D 实验室**（约 3-4 周）
  - a. 接通「最后一公里」，在浏览器中渲染出可交互的静态 3D 实验室场景
  - b. 手动布局拖拽交互 + 碰撞高亮
  - b. 补充缺失设备的 3D 建模
- **阶段二：对 Uni-Lab OS 工作流实现 3D 模拟同步**（约 3-4 周，可与阶段一后半段并行）
  - a. 接通完整数据链路：工作流执行 → 关节角实时推送 → 浏览器动画
  - b. 耗材附着/释放动画；轨迹预览；设备状态颜色指示
- **阶段三：AI 自动实现实验室布局排布**（约 4-6 周，可与阶段二后半段并行）
  - a. LLM 生成初版布局 + 差分进化优化 + 约束验证
  - b. 离线可达性地图；对接 deploy_master 设备推荐

---

## 4. 实现方法（阶段一：静态 3D 实验室）

### 4.1 已知 Bug 修复（开工前必做）

在任何新功能开发之前，先修复代码库中已发现的两处 Bug：

**Bug A：坐标来源二义性（`resource_visalization.py` 第 131-145 行）**

当前代码同时读取 `node["position"]` 和 `node["pose"]` 两条路径，后者会静默覆盖前者，可能导致设备位置错误。

```python
# 修复方案：在 graphio.py 的 canonicalize_nodes_data() 中统一归一化
# 确保输出 graph 节点只有一个坐标字段 "position"，
# 并将 position 单位统一为毫米（ResourceVisualization 负责 /1000 转换）
def canonicalize_nodes_data(node: dict) -> dict:
    if "pose" in node and "position" not in node:
        node["position"] = node.pop("pose")
    elif "pose" in node and "position" in node:
        node.pop("pose")  # position 优先，丢弃 pose
    return node
```

**Bug B：`station_name` 被注释掉（`resource_visalization.py` 第 129-131 行）**

```python
# 当前（已注释）：
# if node["parent"] is not None:
#     new_dev.set("station_name", node["parent"]+'_')

# 修复（取消注释 + 加 None 防护）：
if node.get("parent") is not None:
    new_dev.set("station_name", str(node["parent"]) + '_')
```

此 Bug 导致多层级工作站组装（如 Tecan Fluent 主体 + 子模块）出现 link 命名冲突。

---

### 4.2 技术栈选型（Web 3D 渲染层）

原规划推荐 ros3djs + ROSLIB.js + ROSBridge2，经验证存在 **高风险兼容问题**，需在此明确选型：

**核心风险**：ros3djs 渲染 TF 动画依赖 `tf2_web_republisher` 包将 `/tf` 转发给浏览器。该包在 ROS2 中的替代版本 `tf2_web_republisher_py` 在 ROS2 Humble 上存在已知依赖冲突，可能导致前端动画完全无法工作。

**三种方案对比**：


| 方案               | 技术栈                                     | ROS2 Humble TF 支持                        | 维护状态                | 推荐度     |
| ---------------- | --------------------------------------- | ---------------------------------------- | ------------------- | ------- |
| **方案 A（原文）**     | ros3djs + ROSLIB.js + ROSBridge2（:9090） | ⚠️ 需 tf2_web_republisher_py，Humble 有兼容问题 | ros3djs 2023 年后较少更新 | ⚠️ 有风险  |
| **方案 B（首选推荐）**   | Foxglove Bridge（:8765）+ 自定义 Three.js 前端 | ✅ 原生，无兼容问题                               | 活跃维护                | ✅ 推荐    |
| **方案 C（快速验证备选）** | ROSBridge2 + 直接消费 `/joint_states` JSON  | 🔶 绕过 tf2_web_republisher，手动实现 TF 矩阵计算   | 技术债较高               | 🔶 短期可用 |


**推荐选型（方案 B）：**

```bash
# 服务端安装
sudo apt install ros-humble-foxglove-bridge

# 启动（集成到 create_launch_description() 中）
ros2 run foxglove_bridge foxglove_bridge --ros-args -p port:=8765
```

前端使用 Three.js + `[@pixiv/three-vrm](https://github.com/pixiv/three-vrm)` 或 `[urdf-loader](https://github.com/gkjohnson/urdf-loaders)`（纯 Three.js 实现，不依赖 ros3djs），通过 Foxglove WebSocket 协议接收 `/joint_states`、`/robot_description`、`/tf_static`。

**如选择方案 A，必须先做此验证：**

```bash
# 在 Humble 环境中先验证可用性，再开始前端开发
pip install tf2-web-republisher-py
ros2 run tf2_web_republisher tf2_web_republisher
# 无报错才能推进 ros3djs 方案
```

---

### 4.3 「最后一公里」接入（工作量 2 天，MVP 阻塞项）

#### 4.3.1 启动 ROS Bridge（`device_mesh/resource_visalization.py`）

在 `create_launch_description()` 中追加 Bridge 节点，并将 `enable_rviz` / `enable_bridge` 改为可配置项（云端服务器无显示器，需 `enable_rviz=False`）：

```python
# resource_visalization.py → create_launch_description()

def create_launch_description(
    self,
    enable_rviz: bool = True,
    enable_bridge: bool = False,       # 新增参数
    bridge_type: str = "foxglove",     # "foxglove" | "rosbridge"
    bridge_port: int = 8765,
) -> LaunchDescription:
    ...
    if enable_bridge:
        if bridge_type == "foxglove":
            bridge_node = nd(
                package='foxglove_bridge',
                executable='foxglove_bridge',
                name='foxglove_bridge',
                output='screen',
                parameters=[{'port': bridge_port, 'address': '0.0.0.0',
                             'send_buffer_limit': 10000000}],
                env=dict(os.environ)
            )
        else:  # rosbridge
            bridge_node = nd(
                package='rosbridge_server',
                executable='rosbridge_websocket',
                name='rosbridge_websocket',
                output='screen',
                parameters=[{'port': bridge_port, 'address': '0.0.0.0',
                             'max_message_size': 10000000}],
                env=dict(os.environ)
            )
        self.launch_description.add_action(bridge_node)

    if enable_rviz:
        rviz_config_path = self._generate_rviz_config()  # 动态生成，见 §4.3.4
        rviz_node = nd(package='rviz2', executable='rviz2',
                       arguments=['-d', rviz_config_path], ...)
        self.launch_description.add_action(rviz_node)
```

#### 4.3.2 FastAPI 网格文件静态路由（`app/web/server.py`）

浏览器的 URDF 解析器会 HTTP 请求网格文件，必须将其从本地 `file://` 路径暴露为 HTTP URL：

```python
# unilabos/app/web/server.py

from fastapi.staticfiles import StaticFiles
from pathlib import Path

DEVICE_MESH_DIR = Path(__file__).parent.parent.parent / "device_mesh"

def create_app():
    app = FastAPI(title="Uni-Lab-OS", ...)
    # 挂载网格文件目录
    # 访问路径示例：GET /meshes/devices/arm_slider/meshes/arm_slideway.STL
    app.mount("/meshes", StaticFiles(directory=str(DEVICE_MESH_DIR)), name="meshes")
    ...
```

#### 4.3.3 URDF HTTP 化 + `/api/v1/urdf` 接口

```python
# resource_visalization.py 新增方法
def get_web_urdf(self, server_base_url: str) -> str:
    """返回适合浏览器加载的 URDF：将 file:// 绝对路径替换为 HTTP URL"""
    local_prefix = f"file://{str(self.mesh_path)}"
    http_prefix = f"{server_base_url}/meshes"
    return self.urdf_str.replace(local_prefix, http_prefix)

# unilabos/app/web/api.py 新增路由
@router.get("/api/v1/urdf")
async def get_current_urdf(request: Request):
    """返回当前实验室场景的 URDF（网格路径已转为 HTTP URL）"""
    base_url = str(request.base_url).rstrip("/")
    if resource_visualization is None:
        raise HTTPException(status_code=503, detail="可视化服务未启动")
    return Response(
        content=resource_visualization.get_web_urdf(base_url),
        media_type="application/xml"
    )
```

#### 4.3.4 动态生成 `.rviz` 配置（替代硬编码的 `view_robot.rviz`）

现有 `view_robot.rviz` 硬编码了 `arm_slider_` 和 `thermo_orbitor_rs2_hotel_` 的 link 名称，换布局就会报错。改为在 `create_launch_description()` 中动态生成：

```python
import xml.etree.ElementTree as ET
import tempfile, yaml as pyyaml

def _generate_rviz_config(self) -> str:
    """根据当前实验室布局动态生成临时 .rviz 文件，返回路径"""
    urdf_tree = ET.fromstring(self.urdf_str)
    links = [link.get("name") for link in urdf_tree.findall("link")]

    config = {
        "Visualization Manager": {
            "Global Options": {"Fixed Frame": "world", "Background Color": "48; 48; 48"},
            "Displays": [
                {"Class": "rviz_default_plugins/Grid", "Name": "Grid", "Enabled": True},
                {"Class": "rviz_default_plugins/RobotModel", "Name": "RobotModel",
                 "Enabled": True, "Robot Description": "robot_description"},
                {"Class": "moveit_rviz_plugin/PlanningScene", "Name": "PlanningScene",
                 "Enabled": True, "Planning Scene Topic": "/monitored_planning_scene"},
                {"Class": "moveit_rviz_plugin/MotionPlanning", "Name": "MotionPlanning",
                 "Enabled": True},
            ]
        }
    }
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".rviz", delete=False)
    pyyaml.dump(config, tmp)
    tmp.close()
    return tmp.name
```

---

### 4.4 设备资产准备

资产按类型分为三类，影响 URDF 结构和碰撞注册方式：

- **ArticulationCfg（关节型）**：有可动关节（revolute/prismatic），Xacro 含非 fixed joint，运动过程中碰撞检测由 MoveIt2 实时处理。需 `moveit.` 前缀触发完整 MoveIt2 集成（`moveit_init()` 约束）。
- **StaticObjectCfg（静态物体）**：固定仪器/家具，仅 fixed joint，注册为 PlanningScene 碰撞障碍物。
- **RigidObjectCfg（刚体可抓取）**：耗材/板/管等，阶段二需支持 Attached Collision Object（`ResourceMeshManager.tf_update()` 已实现）。

**模型零点规范**：Z=0 落地面，XY 中心投影，+X 正面朝向。不符合的通过 Xacro `<origin>` 偏移修正。

**Visual / Collision 网格分离**（阶段一必须完成，现有 Xacro 全部使用同一 STL 做两用）：

> 当前所有 Xacro 文件的 `<visual>` 和 `<collision>` 指向同一个 STL。MoveIt2 FCL 碰撞检测加载高精度网格时 CPU 使用率极高，15 台设备场景下规划时间将超出 500ms 指标。

实施方案：

1. **命名规范**：`arm_slideway.STL`（visual 保留原件）+ `arm_slideway_collision.STL`（Blender 凸包简化版）
2. **Blender 批处理脚本**（`scripts/generate_collision_meshes.py`）：

```python
import bpy, glob, os

for visual_stl in glob.glob("device_mesh/devices/**/meshes/*.STL", recursive=True):
    if "_collision" in visual_stl:
        continue
    collision_stl = visual_stl.replace(".STL", "_collision.STL")
    if os.path.exists(collision_stl):
        continue  # 已生成，跳过

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_mesh.stl(filepath=visual_stl)
    obj = bpy.context.selected_objects[0]

    # Decimate 修改器：保留 5% 面数（可调整 ratio）
    mod = obj.modifiers.new("decimate", "DECIMATE")
    mod.ratio = 0.05
    bpy.ops.object.modifier_apply(modifier="decimate")

    bpy.ops.export_mesh.stl(filepath=collision_stl)
    print(f"生成: {collision_stl}")
```

1. **Xacro 宏改造**（以 arm_slider 为例，其他同理）：

```xml
<!-- 改造后：collision 优先用简化版，不存在则回退原文件 -->
<xacro:property name="coll_file" value="${mesh_path}/devices/arm_slider/meshes/arm_slideway_collision.STL"/>
<collision>
  <geometry>
    <mesh filename="file://${coll_file if xacro.file_exists(coll_file) else mesh_path + '/devices/arm_slider/meshes/arm_slideway.STL'}"/>
  </geometry>
</collision>
```

**补充建模优先级**：

- P0：实验台/机柜（桌面需支持设备吸附）
- P1：Elite Robot 完整 MoveIt2 配置（SRDF + kinematics，目前只有 ros2_control）
- P2：Uni-Lab-OS 已对接但缺模型的设备（balance、heaterstirrer、rotavap 等）

**工作站多级组装**（Level 1 + Level 2）：

registry 中定义工作站模板，声明子部件组合及槽位关系，由 Xacro 宏组装。需先修复 `station_name` Bug（见 §4.1）才能正确实现层级命名。

---

### 4.5 设备选择与上架流程

- 用户选择场景/实验 → 从 registry 筛选相关设备列表（对接 deploy_master，即将上线）
- 选取设备后，从 `device_mesh/` 本地目录或阿里云 OSS 拉取 Xacro + STL/DAE 资产
- `ResourceVisualization` 将新设备拼入整体 URDF，`robot_state_publisher` 重新发布，前端自动刷新（通过 `/api/v1/urdf` 接口轮询或 WebSocket 推送）

---

### 4.6 手动布局交互

- **拖拽定位 + 旋转朝向**：设备自动吸附到地面或桌面/柜面
- **碰撞检测**（混合方案，性能与精度兼顾）：


| 阶段      | 技术                                  | 触发时机    | 反馈方式         |
| ------- | ----------------------------------- | ------- | ------------ |
| **粗检测** | 前端 Three.js OBB（轴对齐包围盒）             | 拖拽过程中实时 | 目标位置红色半透明预览  |
| **精检测** | 后端 MoveIt2 FCL（ResourceMeshManager） | 鼠标松开时   | 碰撞对列表 + 设备高亮 |


```
拖拽中（60fps）：Three.js OBB 粗检测 → 实时碰撞预览
       ↓ 松手
POST /api/lab/layout（新位姿）
       ↓
更新 PlanningScene（ResourceMeshManager）
       ↓
返回碰撞对列表 → 前端将冲突设备标红
```

- **布局自动初始化**（粗排）：添加新设备时，取其 AABB 的 XY 投影作为 2D 占用域，在地面网格上用 bottom-left 算法扫描第一个无重叠位置自动放入。后续由 AI 排布（阶段三）替代。
- **布局保存**：保存为 JSON 文件，字段格式与 Uni-Lab-OS 的 physical graph node-link 格式兼容，可直接作为 `--graph` 参数加载。

---

### 4.7 3D 预览渲染

完整数据链路：

```
server.py 启动
  ↓ ResourceVisualization(enable_bridge=True, enable_rviz=False)
  ↓ create_launch_description() 启动：
      robot_state_publisher（/robot_description, /tf_static）
      move_group（PlanningScene）
      ResourceMeshManager（资源 TF 50Hz）
      Foxglove Bridge / ROSBridge2（WebSocket）
  ↓
FastAPI 新增接口：
  GET /api/v1/urdf          → 返回 HTTP 化 URDF
  GET /meshes/...           → 静态网格文件
  WebSocket /ws/3d_status   → 转发 joint_state_repub topic（JointRepublisher 已有）
  ↓
浏览器前端：
  Three.js + urdf-loader 加载 /api/v1/urdf
  Foxglove WebSocket 订阅 /joint_states（throttle 40ms）
  /tf_static 一次性加载（设备固定位置）
  /ws/3d_status 接收耗材位置变化
```

**前端技术栈**：

```
Three.js（渲染引擎）
  + urdf-loader（URDF 解析，支持 STL/DAE/GLB）
  + @foxglove/ws-protocol（Foxglove WebSocket 客户端）
  或
  + roslib.js（ROSBridge2 客户端）
```

**GLB 资产直接利用**：`thermo_orbitor_rs2_hotel/hotel.glb`、`tecan_nested_tip_rack/plate.glb` 等已有 GLB 格式文件，可由 Three.js GLTFLoader 直接加载，渲染质量优于 STL。

**2D / 3D 一键切换**：

- 3D 模式：Three.js + Foxglove/ROSBridge WebSocket 实时数据流
- 2D 模式：从 graph JSON 的 `position.x/y` 字段直接渲染 SVG 平面图，断开 WebSocket 数据流，适合低带宽环境

---

## 5. 实现方法（阶段二：工作流 3D 模拟同步）

### 5.1 完整数据链路

```
用户 POST /api/job/add
  ↓ HostNode → ROS2 Action Goal → 设备驱动执行
  ↓
┌─────────────────────────────────────────────────────────────────┐
│  关节状态数据源（两类设备不同处理）                                  │
│                                                                 │
│  ① moveit. 前缀设备（arm_slider 等）                              │
│    joint_state_broadcaster → /joint_states（100Hz）✅ 已有       │
│                                                                 │
│  ② 真实设备（Elite Robot 等，无 ros2_control）                     │
│    设备驱动 50Hz 主动读取关节角 → JointStateAdapterNode           │
│    → 合并发布到 /joint_states（新增）                              │
└───────────────────────────┬─────────────────────────────────────┘
                            ↓
robot_state_publisher → /tf（关节级实时 TF）
ResourceMeshManager → /tf（耗材 TF，50Hz）✅ 已有
                            ↓
Foxglove Bridge / ROSBridge2 WebSocket
  订阅策略（用订阅参数降频，替代独立 ThrottlerNode）：
  /joint_states    throttle_rate=40ms（≈25Hz）queue_length=1
  /tf_static       latched，一次性传输，无需降频
  /planning_scene  event-driven，变更时推送
                            ↓
浏览器前端实时动画（目标 ≥20fps，延迟 <150ms）
```

### 5.2 JointStateAdapterNode（仅真实设备需要）

> ⚠️ **频率是关键**：`BaseROS2DeviceNode.PropertyPublisher` 默认 `initial_period=5.0`（5秒/次），远低于动画需要的 20Hz。**JointStateAdapterNode 必须解决频率问题**，而不只是话题名转换。

```python
# unilabos/ros/nodes/presets/joint_state_adapter.py

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
import json

class JointStateAdapterNode(Node):
    """
    将真实设备的关节角（从设备驱动 API 主动读取）
    以 50Hz 发布到标准 /joint_states 话题。
    
    仅用于没有 ros2_control / joint_state_broadcaster 的设备
    （如通过 Elite SDK 控制的机械臂）。
    """
    def __init__(self, device_driver, joint_names: list[str], rate_hz: float = 50.0):
        super().__init__('joint_state_adapter')
        self.driver = device_driver
        self.joint_names = joint_names
        self.pub = self.create_publisher(JointState, '/joint_states', 10)
        self.timer = self.create_timer(1.0 / rate_hz, self._publish)

    def _publish(self):
        try:
            positions = self.driver.get_joint_positions()  # 设备驱动 API
        except Exception:
            return
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = self.joint_names
        msg.position = list(positions)
        self.pub.publish(msg)
```

### 5.3 WebSocket 降频策略（订阅参数替代独立 ThrottlerNode）

使用 ROSBridge2 的订阅参数内置降频，无需额外节点：

```json
// 前端订阅消息（ROSBridge2 协议）
{
  "op": "subscribe",
  "topic": "/joint_states",
  "type": "sensor_msgs/JointState",
  "throttle_rate": 40,
  "queue_length": 1
}
```

> ⚠️ **降频策略修正**：原规划将 `/tf` 一并降频到 20Hz 是错误的。
>
> - `/tf_static`：latched topic，传输一次即可，不需要降频
> - `/tf`（动态）：只需转发机械臂相关 TF frame，通过 TF filter 减少数据量而非降频
> - `/joint_states`：降频到 25Hz，前端动画已足够流畅

### 5.4 耗材附着与释放（已有实现，需前端对接）

`ResourceMeshManager.tf_update()` 已完整实现 attach/detach + PlanningScene 更新。

前端对接：订阅 `resource_pose` topic（JSON 字符串，50Hz，ResourceMeshManager 已发布），解析耗材位置变化，在 Three.js 场景中移动对应 mesh：

```javascript
// 前端（伪代码）
ros.subscribe('resource_pose', 'std_msgs/String', (msg) => {
    const changes = JSON.parse(msg.data);
    changes.forEach(({ resource_id, parent_frame, position, quaternion }) => {
        const mesh = scene.getObjectByName(resource_id);
        if (mesh) {
            mesh.position.set(position.x, position.y, position.z);
            mesh.quaternion.set(quaternion.x, quaternion.y, quaternion.z, quaternion.w);
        }
    });
});
```

### 5.5 轨迹预览与设备状态指示

- **轨迹预览**：前端订阅 `/move_group/display_planned_path`（`moveit_msgs/DisplayTrajectory`），按轨迹点时间戳逐帧回放规划动画，工作流执行前可预览路径。
- **设备状态着色**：复用现有 FastAPI `/ws/device_status`（已有，1Hz 推送设备状态 JSON），用颜色/图标实时反映设备状态：
  - 空闲 → 灰色
  - 执行中 → 蓝色
  - 异常 → 红色

---

## 6. 实现方法（阶段三：AI 自动实验室布局）

整体流程：用户选定设备列表 + 实验室场景 → LLM 生成候选布局 → 约束验证 → 差分进化优化迭代 → 输出最终方案

### 6.1 AI 初始布局生成

> ⚠️ **选型修正**：原规划使用 Pencil AI（平面设计工具）生成初版布局。Pencil AI 不支持机器人实验室语义约束，且无法注入硬规则。改用 LLM + Few-shot Prompt 方案：

```
输入：
  - 设备列表（ID + 类型 + 尺寸 + 交接点位置）
  - 实验室平面图（长宽 + 固定设施位置）
  - 约束规则列表（JSON 格式的硬/软约束）

Prompt 示例：
  "根据以下设备列表和约束规则，生成一个 JSON 格式的实验室布局方案，
   每个设备包含 x, y, theta（角度）字段。
   硬约束：{碰撞检测, 可达性, 距离限制}
   软约束：{频繁传递的设备靠近, 振动隔离}"

输出：
  {"devices": [{"id": "stirrer_1", "x": 1.2, "y": 0.5, "theta": 0}, ...]}
```

LLM 输出作为差分进化的**种子个体**注入，加速收敛。

### 6.2 差分进化优化

- **布局编码**：每个设备 3 个参数（x, y, θ），N 台设备编码为 3N 维向量
- **cost function**：
  - 硬约束违反 → 返回 `inf`（直接淘汰）
  - 软约束按权重累加 penalty
- **可达性约束复用**：`ResourceMeshManager.add_resource_collision_meshes()` 已接通 MoveIt2，直接查询碰撞
- **优化库**：`scipy.optimize.differential_evolution`，种群大小 15×设备数，最大迭代 100 轮

### 6.3 约束体系

**硬约束（违反则方案无效）**：

- `no_collision(A, B)`：所有设备对之间无物理碰撞（复用阶段一 PlanningScene FCL）
- `reachable(device, arm)`：设备交接点落在机械臂工作空间内（查离线可达性地图）
- `distance_greater_than(A, B, d_min)`：如防污染隔离、振动隔离（高精度天平远离离心机）
- `distance_less_than(A, B, d_max)`：如频繁传递设备的交接距离上限

**软约束（影响 cost，不淘汰方案）**：

- `minimize_distance(A, B)`：频繁传递样本的设备对越近越好
- `maximize_distance(A, B)`：振动敏感设备对越远越好
- `aisle_width ≥ 0.8m`：操作走道预留
- `cable_routing_space`：线缆走线空间

**无解处理策略**：按优先级逐级松弛（物理碰撞 > 可达性 > 距离约束 > 走道宽度），标记警告供用户人工确认。

### 6.4 机械臂离线可达性地图

**预计算方案**：

```python
# scripts/precompute_reachability.py
import numpy as np
from ikfast_elite_cs66 import get_ik  # 使用 IKFast 离线求解器

# 体素化参数
RESOLUTION = 0.05  # 50mm 体素
X_RANGE = (-2.5, 2.5)  # 5m x 5m x 2m 工作区域
Y_RANGE = (-2.5, 2.5)
Z_RANGE = (0.0, 2.0)

x_bins = int((X_RANGE[1] - X_RANGE[0]) / RESOLUTION)  # 100
y_bins = int((Y_RANGE[1] - Y_RANGE[0]) / RESOLUTION)  # 100
z_bins = int((Z_RANGE[1] - Z_RANGE[0]) / RESOLUTION)  # 40

# 约 100*100*40 = 40万体素，每个 1bit，总计 ~50KB/机型
reachability = np.zeros((x_bins, y_bins, z_bins), dtype=bool)

for xi, x in enumerate(np.arange(*X_RANGE, RESOLUTION)):
    for yi, y in enumerate(np.arange(*Y_RANGE, RESOLUTION)):
        for zi, z in enumerate(np.arange(*Z_RANGE, RESOLUTION)):
            solutions = get_ik(target_pos=(x, y, z), target_rot=...)
            reachability[xi, yi, zi] = len(solutions) > 0

np.savez_compressed(f"reachability_maps/elite_cs66.npz", map=reachability,
                    x_range=X_RANGE, y_range=Y_RANGE, z_range=Z_RANGE,
                    resolution=RESOLUTION)
```

**查表（O(1)）**：

```python
def is_reachable(arm_model: str, target_xyz: tuple) -> bool:
    data = np.load(f"reachability_maps/{arm_model}.npz")
    vmap = data["map"]
    res = float(data["resolution"])
    xi = int((target_xyz[0] - data["x_range"][0]) / res)
    yi = int((target_xyz[1] - data["y_range"][0]) / res)
    zi = int((target_xyz[2] - data["z_range"][0]) / res)
    if not (0 <= xi < vmap.shape[0] and 0 <= yi < vmap.shape[1] and 0 <= zi < vmap.shape[2]):
        return False
    return bool(vmap[xi, yi, zi])
```

---

## 7. 验收指标（修订版）

### 阶段一


| 指标               | 要求     | 测试条件                 |
| ---------------- | ------ | -------------------- |
| 后端 URDF 生成时间     | < 2s   | 5 台设备场景              |
| 前端 Three.js 初始渲染 | < 8s   | 5 台设备，STL 从本地 CDN 加载 |
| 场景总加载时间（后端+前端）   | < 10s  | 同上                   |
| 同时展示的最大设备数       | ≥ 15 台 | Chrome，普通办公电脑        |
| 碰撞精检测响应时间        | < 1s/次 | 后端 MoveIt2 FCL，5 台设备 |


### 阶段二


| 指标                   | 要求      | 测试条件                          |
| -------------------- | ------- | ----------------------------- |
| 工作流下发 → 前端关节动画延迟     | < 150ms | 局域网，ROSBridge/Foxglove Bridge |
| 前端渲染帧率               | ≥ 20fps | 5 台设备场景，Chrome                |
| WebSocket P99 延迟     | < 50ms  | 局域网                           |
| Bohrium 云端首次 URDF 加载 | < 3s    | 以 CDN 加速 STL 文件               |
| MoveIt2 单次运动规划时间     | < 500ms | 5 台设备场景，碰撞对象 ≤ 20 个           |


### 阶段三


| 指标                    | 要求    |
| --------------------- | ----- |
| AI 布局单次迭代（LLM + 约束验证） | < 5s  |
| 可达性查表                 | < 1ms |
| 差分进化收敛（15 台设备）        | < 60s |
| 输出方案硬约束满足率            | 100%  |


---

## 8. 最小可运行版本（MVP）关键路径

要尽快交付一个可展示的 3D 实验室可视化效果，最短路径如下（约 5-7 个工作日）：

```
Day 1
  ├── 修复 Bug A（坐标二义性）和 Bug B（station_name 注释）   0.5天
  ├── create_launch_description() 加 Foxglove Bridge 启动    0.5天
  └── server.py 加 /meshes 静态路由 + /api/v1/urdf 接口       0.5天（可并行）

Day 2
  └── ResourceVisualization.get_web_urdf() 方法               0.5天
      + 动态生成 .rviz 配置                                    0.5天

Day 3-5
  └── 前端基础骨架：
      Three.js + urdf-loader + Foxglove WebSocket 客户端
      - 加载 /api/v1/urdf，渲染静态场景
      - 订阅 /joint_states，驱动关节动画
      - 基础拖拽交互（无碰撞检测）

Day 6-7（并行）
  ├── Blender 凸包简化批处理脚本（arm_slider 等主力设备）
  └── Elite Robot 完整 MoveIt2 配置（SRDF + kinematics）

MVP 验收：
  用 arm_slider + thermo_orbitor 的 stirteststation.json
  ├── 浏览器中能看到实验室 3D 场景
  ├── arm_slider 机械臂在 MoveIt2 规划时有动画
  └── 切换布局后 URDF 自动刷新，场景更新
```

---

## 9. 附录：关键接口速查

### ROS2 话题（阶段一/二相关）


| Topic                       | 类型                              | 发布节点                                            | 频率       | 用途           |
| --------------------------- | ------------------------------- | ----------------------------------------------- | -------- | ------------ |
| `/robot_description`        | `std_msgs/String`               | robot_state_publisher                           | latched  | URDF 字符串     |
| `/joint_states`             | `sensor_msgs/JointState`        | joint_state_broadcaster / JointStateAdapterNode | 100Hz    | 关节角度         |
| `/tf`                       | `tf2_msgs/TFMessage`            | robot_state_publisher + ResourceMeshManager     | 50-100Hz | 坐标变换         |
| `/tf_static`                | `tf2_msgs/TFMessage`            | robot_state_publisher                           | latched  | 静态变换         |
| `/monitored_planning_scene` | `moveit_msgs/PlanningScene`     | move_group                                      | event    | 碰撞场景         |
| `/display_planned_path`     | `moveit_msgs/DisplayTrajectory` | move_group                                      | event    | 规划轨迹         |
| `resource_pose`             | `std_msgs/String`               | ResourceMeshManager                             | 50Hz     | 耗材位置变化 JSON  |
| `joint_state_repub`         | `std_msgs/String`               | JointRepublisher                                | 100Hz    | 关节角 JSON（已有） |


### FastAPI 接口（新增）


| Method      | Path                  | 说明                                   |
| ----------- | --------------------- | ------------------------------------ |
| `GET`       | `/api/v1/urdf`        | 返回当前 URDF（file:// 已替换为 HTTP URL）     |
| `POST`      | `/api/lab/layout`     | 更新设备位置，触发 URDF 重建 + PlanningScene 更新 |
| `GET`       | `/meshes/...`         | 静态网格文件服务（STL/DAE/GLB）                |
| `GET`       | `/api/v1/urdf/assets` | 返回可用资产列表（供前端资产面板）                    |
| `WebSocket` | `/ws/3d_status`       | 转发 resource_pose topic，耗材位置实时更新      |


---

*文档版本：v2.0（2026-03-14）*
*基于 `Uni-lab-os-3D-3.17new.md` 原始规划 + `MatterixUNILAB_3D_ANALYSIS.md` 代码审查结论整合*
*代码依据：`unilabos/device_mesh/resource_visalization.py`、`resource_mesh_manager.py`、`joint_republisher.py`、RViz2 Humble 文档、Foxglove Bridge GitHub*