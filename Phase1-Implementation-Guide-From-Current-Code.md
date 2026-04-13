# Uni-Lab 阶段一实现方法（基于现有代码能力的落地版）

> 目标：只聚焦阶段一（静态 3D 实验室搭建），并且以当前 `uni-lab-os` 仓库现状为基线给出可执行实现路径。  
> 依据：`unilab-3d-3.22.md` + 现有代码（`ResourceVisualization`/`ResourceMeshManager`/`app.web`）。

---

## 1. 阶段一范围（本文件约束）

本文件只覆盖以下能力：

1. 静态 3D 场景加载（浏览器 + RViz）
2. 设备资产接入与拼装（URDF/Xacro + registry）
3. 手动布局拖拽（前端）
4. 布局碰撞检测（前端粗检 + 后端精检）
5. 布局保存/加载

不包含阶段二动态联动（JointState 动画、轨迹预览）和阶段三 AI 排布。

---

## 2. 现有能力盘点（可直接复用 vs 必须新增）

### 2.1 可直接复用（已有）

1. `unilabos/device_mesh/resource_visalization.py`
   - 已能基于 registry 拼装多设备 URDF/SRDF
   - 已能启动 `robot_state_publisher`、`move_group`、`ros2_control_node`、`joint_state_broadcaster`
   - 支持 `enable_rviz=True` 时直接拉起 `rviz2`

2. `unilabos/ros/nodes/presets/resource_mesh_manager.py`
   - 已有 PlanningScene 接入（`/get_planning_scene`、`/apply_planning_scene`）
   - 已有 collision mesh 注册、attach/detach 机制
   - 已有 `tf_update` Action（阶段二也复用）

3. `unilabos/devices/ros_dev/moveit2.py`
   - 已封装 collision object 生命周期 API（add/move/remove/attach/detach）
   - 已封装 allowed collision matrix 处理

4. Web 基础框架已在
   - FastAPI + 页面路由可用（`/status` 等）
   - `unilabos/app/web/static/lab3d-phase2/` 已有前端模块样例（Three.js/URDF loader）

### 2.2 当前缺口（阶段一必须补）

1. 缺 `/api/v1/urdf` 接口（浏览器无法拿到 URDF 文本）
2. 缺 `/meshes/...` 静态路由（URDF 中 mesh URL 无法 HTTP 访问）
3. 缺 `lab3d` 页面与入口（当前只有 `lab3d-phase2` 独立测试目录）
4. 缺布局 API（如 `POST /api/v1/lab/layout`）
5. 缺拖拽编辑器（`layout-editor.js` 不存在）
6. 缺布局持久化 API（save/load JSON）

---

## 3. 推荐实现顺序（最小可运行路径）

按以下顺序开发，能最快拿到“可演示”阶段一成果：

1. 先打通 **URDF + mesh HTTP 输出**
2. 再打通 **浏览器静态渲染页面**
3. 再做 **拖拽 + 前端 OBB 粗碰撞**
4. 最后接 **后端 PlanningScene 精碰撞 + 布局保存**

原因：前两步完成即可先验证资产和坐标体系，降低后续调试成本。

---

## 4. 文件级改造清单

## 4.1 后端

1. `unilabos/device_mesh/resource_visalization.py`
   - 新增 `get_web_urdf()`：将 `self.urdf_str` 中 mesh 路径转换为 HTTP 可访问路径（如 `/meshes/devices/...`）
   - 新增 `update_device_pose(device_id, pose)`：更新设备位姿后重建 URDF（用于布局更新）

2. `unilabos/app/main.py`
   - 在初始化后调用一个 setter（全局注册 `ResourceVisualization` 实例），供 API 层访问 URDF 与布局更新能力

3. `unilabos/app/web/api.py`
   - 新增 `GET /api/v1/urdf`
   - 新增 `POST /api/v1/lab/layout`
   - 新增 `GET /api/v1/lab/layout`（读取当前布局）
   - 可选：新增 `POST /api/v1/lab/layout/save`、`POST /api/v1/lab/layout/load`

4. `unilabos/app/web/server.py`
   - 挂载静态路由：`/meshes -> unilabos/device_mesh`

5. `unilabos/app/web/utils/`（建议新增）
   - `visualization_state.py`：保存/获取 `ResourceVisualization` 全局实例
   - `layout_service.py`：封装布局更新、坐标转换、碰撞查询逻辑

## 4.2 前端

1. 新建目录：`unilabos/app/web/static/lab3d/`
2. 新建 `main.js`（入口）
3. 复用并调整 `lab3d-phase2/urdf-scene.js`
4. 新建 `layout-editor.js`（拖拽、旋转、吸附、OBB）
5. 新建 `layout-api.js`（调用 `/api/v1/lab/layout`）
6. 新建 `index.html` 或模板页，挂到 `/lab3d`

---

## 5. 分模块实现方法（对应 `unilab-3d-3.22.md` 第 4 节）

## 5.1 4.1 实验室场景配置

### 数据结构建议（JSON）

```json
{
  "scene": {
    "floor": { "width_mm": 8000, "depth_mm": 5000 },
    "blocked_zones": [],
    "anchors": []
  },
  "devices": [
    {
      "id": "arm_slider_1",
      "class": "robotic_arm.SCARA_with_slider.moveit.virtual",
      "pose": { "position": { "x": 1000, "y": 500, "z": 0 }, "rotation": { "x": 0, "y": 0, "z": 0 } }
    }
  ]
}
```

### 实施建议

1. 先做最小版：只支持矩形地面 + 设备列表
2. blocked/anchor 先作为字段透传，不阻塞主流程
3. 布局文件直接复用 `graph` 的节点结构，避免双格式维护

## 5.2 4.2 设备资产准备

### 已有基础

- registry 已有 model 声明能力
- `ResourceVisualization` 已按 `model.type` 区分 `device/resource`
- moveit 设备已走 `macro.ros2_control.xacro` + `macro.srdf.xacro`

### 本阶段要补

1. 新增资产盘点脚本（建议：`scripts/check_device_assets.py`）
   - 扫 registry 的 `device_type_registry`、`resource_type_registry`
   - 检查 model.mesh 路径是否存在 `macro_device.xacro` 与 meshes
   - 输出缺失清单（CSV/Markdown）

2. 统一零点规范（文档 + 脚本检查）
   - 新增 `scripts/validate_model_origin.py`
   - 先检测，不自动修复；修复通过 xacro `<origin>` 完成

3. Visual/Collision 分离（按优先级）
   - 优先处理高面数设备
   - collision 先用简化 STL，后续再做凸包优化流水线

## 5.3 4.3 设备选择与上架

### 可行做法

1. 前端先调用现有 `/api/v1/devices`、`/api/v1/resources` 获取可选项
2. 选中设备后写入布局 JSON
3. 提交后端，调用 `ResourceVisualization` 重建 URDF
4. 前端重新请求 `/api/v1/urdf` 并刷新场景

备注：deploy_master 联动可以后接，不影响阶段一完成。

## 5.4 4.4 手动布局交互

### 前端（实时）

1. Raycast 选中设备
2. 平面投影拖拽（地面 y=0 或桌面吸附平面）
3. OBB 粗碰撞实时反馈（红色预览）
4. 鼠标释放后调用后端精碰撞

### 后端（精检）

1. `POST /api/v1/lab/layout`
2. 更新对应设备位姿
3. 更新 PlanningScene（MOVE collision object）
4. 返回碰撞对列表

返回示例：

```json
{
  "ok": true,
  "collision": true,
  "colliding_pairs": [["arm_slider_1", "hplc_station_1"]]
}
```

### 关键点

- 前端 60fps 粗检只做交互反馈
- 后端精检作为最终判定，避免前端几何误差

## 5.5 4.5 3D 预览渲染

### 技术路线（阶段一）

1. 前端直接 `fetch('/api/v1/urdf')` + `urdf-loader` 渲染
2. 不依赖 ROS Topic 动态订阅（这是阶段二）
3. 支持 `/lab3d` 页面与 `/status` 并存

### 最小页面能力

1. 加载 URDF
2. 显示设备树/选中设备信息
3. 拖拽与碰撞提示
4. 保存布局

---

## 6. 关键 API 设计（建议）

1. `GET /api/v1/urdf`
   - 输出：URDF xml 文本（mesh URL 已 http 化）

2. `GET /api/v1/lab/layout`
   - 输出：当前布局 JSON

3. `POST /api/v1/lab/layout`
   - 输入：设备 pose 更新（单个或批量）
   - 输出：碰撞结果 + 修正后的 pose

4. `POST /api/v1/lab/layout/save`
   - 输入：name/path
   - 输出：保存成功与文件路径

5. `POST /api/v1/lab/layout/load`
   - 输入：path
   - 输出：加载后的完整布局

---

## 7. 三终端调试方式（阶段一）

1. 终端 A（后端 + RViz）

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS
python -m unilabos --graph unilabos/test/experiments/mock_protocol/stirteststation.json --visual rviz --port 8002
```

2. 终端 B（前端开发）

```bash
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d
npx vite
```

3. 终端 C（调试）

```bash
# URDF
curl http://localhost:8002/api/v1/urdf | wc -c

# 布局更新
curl -X POST http://localhost:8002/api/v1/lab/layout \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"arm_slider_1","pose":{"x":1200,"y":800,"z":0,"rz":1.57}}'
```

---

## 8. 验收标准（阶段一）

1. 浏览器打开 `/lab3d` 后 10 秒内加载出 5 台设备
2. `/api/v1/urdf` 可稳定返回，且不含 `file://` mesh 路径
3. 拖拽设备时前端能实时显示碰撞提示（无明显卡顿）
4. 松手后后端返回碰撞对，前端可高亮冲突设备
5. 布局可保存、可加载，重启后可复现
6. RViz 与网页场景布局一致（坐标系统一）

---

## 9. 建议开发节奏（7 天）

1. Day 1：URDF API + mesh 静态路由
2. Day 2：`/lab3d` 页面基础渲染
3. Day 3：拖拽与前端 OBB
4. Day 4：后端布局更新 API + 精碰撞返回
5. Day 5：布局保存/加载 + 异常处理
6. Day 6：坐标系校准 + 多设备压力测试
7. Day 7：验收脚本与演示录制

---

## 10. 一句话结论

阶段一不需要从零重写 3D 引擎或碰撞系统：  
应以 `ResourceVisualization` + `ResourceMeshManager` + `moveit2.py` 为后端核心，补齐 Web 接口与前端交互层（`/api/v1/urdf`、`/api/v1/lab/layout`、`lab3d` 页面、拖拽编辑器）即可完成可演示交付。
