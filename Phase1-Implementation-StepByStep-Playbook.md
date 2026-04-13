# Uni-Lab 阶段一实施手册（Step-by-Step Playbook）

> 这是一份可直接执行的阶段一实施手册。  
> 基于：`Phase1-Implementation-Guide-From-Current-Code.md`、`unilab-3d-3.22.md`，以及当前仓库真实代码现状。  
> 目标：在不引入阶段二动态链路的前提下，交付“可用的静态 3D 场景 + 拖拽布局 + 碰撞反馈 + 布局持久化”。

---

## 0. 先确认的事实（避免走偏）

### 当前仓库已经有

1. `ResourceVisualization` 已可拼装 URDF/SRDF，并可启动 `robot_state_publisher`、`move_group`、`rviz2`。
2. `ResourceMeshManager` + `moveit2.py` 已有 PlanningScene/CollisionObject 能力。
3. FastAPI 路由已采用 `api` router + `prefix=/api/v1`。
4. `lab3d-phase2` 目录有可复用的 Three.js/urdf-loader 代码。

### 当前仓库还没有

1. `GET /api/v1/urdf`
2. `/meshes` 静态路由
3. `/lab3d` 页面与其模板
4. `POST /api/v1/lab/layout` 等布局 API
5. `static/lab3d/` 正式前端目录和拖拽编辑器

---

## 1. 交付物定义（阶段一 Done Definition）

满足以下 7 条才算阶段一完成：

1. 打开 `/lab3d` 能加载 3D 场景（>= 5 台设备）。
2. `GET /api/v1/urdf` 返回可解析 URDF，mesh 路径全为 HTTP 路径。
3. 拖拽设备时有实时粗碰撞反馈（前端 OBB）。
4. 松手后后端返回精检结果（至少 collision true/false）。
5. 可保存布局 JSON，且可重新加载恢复。
6. RViz 场景和 Web 场景的设备位置一致。
7. 关键链路命令可复现（文末附命令集）。

---

## 2. 实施总顺序（强烈建议按此顺序）

1. 后端状态托管层（可让 API 访问 `ResourceVisualization`）
2. `/api/v1/urdf` + `/meshes` 路由打通
3. `/lab3d` 页面框架 + `static/lab3d` 最小前端
4. 前端拖拽 + OBB 粗碰撞
5. 后端布局更新 API（`POST /api/v1/lab/layout`）
6. 布局保存/加载 API
7. 联调与压测

不要倒序做。先拿到“能看到场景”，再做交互。

---

## 3. Phase A：后端基础能力打通

## A1. 新增可视化实例托管（全局状态）

### 目的

`api.py` 里需要拿到运行中的 `ResourceVisualization` 实例，但当前 `main.py` 是局部变量。

### 新增文件

`unilabos/app/web/utils/visualization_state.py`

### 建议实现

```python
# visualization_state.py
from typing import Optional

_resource_visualization = None

def set_resource_visualization(rv) -> None:
    global _resource_visualization
    _resource_visualization = rv

def get_resource_visualization():
    return _resource_visualization
```

### 修改文件

`unilabos/app/main.py`

在创建 `resource_visualization = ResourceVisualization(...)` 后，设置到全局托管：

```python
from unilabos.app.web.utils.visualization_state import set_resource_visualization
set_resource_visualization(resource_visualization)
```

### 验证

启动后在 Python REPL 临时验证：

```bash
python - <<'PY'
from unilabos.app.web.utils.visualization_state import get_resource_visualization
print("rv obj:", get_resource_visualization())
PY
```

---

## A2. 增强 `ResourceVisualization` 的 Web 输出能力

### 目标

补齐两个能力：

1. 给 API 提供 web 版本 URDF（mesh 路径转 `/meshes/...`）。
2. 提供按 `device_id` 更新位姿并重建 URDF 的入口。

### 修改文件

`unilabos/device_mesh/resource_visalization.py`

### 建议新增方法

1. `get_web_urdf(self) -> str`
2. `update_device_pose(self, device_id: str, pose: dict) -> dict`
3. （建议）`rebuild(self) -> None`，把 `__init__` 中拼装逻辑拆出来可复用

### 注意点（与现有代码兼容）

1. 当前 `__init__` 里直接消耗入参 `device` 与 `resource`，应保留一份 `self.device_dict` 的可变副本。
2. 坐标单位要统一：当前内部大量使用毫米转米（`/1000`）。
3. `get_web_urdf()` 只做字符串路径替换，不要改动 URDF 结构。

### `get_web_urdf()` 路径替换建议

将类似：

- `/.../unilabos/device_mesh/devices/...`
- `/.../unilabos/device_mesh/resources/...`

替换为：

- `/meshes/devices/...`
- `/meshes/resources/...`

### 验证

```bash
python - <<'PY'
from unilabos.app.web.utils.visualization_state import get_resource_visualization
rv = get_resource_visualization()
if rv:
    u = rv.get_web_urdf()
    print("len:", len(u))
    print("contains file://", "file://" in u)
    print("contains /meshes/", "/meshes/" in u)
PY
```

---

## A3. 增加 API：`GET /api/v1/urdf`

### 修改文件

`unilabos/app/web/api.py`

### 建议实现

沿用现有 `Resp` 风格：

```python
from unilabos.app.web.utils.visualization_state import get_resource_visualization

@api.get("/urdf", summary="Get web URDF", response_model=Resp)
def get_urdf():
    rv = get_resource_visualization()
    if rv is None:
        return Resp(code=RespCode.ErrorHostNotInit, message="ResourceVisualization not initialized")
    return Resp(data={"urdf": rv.get_web_urdf()})
```

### 验证

```bash
curl -s http://localhost:8002/api/v1/urdf | python -m json.tool | head -80
```

---

## A4. 增加静态路由：`/meshes`

### 修改文件

`unilabos/app/web/server.py`

### 建议实现

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

mesh_root = Path(__file__).resolve().parents[2] / "device_mesh"
app.mount("/meshes", StaticFiles(directory=str(mesh_root)), name="meshes")
```

> 备注：请确认路径层级；`server.py` 位于 `unilabos/app/web/`，`device_mesh` 位于 `unilabos/device_mesh/`。

### 验证

```bash
curl -I http://localhost:8002/meshes/devices/arm_slider/meshes/arm_slideway.STL
# 预期 HTTP 200
```

---

## 4. Phase B：`/lab3d` 页面与最小前端渲染

## B1. 新建前端目录并复制最小骨架

### 新建目录

`unilabos/app/web/static/lab3d/`

### 初始文件建议

1. `index.html`
2. `main.js`
3. `urdf-scene.js`（从 `lab3d-phase2` 复制并瘦身）
4. `layout-editor.js`（后续填）
5. `layout-api.js`（后续填）

### `main.js` 最小逻辑

1. 调用 `/api/v1/urdf`
2. 提取 `data.urdf`
3. `urdf-scene.loadURDFFromString()` 或 `loadURDF(url)`（二选一）
4. 启动渲染循环

> 建议把 `urdf-scene.js` 改为支持“传入 URDF 文本”，减少二次请求和跨域复杂度。

---

## B2. 新增 `/lab3d` 页面路由

### 修改文件

1. `unilabos/app/web/pages.py`
2. 新模板 `unilabos/app/web/templates/lab3d.html`

### 路由建议

```python
@router.get("/lab3d", response_class=HTMLResponse, summary="3D Lab")
async def lab3d_page() -> str:
    template = env.get_template("lab3d.html")
    return template.render()
```

### 模板建议

1. 左侧 canvas 区
2. 右侧设备列表 + 碰撞信息区
3. 引入 `/static/lab3d/main.js`（或直接内联 module script）

> 若你希望走 FastAPI StaticFiles 标准挂载，也可新增 `/static` mount；当前仓库未显式挂载静态目录，建议一并补齐。

### 验证

```bash
open http://localhost:8002/lab3d
```

---

## 5. Phase C：拖拽交互与碰撞（前端粗检 + 后端精检）

## C1. 前端 `layout-editor.js`（实时交互）

### 目标功能

1. 鼠标拾取设备（Raycast）
2. 在地面平面拖拽
3. 拖拽中做 OBB 粗碰撞
4. 松手提交后端精检

### 关键实现点

1. `urdf-scene` 需要维护 `deviceMeshes: Map[deviceId, THREE.Object3D]`
2. 每次拖拽仅更新目标 mesh 的 transform，不立即写后端
3. OBB 检测优先用 `THREE.Box3`（MVP），后续可升级 OBB 算法

### 粗检输出

`collisionHint = { hasCollision: bool, candidates: [deviceId...] }`

用于 UI 高亮，不作为最终判定。

---

## C2. 后端精检 API：`POST /api/v1/lab/layout`

### 修改文件

1. `unilabos/app/web/api.py`
2. （建议）`unilabos/app/web/utils/layout_service.py`

### 请求体建议

```json
{
  "updates": [
    {
      "device_id": "arm_slider_1",
      "pose": { "x_mm": 1200, "y_mm": 800, "z_mm": 0, "rz_rad": 1.57 }
    }
  ],
  "validate_collision": true
}
```

### 响应体建议

```json
{
  "ok": true,
  "collision": false,
  "colliding_pairs": [],
  "applied": ["arm_slider_1"]
}
```

### 先做 MVP，再做“碰撞对列表”

#### MVP（建议先落）

1. 更新 `ResourceVisualization` 内存布局
2. 重建 URDF
3. 返回 `ok + applied`（先不返回 pairs）

#### 再增强 collision 结果

可选两条路：

1. **工程可控路线（推荐）**：后端维护简化碰撞体 AABB，返回候选冲突对（和前端一致性好）
2. **MoveIt 深度路线**：新增 `GetStateValidity` 链路拿 contacts（复杂度高，放后）

> 你当前最重要是“阶段一可交付”，建议先 1 再 2。

---

## C3. 布局持久化 API

### 建议新增

1. `POST /api/v1/lab/layout/save`
2. `POST /api/v1/lab/layout/load`
3. `GET /api/v1/lab/layout`

### 存储位置建议

`unilabos/test/layouts/*.json` 或用户工作目录下 `layouts/*.json`

### 落盘结构建议

直接复用 graph 节点结构（减少转换）：

```json
{
  "nodes": [...],
  "links": [...]
}
```

---

## 6. Phase D：资产治理（阶段一必须做到“可控”）

## D1. 资产盘点脚本

### 新增脚本

`scripts/check_device_assets.py`

### 输出

1. `reports/device_asset_missing.csv`
2. `reports/device_asset_missing.md`

字段至少包括：`class`, `model.mesh`, `xacro_exists`, `meshes_exists`, `srdf_exists`, `priority`。

## D2. 零点规范检查脚本

### 新增脚本

`scripts/validate_model_origin.py`

### 检查项

1. Z=0 落地
2. XY 中心投影
3. +X 朝向

先做检查报告，不做自动修复。

---

## 7. 每日执行清单（建议 8 天）

## Day 1：后端最小链路

1. `visualization_state.py`
2. `main.py` 注册实例
3. `api.py` 增加 `/api/v1/urdf`
4. `server.py` 增加 `/meshes`

验收命令：

```bash
curl http://localhost:8002/api/v1/urdf | wc -c
curl -I http://localhost:8002/meshes/devices/arm_slider/meshes/arm_slideway.STL
```

## Day 2：`/lab3d` 页面可显示模型

1. `pages.py` 加 `/lab3d`
2. `templates/lab3d.html`
3. `static/lab3d/` 最小渲染

验收：打开 `/lab3d` 能看到模型。

## Day 3：拖拽 MVP

1. `layout-editor.js` 基础拖拽
2. 设备选中高亮
3. 地面吸附

验收：可拖动，摄像机控制可切换。

## Day 4：OBB 粗碰撞

1. 前端 `Box3` 粗检
2. UI 红色预警

验收：重叠时高亮。

## Day 5：布局 API

1. `POST /api/v1/lab/layout`
2. 更新内存布局 + 重建 URDF

验收：拖拽后刷新页面，设备位置保留。

## Day 6：布局持久化

1. save/load/get API
2. 前端保存/加载按钮

验收：重启服务后可恢复布局。

## Day 7：资产脚本与坐标校准

1. `check_device_assets.py`
2. `validate_model_origin.py`
3. 5 台设备一致性校准

## Day 8：回归与演示准备

1. 压测（加载时间、交互流畅度）
2. 录制演示脚本
3. 文档收口

---

## 8. 三终端运行模板

## 终端 A：后端 + RViz

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS
python -m unilabos \
  --graph unilabos/test/experiments/mock_protocol/stirteststation.json \
  --visual rviz \
  --port 8002
```

## 终端 B：前端开发（阶段一目录）

```bash
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d
npm install
npx vite --port 3000
```

## 终端 C：接口联调

```bash
curl -s http://localhost:8002/api/v1/urdf | python -m json.tool | head -40

curl -X POST http://localhost:8002/api/v1/lab/layout \
  -H "Content-Type: application/json" \
  -d '{"updates":[{"device_id":"arm_slider_1","pose":{"x_mm":1200,"y_mm":500,"z_mm":0,"rz_rad":0.0}}],"validate_collision":true}'
```

---

## 9. 风险与规避（务必看）

1. `resource_visalization.py` 文件名拼写错误（visalization）是现状，不要“顺手改名”。
2. 若 `rviz2` 不弹窗，优先查 GUI 环境（`$DISPLAY`、是否 SSH 远程）。
3. URDF mesh 路径替换不要破坏原始 `package://` 或绝对路径解析逻辑。
4. 布局 API 的坐标单位必须统一（建议 API 用 mm，内部用 m）。
5. 不要在阶段一引入阶段二话题订阅逻辑，避免范围失控。

---

## 10. 代码评审清单（提交前自查）

1. 所有新增 API 是否加到 `api` router（`/api/v1` 前缀）？
2. `/meshes` 路由是否可访问设备与资源目录？
3. `/lab3d` 页面在不连 ROS 话题时是否也可加载（静态阶段）？
4. 拖拽过程中是否不卡主线程（避免频繁重建整个场景）？
5. 保存的布局 JSON 是否可回放且无坐标漂移？
6. 异常路径（无设备、无模型、路径不存在）是否有可读报错？

---

## 11. 最终建议

阶段一要成功，关键不是“算法复杂度”，而是“把现有后端能力稳定暴露到 Web 层”：

1. 先把 URDF/mesh 输出变成稳定 API；
2. 再把前端交互做薄（拖拽 + 粗碰撞）；
3. 最后用后端布局 API 做最终判定和持久化。

按本手册执行，你可以在一个迭代内拿到可演示、可验收的阶段一版本。

