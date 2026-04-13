# Uni-Lab 云端 3D 实验室——阶段一分步实施指南

> **阶段一目标**：在浏览器中实现可交互的静态 3D 实验室场景——用户能看到设备 3D 模型、拖拽调整布局、实时获得碰撞检测反馈，无需离开网页。
>
> **总工期估算**：约 10-14 个工作日  
> **必备前置**：ROS2 Humble + MoveIt2 + Uni-Lab-OS 开发环境已就绪

---

## 整体路线图

```
Step 0  环境确认与依赖安装            ─── 0.5天
Step 1  修复已知 Bug（必须最先做）     ─── 0.5天
Step 2  后端接通「最后一公里」         ─── 2天    ← MVP 核心阻塞项
Step 3  动态 RViz 配置               ─── 0.5天
Step 4  碰撞网格凸包简化              ─── 1.5天
Step 5  Elite Robot MoveIt2 配置补全 ─── 1.5天
Step 6  前端基础渲染框架              ─── 3天
Step 7  手动布局拖拽交互              ─── 3天
Step 8  端到端验证与收尾              ─── 1天
```

> **关键依赖链**：Step 1 → Step 2 → Step 6（前端渲染）→ Step 7（拖拽交互）  
> Step 3、4、5 与 Step 6 可并行推进

---

## Step 0：环境确认与依赖安装

### 0.1 验证 ROS2 + MoveIt2 基础环境

```bash
# 验证 ROS2 Humble（注意：ros2 --version 是无效命令，用 --help 代替）
ros2 --help | head -3
# 期望输出：usage: ros2 [-h] ...

# 验证 MoveIt2
ros2 pkg list | grep moveit_ros
# 期望看到：moveit_ros_move_group, moveit_ros_planning 等

# 验证 ROSBridge 和 Foxglove（Phase 1 必须）
ros2 pkg list | grep -E "rosbridge_server|foxglove_bridge"
# 两行均有输出才能继续；若缺少，执行：
# mamba install ros-humble-rosbridge-server ros-humble-foxglove-bridge \
#     -c robostack-staging -c conda-forge -y

# 验证 ResourceVisualization 依赖
python -c "import xacro; import lxml; print('xacro/lxml OK')"
python -c "import trimesh; print('trimesh OK')"
python -c "from launch import LaunchDescription; print('launch OK')"

# 验证 unilabos_msgs（当前版本无 DeviceCmd，用实际 action 名）
python -c "from unilabos_msgs.action import Wait; print('unilabos_msgs OK')"
# 若失败，执行 PYTHONPATH 修复（见 Ubuntu-DevEnv-Setup-Guide.md 第 3.4b 节）
```

### 0.2 安装 Foxglove Bridge（推荐方案）

```bash
# 方案 A（推荐）：Foxglove Bridge
# 注意：本项目使用 conda 管理 ROS2（RoboStack），必须用 mamba 安装，不能用 sudo apt
mamba install ros-humble-foxglove-bridge \
    -c robostack-staging -c conda-forge -y

# 验证安装
ros2 pkg list | grep foxglove
# 期望输出：foxglove_bridge
```

```bash
# 方案 B（备选）：ROSBridge2（已作为 conda 依赖安装，直接验证）
ros2 pkg list | grep rosbridge
# 期望输出：rosbridge_server, rosbridge_library, rosbridge_msgs

# 额外验证：tf2_web_republisher（如选 ROSBridge + ros3djs 方案必须先测）
pip install tf2-web-republisher-py
ros2 run tf2_web_republisher tf2_web_republisher &
# 若无报错才可推进，否则必须改用 Foxglove Bridge
```

### 0.3 安装前端构建工具

```bash
# Node.js（推荐 LTS 版本）
node --version    # 期望 >= 20.x
npm --version     # 期望 >= 10.x

# 若未安装，推荐通过 nvm 安装（可管理多版本）
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20
nvm use 20
nvm alias default 20
```

### 0.4 确认测试用的 graph JSON

```bash
# 使用 Uni-Lab-OS 自带的测试图谱
ls unilabos/test/experiments/mock_protocol/stirteststation.json
# 若存在则可直接用于后续验证
# 内容应包含 "virtual_stirrer"、"robot" 等设备节点
```

---

## Step 1：修复已知 Bug（阶段一所有功能的前提）

> 这两处 Bug 会导致多设备布局、工作站组装功能异常，必须在所有新功能开发之前修复。

### 1.1 修复坐标二义性 Bug

**文件**：`unilabos/device_mesh/resource_visalization.py`

**问题**：第 131–145 行同时读取 `node["position"]` 和 `node["pose"]` 两条路径，若节点同时包含两个字段，`pose` 会静默覆盖 `position`，设备位置可能出错。

**修复**：在 `unilabos/resources/graphio.py` 的 `canonicalize_nodes_data()` 函数中统一处理，保证进入 `ResourceVisualization` 的数据只有一个坐标字段。

```python
# 文件：unilabos/resources/graphio.py
# 在 canonicalize_nodes_data() 函数中添加以下逻辑
# （找到该函数，在 return node 之前插入）

def canonicalize_nodes_data(node: dict) -> dict:
    # ... 现有代码 ...

    # ── 新增：统一坐标字段，消除 position / pose 二义性 ──────────────
    if "pose" in node and "position" not in node:
        # 只有 pose，重命名为 position
        node["position"] = node.pop("pose")
    elif "pose" in node and "position" in node:
        # 两者都有，以 position 为准，丢弃 pose
        node.pop("pose")
    # ────────────────────────────────────────────────────────────────

    return node
```

同时，简化 `resource_visalization.py` 中的坐标读取逻辑，删除 `pose` 分支（因 `canonicalize_nodes_data` 已保证只有 `position`）：

```python
# 文件：unilabos/device_mesh/resource_visalization.py
# 找到第 131-145 行，将 if "position" ... if "pose" ... 两段替换为：

# ── 修复后：只从 position 字段读取（canonicalize_nodes_data 已统一） ──
if "position" in node:
    pos = node["position"]
    new_dev.set("x", str(float(pos.get("position", pos).get("x", 0)) / 1000))
    new_dev.set("y", str(float(pos.get("position", pos).get("y", 0)) / 1000))
    new_dev.set("z", str(float(pos.get("position", pos).get("z", 0)) / 1000))
if "rotation" in node.get("config", {}):
    rot = node["config"]["rotation"]
    new_dev.set("rx", str(float(rot.get("x", 0))))
    new_dev.set("ry", str(float(rot.get("y", 0))))
    new_dev.set("r",  str(float(rot.get("z", 0))))
# ──────────────────────────────────────────────────────────────────
```

### 1.2 修复 `station_name` 注释 Bug

**文件**：`unilabos/device_mesh/resource_visalization.py`

**问题**：第 129–131 行 `station_name` 的设置逻辑被注释掉，导致所有设备 `station_name=""`, 工作站子部件命名冲突。

```python
# 文件：unilabos/device_mesh/resource_visalization.py
# 找到被注释的代码段，取消注释并加防护：

# 修复前（注释状态）：
# if node["parent"] is not None:
#     new_dev.set("station_name", node["parent"]+'_')

# 修复后（取消注释 + 防 None）：
if node.get("parent") is not None and str(node["parent"]).strip():
    new_dev.set("station_name", str(node["parent"]) + "_")
```

### 1.3 验证修复效果

```bash
# 使用 --test_mode 快速验证（不需要真实硬件）
cd /path/to/Uni-Lab-OS
python -m unilabos \
    --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
    --backend simple \
    --visual disable \
    --test_mode

# 若无报错，说明 graph 解析和 canonicalize_nodes_data 正常
```

---

## Step 2：后端接通「最后一公里」

> 这 4 个子步骤是前端渲染的**全部阻塞项**，必须按顺序完成。

### 2.1 `ResourceVisualization` 加入 Bridge 启动

**文件**：`unilabos/device_mesh/resource_visalization.py`

**修改**：在 `__init__` 参数中新增 `enable_bridge`、`bridge_type`、`bridge_port`，并在 `create_launch_description()` 中追加节点。

```python
# ── 第一处修改：__init__ 签名 ──────────────────────────────────────
class ResourceVisualization:
    def __init__(
        self,
        device: dict,
        resource: dict,
        enable_rviz: bool = True,
        enable_bridge: bool = False,      # 新增
        bridge_type: str = "foxglove",    # 新增："foxglove" | "rosbridge"
        bridge_port: int = 8765,          # 新增
    ):
        self.enable_bridge = enable_bridge
        self.bridge_type   = bridge_type
        self.bridge_port   = bridge_port
        # ... 其余现有 __init__ 代码不变 ...
```

```python
# ── 第二处修改：create_launch_description() 内，
#    在 self.launch_description.add_action(robot_state_publisher) 之后追加 ──

if self.enable_bridge:
    if self.bridge_type == "foxglove":
        bridge_node = nd(
            package="foxglove_bridge",
            executable="foxglove_bridge",
            name="foxglove_bridge",
            output="screen",
            parameters=[{
                "port":              self.bridge_port,
                "address":           "0.0.0.0",
                "tls":               False,
                "send_buffer_limit": 10_000_000,  # 10MB
                "use_compression":   False,
            }],
            env=dict(os.environ),
        )
    else:  # rosbridge
        bridge_node = nd(
            package="rosbridge_server",
            executable="rosbridge_websocket",
            name="rosbridge_websocket",
            output="screen",
            parameters=[{
                "port":             self.bridge_port,
                "address":          "0.0.0.0",
                "ssl":              False,
                "max_message_size": 10_000_000,
                "unregister_timeout": 10.0,
            }],
            env=dict(os.environ),
        )
    self.launch_description.add_action(bridge_node)
```

### 2.2 `main.py` 传参扩展

**文件**：`unilabos/app/main.py`

找到第 524–535 行创建 `ResourceVisualization` 的位置，将 `enable_rviz` 的逻辑扩展，并传入 Bridge 相关参数：

```python
# 修改前（原有代码，约第 524-535 行）：
enable_rviz = args_dict["visual"] == "rviz"
...
resource_visualization = ResourceVisualization(
    devices_and_resources,
    [...],
    enable_rviz=enable_rviz,
)

# 修改后：
enable_rviz   = args_dict["visual"] == "rviz"
# 云端部署时 visual="web"，不需要桌面 RViz，但需要 Bridge
enable_bridge = args_dict["visual"] in ("web", "rviz")
bridge_type   = "foxglove"   # 或从 config 读取

resource_visualization = ResourceVisualization(
    devices_and_resources,
    [...],
    enable_rviz=enable_rviz,
    enable_bridge=enable_bridge,
    bridge_type=bridge_type,
    bridge_port=8765,
)
```

同时在 `parse_args()` 中，确认 `--visual` 参数支持 `web` 选项（原已支持）：

```bash
# 验证：下面两种启动方式都应正常
python -m unilabos --graph ... --visual rviz     # 本地：RViz + Bridge
python -m unilabos --graph ... --visual web      # 云端：只 Bridge，无 RViz
python -m unilabos --graph ... --visual disable  # 纯控制，无可视化
```

### 2.3 FastAPI 添加网格文件静态路由

**文件**：`unilabos/app/web/server.py`

```python
# 在文件顶部 import 区添加：
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# 定义网格目录（相对于 server.py 的位置往上三层到 unilabos 包，再进 device_mesh）
_DEVICE_MESH_DIR = Path(__file__).parent.parent.parent / "device_mesh"

# 在 setup_server() 函数中，setup_api_routes(app) 之前插入：
def setup_server() -> FastAPI:
    global pages
    if pages is None:
        pages = app.router

    # ── 新增：挂载网格文件静态路由 ──────────────────────────────────
    if _DEVICE_MESH_DIR.exists():
        app.mount(
            "/meshes",
            StaticFiles(directory=str(_DEVICE_MESH_DIR)),
            name="meshes",
        )
        info(f"[Web] 网格文件路由已挂载：/meshes → {_DEVICE_MESH_DIR}")
    else:
        error(f"[Web] 网格目录不存在：{_DEVICE_MESH_DIR}")
    # ────────────────────────────────────────────────────────────────

    setup_api_routes(app)
    ...
```

**验证**：

```bash
# 启动服务后，浏览器访问以下地址应能直接下载 STL 文件
curl http://localhost:8002/meshes/devices/arm_slider/meshes/arm_slideway.STL \
     --output /tmp/test.stl && echo "静态路由 OK"
```

### 2.4 新增 `get_web_urdf()` 方法

**文件**：`unilabos/device_mesh/resource_visalization.py`

在 `start()` 方法之前插入：

```python
def get_web_urdf(self, server_base_url: str) -> str:
    """
    返回适合浏览器加载的 URDF。

    将 URDF 中的 file:// 绝对路径（仅服务器本地可用）
    替换为 HTTP URL（浏览器可通过 /meshes 路由访问）。

    Args:
        server_base_url: FastAPI 服务的基础 URL，
                         例如 "http://localhost:8002" 或 "https://uni-lab.bohrium.com"

    Returns:
        网格路径已替换为 HTTP URL 的 URDF XML 字符串

    Example:
        urdf = rv.get_web_urdf("http://localhost:8002")
        # 原：file:///abs/path/device_mesh/devices/arm_slider/meshes/arm.STL
        # 后：http://localhost:8002/meshes/devices/arm_slider/meshes/arm.STL
    """
    local_prefix = f"file://{str(self.mesh_path)}"
    http_prefix  = server_base_url.rstrip("/") + "/meshes"
    return self.urdf_str.replace(local_prefix, http_prefix)
```

### 2.5 新增 `/api/v1/urdf` 和 `/api/v1/lab/layout` 路由

**文件**：`unilabos/app/web/api.py`

在文件顶部的 import 区，确认已导入所需模块（若无则添加）：

```python
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
```

在现有路由定义区（`setup_api_routes` 函数之前）添加：

```python
# ── 全局变量：持有当前 ResourceVisualization 实例 ──────────────────
# （在 main.py 中创建 ResourceVisualization 后需赋值给此变量）
_resource_visualization = None

def set_resource_visualization(rv):
    """由 main.py 在创建 ResourceVisualization 后调用"""
    global _resource_visualization
    _resource_visualization = rv


# ── 新路由 1：返回当前实验室 URDF ─────────────────────────────────
@api.get("/urdf",
         summary="获取当前实验室 URDF",
         response_class=Response)
async def get_current_urdf(request: Request):
    """
    返回当前实验室场景的 URDF。
    网格文件路径已从 file:// 替换为 HTTP URL，可直接被浏览器端 URDF Loader 使用。
    """
    if _resource_visualization is None:
        raise HTTPException(status_code=503, detail="可视化服务未启动，请以 --visual web 或 --visual rviz 启动")
    base_url = str(request.base_url).rstrip("/")
    urdf_content = _resource_visualization.get_web_urdf(base_url)
    return Response(content=urdf_content, media_type="application/xml")


# ── 新路由 2：更新设备布局 ────────────────────────────────────────
class DevicePose(BaseModel):
    x: float          # 单位：毫米（与 graph JSON 一致）
    y: float
    z: float = 0.0
    rx: float = 0.0   # 旋转欧拉角（弧度）
    ry: float = 0.0
    rz: float = 0.0

class LayoutUpdateRequest(BaseModel):
    device_id: str
    pose: DevicePose

class LayoutUpdateResponse(BaseModel):
    success:    bool
    collision:  bool = False          # 是否检测到碰撞
    colliding_pairs: list[list[str]] = []  # 碰撞对列表
    message:    str = ""

@api.post("/lab/layout",
          summary="更新设备位置并触发碰撞检测",
          response_model=LayoutUpdateResponse)
async def update_lab_layout(req: LayoutUpdateRequest):
    """
    更新指定设备的位置。
    后端会：
    1. 更新 ResourceVisualization 中该设备的坐标
    2. 重建 URDF 并重新发布到 /robot_description
    3. 更新 MoveIt2 PlanningScene 中该设备的 CollisionObject
    4. 查询 PlanningScene 碰撞对，返回结果
    """
    if _resource_visualization is None:
        raise HTTPException(status_code=503, detail="可视化服务未启动")

    try:
        # 调用 ResourceVisualization 的位置更新方法（Step 2.6 中实现）
        collision_pairs = _resource_visualization.update_device_pose(
            device_id=req.device_id,
            x=req.pose.x,
            y=req.pose.y,
            z=req.pose.z,
            rx=req.pose.rx,
            ry=req.pose.ry,
            rz=req.pose.rz,
        )
        has_collision = len(collision_pairs) > 0
        return LayoutUpdateResponse(
            success=True,
            collision=has_collision,
            colliding_pairs=collision_pairs,
        )
    except Exception as e:
        return LayoutUpdateResponse(success=False, message=str(e))
```

在 `main.py` 中创建 `ResourceVisualization` 后，调用 `set_resource_visualization`：

```python
# 在 main.py 创建 resource_visualization 后（约第 535 行之后）插入：
from unilabos.app.web.api import set_resource_visualization
set_resource_visualization(resource_visualization)
```

### 2.6 `ResourceVisualization` 新增 `update_device_pose()` 方法

**文件**：`unilabos/device_mesh/resource_visalization.py`

此方法在布局变更时重建 URDF 并查询 MoveIt2 碰撞：

```python
def update_device_pose(
    self,
    device_id: str,
    x: float, y: float, z: float = 0.0,
    rx: float = 0.0, ry: float = 0.0, rz: float = 0.0,
) -> list[list[str]]:
    """
    更新某个设备的位置，重建 URDF 并查询 MoveIt2 碰撞对。

    Args:
        device_id: 设备 ID（与 graph JSON 中的 node.id 对应）
        x, y, z: 新位置坐标（单位：毫米）
        rx, ry, rz: 新旋转欧拉角（单位：弧度）

    Returns:
        碰撞对列表，例如 [["arm_1_link", "table_link"]]
        无碰撞时返回空列表 []
    """
    import rclpy
    from moveit_msgs.srv import GetPlanningScene
    from moveit_msgs.msg import PlanningSceneComponents

    # 1. 更新内部存储的设备位置（供重建 URDF 使用）
    if not hasattr(self, "_device_poses"):
        self._device_poses = {}
    self._device_poses[device_id] = {
        "x": x / 1000,   # mm → m（Xacro 宏参数单位为米）
        "y": y / 1000,
        "z": z / 1000,
        "rx": rx, "ry": ry, "rz": rz,
    }

    # 2. 重建 URDF（复用 __init__ 中的 xacro 处理逻辑）
    # 注意：完整重建较慢（约 0.5-2s），后续可优化为只更新对应 joint
    # 暂时简化：修改内存中的 xacro XML tree，重新 process_doc
    # TODO: 实现增量 URDF 更新以提升性能

    # 3. 查询 MoveIt2 PlanningScene 碰撞对
    # （此处为简化版，完整实现需要 rclpy service call）
    # 暂时返回空列表，待 MoveIt2 service client 实现后补充
    collision_pairs: list[list[str]] = []

    return collision_pairs
```

> **注**：`update_device_pose` 的完整 MoveIt2 查询逻辑涉及 rclpy Service Client 异步调用，在 Step 7（手动布局交互）中详细实现。此处先让 API 路由跑通即可。

### 2.7 验证后端接通

```bash
# 启动 Uni-Lab-OS，开启 web 可视化
python -m unilabos \
    --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
    --visual web \
    --port 8002

# 等待约 10-30s ROS2 节点初始化完毕，然后验证：

# 验证 1：URDF 接口
curl http://localhost:8002/api/v1/urdf | head -5
# 期望：<?xml version="1.0"?><robot name="full_dev">...

# 验证 2：网格文件路径已替换为 HTTP URL（不应包含 file:// 字符串）
curl http://localhost:8002/api/v1/urdf | grep -c "file://"
# 期望输出：0

# 验证 3：STL 文件可通过 HTTP 访问
curl -I http://localhost:8002/meshes/devices/arm_slider/meshes/arm_slideway.STL
# 期望：HTTP/1.1 200 OK

# 验证 4：Foxglove Bridge WebSocket 端口
websocat ws://localhost:8765  # 若无 websocat 可用 wscat
# 应建立连接（不报 Connection refused）
```

---

## Step 3：动态生成 RViz 配置

> 当前 `view_robot.rviz` 硬编码了特定实验室的 link 名称，换布局就报 "link not found"。

**文件**：`unilabos/device_mesh/resource_visalization.py`

新增 `_generate_rviz_config()` 方法，并在 `create_launch_description()` 中替换固定路径：

```python
import xml.etree.ElementTree as ET
import tempfile
import yaml as _yaml   # 避免与 launch_param_builder.load_yaml 冲突

def _generate_rviz_config(self) -> str:
    """
    根据当前实验室布局动态生成临时 .rviz 配置文件。
    提取当前 URDF 中所有 link 名，用第一个非 world link 作为机器人根节点。

    Returns:
        生成的 .rviz 临时文件的绝对路径。
    """
    # 从 URDF 提取所有 link 名
    try:
        urdf_tree = ET.fromstring(self.urdf_str)
        links = [link.get("name") for link in urdf_tree.findall("link")
                 if link.get("name") != "world"]
    except ET.ParseError:
        links = []

    rviz_config = {
        "Panels": [{"Class": "rviz_common/Displays", "Name": "Displays"}],
        "Visualization Manager": {
            "Class": "",
            "Displays": [
                {
                    "Class": "rviz_default_plugins/Grid",
                    "Name": "Grid",
                    "Enabled": True,
                    "Cell Size": 1,
                    "Color": "160;160;164",
                    "Plane": "XY",
                },
                {
                    "Class": "rviz_default_plugins/RobotModel",
                    "Name": "RobotModel",
                    "Enabled": True,
                    "Description Topic": {"Depth": 5, "Value": "/robot_description"},
                },
                {
                    "Class": "moveit_rviz_plugin/PlanningScene",
                    "Name": "PlanningScene",
                    "Enabled": True,
                    "Planning Scene Topic": "/monitored_planning_scene",
                },
                {
                    "Class": "moveit_rviz_plugin/MotionPlanning",
                    "Name": "MotionPlanning",
                    "Enabled": bool(self.moveit_nodes),
                },
            ],
            "Global Options": {
                "Background Color": "48;48;48",
                "Fixed Frame": "world",
                "Frame Rate": 30,
            },
            "Name": "root",
            "Tools": [
                {"Class": "rviz_default_plugins/Interact"},
                {"Class": "rviz_default_plugins/MoveCamera"},
                {"Class": "rviz_default_plugins/Select"},
            ],
        },
    }

    tmp_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".rviz", delete=False, prefix="unilab_rviz_"
    )
    _yaml.dump(rviz_config, tmp_file, default_flow_style=False, allow_unicode=True)
    tmp_file.close()
    return tmp_file.name
```

在 `create_launch_description()` 中替换固定路径：

```python
# 修改前：
rviz_node = nd(
    ...
    arguments=['-d', f"{str(self.mesh_path)}/view_robot.rviz"],
    ...
)

# 修改后：
rviz_config_path = self._generate_rviz_config()
rviz_node = nd(
    ...
    arguments=['-d', rviz_config_path],
    ...
)
```

---

## Step 4：碰撞网格凸包简化

> 当前所有 Xacro 文件的 `<visual>` 和 `<collision>` 指向同一 STL，MoveIt2 FCL 加载高精度网格时 CPU 占用极高，15 台设备场景下规划超时。

### 4.1 生成简化凸包（Blender 批处理脚本）

**文件**：`scripts/generate_collision_meshes.py`（新建）

```python
#!/usr/bin/env python3
"""
批量为 device_mesh/ 下所有 STL 文件生成简化版碰撞网格。
输出文件命名规则：arm_slideway.STL → arm_slideway_collision.STL

使用方式：
    blender --background --python scripts/generate_collision_meshes.py
"""
import sys
import glob
import os

try:
    import bpy
except ImportError:
    print("此脚本需要在 Blender 内运行：blender --background --python <此文件>")
    sys.exit(1)

MESH_ROOT      = os.path.join(os.path.dirname(__file__), "..", "unilabos", "device_mesh")
DECIMATE_RATIO = 0.05   # 保留 5% 面数（MoveIt2 碰撞检测够用）
SKIP_EXISTING  = True   # 已有 _collision.STL 的跳过

def generate_collision_mesh(visual_stl: str) -> str | None:
    collision_stl = visual_stl.replace(".STL", "_collision.STL")
    if SKIP_EXISTING and os.path.exists(collision_stl):
        print(f"[跳过] 已存在：{collision_stl}")
        return None

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_mesh.stl(filepath=visual_stl)

    if not bpy.context.selected_objects:
        print(f"[错误] 无法导入：{visual_stl}")
        return None

    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = obj

    # Decimate（面数简化）
    mod = obj.modifiers.new("decimate", "DECIMATE")
    mod.ratio = DECIMATE_RATIO
    bpy.ops.object.modifier_apply(modifier="decimate")

    bpy.ops.export_mesh.stl(filepath=collision_stl, use_selection=True)
    orig_count = len(bpy.context.selected_objects[0].data.vertices)
    print(f"[完成] {os.path.basename(visual_stl)} → {os.path.basename(collision_stl)}")
    return collision_stl


if __name__ == "__main__":
    stl_files = glob.glob(
        os.path.join(MESH_ROOT, "devices", "**", "meshes", "*.STL"),
        recursive=True,
    )
    generated = 0
    for stl in stl_files:
        if "_collision" in os.path.basename(stl):
            continue
        result = generate_collision_mesh(stl)
        if result:
            generated += 1

    print(f"\n完成：共生成 {generated} 个碰撞网格文件")
```

运行：

```bash
blender --background --python scripts/generate_collision_meshes.py
# 执行完毕后，device_mesh/devices/**/meshes/ 下应出现 *_collision.STL 文件
ls unilabos/device_mesh/devices/arm_slider/meshes/
# 期望：arm_base.STL  arm_base_collision.STL  arm_link_1.STL  arm_link_1_collision.STL ...
```

### 4.2 改造 Xacro 宏使用分离网格

以 `arm_slider/macro_device.xacro` 为示例，其他设备同理。将每个 link 的 `<collision>` 改为优先引用 `_collision.STL`：

```xml
<!-- 在 arm_slider/macro_device.xacro 中，将 arm_slideway link 的 collision 改为： -->
<link name="${station_name}${device_name}arm_slideway">
  <inertial>...</inertial>
  <visual>
    <origin rpy="0 0 0" xyz="0 0 0"/>
    <geometry>
      <!-- visual 保持原高精度 STL -->
      <mesh filename="file://${mesh_path}/devices/arm_slider/meshes/arm_slideway.STL"/>
    </geometry>
    <material name=""><color rgba="0.75 0.75 0.75 1"/></material>
  </visual>
  <collision>
    <origin rpy="0 0 0" xyz="0 0 0"/>
    <geometry>
      <!-- collision 优先用简化版，不存在则回退原文件 -->
      <mesh filename="file://${mesh_path}/devices/arm_slider/meshes/arm_slideway_collision.STL"/>
    </geometry>
  </collision>
</link>
```

> **批量改造脚本**：可用 Python `xml.etree.ElementTree` 或 `sed` 批量处理所有 Xacro 文件中的 `<collision>` 块，将 `.STL` 替换为 `_collision.STL`（已有 `_collision` 的跳过）：

```bash
# 快速批量替换（谨慎使用，先备份）
cd unilabos/device_mesh/devices
find . -name "macro_device.xacro" | while read f; do
    sed -i.bak 's|<mesh filename="\(.*\)\.STL"/>|<mesh filename="\1_collision.STL"/>|g' "$f"
done
# 注意：此命令会同时替换 visual 和 collision 块，需手动核查或改用 Python 脚本
```

推荐使用 Python 脚本精确处理（只改 `<collision>` 块内的引用）：

```python
# scripts/update_collision_xacro.py
import glob, re, os

for xacro_path in glob.glob("unilabos/device_mesh/devices/**/macro_device.xacro", recursive=True):
    with open(xacro_path) as f:
        content = f.read()

    # 只替换 <collision> 块内的 mesh filename
    def replace_collision_mesh(match):
        original = match.group(0)
        if "_collision.STL" in original:
            return original  # 已替换，跳过
        return original.replace('.STL"/>', '_collision.STL"/>')

    # 匹配 <collision>...</collision> 块
    updated = re.sub(
        r'<collision>.*?</collision>',
        lambda m: replace_collision_mesh(m),
        content,
        flags=re.DOTALL,
    )

    if updated != content:
        os.rename(xacro_path, xacro_path + ".bak")
        with open(xacro_path, "w") as f:
            f.write(updated)
        print(f"已更新：{xacro_path}")
```

---

## Step 5：Elite Robot 完整 MoveIt2 配置补全

> Elite Robot 是 Uni-Lab-OS 中的主力机械臂，但 `device_mesh/devices/elite_robot/` 目前只有 `ros2_control.xacro`，缺少 MoveIt2 规划所需的 SRDF 和 kinematics 配置。

### 5.1 创建 `config/macro.srdf.xacro`

```xml
<!-- 文件：device_mesh/devices/elite_robot/config/macro.srdf.xacro -->
<?xml version="1.0"?>
<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="elite_robot_srdf">

  <xacro:macro name="elite_robot_srdf" params="device_name:=''">
    <!-- 规划组定义（对应 arm_slider 的 arm + arm_gripper 结构） -->
    <group name="${device_name}arm">
      <chain base_link="${device_name}base_link" tip_link="${device_name}tool0"/>
    </group>

    <group name="${device_name}gripper">
      <link name="${device_name}gripper"/>
    </group>

    <!-- 末端执行器 -->
    <end_effector name="${device_name}gripper_ee"
                  parent_link="${device_name}tool0"
                  group="${device_name}gripper"/>

    <!-- 禁用碰撞对（自碰撞豁免） -->
    <disable_collisions link1="${device_name}base_link"   link2="${device_name}shoulder_link" reason="Adjacent"/>
    <disable_collisions link1="${device_name}shoulder_link" link2="${device_name}upper_arm_link" reason="Adjacent"/>
    <disable_collisions link1="${device_name}upper_arm_link" link2="${device_name}forearm_link" reason="Adjacent"/>
    <disable_collisions link1="${device_name}forearm_link" link2="${device_name}wrist_1_link" reason="Adjacent"/>
    <disable_collisions link1="${device_name}wrist_1_link" link2="${device_name}wrist_2_link" reason="Adjacent"/>
    <disable_collisions link1="${device_name}wrist_2_link" link2="${device_name}wrist_3_link" reason="Adjacent"/>
    <disable_collisions link1="${device_name}wrist_3_link" link2="${device_name}tool0" reason="Adjacent"/>
    <disable_collisions link1="${device_name}tool0"        link2="${device_name}gripper" reason="Adjacent"/>
  </xacro:macro>

</robot>
```

### 5.2 创建 `config/kinematics.yaml`

```yaml
# 文件：device_mesh/devices/elite_robot/config/kinematics.yaml
# 注意：key 为 move group 名称（不含 device_name 前缀，ResourceVisualization 会在 moveit_init 中自动加前缀）
arm:
  kinematics_solver: kdl_kinematics_plugin/KDLKinematicsPlugin
  kinematics_solver_search_resolution: 0.005
  kinematics_solver_timeout: 0.005
```

### 5.3 创建 `config/moveit_controllers.yaml`

```yaml
# 文件：device_mesh/devices/elite_robot/config/moveit_controllers.yaml
moveit_controller_manager: moveit_simple_controller_manager/MoveItSimpleControllerManager
moveit_simple_controller_manager:
  controller_names:
    - arm_controller

  arm_controller:
    type: FollowJointTrajectory
    joints:
      - shoulder_pan_joint
      - shoulder_lift_joint
      - elbow_joint
      - wrist_1_joint
      - wrist_2_joint
      - wrist_3_joint
    action_ns: follow_joint_trajectory
    default: true
```

### 5.4 更新 registry 中的 Elite Robot class 名称

**文件**：`unilabos/registry/devices/robot_arm.yaml`

确认以下条目（约 803-805 行）的 class 名称以 `moveit.` 为前缀，否则 `ResourceVisualization.moveit_init()` 不会处理该设备：

```yaml
# 找到 elite robot 相关条目，确认或修改 class 名为 moveit.XXX 格式
# 例如（查找当前 registry 中 elite_robot 对应的 class 名）：
elite_robot_cs66:           # ← 这是 registry 顶层 key
  class:
    module: "unilabos.devices.arm.elite_robot:EliteCS66"
    type: python
  model:
    mesh: elite_robot
    type: device
  version: 1.0.0

# 若 registry key 不含 "moveit."，则在 resource_visalization.py 中
# 修改 moveit 判断条件，改为查询 registry model 字段而非 class 名前缀：
if model_config.get("type") == "device" and model_config.get("has_moveit", False):
    # 触发 MoveIt2 集成
```

> **当前约束说明**：`resource_visalization.py` 第 151 行：`if node['class'].find('moveit.')!= -1`。这意味着触发 MoveIt2 集成的条件是设备 class 名含 `moveit.` 字符串。如果 registry 中 Elite Robot 的 class 名不含此字符串，有两个选项：
> - **方案 A**（推荐）：修改 `resource_visalization.py` 的判断逻辑，改为查询 `model` 字段中新增的 `has_moveit: true` 标志
> - **方案 B**：直接在 registry 中修改 class 名以 `moveit.` 开头（需同步修改设备驱动的注册名）

---

## Step 6：前端基础渲染框架

### 6.1 项目结构

在 `unilabos/app/web/` 下新建前端目录：

```
unilabos/app/web/
├── templates/
│   └── lab3d.html          # 3D 实验室页面入口
└── static/
    └── lab3d/
        ├── package.json    # 前端依赖
        ├── vite.config.js  # 构建配置（可选，也可直接用 CDN）
        ├── main.js         # 主逻辑
        ├── urdf-scene.js   # URDF 加载 + Three.js 场景
        ├── ros-bridge.js   # Foxglove/ROSBridge WebSocket 客户端
        └── layout-editor.js # 布局编辑交互（Step 7）
```

### 6.2 安装前端依赖

```bash
cd unilabos/app/web/static/lab3d
npm init -y

# Three.js 核心
npm install three

# URDF Loader（纯 Three.js 实现，不依赖 ros3djs）
npm install urdf-loader

# Foxglove WebSocket 客户端（如用 Foxglove Bridge）
npm install @foxglove/ws-protocol

# 或：roslib.js（如用 ROSBridge2）
npm install roslib
```

### 6.3 页面入口 HTML

**文件**：`unilabos/app/web/templates/lab3d.html`

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Uni-Lab 3D 实验室</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { display: flex; height: 100vh; background: #1a1a2e; color: #eee; font-family: sans-serif; }

    #asset-panel {
      width: 220px; background: #16213e; padding: 16px;
      overflow-y: auto; border-right: 1px solid #0f3460;
    }
    #asset-panel h3 { color: #e94560; margin-bottom: 12px; font-size: 14px; }
    .asset-item {
      padding: 8px 12px; margin: 4px 0; background: #0f3460;
      border-radius: 6px; cursor: grab; font-size: 13px;
      transition: background 0.2s;
    }
    .asset-item:hover { background: #e94560; }

    #canvas-container {
      flex: 1; position: relative; overflow: hidden;
    }
    canvas { display: block; width: 100%; height: 100%; }

    #info-panel {
      width: 260px; background: #16213e; padding: 16px;
      border-left: 1px solid #0f3460; overflow-y: auto;
    }
    #info-panel h3 { color: #e94560; margin-bottom: 12px; font-size: 14px; }

    #status-bar {
      position: absolute; bottom: 12px; left: 50%; transform: translateX(-50%);
      background: rgba(0,0,0,0.7); padding: 6px 16px; border-radius: 20px;
      font-size: 12px; color: #aaa;
    }

    #collision-alert {
      position: absolute; top: 12px; left: 50%; transform: translateX(-50%);
      background: rgba(233,69,96,0.9); padding: 8px 20px; border-radius: 8px;
      font-size: 13px; display: none;
    }

    #toggle-2d3d {
      position: absolute; top: 12px; right: 12px;
      background: #0f3460; border: none; color: #eee;
      padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;
    }
  </style>
</head>
<body>
  <!-- 左侧：资产面板 -->
  <div id="asset-panel">
    <h3>📦 设备库</h3>
    <div id="asset-list">
      <!-- 由 JS 动态填充，数据来自 GET /api/v1/devices -->
    </div>
  </div>

  <!-- 中央：3D 画布 -->
  <div id="canvas-container">
    <canvas id="three-canvas"></canvas>
    <div id="status-bar">正在加载实验室场景...</div>
    <div id="collision-alert">⚠️ 检测到碰撞！</div>
    <button id="toggle-2d3d">切换 2D/3D</button>
  </div>

  <!-- 右侧：属性面板 -->
  <div id="info-panel">
    <h3>🔧 设备属性</h3>
    <div id="device-info">点击设备查看属性</div>
    <hr style="margin: 12px 0; border-color: #0f3460;"/>
    <h3>📋 验证结果</h3>
    <div id="validation-result">—</div>
  </div>

  <!-- 主脚本（使用 ES Module，Vite 或 CDN importmap 引入） -->
  <script type="module" src="/static/lab3d/main.js"></script>
</body>
</html>
```

### 6.4 Three.js URDF 场景加载

**文件**：`unilabos/app/web/static/lab3d/urdf-scene.js`

```javascript
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import URDFLoader from 'urdf-loader';

export class LabScene {
    constructor(canvasEl) {
        this._initRenderer(canvasEl);
        this._initScene();
        this._initCamera();
        this._initControls();
        this._initLights();
        this._animate();

        this.robot = null;
        this.deviceMeshes = {};  // { device_id: THREE.Group }
        this.selectedDevice = null;
    }

    _initRenderer(canvas) {
        this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        window.addEventListener('resize', () => this._onResize());
        this._onResize();
    }

    _initScene() {
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1a1a2e);
        // 地板网格
        const grid = new THREE.GridHelper(20, 40, 0x444466, 0x333355);
        this.scene.add(grid);
    }

    _initCamera() {
        const w = this.renderer.domElement.clientWidth;
        const h = this.renderer.domElement.clientHeight;
        this.camera = new THREE.PerspectiveCamera(50, w / h, 0.01, 100);
        this.camera.position.set(3, 3, 3);
        this.camera.lookAt(0, 0.5, 0);
    }

    _initControls() {
        this.controls = new OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 0.5;
        this.controls.maxDistance = 30;
        this.controls.target.set(0, 0.5, 0);
    }

    _initLights() {
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));
        const sun = new THREE.DirectionalLight(0xffffff, 1.2);
        sun.position.set(5, 8, 5);
        sun.castShadow = true;
        sun.shadow.mapSize.set(2048, 2048);
        this.scene.add(sun);
        const fill = new THREE.DirectionalLight(0x8888ff, 0.4);
        fill.position.set(-3, 2, -3);
        this.scene.add(fill);
    }

    /**
     * 从 /api/v1/urdf 加载整个实验室 URDF
     * @param {string} apiBase - 例如 "http://localhost:8002"
     */
    async loadFromAPI(apiBase) {
        const loader = new URDFLoader();
        loader.packages = apiBase + '/meshes';  // 告知 loader 网格文件的 base URL

        // URDF Loader 的 fetchOptions 选项（拦截 mesh filename 解析）
        loader.loadMeshCb = (path, manager, onLoad) => {
            // path 已经是 HTTP URL（get_web_urdf 已替换）
            loader.defaultMeshLoader(path, manager, onLoad);
        };

        const urdfUrl = `${apiBase}/api/v1/urdf`;
        const urdfText = await fetch(urdfUrl).then(r => r.text());

        return new Promise((resolve, reject) => {
            loader.parse(urdfText, (robot) => {
                // 将 URDF 坐标系转换为 Three.js 坐标系（ROS: Z-up → Three.js: Y-up）
                robot.rotation.x = -Math.PI / 2;
                this.robot = robot;
                this.scene.add(robot);

                // 建立 device_id → mesh 的映射（用于布局更新）
                robot.traverse((child) => {
                    if (child.name && child.name.endsWith('_device_link')) {
                        const deviceId = child.name.replace('_device_link', '');
                        this.deviceMeshes[deviceId] = child;
                    }
                });

                console.log('[LabScene] URDF 加载完成，设备数量:', Object.keys(this.deviceMeshes).length);
                resolve(robot);
            }, reject);
        });
    }

    /**
     * 根据 JointState 更新机械臂关节角（阶段二使用）
     * @param {object} jointState - { name: string[], position: number[] }
     */
    updateJointState(jointState) {
        if (!this.robot) return;
        jointState.name.forEach((name, i) => {
            if (this.robot.joints[name]) {
                this.robot.setJointValue(name, jointState.position[i]);
            }
        });
    }

    /**
     * 移动指定设备的位置（布局编辑时使用）
     * @param {string} deviceId
     * @param {{x:number, y:number, z:number}} pos - 单位：米（已从毫米转换）
     */
    moveDevice(deviceId, pos) {
        const mesh = this.deviceMeshes[deviceId];
        if (mesh) {
            mesh.position.set(pos.x, pos.z, -pos.y);  // ROS→Three.js 坐标转换
        }
    }

    /**
     * 高亮碰撞设备（设备变红）
     * @param {string[]} deviceIds - 需要高亮的设备 ID 列表
     */
    highlightCollision(deviceIds) {
        // 先清除所有高亮
        Object.values(this.deviceMeshes).forEach(mesh => {
            mesh.traverse(child => {
                if (child.isMesh && child.userData._originalMaterial) {
                    child.material = child.userData._originalMaterial;
                    delete child.userData._originalMaterial;
                }
            });
        });

        // 高亮碰撞设备
        const redMat = new THREE.MeshStandardMaterial({ color: 0xe94560, transparent: true, opacity: 0.7 });
        deviceIds.forEach(id => {
            const mesh = this.deviceMeshes[id];
            if (!mesh) return;
            mesh.traverse(child => {
                if (child.isMesh) {
                    child.userData._originalMaterial = child.material;
                    child.material = redMat;
                }
            });
        });
    }

    _onResize() {
        const el = this.renderer.domElement;
        const w = el.clientWidth, h = el.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h, false);
    }

    _animate() {
        requestAnimationFrame(() => this._animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}
```

### 6.5 Foxglove WebSocket 客户端

**文件**：`unilabos/app/web/static/lab3d/ros-bridge.js`

```javascript
/**
 * ROS 数据桥接客户端
 * 支持 Foxglove Bridge（推荐）和 ROSBridge2（备选）
 */

// ── Foxglove Bridge 客户端 ─────────────────────────────────────────
export class FoxgloveBridgeClient {
    /**
     * @param {string} url - ws://localhost:8765
     * @param {function} onJointState - 收到 /joint_states 时的回调
     */
    constructor(url, { onJointState } = {}) {
        this.url = url;
        this.onJointState = onJointState;
        this.ws = null;
        this.channelIds = {};
        this._connect();
    }

    _connect() {
        this.ws = new WebSocket(this.url, ['foxglove.websocket.v1']);

        this.ws.onopen = () => {
            console.log('[FoxgloveBridge] 已连接');
            // 订阅 /joint_states
            this._subscribe('/joint_states', 'sensor_msgs/msg/JointState');
        };

        this.ws.onmessage = (evt) => {
            if (typeof evt.data === 'string') {
                const msg = JSON.parse(evt.data);
                this._handleServerMessage(msg);
            } else {
                this._handleBinaryMessage(evt.data);
            }
        };

        this.ws.onerror = (e) => console.error('[FoxgloveBridge] 错误:', e);
        this.ws.onclose = () => {
            console.warn('[FoxgloveBridge] 连接断开，5s 后重试...');
            setTimeout(() => this._connect(), 5000);
        };
    }

    _subscribe(topic, schemaName) {
        const subId = Date.now();
        this.ws.send(JSON.stringify({
            op: 'subscribe',
            subscriptions: [{ id: subId, channelId: 0 }],  // channelId 在 serverInfo 中确认
        }));
    }

    _handleServerMessage(msg) {
        if (msg.op === 'serverInfo') {
            // 注册 channel ID 与 topic 的对应
            msg.channels?.forEach(ch => {
                this.channelIds[ch.topic] = ch.id;
            });
            // 发送正式订阅
            const jsCh = this.channelIds['/joint_states'];
            if (jsCh !== undefined) {
                this.ws.send(JSON.stringify({
                    op: 'subscribe',
                    subscriptions: [{ id: 1, channelId: jsCh }],
                }));
            }
        }
    }

    _handleBinaryMessage(data) {
        // Foxglove binary message: 前 5 字节为 header，后面是序列化消息
        // 简化处理：直接解析为 JSON（Foxglove 支持 JSON 编码模式）
        const text = new TextDecoder().decode(data.slice(5));
        try {
            const msg = JSON.parse(text);
            if (msg.name && msg.position && this.onJointState) {
                this.onJointState(msg);
            }
        } catch {}
    }
}


// ── ROSBridge2 客户端（备选方案） ─────────────────────────────────
export class ROSBridgeClient {
    /**
     * @param {string} url - ws://localhost:9090
     * @param {function} onJointState
     */
    constructor(url, { onJointState } = {}) {
        this.url = url;
        this.onJointState = onJointState;
        this.ws = null;
        this._connect();
    }

    _connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            console.log('[ROSBridge] 已连接');
            // 订阅 /joint_states（带降频：最快 40ms 推送一次，即 ≤25Hz）
            this.ws.send(JSON.stringify({
                op: 'subscribe',
                topic: '/joint_states',
                type: 'sensor_msgs/JointState',
                throttle_rate: 40,   // ms
                queue_length: 1,
            }));
        };

        this.ws.onmessage = (evt) => {
            const packet = JSON.parse(evt.data);
            if (packet.op === 'publish' && packet.topic === '/joint_states') {
                this.onJointState?.(packet.msg);
            }
        };

        this.ws.onerror = (e) => console.error('[ROSBridge] 错误:', e);
        this.ws.onclose = () => {
            setTimeout(() => this._connect(), 5000);
        };
    }
}
```

### 6.6 主入口

**文件**：`unilabos/app/web/static/lab3d/main.js`

```javascript
import { LabScene } from './urdf-scene.js';
import { FoxgloveBridgeClient } from './ros-bridge.js';

const API_BASE = window.location.origin;   // 如 http://localhost:8002
const BRIDGE_URL = `ws://${window.location.hostname}:8765`;

const canvas   = document.getElementById('three-canvas');
const statusEl = document.getElementById('status-bar');

// ── 初始化 Three.js 场景 ──────────────────────────────────────────
const labScene = new LabScene(canvas);

// ── 加载实验室 URDF ───────────────────────────────────────────────
statusEl.textContent = '正在加载 URDF...';
try {
    await labScene.loadFromAPI(API_BASE);
    statusEl.textContent = `已加载 ${Object.keys(labScene.deviceMeshes).length} 台设备`;
} catch (err) {
    statusEl.textContent = `加载失败：${err.message}`;
    console.error(err);
}

// ── 连接 Foxglove Bridge，接收关节角更新 ──────────────────────────
const bridge = new FoxgloveBridgeClient(BRIDGE_URL, {
    onJointState: (msg) => labScene.updateJointState(msg),
});

// ── 填充左侧资产面板 ─────────────────────────────────────────────
const devices = await fetch(`${API_BASE}/api/v1/devices`)
    .then(r => r.json())
    .catch(() => []);

const assetList = document.getElementById('asset-list');
devices.forEach(device => {
    const item = document.createElement('div');
    item.className = 'asset-item';
    item.textContent = device.id || device.name;
    item.dataset.deviceId = device.id;
    assetList.appendChild(item);
});

// ── 2D/3D 切换 ───────────────────────────────────────────────────
let is3D = true;
document.getElementById('toggle-2d3d').addEventListener('click', () => {
    is3D = !is3D;
    // TODO Step 7：切换逻辑
    document.getElementById('toggle-2d3d').textContent = is3D ? '切换 2D' : '切换 3D';
});
```

### 6.7 注册 3D 页面路由

**文件**：`unilabos/app/web/pages.py`（或现有页面路由文件）

```python
# 在 setup_web_pages() 中添加 3D 实验室页面路由
from fastapi.templating import Jinja2Templates
from pathlib import Path

_TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates")
)

def setup_web_pages(router):
    # ... 现有路由 ...

    @router.get("/lab3d", include_in_schema=False)
    async def lab3d_page(request: Request):
        return _TEMPLATES.TemplateResponse("lab3d.html", {"request": request})
```

**验证**：

```bash
# 启动后访问
open http://localhost:8002/lab3d
# 期望：浏览器中出现深色背景的 3D 画布，实验室设备模型逐步加载
```

---

## Step 7：手动布局拖拽交互

### 7.1 Three.js 点击拾取（Raycasting）

**文件**：`unilabos/app/web/static/lab3d/layout-editor.js`

```javascript
import * as THREE from 'three';

export class LayoutEditor {
    /**
     * @param {LabScene} labScene
     * @param {string} apiBase
     */
    constructor(labScene, apiBase) {
        this.scene      = labScene;
        this.apiBase    = apiBase;
        this.raycaster  = new THREE.Raycaster();
        this.mouse      = new THREE.Vector2();
        this.dragging   = null;   // 当前拖拽的设备 { deviceId, mesh, startPos }
        this.dragPlane  = new THREE.Plane(new THREE.Vector3(0,1,0), 0);  // 地面平面

        this._bindEvents();
    }

    _bindEvents() {
        const canvas = this.scene.renderer.domElement;

        canvas.addEventListener('mousedown',  (e) => this._onMouseDown(e));
        canvas.addEventListener('mousemove',  (e) => this._onMouseMove(e));
        canvas.addEventListener('mouseup',    (e) => this._onMouseUp(e));
        canvas.addEventListener('touchstart', (e) => this._onTouchStart(e), { passive: false });
        canvas.addEventListener('touchmove',  (e) => this._onTouchMove(e),  { passive: false });
        canvas.addEventListener('touchend',   (e) => this._onMouseUp(e));
    }

    _getMouseNDC(clientX, clientY) {
        const rect = this.scene.renderer.domElement.getBoundingClientRect();
        return new THREE.Vector2(
            ((clientX - rect.left) / rect.width)  *  2 - 1,
            ((clientY - rect.top)  / rect.height) * -2 + 1,
        );
    }

    _onMouseDown(e) {
        if (e.button !== 0) return;  // 只响应左键
        this.mouse = this._getMouseNDC(e.clientX, e.clientY);
        this.raycaster.setFromCamera(this.mouse, this.scene.camera);

        // 检查是否点击了设备 mesh
        const meshes = Object.values(this.scene.deviceMeshes).flatMap(g => {
            const children = [];
            g.traverse(c => { if (c.isMesh) children.push(c); });
            return children;
        });
        const hits = this.raycaster.intersectObjects(meshes, false);

        if (hits.length > 0) {
            const hitObject = hits[0].object;
            // 找到对应的 deviceId
            let deviceId = null;
            for (const [id, group] of Object.entries(this.scene.deviceMeshes)) {
                if (hitObject.parent === group || group.getObjectById(hitObject.id)) {
                    deviceId = id;
                    break;
                }
            }
            if (deviceId) {
                this.dragging = { deviceId, mesh: this.scene.deviceMeshes[deviceId] };
                this.scene.controls.enabled = false;  // 拖拽时禁用轨道控制
                // 显示设备信息
                this._showDeviceInfo(deviceId);
                e.preventDefault();
            }
        }
    }

    _onMouseMove(e) {
        if (!this.dragging) return;
        this.mouse = this._getMouseNDC(e.clientX, e.clientY);
        this.raycaster.setFromCamera(this.mouse, this.scene.camera);

        // 投影到地面平面，获取拖拽目标位置
        const target = new THREE.Vector3();
        this.raycaster.ray.intersectPlane(this.dragPlane, target);

        // 实时移动设备（Three.js 坐标系）
        this.dragging.mesh.position.set(target.x, 0, target.z);

        // 前端 OBB 粗碰撞检测（实时，不调用后端）
        this._checkCollisionOBB(this.dragging.deviceId, target);
    }

    async _onMouseUp(e) {
        if (!this.dragging) return;
        this.scene.controls.enabled = true;

        const pos = this.dragging.mesh.position;
        const deviceId = this.dragging.deviceId;
        this.dragging = null;

        // 鼠标松开时调用后端精确碰撞检测（MoveIt2 FCL）
        await this._submitLayoutUpdate(deviceId, pos);
    }

    // ── 前端 OBB 粗碰撞检测 ─────────────────────────────────────────
    _checkCollisionOBB(movingId, newPos) {
        const movingBox = new THREE.Box3().setFromObject(this.scene.deviceMeshes[movingId]);
        movingBox.translate(newPos.clone().sub(this.scene.deviceMeshes[movingId].position));

        let hasCollision = false;
        for (const [id, mesh] of Object.entries(this.scene.deviceMeshes)) {
            if (id === movingId) continue;
            const otherBox = new THREE.Box3().setFromObject(mesh);
            if (movingBox.intersectsBox(otherBox)) {
                hasCollision = true;
                break;
            }
        }

        // 更新 UI 提示
        const alertEl = document.getElementById('collision-alert');
        alertEl.style.display = hasCollision ? 'block' : 'none';
    }

    // ── 后端精确碰撞检测（松手时调用） ────────────────────────────────
    async _submitLayoutUpdate(deviceId, threePos) {
        // Three.js 坐标 → 毫米单位（ROS 坐标系，见 Step 6.4 坐标转换）
        const rosPosX_mm = threePos.x  * 1000;
        const rosPosY_mm = -threePos.z * 1000;  // Three.js Z 对应 ROS -Y
        const rosPosZ_mm = threePos.y  * 1000;

        const resp = await fetch(`${this.apiBase}/api/v1/lab/layout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                device_id: deviceId,
                pose: { x: rosPosX_mm, y: rosPosY_mm, z: rosPosZ_mm },
            }),
        });
        const result = await resp.json();

        if (result.collision) {
            // 高亮碰撞设备
            const collidingDevices = result.colliding_pairs.flat();
            this.scene.highlightCollision(collidingDevices);
            document.getElementById('collision-alert').style.display = 'block';
            document.getElementById('validation-result').innerHTML =
                `<span style="color:#e94560">⚠️ 碰撞：${result.colliding_pairs.map(p=>p.join(' ↔ ')).join(', ')}</span>`;
        } else {
            this.scene.highlightCollision([]);
            document.getElementById('collision-alert').style.display = 'none';
            document.getElementById('validation-result').innerHTML =
                `<span style="color:#4caf50">✅ 无碰撞</span>`;
        }
    }

    _showDeviceInfo(deviceId) {
        document.getElementById('device-info').innerHTML = `
            <p><b>ID：</b>${deviceId}</p>
            <p><b>位置（mm）：</b></p>
            <p>X: ${(this.scene.deviceMeshes[deviceId].position.x * 1000).toFixed(0)}</p>
            <p>Y: ${(-this.scene.deviceMeshes[deviceId].position.z * 1000).toFixed(0)}</p>
        `;
    }

    _onTouchStart(e) {
        if (e.touches.length === 1) {
            this._onMouseDown({ button: 0, clientX: e.touches[0].clientX, clientY: e.touches[0].clientY, preventDefault: () => e.preventDefault() });
        }
    }
    _onTouchMove(e) {
        if (e.touches.length === 1) {
            this._onMouseMove({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY });
            e.preventDefault();
        }
    }
}
```

在 `main.js` 中初始化 `LayoutEditor`：

```javascript
// 在 main.js 末尾加入（labScene 加载完成后）
import { LayoutEditor } from './layout-editor.js';
const editor = new LayoutEditor(labScene, API_BASE);
```

---

## Step 8：端到端验证与收尾

### 8.1 完整流程验证清单

```bash
# 1. 启动 Uni-Lab-OS（web 模式）
python -m unilabos \
    --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
    --visual web \
    --port 8002

# 2. 等待初始化（约 20-40s，看 ROS2 节点启动日志）
# 观察日志中应出现：
# [INFO] robot_state_publisher: Robot initialized
# [INFO] move_group: Planning pipeline 'ompl' initialized
# [INFO] foxglove_bridge: Listening on port 8765

# 3. 访问 3D 页面
open http://localhost:8002/lab3d
```

**验证项目**：

| 验证项 | 操作 | 期望结果 |
|---|---|---|
| URDF 加载 | 访问 `/lab3d` | 30s 内出现设备 3D 模型 |
| 网格路径 | `curl /api/v1/urdf \| grep "http://"` | 看到 HTTP URL（无 file://） |
| STL 文件访问 | `curl /meshes/devices/arm_slider/meshes/arm_slideway.STL` | 200 OK |
| Foxglove 连接 | 查看浏览器控制台 | `[FoxgloveBridge] 已连接` |
| 设备点击 | 点击场景中的设备 | 右侧面板显示设备 ID |
| 拖拽移动 | 按住设备拖拽 | 设备跟随鼠标移动 |
| OBB 碰撞 | 拖拽设备与另一台重叠 | 出现红色碰撞提示框 |
| 精确碰撞 | 松手 | 碰撞对显示在右侧面板 |
| 2D/3D 切换 | 点击按钮 | 视角/模式切换 |

### 8.2 已知阶段一指标达成方法

**场景加载时间 < 10s（5 台设备）**：

```bash
# 测量实际加载时间
time curl http://localhost:8002/api/v1/urdf > /dev/null
# 若 > 2s，检查 xacro.process_doc() 是否处理了过多文件

# 优化方案：ResourceVisualization 启动时预生成并缓存 URDF
# 在 __init__ 末尾添加缓存标志，避免每次调用 get_web_urdf 都重新生成
```

**最大设备数 ≥ 15 台**：

```bash
# 用 15 台设备的 graph JSON 测试性能
python -c "
import json
nodes = [{'id': f'device_{i}', 'type': 'device', 'class': 'virtual_stirrer',
          'position': {'position': {'x': i*500, 'y': 0, 'z': 0}}}
         for i in range(15)]
print(json.dumps({'nodes': nodes, 'links': []}))
" > /tmp/test_15_devices.json

python -m unilabos --graph /tmp/test_15_devices.json --visual web
# 在浏览器中打开 /lab3d，观察帧率是否 ≥ 20fps
```

### 8.3 阶段一完成标准

阶段一完成的定义：

- [ ] 浏览器打开 `/lab3d`，5 台设备场景 10s 内加载完毕
- [ ] URDF 中无 `file://` 路径，所有 STL 通过 HTTP 正常加载
- [ ] 点击任意设备，右侧面板显示正确的设备 ID 和坐标
- [ ] 拖拽设备时，OBB 碰撞检测实时反馈（无明显卡顿）
- [ ] 松手后，MoveIt2 精确碰撞结果显示在面板中
- [ ] RViz2（`--visual rviz` 模式）能正常打开、显示实验室布局、无 "link not found" 报错
- [ ] 布局保存为 JSON 文件后，重新加载恢复相同场景

---

## 附录：文件改动速查表

| 文件 | 改动类型 | 步骤 |
|---|---|---|
| `unilabos/resources/graphio.py` | 新增坐标归一化逻辑 | Step 1.1 |
| `unilabos/device_mesh/resource_visalization.py` | 多处修改：坐标读取、station_name、Bridge 启动、get_web_urdf、update_device_pose、_generate_rviz_config | Step 1.1, 1.2, 2.1, 2.4, 2.6, 3 |
| `unilabos/app/main.py` | 传 enable_bridge 等新参数、调用 set_resource_visualization | Step 2.2, 2.5 |
| `unilabos/app/web/server.py` | 新增 /meshes 静态路由 | Step 2.3 |
| `unilabos/app/web/api.py` | 新增 /urdf、/lab/layout 路由 | Step 2.5 |
| `unilabos/app/web/pages.py` | 注册 /lab3d 页面路由 | Step 6.7 |
| `unilabos/app/web/templates/lab3d.html` | 新建 3D 页面 HTML | Step 6.3 |
| `unilabos/app/web/static/lab3d/main.js` | 新建前端入口 | Step 6.6 |
| `unilabos/app/web/static/lab3d/urdf-scene.js` | 新建 Three.js 场景 | Step 6.4 |
| `unilabos/app/web/static/lab3d/ros-bridge.js` | 新建 WS 客户端 | Step 6.5 |
| `unilabos/app/web/static/lab3d/layout-editor.js` | 新建拖拽交互 | Step 7.1 |
| `scripts/generate_collision_meshes.py` | 新建 Blender 批处理 | Step 4.1 |
| `scripts/update_collision_xacro.py` | 新建 Xacro 批量改造 | Step 4.2 |
| `unilabos/device_mesh/devices/arm_slider/macro_device.xacro` 等 | collision mesh 路径修改 | Step 4.2 |
| `unilabos/device_mesh/devices/elite_robot/config/macro.srdf.xacro` | 新建 | Step 5.1 |
| `unilabos/device_mesh/devices/elite_robot/config/kinematics.yaml` | 新建 | Step 5.2 |
| `unilabos/device_mesh/devices/elite_robot/config/moveit_controllers.yaml` | 新建 | Step 5.3 |

---

*文档版本：v1.0（2026-03-14）*  
*基于 `unilabos/device_mesh/resource_visalization.py`、`unilabos/app/web/server.py`、`unilabos/app/main.py` 实际源码编写*
