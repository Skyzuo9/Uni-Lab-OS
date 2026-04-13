# Layout Optimizer 集成文档（Agent 工作手册）

**写作对象**: AI Agent  
**最后更新**: 2026-04-10  
**当前状态**: Phase 1 + Phase 2 代码已在 macOS 完成，Uni-Lab-OS-main 整体传到 Ubuntu 后直接验证即可

---

## 0. 快速定位

| 你需要做什么 | 跳到哪里 |
|---|---|
| 了解项目是什么 | § 1 |
| 找到所有相关文件 | § 2 |
| 在 Ubuntu 上完成环境配置 | § 3 |
| 验证 Phase 1（Mock 模式） | § 4 |
| 验证 Phase 2（MoveIt2 真实检测） | § 5 |
| 查看 API 端点规范 | § 6 |
| 理解核心算法 | § 7 |
| 了解还剩什么没做（Phase 3-5） | § 8 |
| 排查常见问题 | § 9 |

---

## 1. 项目是什么

**目标**: 将 `layout_optimizer`（实验室设备自动布局优化模块）集成进 `Uni-Lab-OS` 作为原生服务，用 MoveIt2 的真实碰撞检测和 IK 可达性验证替代 Mock 实现。

**layout_optimizer 做什么**: 给定实验室设备列表和约束条件（"机械臂能到达 HPLC"、"离心机和冰箱要靠近"），用差分进化算法（DE）计算每个设备的最优 (x, y, θ) 摆放位置。

**已完成的集成架构**:
```
Uni-Lab-OS 进程 (FastAPI :8002 + ROS2 + Layout Optimizer)
┌────────────────────────────────────────────────────────────┐
│  /api/v1/layout/interpret                                  │
│  /api/v1/layout/optimize       ← 已注册到 api.py           │
│  /api/v1/layout/schema                                     │
│         │ (同进程调用)                                      │
│  unilabos/services/layout_optimizer/  ← 已创建              │
│    ├── LayoutService 单例 (service.py)                     │
│    ├── 差分进化优化器 (optimizer.py)                         │
│    ├── OBB / FCL 碰撞检测 (mock_checkers / ros_checkers)    │
│    └── MoveIt2 桥接层 (checker_bridge.py) ← Phase 2 已实现  │
│         │ (同进程读取)                                      │
│  registered_devices → MoveitInterface.moveit2 → MoveIt2    │
│  优化完成后 → sync_to_planning_scene() → RViz              │
└────────────────────────────────────────────────────────────┘
```

---

## 2. 文件清单

### 2.1 Uni-Lab-OS 中新增/修改的文件（全部已完成）

仓库路径（Ubuntu 上）: `/home/ubuntu/workspace/Uni-Lab-OS/`

```
Uni-Lab-OS/
└── unilabos/
    ├── services/                                  # 【新建目录】
    │   ├── __init__.py                            # 【新建】服务层包
    │   └── layout_optimizer/                      # 【新建目录】
    │       ├── __init__.py                        # 【新建】导出 LayoutService
    │       ├── service.py                         # 【新建】LayoutService 单例，核心入口
    │       ├── checker_bridge.py                  # 【新建】MoveIt2 桥接层，Phase 2 已实现
    │       ├── optimizer.py                       # 【新建】DE 优化器（去除 pencil 依赖）
    │       ├── ros_checkers.py                    # 【新建】MoveIt2 FCL/OBB 碰撞 + IK 检测
    │       ├── mock_checkers.py                   # 【复制】Mock 模式检测器
    │       ├── models.py                          # 【复制】数据模型
    │       ├── obb.py                             # 【复制】OBB 几何计算
    │       ├── constraints.py                     # 【复制】约束评估引擎
    │       ├── seeders.py                         # 【复制】力导向种子布局
    │       ├── intent_interpreter.py              # 【复制】语义意图 → 约束翻译
    │       ├── interfaces.py                      # 【复制】Protocol 接口定义
    │       ├── device_catalog.py                  # 【复制】设备目录
    │       ├── lab_parser.py                      # 【复制】实验室配置解析
    │       ├── footprints.json                    # 【复制】499 设备离线尺寸数据库
    │       └── voxel_maps/                        # 【新建空目录】Phase 4 体素图存放位置
    └── app/web/
        ├── api.py                                 # 【已修改】setup_api_routes 末尾新增 layout_router
        └── routers/
            ├── __init__.py                        # 【新建】
            └── layout.py                          # 【新建】6 个 API 端点定义
```

**api.py 修改内容**（文件末尾 `setup_api_routes()` 函数新增 3 行）:
```python
# Layout Optimizer 路由 (/api/v1/layout/*)
from unilabos.app.web.routers.layout import layout_router
app.include_router(layout_router, prefix="/api/v1")
```

### 2.2 Uni-Lab-OS 中关键的已有文件（Phase 2 依赖）

| 文件 | 用途 |
|---|---|
| `unilabos/ros/nodes/base_device_node.py` | 定义 `registered_devices` 字典和 `DeviceInfoType` |
| `unilabos/devices/ros_dev/moveit_interface.py` | `MoveitInterface` 类，含 `moveit2: dict` 属性 |
| `unilabos/devices/ros_dev/moveit2.py` | `MoveIt2` 类，含 `compute_ik()`、`add_collision_box()` |
| `unilabos/ros/nodes/presets/resource_mesh_manager.py` | `ResourceMeshManager`，含 `add_resource_collision_meshes()` |

---

## 3. Ubuntu 环境配置

> 假设 Ubuntu 已有 Uni-Lab-OS 基础环境：conda `unilab` 环境，unilabos editable install。

### Step 3.1 激活环境

```bash
conda activate unilab
```

### Step 3.2 安装新增 Python 依赖

```bash
# scipy — DE 优化器核心依赖（Uni-Lab-OS 原本不包含）
pip install "scipy>=1.10" "numpy>=1.24"

# 验证
python -c "import scipy; import numpy; print('OK', scipy.__version__, numpy.__version__)"
```

### Step 3.3 部署 Uni-Lab-OS-main

将 macOS 的 `Uni-Lab-OS-main/` 整体传到 Ubuntu，覆盖原有仓库，然后重新 editable install：

```bash
pip install -e /home/ubuntu/workspace/Uni-Lab-OS
```

### Step 3.4 验证部署

```bash
cd /home/ubuntu/workspace/Uni-Lab-OS
python -c "
from unilabos.services.layout_optimizer import LayoutService
svc = LayoutService.get_instance()
print('OK:', svc.get_checker_status())
"
```

期望输出：
```
INFO: LayoutService: Mock checkers initialized
OK: {'mode': 'mock', 'collision_checker': 'MockCollisionChecker', 'reachability_checker': 'MockReachabilityChecker'}
```

### Step 3.5 安装 python-fcl（Phase 2 精确碰撞，可选）

```bash
pip install python-fcl
python -c "import fcl; print('fcl OK')" 2>/dev/null || echo "fcl not available, will use OBB fallback"
```

---

## 4. Phase 1 验收（Mock 模式）

### 启动

```bash
conda activate unilab
cd /home/ubuntu/workspace/Uni-Lab-OS
unilab -g <任意实验室配置.json> --port 8002
```

> `--backend mock` 可跳过 ROS2 做纯 Python 测试（如果该参数存在）。

### 验收命令

```bash
# 1. 健康检查
curl http://localhost:8002/api/v1/layout/health
# 期望: {"status": "ok", "module": "layout_optimizer"}

# 2. 检测器状态
curl http://localhost:8002/api/v1/layout/checker_status
# 期望: {"mode": "mock", "collision_checker": "MockCollisionChecker", ...}

# 3. 布局优化（核心验收）
curl -X POST http://localhost:8002/api/v1/layout/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "devices": [
      {"id": "arm_slider", "name": "Arm", "size": [0.6, 0.4], "device_type": "articulation"},
      {"id": "hplc_station", "name": "HPLC", "size": [0.6, 0.5]},
      {"id": "slide_w140", "name": "Slide", "size": [0.6, 0.4]}
    ],
    "lab": {"width": 4.0, "depth": 4.0},
    "constraints": [
      {"type": "hard", "rule_name": "min_spacing", "params": {"min_gap": 0.05}},
      {"type": "soft", "rule_name": "minimize_distance",
       "params": {"device_a": "hplc_station", "device_b": "slide_w140"}, "weight": 8.0}
    ],
    "seeder": "compact_outward", "run_de": true, "maxiter": 50
  }' | python3 -m json.tool
# 期望: placements 数组，success=true，cost 接近 0
```

---

## 5. Phase 2 验收（MoveIt2 真实检测）

**代码已完成，无需再写**。以下是在 Ubuntu 上验证的步骤。

### 5.1 前置条件

- Phase 1 验收通过
- ROS2 + MoveIt2 在 Ubuntu 上正常运行（`move_group` 节点已启动）
- 至少一个使用 `MoveitInterface` 驱动的机器人设备已加载到 `registered_devices`

### 5.2 Phase 2 的实现逻辑（供 debug 参考）

**`checker_bridge.py` 工作原理**：

```
registered_devices (base_device_node.py)
  └── device_info["driver_instance"]  ← DeviceInfoType TypedDict
        └── isinstance(driver, MoveitInterface)?  ← moveit_interface.py
              └── driver.moveit2  ← dict[move_group_name, MoveIt2]
                    └── MoveIt2 实例  ← moveit2.py
                          ├── compute_ik(position, quat_xyzw) → JointState | None
                          └── add_collision_box(id, size, position, quat_xyzw)
```

**`service.py` 优化流程**（moveit 模式）：
```
run_optimize()
  ├── 1. resolve_seeder_params → seed_layout (力导向初始布局)
  ├── 2. optimize() 调用 DE，cost_function ~10万次
  │     └── MoveItCollisionChecker.check() → sync_to_scene=False (不发 ROS 消息)
  │         └── python-fcl 或 OBB SAT 检测
  ├── 3. snap_theta (吸附到直角)
  ├── 4. evaluate_default_hard_constraints (最终评分)
  └── 5. collision_checker.sync_to_planning_scene()
        └── add_collision_box() × N → MoveIt2 Planning Scene → RViz
```

### 5.3 启动 moveit 模式

```bash
LAYOUT_CHECKER_MODE=moveit unilab -g <实验室配置.json> --backend ros --port 8002
```

启动时 log 中应出现：
```
INFO: CheckerBridge: found N MoveIt2 instance(s): ['device_id_group_name', ...]
INFO: MoveIt2 checkers created (voxel_dir=.../voxel_maps, fcl=True/False)
INFO: LayoutService: MoveIt2 checkers initialized
```

### 5.4 Phase 2 验收命令

```bash
# 1. 确认 moveit 模式已激活
curl http://localhost:8002/api/v1/layout/checker_status
# 期望: {"mode": "moveit", "collision_checker": "MoveItCollisionChecker", ...}

# 2. 优化（同上 Phase 1 命令），观察 RViz 中碰撞盒是否出现在正确位置
curl -X POST http://localhost:8002/api/v1/layout/optimize \
  -H "Content-Type: application/json" \
  -d '{...}' | python3 -m json.tool
# 期望: success=true，RViz Planning Scene 中设备碰撞盒位置与 placements 一致
```

### 5.5 Phase 2 可能遇到的问题

**问题：`CheckerBridge: found 0 MoveIt2 instances`**

`registered_devices` 中没有找到 `MoveitInterface` 类型的 driver。排查：
```python
# 在 Python shell 中（Uni-Lab-OS 启动后）
from unilabos.ros.nodes.base_device_node import registered_devices
for k, v in registered_devices.items():
    print(k, type(v.get("driver_instance")))
```
如果 driver_instance 不是 `MoveitInterface`，检查实验室配置 JSON 中机器人设备是否配置了正确的驱动。

**问题：自动回退 mock（WARNING 日志）**

`service.py` 捕获了 `checker_bridge.create_checkers()` 的所有异常并回退 mock。查看完整 WARNING 消息定位根因：
```bash
# 启动时加 -v 或查看日志
LAYOUT_CHECKER_MODE=moveit unilab ... 2>&1 | grep -i "layout\|moveit\|checker"
```

**问题：优化完成但 RViz 中看不到碰撞盒**

`sync_to_planning_scene()` 调用了 `add_collision_box()`，但 Planning Scene 没更新。可能原因：
- `move_group` 节点未运行（`add_collision_box` 是发布到 `/collision_object` topic）
- frame_id 不匹配（默认用 `MoveIt2` 实例的 `base_link_name`）

---

## 6. API 端点规范

所有端点挂载在 `/api/v1/layout/` 前缀下。

### GET /api/v1/layout/health
```json
{"status": "ok", "module": "layout_optimizer"}
```

### GET /api/v1/layout/checker_status
```json
{"mode": "mock", "collision_checker": "MockCollisionChecker", "reachability_checker": "MockReachabilityChecker"}
```

### GET /api/v1/layout/schema
返回 10 种意图类型规范（reachable_by, close_together, far_apart, max_distance, min_distance, min_spacing, workflow_hint, face_outward, face_inward, align_cardinal）

### GET /api/v1/layout/devices?source=all
返回设备目录。`source`: `all`（默认）/ `registry` / `assets`

### POST /api/v1/layout/interpret

请求：
```json
{
  "intents": [
    {"intent": "close_together", "params": {"devices": ["hplc", "slide"], "priority": "high"}},
    {"intent": "reachable_by", "params": {"arm": "arm_slider", "targets": ["hplc", "slide"]}}
  ]
}
```
响应：
```json
{
  "constraints": [...],
  "translations": [...],
  "workflow_edges": [],
  "errors": []
}
```

### POST /api/v1/layout/optimize

请求：
```json
{
  "devices": [
    {"id": "arm_slider", "name": "Arm Slider", "size": [0.6, 0.4], "device_type": "articulation", "uuid": ""},
    {"id": "hplc_station", "name": "HPLC", "size": [0.6, 0.5]}
  ],
  "lab": {"width": 4.0, "depth": 4.0, "obstacles": []},
  "constraints": [
    {"type": "hard", "rule_name": "min_spacing", "params": {"min_gap": 0.05}, "weight": 1.0},
    {"type": "soft", "rule_name": "minimize_distance",
     "params": {"device_a": "hplc_station", "device_b": "slide_w140"}, "weight": 8.0},
    {"type": "hard", "rule_name": "reachability",
     "params": {"arm_id": "arm_slider", "target_device_id": "hplc_station"}}
  ],
  "seeder": "compact_outward",
  "seeder_overrides": {},
  "run_de": true,
  "workflow_edges": [],
  "maxiter": 200,
  "seed": null
}
```

响应：
```json
{
  "placements": [
    {"device_id": "arm_slider", "uuid": "", "position": {"x": 1.2, "y": 0.8, "z": 0.0}, "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}},
    {"device_id": "hplc_station", "uuid": "", "position": {"x": 2.1, "y": 1.4, "z": 0.0}, "rotation": {"x": 0.0, "y": 0.0, "z": 1.5708}}
  ],
  "cost": 0.0,
  "success": true,
  "seeder_used": "compact_outward",
  "de_ran": true
}
```

**约束规则速查**：

| rule_name | type | 关键参数 |
|---|---|---|
| `min_spacing` | hard | `min_gap`（米，默认 0.3） |
| `reachability` | hard | `arm_id`, `target_device_id` |
| `distance_less_than` | hard | `device_a`, `device_b`, `distance` |
| `distance_greater_than` | hard | `device_a`, `device_b`, `distance` |
| `in_zone` | hard | `device_id`, `zone_x`, `zone_y`, `zone_w`, `zone_d` |
| `minimize_distance` | soft | `device_a`, `device_b` |
| `maximize_distance` | soft | `device_a`, `device_b` |
| `prefer_orientation_mode` | soft | `mode`: `outward` / `inward` |
| `prefer_aligned` | soft | （无参数） |

**seeder 预设**：

| 名称 | 效果 |
|---|---|
| `compact_outward` | 紧凑布局，设备朝外（默认） |
| `spread_inward` | 分散布局，设备朝内 |
| `workflow_cluster` | 按 `workflow_edges` 分组聚类 |

---

## 7. 核心算法说明

### 差分进化优化器（optimizer.py）

- **编码**：N 个设备 → 3N 维向量 `[x0, y0, θ0, x1, y1, θ1, ...]`
- **搜索边界**：x/y 按设备包围盒半径收紧，θ ∈ `[0, 2π]`
- **种群初始化**：种子个体（力导向）注入第 0 号位置 + 随机个体填充
- **停止条件**：`maxiter` 次迭代 or 绝对容差 `atol=1e-3` 收敛
- **后处理**：`snap_theta` 将接近直角的角度吸附到 0°/90°/180°/270°

### 约束评估（constraints.py）

- **硬约束违反** → cost = inf → 替换为 1e18（DE 不接受 inf）→ 方案直接淘汰
- **软约束违反** → `weight × penalty` 累加到总 cost
- 默认硬约束（OBB 碰撞 + 边界）在用户约束前评估，inf 时跳过用户约束计算

### 检测器双模式（mock vs moveit）

| | Mock 模式 | MoveIt2 模式 |
|---|---|---|
| 碰撞检测 | OBB SAT（obb.py） | python-fcl 或 OBB 回退（ros_checkers.py） |
| 可达性检测 | 欧氏距离阈值 | 体素图 O(1) → compute_ik 实时回退 |
| DE 循环中 | OBB SAT | python-fcl / OBB（不发 ROS 消息） |
| 优化完成后 | 无 | `sync_to_planning_scene()` → Planning Scene |
| 依赖 | 无 ROS | ROS2 + move_group 运行中 |

---

## 8. 剩余工作（Phase 3-5）

Phase 1、Phase 2 代码均已完成，以下是后续工作。

### Phase 3：IK 真实可达性验证

- [ ] `IKFastReachabilityChecker.is_reachable()` 已接入 `compute_ik`，但目前仅在 `is_reachable()` 中调用
- [ ] 在 `service.py` 的 `run_optimize()` 末尾，对所有 `reachability` 约束做最终 IK 验证
- [ ] 响应中新增 `reachability_verification` 字段：
  ```json
  {
    "reachability_verification": {
      "mode": "moveit_ik",
      "all_passed": true,
      "failures": [],
      "checked_count": 2
    }
  }
  ```
- [ ] 验收：`compute_ik` 返回 None 时 `success` 仍为 false 且有详细 failures

### Phase 4：预计算可达性体素图（O(1) 查表）

- [ ] 新建 `precompute_reachability.py` 离线工具：在机械臂基坐标系中按 2cm 步长网格化，每点调用 `compute_ik` 并存为 `voxel_maps/{arm_id}.npz`
- [ ] `IKFastReachabilityChecker` 自动加载 `voxel_maps/` 中匹配 arm_id 的 .npz（代码已支持，只缺 .npz 文件）
- [ ] 验收：优化速度与 mock 模式差距 < 20%

### Phase 5：设备目录统一 + LLM 联调

- [ ] `device_catalog.py` 新增 `load_devices_from_registry_live()`，接入运行时 `registered_devices`
- [ ] `GET /api/v1/layout/devices` 优先返回在线设备，兜底 footprints.json
- [ ] 端到端测试：自然语言 → `/interpret` → `/optimize` → MoveIt2 场景更新

---

## 9. 常见问题排查

### `No module named 'scipy'`
```bash
conda activate unilab && pip install "scipy>=1.10"
```

### `ModuleNotFoundError: unilabos.services`
```bash
ls /home/ubuntu/workspace/Uni-Lab-OS/unilabos/services/__init__.py
# 不存在则：touch /home/ubuntu/workspace/Uni-Lab-OS/unilabos/services/__init__.py
```

### `/api/v1/layout/*` 返回 404
```bash
tail -8 /home/ubuntu/workspace/Uni-Lab-OS/unilabos/app/web/api.py
# 期望末尾有：
# from unilabos.app.web.routers.layout import layout_router
# app.include_router(layout_router, prefix="/api/v1")
```

### moveit 模式回退 mock（WARNING）
查看日志中 WARNING 消息的具体异常。最常见原因：
1. `registered_devices` 为空（unilab 启动时未加载机器人设备）
2. driver_instance 不是 `MoveitInterface` 类型
3. `move_group` 未启动，导致 `MoveitInterface.__init__` 失败

### optimize 返回 `success: false`（cost = inf）
硬约束违反（设备重叠或越界）。依次检查：
1. 实验室尺寸 `lab.width/depth` 是否能容纳所有设备
2. `min_gap` 是否过大
3. 增大 `maxiter`（默认 200，可试 500）

---

## 10. 关键文件速查

| 需要了解 | 文件路径 | 关键位置 |
|---|---|---|
| LayoutService 完整流程 | `unilabos/services/layout_optimizer/service.py` | `run_optimize()` L197+ |
| MoveIt2 桥接实现 | `unilabos/services/layout_optimizer/checker_bridge.py` | `discover_moveit2_instances()` / `create_checkers()` |
| FCL/OBB/IK 检测器 | `unilabos/services/layout_optimizer/ros_checkers.py` | `MoveItCollisionChecker` / `IKFastReachabilityChecker` |
| registered_devices 定义 | `unilabos/ros/nodes/base_device_node.py` | L79 + `DeviceInfoType` L2075 |
| MoveitInterface 驱动 | `unilabos/devices/ros_dev/moveit_interface.py` | `moveit2: dict` 属性 |
| MoveIt2 API | `unilabos/devices/ros_dev/moveit2.py` | `compute_ik()` L1279, `add_collision_box()` L1501 |
| API 路由定义 | `unilabos/app/web/routers/layout.py` | 6 个端点 |
| API 路由注册 | `unilabos/app/web/api.py` | 最后 5 行 |
| 设备尺寸数据库 | `unilabos/services/layout_optimizer/footprints.json` | 499 条设备记录 |
