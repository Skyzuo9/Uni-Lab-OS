# Layout Optimizer × Uni-Lab-OS — 项目对接文档

**日期**: 2026-03-27  
**版本**: 1.1  
**状态**: 已集成并验证（Mock 模式 + MoveIt2 模式均可运行，3D 真实模型渲染已启用）

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [文件结构](#3-文件结构)
4. [数据模型详解](#4-数据模型详解)
5. [API 接口文档](#5-api-接口文档)（含 5.9 mesh_manifest / 5.10 meshes 新接口）
6. [核心模块说明](#6-核心模块说明)
7. [检测器双模式（Mock ↔ MoveIt2）](#7-检测器双模式mock--moveit2)
8. [优化算法详解](#8-优化算法详解)
9. [LLM Skill 集成](#9-llm-skill-集成)
10. [部署指南](#10-部署指南)（含 10.2 启动注意事项 / 10.7 3D 模型路由 / 10.8 完整部署速查）
11. [Demo 展示](#11-demo-展示)（含 11.1.1 3D 模型加载架构 / 11.3 Status 页 / 11.7 端到端验证）
12. [测试体系](#12-测试体系)
13. [扩展指南](#13-扩展指南)（含 13.4 为新设备添加 3D 模型）
14. [已知限制与风险](#14-已知限制与风险)
15. [环境变量速查](#15-环境变量速查)
16. [常见问题 FAQ](#16-常见问题-faq)
17. [集成过程踩坑记录](#17-集成过程踩坑记录)（v1.1 新增）

---

## 1. 项目概述

### 1.1 定位

Layout Optimizer 是 Uni-Lab-OS 平台的**实验室设备自动布局模块**。给定一组实验室设备、实验室尺寸和约束条件（硬约束 + 软约束），使用差分进化（Differential Evolution）全局优化算法自动计算最优的设备摆放位置和朝向。

该模块已作为 Uni-Lab-OS 的**同进程模块**集成（非独立微服务），直接复用 Uni-Lab-OS 的 FastAPI 路由和 ROS2 运行时。

### 1.2 核心能力一览

| 能力 | 说明 | 实现文件 |
|------|------|---------|
| 自然语言 → 约束 | 用户说"把 PCR 仪和离心机放近一点"，系统自动转为 `minimize_distance` 软约束 | `intent_interpreter.py` |
| 差分进化优化 | scipy DE 全局优化器，3N 维搜索空间（每设备 x, y, θ） | `optimizer.py` |
| OBB 碰撞检测 | 有向包围盒 + 分离轴定理（SAT），支持任意角度旋转 | `obb.py` + `mock_checkers.py` |
| MoveIt2 碰撞检测 | 通过 python-fcl 或 PlanningScene 进行精确碰撞判断 | `ros_checkers.py` + `checker_bridge.py` |
| IK 可达性验证 | 优化后调用 MoveIt2 `compute_ik` 验证机械臂是否能到达目标 | `ros_checkers.py` |
| 体素图加速 | 预计算 3D 可达性网格，O(1) 查表替代 ~5ms/次 的 IK 调用 | `precompute_reachability.py` |
| 力导向种子布局 | 初始布局生成，为 DE 提供高质量起点加速收敛 | `seeders.py` |
| 双源设备目录 | 从 footprints.json 离线数据 + Uni-Lab-OS registry 合并设备信息 | `device_catalog.py` |
| 3D 前端可视化 | Three.js 3D 场景，支持设备添加、NL 输入、自动布局动画 | `demo/lab3d_integrated.html` |
| 真实 3D 模型渲染 | 从 xacro/STL 加载设备真实几何模型，替代彩色方块，自动回退 | `demo/mesh_manifest.json` + 内置 STL 解析器 |
| LLM Skill | Prompt 模板，使 LLM 能将自然语言翻译为结构化意图 | `llm_skill/layout_intent_translator.md` |

### 1.3 端到端流程图

```
用户自然语言："把 PCR 仪和离心机放近一点，机械臂要能够到它们"
   │
   ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: POST /api/v1/layout/interpret                           │
│   输入: intents[] (由 LLM 或前端关键词匹配生成)                    │
│   处理: intent_interpreter.py — 分发到 10 种 handler             │
│   输出: constraints[] + workflow_edges[] + translations[]        │
└────────────────────────┬─────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 2: POST /api/v1/layout/optimize                            │
│   输入: devices[] + lab{} + constraints[] + seeder配置            │
│   处理:                                                          │
│     1. seeders.py — 力导向模拟生成种子布局                         │
│     2. optimizer.py — DE 全局优化 (3N维, ~100K cost 评估)         │
│     3. constraints.py — 每次 cost 评估: 硬约束 + 软约束            │
│     4. snap_theta — 后处理: 将接近 90° 的角度吸附                  │
│     5. _verify_reachability — MoveIt2 模式下用真实 IK 验证        │
│   输出: placements[] + cost + success + reachability_verification │
└────────────────────────┬─────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│ Step 3: 3D 前端渲染 (lab3d_integrated.html)                      │
│   加载: mesh_manifest.json → 逐设备 fetch STL 零件               │
│   渲染: 真实 3D 模型 (STL) / 彩色方块回退                         │
│   动画: 设备平滑移动到最优位置 + 旋转                              │
│   状态栏: cost、碰撞状态、MoveIt2 IK 可达性验证结果               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 系统架构

### 2.1 整体架构图

```
Uni-Lab-OS 进程 (FastAPI :8002 + ROS2)
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  FastAPI 路由层 (unilabos/app/web/routers/layout.py)            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  GET  /api/v1/layout/health          健康检查             │    │
│  │  GET  /api/v1/layout/devices         可用设备列表         │    │
│  │  GET  /api/v1/layout/schema          意图类型元数据       │    │
│  │  POST /api/v1/layout/interpret       意图 → 约束翻译      │    │
│  │  POST /api/v1/layout/optimize        差分进化布局优化      │    │
│  │  GET  /api/v1/layout/checker_status  检测器运行状态       │    │
│  │  GET  /api/v1/layout/demo            3D 前端页面          │    │
│  │  GET  /api/v1/layout/demo/lib/{f}    Three.js 本地资源    │    │
│  │  GET  /api/v1/layout/mesh_manifest  STL 零件清单 JSON     │    │
│  │  GET  /api/v1/layout/meshes/{d}/{f} STL 模型文件下载      │    │
│  └──────────────────────┬──────────────────────────────────┘    │
│                         ▼                                       │
│  服务层 (service.py — LayoutService 单例)                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  interpret()   → intent_interpreter.py                   │    │
│  │  optimize()    → seeders.py → optimizer.py (DE)          │    │
│  │  get_devices() → device_catalog.py + footprints.json     │    │
│  │  checker_status() → 返回当前检测器状态                     │    │
│  │  _verify_reachability() → 最终 IK 验证                    │    │
│  │  _try_moveit_checkers() → MoveIt2 延迟初始化/重试         │    │
│  └──────────────────────┬──────────────────────────────────┘    │
│                         ▼                                       │
│  检测器层 (可切换: LAYOUT_CHECKER_MODE 环境变量)                  │
│  ┌───────────────────────┐ ┌──────────────────────────────┐    │
│  │ MockCollisionChecker   │ │ MoveItCollisionChecker       │    │
│  │ (OBB SAT, O(n²))      │ │ (python-fcl / OBB 回退)      │    │
│  ├───────────────────────┤ ├──────────────────────────────┤    │
│  │ MockReachabilityChecker│ │ IKFastReachabilityChecker    │    │
│  │ (欧氏距离 < 臂展)      │ │ (体素图 O(1) + 实时 IK 回退)│    │
│  └───────────────────────┘ └────────────┬─────────────────┘    │
│         ↑ mode=mock                      ↑ mode=moveit          │
│                                          ▼                      │
│  桥接层 (checker_bridge.py)                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  CheckerBridge.discover_moveit2_instances()              │    │
│  │    → registered_devices                                  │    │
│  │    → device_info["driver_instance"].moveit2              │    │
│  │    → dict[str, MoveIt2]                                  │    │
│  │  CheckerBridge.discover_resource_mesh_manager()          │    │
│  │    → device_info["base_node_instance"]                   │    │
│  │  CheckerBridge.create_checkers()                         │    │
│  │    → (MoveItCollisionChecker, IKFastReachabilityChecker) │    │
│  └──────────────────────┬──────────────────────────────────┘    │
│                         ▼                                       │
│  ROS2 层 (Uni-Lab-OS 原有)                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  move_group 节点 → /compute_ik, /get_planning_scene      │    │
│  │  robot_state_publisher → TF 坐标变换                      │    │
│  │  ros2_control → 关节状态与控制                             │    │
│  │  registered_devices → 所有在线设备的运行时注册表            │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 为什么同进程集成

> **关键架构决策**: layout_optimizer 不再作为独立 FastAPI 服务，而是作为 Uni-Lab-OS 的同进程模块集成。
>
> 理由：Uni-Lab-OS 的 FastAPI 和 ROS2 节点运行在同一进程中，API handler 通过 `HostNode` 单例和 `registered_devices` 字典直接读取 ROS2 节点状态。Layout optimizer 需要 MoveIt2 实例做碰撞检测和 IK 可达性，最高效的方式是同进程访问，避免跨进程 RPC 开销。

### 2.3 数据流总览

```
Device Catalog (footprints.json / registry)
         │
         ▼
   ┌─────────┐    intents[]    ┌────────────┐   constraints[]   ┌───────────┐
   │ /devices │───────────────→│ /interpret  │─────────────────→│ /optimize │
   └─────────┘                 └────────────┘                   └─────┬─────┘
                                                                       │
   ┌─ cost_function 内部循环 (DE ~100K 次) ────────────────────────────┤
   │                                                                   │
   │  constraints.py::evaluate_default_hard_constraints()              │
   │    → OBB 碰撞 (graduated penalty)                                 │
   │    → 边界检测 (graduated penalty)                                  │
   │                                                                   │
   │  constraints.py::evaluate_constraints()                           │
   │    → 用户约束逐条评估                                              │
   │    → reachability: 体素图 O(1) / Mock 欧氏距离                     │
   │    → minimize_distance: OBB edge-to-edge 距离                     │
   │    → ...                                                          │
   └───────────────────────────────────────────────────────────────────┘
         │
         ▼ (最终结果)
   placements[] + cost + reachability_verification
```

---

## 3. 文件结构

### 3.1 Uni-Lab-OS 集成位置（Ubuntu 生产环境）

```
/home/ubuntu/workspace/Uni-Lab-OS/
├── unilabos/
│   ├── app/web/
│   │   ├── api.py                          # ← 修改: setup_api_routes 中注册 layout_router
│   │   └── routers/
│   │       └── layout.py                   # ← 新增: Layout Optimizer 所有 API 路由定义
│   │
│   └── services/layout_optimizer/          # ← 新增: 核心模块目录
│       ├── __init__.py                     # 模块入口
│       ├── service.py                      # LayoutService 单例 — 协调所有子模块
│       ├── checker_bridge.py               # MoveIt2 实例发现 + 桥接层
│       ├── precompute_reachability.py       # 离线体素图生成命令行工具
│       │
│       ├── models.py                       # 数据模型: Device, Lab, Placement, Constraint, Intent
│       ├── optimizer.py                    # 差分进化优化器 (scipy DE)
│       ├── constraints.py                  # 约束评估引擎 (硬约束 + 软约束)
│       ├── intent_interpreter.py           # 意图 → 约束翻译器 (10 种 handler)
│       ├── seeders.py                      # 力导向种子布局生成 (3 种预设)
│       ├── obb.py                          # OBB 几何: corners, overlap (SAT), min_distance, penetration_depth
│       ├── mock_checkers.py                # Mock 碰撞/可达性检测 (无 ROS 依赖)
│       ├── ros_checkers.py                 # MoveIt2 碰撞/可达性检测 (需 ROS2)
│       ├── interfaces.py                   # Protocol 接口: CollisionChecker, ReachabilityChecker
│       ├── device_catalog.py               # 双源设备目录管理 (footprints + registry)
│       ├── lab_parser.py                   # 实验室配置解析
│       ├── footprints.json                 # 离线设备尺寸库 (碰撞包围盒, 开口方向等)
│       │
│       ├── llm_skill/
│       │   └── layout_intent_translator.md # LLM Prompt 模板
│       │
│       ├── demo/
│       │   ├── lab3d_integrated.html       # 3D 前端 Demo (Three.js + 内置 STL 解析器)
│       │   ├── mesh_manifest.json          # ← 新增: 6 种设备的 STL 零件清单 + 关节位姿
│       │   └── lib/                        # 本地 Three.js 文件 (避免 CDN 依赖)
│       │       ├── three.module.js
│       │       ├── OrbitControls.js
│       │       └── CSS2DRenderer.js
│       │
│       ├── voxel_maps/                     # 预计算体素图 (.npz)
│       │   └── arm_slider_arm.npz          # （运行 precompute 后生成）
│       │
│       └── tests/                          # 测试套件 (12 个测试文件)
│           ├── test_optimizer.py
│           ├── test_constraints.py
│           ├── test_intent_interpreter.py
│           ├── test_seeders.py
│           ├── test_obb.py
│           ├── test_mock_checkers.py
│           ├── test_ros_checkers.py
│           ├── test_device_catalog.py
│           ├── test_interpret_api.py
│           ├── test_llm_skill.py
│           ├── test_bugfixes_v2.py
│           └── test_e2e_pcr_pipeline.py
│
└── lab_with_arm.json                       # MoveIt2 模式实验室配置 (含 arm_slider)
```

### 3.2 开发仓库（handover_layout_optimizer/）

```
~/Desktop/handover_layout_optimizer/
├── pyproject.toml               # 包定义 + 依赖声明 (pip install -e ".[dev]")
├── .gitignore                   # Git 忽略规则
├── README.md                    # 快速复现指南
├── PROJECT_HANDOVER.md          # 本文档（详细对接文档）
├── INTEGRATION_PLAN.md          # 集成架构方案（5 Phase）
├── UBUNTU_SETUP_GUIDE.md        # Ubuntu 部署手册
├── lab_with_arm.json            # MoveIt2 实验室配置示例
├── lab3d.html                   # 原始 3D 前端（独立使用，无需后端）
├── patch_layout_routes.py       # Uni-Lab-OS 集成补丁脚本
│
└── layout_optimizer/            # ← Python 包（所有源码在此目录下）
    ├── __init__.py              # 包入口
    ├── models.py                # 数据模型
    ├── optimizer.py             # 差分进化优化器
    ├── constraints.py           # 约束评估引擎
    ├── seeders.py               # 力导向种子布局
    ├── obb.py                   # OBB 几何
    ├── mock_checkers.py         # Mock 检测器
    ├── ros_checkers.py          # MoveIt2 检测器
    ├── interfaces.py            # Protocol 接口
    ├── device_catalog.py        # 设备目录
    ├── lab_parser.py            # 实验室解析
    ├── footprints.json          # 设备尺寸库 (499 个设备)
    ├── server.py                # 独立 FastAPI 服务（开发/测试用，端口 8000）
    ├── pencil_integration.py    # 初始布局回退 stub
    ├── extract_footprints.py    # 离线工具: 从 STL/GLB 提取设备尺寸
    │
    ├── static/
    │   └── lab3d.html           # 3D 前端（server.py 挂载）
    ├── demo/
    │   ├── lab3d_integrated.html # 集成版 3D 前端（适配 Uni-Lab-OS + STL 加载）
    │   ├── mesh_manifest.json   # STL 零件清单 (从 xacro 提取的 6 设备位姿)
    │   └── layout_demo.html     # 2D 简化版
    ├── llm_skill/
    │   └── layout_intent_translator.md  # LLM Prompt 模板
    │
    └── tests/                   # 测试套件 (12 文件, 183 pass + 10 LLM skip)
        ├── __init__.py
        ├── fixtures/
        │   ├── sample_devices.json
        │   └── sample_lab.json
        ├── test_optimizer.py
        ├── test_constraints.py
        ├── test_intent_interpreter.py
        ├── test_seeders.py
        ├── test_obb.py
        ├── test_mock_checkers.py
        ├── test_ros_checkers.py
        ├── test_device_catalog.py
        ├── test_interpret_api.py
        ├── test_llm_skill.py
        ├── test_bugfixes_v2.py
        └── test_e2e_pcr_pipeline.py
```

> **复现步骤**: `pip install -e ".[dev]"` → `uvicorn layout_optimizer.server:app --port 8000` → 浏览器 http://localhost:8000/lab3d

### 3.3 集成时的代码改动总结

| 改动类型 | 文件 | 说明 |
|---------|------|------|
| **新增** | `service.py` | LayoutService 单例，协调 interpret/optimize/get_devices |
| **新增** | `checker_bridge.py` | MoveIt2 实例发现，从 `registered_devices` 桥接 |
| **新增** | `precompute_reachability.py` | 离线体素图生成工具 |
| **新增** | `layout.py` (路由) | FastAPI 路由定义，挂载到 `/api/v1/layout/` |
| **修改** | `api.py` | 在 `setup_api_routes` 中 `include_router(layout_router)` |
| **修改** | `optimizer.py` | 去除 `pencil_integration` 依赖，种子由 `seeders.py` 生成后传入 |
| **修改** | `seeders.py` | `row_fallback` 模式改为内置 `_row_fallback()` 函数 |
| **修改** | `intent_interpreter.py` | `from layout_optimizer.models` → `from .models` |
| **修改** | `mock_checkers.py` | `from layout_optimizer.obb` → `from .obb` |
| **新增** | `demo/mesh_manifest.json` | 6 种设备的 STL 零件坐标清单（从 xacro 关节链提取） |
| **新增** | `patch_layout_routes.py` | 补丁脚本：给 `layout.py` 添加 `/mesh_manifest` 和 `/meshes/` 路由 |
| **修改** | `layout.py` (路由) | 新增 STL 文件下载路由 + mesh_manifest 路由 |
| **修改** | `demo/lab3d_integrated.html` | 内置二进制 STL 解析器，`createDeviceMesh()` 改为异步加载真实模型 |
| **直接复制** | 其余核心文件 | models, obb, constraints, interfaces, ros_checkers, device_catalog, lab_parser, footprints.json |

---

## 4. 数据模型详解

### 4.1 Device（设备）

```python
@dataclass
class Device:
    id: str                                         # 唯一标识（如 "hplc_station"）
    name: str                                       # 显示名称（如 "HPLC Station"）
    bbox: tuple[float, float] = (0.6, 0.4)          # 碰撞包围盒 (width, depth)，单位：米
    device_type: Literal["static", "articulation", "rigid"] = "static"
    height: float = 0.4                             # 高度（3D 渲染和碰撞盒用）
    origin_offset: tuple[float, float] = (0.0, 0.0) # 原点偏移
    openings: list[Opening] = []                     # 访问开口（影响朝向约束）
    source: Literal["registry", "assets", "manual"] = "manual"
    model_path: str = ""                            # 3D 模型路径
    model_type: str = ""                            # 模型格式（glb, stl 等）
    thumbnail_url: str = ""                         # 缩略图 URL
```

**device_type 说明**：
- `static`: 固定设备（PCR 仪、离心机、HPLC 等）
- `articulation`: 可运动设备（机械臂），用于可达性约束的臂端
- `rigid`: 可移动刚体

**Opening**（访问开口）：
```python
@dataclass
class Opening:
    direction: tuple[float, float] = (0.0, -1.0)  # 设备局部坐标系方向向量
    label: str = ""                                 # 开口标签（如 "front_door"）
```

### 4.2 Lab（实验室）

```python
@dataclass
class Lab:
    width: float   # X 方向长度，单位：米
    depth: float   # Y 方向长度，单位：米
    obstacles: list[Obstacle] = []  # 固定障碍物
```

### 4.3 Placement（布局位姿）

```python
@dataclass
class Placement:
    device_id: str
    x: float       # 设备中心 X 坐标
    y: float       # 设备中心 Y 坐标
    theta: float   # 旋转角（弧度），绕 Z 轴
    uuid: str = "" # 前端透传标识
```

### 4.4 Constraint（约束规则）

```python
@dataclass
class Constraint:
    type: Literal["hard", "soft"]  # hard=违反则方案淘汰, soft=加权惩罚
    rule_name: str                  # 规则名称（见下表）
    params: dict = {}               # 规则参数
    weight: float = 1.0             # 仅 soft 约束使用
```

**完整约束规则表**：

| rule_name | type | params | 说明 | constraints.py 行为 |
|-----------|------|--------|------|-------------------|
| `no_collision` | hard/soft | — | 设备间无碰撞 | OBB SAT 检测，hard→inf, soft→weight×碰撞数 |
| `within_bounds` | hard/soft | — | 设备不超出边界 | AABB 边界检测 |
| `min_spacing` | hard/soft | `min_gap: float` | 所有设备间最小间距 | OBB edge-to-edge 距离 < min_gap |
| `reachability` | hard/soft | `arm_id: str, target_device_id: str` | 机械臂可达目标 | 调用 reachability_checker.is_reachable() |
| `distance_less_than` | hard/soft | `device_a, device_b, distance` | 最大距离限制 | OBB 距离 > distance → 惩罚 |
| `distance_greater_than` | hard/soft | `device_a, device_b, distance` | 最小距离限制 | OBB 距离 < distance → 惩罚 |
| `minimize_distance` | soft | `device_a, device_b` | 最小化两设备距离 | cost = weight × OBB距离 |
| `maximize_distance` | soft | `device_a, device_b` | 最大化两设备距离 | cost = weight × (对角线 - OBB距离) |
| `prefer_aligned` | soft | — | 偏好 90° 对齐 | cost = Σ (1-cos(4θ))/2 |
| `prefer_orientation_mode` | soft | `mode: "outward"\|"inward"` | 朝向偏好 | 基于设备相对实验室中心的角度 |
| `prefer_seeder_orientation` | soft | `target_thetas: dict[str,float]` | 保持种子朝向 | cost = Σ (1-cos(θ-target))/2 |

### 4.5 Intent（语义化意图）

```python
@dataclass
class Intent:
    intent: str        # 意图类型（如 "reachable_by"）
    params: dict = {}  # 意图参数
    description: str = ""  # 可选自然语言描述（用于审计）
```

**完整意图类型及其映射**：

| intent 类型 | 参数 | 翻译后生成的约束 | 优先级映射 |
|------------|------|---------------|-----------|
| `reachable_by` | `arm: str, targets: list[str]` | N 个 `reachability` 硬约束 | — |
| `close_together` | `devices: list[str], priority: str` | C(n,2) 个 `minimize_distance` 软约束 | low=1.0, medium=3.0, high=8.0 |
| `far_apart` | `devices: list[str], priority: str` | C(n,2) 个 `maximize_distance` 软约束 | 同上 |
| `max_distance` | `device_a, device_b, distance` | 1 个 `distance_less_than` 硬约束 | — |
| `min_distance` | `device_a, device_b, distance` | 1 个 `distance_greater_than` 硬约束 | — |
| `min_spacing` | `min_gap: float` | 1 个 `min_spacing` 硬约束 | — |
| `face_outward` | — | 1 个 `prefer_orientation_mode(mode=outward)` 软约束 | — |
| `face_inward` | — | 1 个 `prefer_orientation_mode(mode=inward)` 软约束 | — |
| `align_cardinal` | — | 1 个 `prefer_aligned` 软约束 | — |
| `workflow_hint` | `workflow: str, devices: list[str]` | 相邻设备 `minimize_distance` + workflow_edges | confidence="low" |

### 4.6 Protocol 接口

```python
class CollisionChecker(Protocol):
    def check(self, placements: list[dict]) -> list[tuple[str, str]]:
        """placements: [{"id": str, "bbox": (w, d), "pos": (x, y, θ)}]
           返回碰撞设备对列表 [("device_a", "device_b")]"""

class ReachabilityChecker(Protocol):
    def is_reachable(self, arm_id: str, arm_pose: dict, target: dict) -> bool:
        """arm_pose: {"x", "y", "theta"}, target: {"x", "y", "z"}
           返回是否可达"""
```

---

## 5. API 接口文档

**Base URL**: `http://<host>:8002/api/v1/layout`

### 5.1 GET /health

健康检查，验证服务可用。

**响应示例**:
```json
{
    "status": "ok",
    "collision_checker": "MoveItCollisionChecker"
}
```

---

### 5.2 GET /devices

返回可用设备列表。支持 `source` 查询参数过滤来源。

**参数**: `?source=all|registry|assets|manual`

**响应示例**:
```json
[
    {
        "id": "hplc_station",
        "name": "HPLC Station",
        "device_type": "static",
        "source": "manual",
        "bbox": [0.6, 0.5],
        "height": 0.4,
        "origin_offset": [0.0, 0.0],
        "openings": [],
        "model_path": "",
        "model_type": "",
        "thumbnail_url": ""
    },
    {
        "id": "arm_slider",
        "name": "Arm Slider",
        "device_type": "articulation",
        "source": "registry",
        "bbox": [1.2, 0.3],
        "height": 0.8,
        "origin_offset": [0.0, 0.0],
        "openings": [{"direction": [0, -1], "label": "front"}],
        "model_path": "/models/arm_slider/model.glb",
        "model_type": "glb",
        "thumbnail_url": ""
    }
]
```

---

### 5.3 GET /schema

返回所有支持的意图类型及其参数规格。用于 LLM 或前端动态发现可用约束。

**响应示例**:
```json
{
    "intent_types": ["reachable_by", "close_together", "far_apart", "max_distance",
                     "min_distance", "min_spacing", "face_outward", "face_inward",
                     "align_cardinal", "workflow_hint"],
    "priority_options": ["low", "medium", "high"],
    "seeder_presets": ["compact_outward", "spread_inward", "workflow_cluster", "row_fallback"]
}
```

---

### 5.4 POST /interpret

将语义化意图翻译为约束列表。这是 NL → 优化管线的中间步骤。

**请求**:
```json
{
    "intents": [
        {
            "intent": "close_together",
            "params": {"devices": ["ot2", "shaker"], "priority": "high"},
            "description": "PCR 仪和离心机放近一点"
        },
        {
            "intent": "reachable_by",
            "params": {"arm": "arm_slider", "targets": ["ot2", "shaker"]},
            "description": "机械臂要能够到它们"
        }
    ]
}
```

**响应**:
```json
{
    "constraints": [
        {
            "type": "soft",
            "rule_name": "minimize_distance",
            "params": {"device_a": "ot2", "device_b": "shaker"},
            "weight": 8.0
        },
        {
            "type": "hard",
            "rule_name": "reachability",
            "params": {"arm_id": "arm_slider", "target_device_id": "ot2"},
            "weight": 1.0
        },
        {
            "type": "hard",
            "rule_name": "reachability",
            "params": {"arm_id": "arm_slider", "target_device_id": "shaker"},
            "weight": 1.0
        }
    ],
    "translations": [
        {
            "source_intent": "close_together",
            "source_params": {"devices": ["ot2", "shaker"], "priority": "high"},
            "generated_constraints": [...],
            "explanation": "设备组 ['ot2', 'shaker'] 应尽量靠近（优先级: high）"
        },
        {
            "source_intent": "reachable_by",
            "source_params": {"arm": "arm_slider", "targets": ["ot2", "shaker"]},
            "generated_constraints": [...],
            "explanation": "机械臂 'arm_slider' 需要能够到达 2 个目标设备"
        }
    ],
    "workflow_edges": [],
    "errors": []
}
```

---

### 5.5 POST /optimize

执行差分进化布局优化，返回最优设备坐标。

**请求**:
```json
{
    "devices": [
        {"id": "arm_slider", "name": "Arm Slider", "size": [0.6, 0.4], "device_type": "articulation"},
        {"id": "hplc_station", "name": "HPLC Station", "size": [0.6, 0.5]},
        {"id": "slide_w140", "name": "Slide W140", "size": [0.6, 0.4]}
    ],
    "lab": {"width": 4.0, "depth": 4.0},
    "constraints": [
        {"type": "hard", "rule_name": "min_spacing", "params": {"min_gap": 0.05}},
        {"type": "hard", "rule_name": "reachability", "params": {"arm_id": "arm_slider", "target_device_id": "hplc_station"}},
        {"type": "soft", "rule_name": "minimize_distance", "params": {"device_a": "hplc_station", "device_b": "slide_w140"}, "weight": 8.0}
    ],
    "seeder": "compact_outward",
    "run_de": true,
    "maxiter": 300
}
```

**请求参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `devices` | list[dict] | 是 | 设备列表，`id` 必填，`size` 可选（回退到 footprints.json） |
| `lab` | dict | 是 | `{width, depth}` 实验室尺寸（米） |
| `constraints` | list[dict] | 否 | 约束规则列表 |
| `seeder` | string | 否 | 种子策略：`compact_outward`（默认）/ `spread_inward` / `workflow_cluster` / `row_fallback` |
| `run_de` | bool | 否 | 是否运行 DE 优化（false = 仅返回种子布局） |
| `maxiter` | int | 否 | DE 最大迭代次数（默认 200） |
| `workflow_edges` | list | 否 | 工作流边 `[[device_a, device_b], ...]`，由 `/interpret` 产出 |

**响应**:
```json
{
    "placements": [
        {
            "device_id": "arm_slider",
            "uuid": "arm_slider",
            "position": {"x": 2.0, "y": 2.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}
        },
        {
            "device_id": "hplc_station",
            "uuid": "hplc_station",
            "position": {"x": 2.54, "y": 2.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 1.5708}
        },
        {
            "device_id": "slide_w140",
            "uuid": "slide_w140",
            "position": {"x": 1.46, "y": 2.0, "z": 0.0},
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0}
        }
    ],
    "cost": 0.342,
    "success": true,
    "seeder_used": "compact_outward",
    "de_ran": true,
    "reachability_verification": {
        "mode": "moveit_ik",
        "all_passed": true,
        "failures": [],
        "checked_count": 1
    }
}
```

**`reachability_verification` 字段**（仅 MoveIt2 模式下出现）:

| 字段 | 说明 |
|------|------|
| `mode` | `"moveit_ik"` = 真实 IK 验证, `"mock"` = 欧氏距离 |
| `all_passed` | 所有可达性约束是否通过 |
| `failures` | 失败列表 `[{arm_id, target_device_id, reason}]` |
| `checked_count` | 检查的约束总数 |

---

### 5.6 GET /checker_status

返回当前碰撞/可达性检测器的运行状态。

**Mock 模式响应**:
```json
{
    "mode": "mock",
    "collision_checker": "MockCollisionChecker",
    "reachability_checker": "MockReachabilityChecker"
}
```

**MoveIt2 模式响应**:
```json
{
    "mode": "moveit",
    "collision_checker": "MoveItCollisionChecker",
    "reachability_checker": "IKFastReachabilityChecker"
}
```

---

### 5.7 GET /demo

返回 3D Lab Designer 前端页面（HTML）。优先加载 `lab3d_integrated.html`，回退到 `layout_demo.html`。

---

### 5.8 GET /demo/lib/{filename}

提供 Three.js 本地 JS 文件（`three.module.js`, `OrbitControls.js`, `CSS2DRenderer.js`），避免外网 CDN 依赖。

---

### 5.9 GET /mesh_manifest

返回设备 3D 模型零件清单 JSON。前端用此清单决定为每个设备加载哪些 STL 文件及其位姿。

**响应示例（节选）**:
```json
{
    "arm_slider": {
        "parts": [
            {"file": "arm_slideway.STL", "position": [0, 0, 0], "rotation": [0, 0, 0], "color": [0.753, 0.753, 0.753]},
            {"file": "arm_base.STL", "position": [0.307, 0, 0.1225], "rotation": [0, 0, 0], "color": [1, 1, 1]},
            {"file": "arm_link_1.STL", "position": [0.307, 0.1249, 0.2725], "rotation": [0, 0, 0], "color": [1, 1, 1]}
        ]
    },
    "thermo_orbitor_rs2_hotel": {
        "parts": [
            {"file": "hotel.stl", "position": [0, 0, 0], "rotation": [-1.5708, 0, 3.1416], "color": [1, 1, 1]}
        ]
    }
}
```

**零件位姿说明**:
- `position`: URDF 坐标系下的绝对位置 `[x, y, z]`（Z 朝上），从 xacro 关节链累计计算
- `rotation`: URDF 坐标系下的 Euler 角 `[rx, ry, rz]`（RPY 顺序）
- `color`: 材质 RGB `[r, g, b]`，取自 xacro `<material>` 标签
- 前端加载后统一旋转 -90° 绕 X 轴，将 URDF Z-up 转换为 Three.js Y-up

**已收录的 6 种设备（27 个 STL 零件）**:

| 设备 ID | 零件数 | 来源 xacro |
|---------|-------|-----------|
| `arm_slider` | 8 | `device_mesh/devices/arm_slider/macro_device.xacro` |
| `hplc_station` | 5 | `device_mesh/devices/hplc_station/macro_device.xacro` |
| `liquid_transform_xyz` | 4 | `device_mesh/devices/liquid_transform_xyz/macro_device.xacro` |
| `slide_w140` | 4 | `device_mesh/devices/slide_w140/macro_device.xacro` |
| `thermo_orbitor_rs2_hotel` | 1 | `device_mesh/devices/thermo_orbitor_rs2_hotel/macro_device.xacro` |
| `opentrons_liquid_handler` | 5 | `device_mesh/devices/opentrons_liquid_handler/macro_device.xacro` |

---

### 5.10 GET /meshes/{device_id}/{filename}

提供设备 STL 网格文件下载。文件来自 `unilabos/device_mesh/devices/{device_id}/meshes/{filename}`。

**示例**: `GET /api/v1/layout/meshes/arm_slider/arm_slideway.STL`

**响应**: 二进制 STL 文件，`content-type: application/sla`

**安全**: 路径遍历保护（文件路径必须在 `device_mesh/devices/` 目录内）。

---

### 5.11 API 端点变更对照表（原 handover → Uni-Lab-OS）

| 原 handover 端点 | 新 Uni-Lab-OS 端点 | 变化 |
|---|---|---|
| `GET /health` | `GET /api/v1/layout/health` | 路径前缀 |
| `GET /devices` | `GET /api/v1/layout/devices` | 路径前缀 + 可接入 registry |
| `POST /interpret` | `POST /api/v1/layout/interpret` | 路径前缀 |
| `GET /interpret/schema` | `GET /api/v1/layout/schema` | 路径简化 |
| `POST /optimize` | `POST /api/v1/layout/optimize` | 路径前缀 + 响应增加 `reachability_verification` |
| (无) | `GET /api/v1/layout/checker_status` | 新增 |
| (无) | `GET /api/v1/layout/demo` | 新增 |
| (无) | `GET /api/v1/layout/mesh_manifest` | 新增: 3D 模型零件清单 |
| (无) | `GET /api/v1/layout/meshes/{d}/{f}` | 新增: STL 文件下载 |

---

## 6. 核心模块说明

### 6.1 service.py — LayoutService 单例

**职责**: 对外唯一入口，协调所有子模块。

```python
class LayoutService:
    _instance = None                        # 单例

    def __init__(self):
        self._checker_mode = "mock"          # 由 LAYOUT_CHECKER_MODE 控制
        self._collision_checker = None       # Mock 或 MoveIt 实例
        self._reachability_checker = None    # Mock 或 IKFast 实例
        self._init_checkers()                # 启动时初始化

    def interpret(self, intents) -> dict     # 调用 intent_interpreter
    def optimize(self, ...) -> dict          # 调用 seeders + optimizer + verify
    def get_devices(self, source) -> list    # 调用 device_catalog
    def checker_status(self) -> dict         # 返回检测器状态
    def _try_moveit_checkers(self)           # MoveIt2 延迟初始化/重试
    def _verify_reachability(self, ...)      # 最终 IK 验证
```

**关键设计**:
- `_try_moveit_checkers()` 支持延迟重试，因为 ROS2 设备初始化是异步的，`LayoutService` 可能在 MoveIt2 就绪前被创建
- `_verify_reachability()` 仅在最终结果上运行（不在 DE 循环中），因为 `compute_ik` 是 ROS service 调用（~5ms/次）

### 6.2 checker_bridge.py — MoveIt2 桥接层

**职责**: layout_optimizer 与 Uni-Lab-OS ROS2 层的**唯一接触点**。

```python
class CheckerBridge:
    @staticmethod
    def discover_moveit2_instances() -> dict[str, MoveIt2]:
        """遍历 registered_devices，找到 driver_instance.moveit2 字典"""
        # 访问路径: registered_devices[device_id]["driver_instance"].moveit2[group_name]

    @staticmethod
    def discover_resource_mesh_manager():
        """找到具有 add_resource_collision_meshes 方法的节点"""
        # 访问路径: registered_devices[device_id]["base_node_instance"]

    @classmethod
    def create_checkers(cls, primary_arm_id=None):
        """创建 (MoveItCollisionChecker, IKFastReachabilityChecker) 元组"""
```

**`registered_devices` 数据结构**（来自 `unilabos/ros/nodes/base_device_node.py`）:
```python
registered_devices: dict[str, DeviceInfoType] = {}
# DeviceInfoType 的关键字段:
#   "driver_instance": MoveitInterface 实例（含 .moveit2 字典）
#   "base_node_instance": BaseDeviceNode 实例（含 add_resource_collision_meshes）
```

### 6.3 optimizer.py — 差分进化优化器

**核心函数**: `optimize(devices, lab, constraints, ...) -> list[Placement]`

**编码方案**: N 个设备 → 3N 维连续向量 `[x₀, y₀, θ₀, x₁, y₁, θ₁, ...]`

**DE 参数**:
- `mutation=(0.5, 1.0)`: 变异因子范围
- `recombination=0.7`: 交叉概率
- `tol=1e-6, atol=1e-3`: 收敛容差
- `popsize * 3N`: 种群大小

**cost 函数内部调用**:
```
cost_function(x)
  ├── evaluate_default_hard_constraints()  → 碰撞 + 边界（graduated penalty）
  └── evaluate_constraints()               → 用户约束逐条评估
```

**后处理**: `snap_theta()` 将接近 90° 倍数的角度吸附（阈值 15°）。

### 6.4 constraints.py — 约束评估引擎

**两种评估模式**:

1. **Graduated Penalty（默认）**: 碰撞和边界违反按严重程度加权，给 DE 平滑梯度
   - 碰撞惩罚 = `1000 × 穿透深度`（通过 `obb_penetration_depth` 计算）
   - 边界惩罚 = `1000 × 越界距离`
   
2. **Binary（旧模式）**: 违反即返回 inf

**关键**: DE 不接受 `inf`，所以 `optimizer.py` 将 `inf` 映射为 `1e18`。

### 6.5 seeders.py — 力导向种子布局

**3 种预设策略**:

| 预设 | boundary_attraction | mutual_repulsion | orientation_mode | 适用场景 |
|------|-------------------|------------------|-----------------|---------|
| `compact_outward` | -1.0（向中心聚拢） | 0.5 | outward | 紧凑布局，开口朝外 |
| `spread_inward` | +1.0（向墙壁推） | 1.0 | inward | 分散布局，开口朝内 |
| `workflow_cluster` | -0.5 | 0.5 | outward | 工作流分组 |

**模拟流程**: 初始网格 → 力导向迭代（80步）→ 碰撞消解（5遍）→ 种子布局

### 6.6 obb.py — OBB 几何引擎

提供 4 个核心函数：
- `obb_corners(cx, cy, w, h, theta)`: 4 个角点坐标
- `obb_overlap(corners_a, corners_b)`: SAT 重叠检测
- `obb_penetration_depth(corners_a, corners_b)`: 最小穿透深度
- `obb_min_distance(corners_a, corners_b)`: edge-to-edge 最小距离

### 6.7 device_catalog.py — 双源设备目录

**数据来源优先级**:
1. `footprints.json` — 离线提取的真实设备尺寸（含碰撞包围盒、开口方向）
2. `KNOWN_SIZES` 字典 — 手工配置的常见设备尺寸
3. `DEFAULT_BBOX (0.6, 0.4)` — 兜底默认值

**设备创建入口**:
- `create_devices_from_list(specs)`: 从 API 请求创建（用于 `/optimize`）
- `load_devices_from_assets(path)`: 从 uni-lab-assets 的 data.json 加载
- `load_devices_from_registry(path)`: 从 Uni-Lab-OS device_mesh 加载
- `merge_device_lists(registry, assets)`: 合并去重（registry 优先）

---

## 7. 检测器双模式（Mock ↔ MoveIt2）

通过环境变量 `LAYOUT_CHECKER_MODE` 切换，**零代码改动**。

### 7.1 对比表

| 维度 | Mock 模式 | MoveIt2 模式 |
|------|----------|-------------|
| **环境变量** | `mock`（默认） | `moveit` |
| **碰撞检测 (DE 循环)** | OBB SAT, O(n²), ~0.01ms | python-fcl 或 OBB 回退, ~0.05ms |
| **碰撞检测 (最终)** | 同上 | 同上 + sync_to_planning_scene |
| **可达性 (DE 循环)** | 欧氏距离判断, ~0.001ms | 体素图 O(1) 查表, ~0.005ms |
| **可达性 (最终验证)** | 同上 | compute_ik (ROS service), ~5ms |
| **ROS2 依赖** | 无 | 需要 move_group 运行 |
| **精度** | 低（2D 简化，臂展半径） | 高（3D FCL + 真实 IK） |
| **适用场景** | 开发测试、无机械臂场景 | 生产环境、真实臂验证 |

### 7.2 Mock 碰撞检测器

```python
class MockCollisionChecker:
    def check(placements) -> list[(str,str)]  # OBB SAT 两两碰撞检测
    def check_bounds(placements, w, d) -> list[str]  # AABB 边界检测
```

### 7.3 Mock 可达性检测器

```python
class MockReachabilityChecker:
    DEFAULT_ARM_REACH = {
        "elite_cs63": 0.624,   # 624mm
        "elite_cs66": 0.914,   # 914mm
        "elite_cs612": 1.304,  # 1304mm
        "elite_cs620": 1.800,  # 1800mm
    }
    DEFAULT_FALLBACK_REACH = 100.0  # 未知型号: 乐观回退

    def is_reachable(arm_id, arm_pose, target) -> bool
        # 欧氏距离 <= 臂展 → True
```

### 7.4 MoveIt2 碰撞检测器

```python
class MoveItCollisionChecker:
    def __init__(moveit2, *, sync_to_scene=True):
        # 尝试加载 python-fcl，不可用则回退到 OBB

    def check(placements):
        if sync_to_scene: _sync_collision_objects(placements)  # 发布到 /collision_object
        if fcl_available: return _check_with_fcl(placements)
        return _check_with_obb(placements)  # OBB 回退

    def sync_to_planning_scene(placements):
        # 最终布局同步到 MoveIt2，使运动规划感知设备位置
```

### 7.5 IKFast 可达性检测器

```python
class IKFastReachabilityChecker:
    def __init__(moveit2, *, voxel_dir=None):
        # 加载 voxel_maps/*.npz 文件

    def is_reachable(arm_id, arm_pose, target) -> bool:
        local = _transform_to_arm_frame(arm_pose, target)  # 世界坐标 → 臂基坐标
        if arm_id in voxel_maps: return _check_voxel(arm_id, local)  # O(1)
        if moveit2: return _check_live_ik(local)  # compute_ik, ~5ms
        return True  # 无可用检测，乐观返回

    def _check_live_ik(local):
        # 末端执行器朝下姿态: quat = (0, 1, 0, 0)
        result = moveit2.compute_ik(position=local, quat_xyzw=(0,1,0,0))
        return result is not None
```

### 7.6 可达性检测优先级

```
1. 体素图命中 → O(1) 查表 → 精确 ✓ 快速 ✓
2. 体素图未命中 → compute_ik() → 精确 ✓ 慢 ✗ (仅最终验证)
3. 无 MoveIt2 → Mock 欧氏距离 → 不精确 ✗ 快速 ✓
```

---

## 8. 优化算法详解

### 8.1 差分进化（DE）

**搜索空间**: 3N 维连续空间
- 每设备 `x ∈ [半径, lab_width - 半径]`
- 每设备 `y ∈ [半径, lab_depth - 半径]`
- 每设备 `θ ∈ [0, 2π]`

**cost 函数组成**:
```
total_cost = hard_cost + user_cost

hard_cost (always evaluated):
  = Σ collision_weight × penetration_depth    # 碰撞惩罚
  + Σ boundary_weight × overshoot_distance    # 边界惩罚
  (collision_weight = boundary_weight = 1000)

user_cost (from constraints[]):
  = Σ constraint.weight × violation_metric    # 每条约束独立评估
  (hard constraint violation → 1e18)
```

**种子注入**: 初始种群的第一个个体设为种子布局向量，大幅加速收敛。

**收敛条件**: 种群 cost 标准差 < tol × mean + atol

### 8.2 为什么使用 graduated penalty

传统做法（碰撞即返回 inf）导致 DE 无法区分"几乎不碰"和"严重重叠"的方案，搜索效率低。graduated penalty 让 DE 获得平滑梯度：
- 穿透深度 1mm: 惩罚 = 1.0
- 穿透深度 1cm: 惩罚 = 10.0
- 穿透深度 10cm: 惩罚 = 100.0

DE 可以逐步修复特定碰撞对，而非丢弃整个近优方案。

### 8.3 OBB 距离计算

约束中的距离全部使用 **OBB edge-to-edge 最小距离**（非中心距离），更符合物理直觉：
- 两个大设备中心距 2m，但边缘可能只相距 0.5m
- `minimize_distance` 约束期望设备紧邻，OBB 距离比中心距更准确

---

## 9. LLM Skill 集成

### 9.1 Prompt 模板位置

`llm_skill/layout_intent_translator.md`

### 9.2 工作流

```
LLM 收到用户自然语言 + 当前设备列表
       │
       ▼ (使用 Prompt 模板翻译)
LLM 输出 JSON { "intents": [...] }
       │
       ▼
POST /api/v1/layout/interpret
       │
       ▼
返回 constraints[] + translations[] (含人类可读解释)
       │
       ▼ (用户确认后)
POST /api/v1/layout/optimize (传入 constraints)
```

### 9.3 设备名称解析规则

LLM 需要将用户的自然语言设备名映射到精确的 `device_id`：

1. **精确匹配**: "arm_slider" → `arm_slider`
2. **品牌匹配**: "opentrons" → `opentrons_liquid_handler`
3. **功能匹配**: "PCR machine" → `inheco_odtc_96xl`
4. **类型匹配**: "robot arm" → 查找 `device_type: articulation`
5. **模糊匹配**: 多候选时，description 字段列出候选，选最可能的

### 9.4 翻译规则

- **机械臂推断**: 如有机械臂在设备列表中，且工作流涉及样品转移，所有相关设备都应在 `reachable_by.targets` 中
- **工作流顺序**: 用户描述顺序处理步骤 → 提取设备顺序 → `workflow_hint`
- **隐式约束**: 频繁交换物品 → `close_together(high)`, 安全隔离 → `far_apart`
- **避免过度约束**: 仅添加用户描述暗示的约束

---

## 10. 部署指南

### 10.1 前提条件

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行环境 |
| Conda (unilab env) | — | 环境管理 |
| scipy | ≥ 1.10 | DE 优化器 |
| numpy | ≥ 1.24 | 数值计算 |
| FastAPI + Uvicorn | — | Web 服务（Uni-Lab-OS 已有） |
| ROS2 Humble | — | MoveIt2 模式需要 |
| MoveIt2 | — | MoveIt2 模式需要 |
| python-fcl | ≥ 0.7 | 可选：精确碰撞检测 |

### 10.2 重要启动说明

> **关键注意**: 不能直接用 `python3 -m uvicorn unilabos.app.web.server:app` 启动！
> 
> 原因：`setup_api_routes(app)` 在 `start_web_server()` 函数内部调用，而 uvicorn 直接加载模块时只创建空的 `app` 对象，不会执行路由注册，导致所有 `/api/v1/layout/*` 路由返回 404。
>
> **必须使用 `unilab` CLI 启动**，它会调用 `start_web_server()` 完成路由注册、ROS2 初始化等。

### 10.3 Mock 模式部署（无 ROS2 依赖）

适合开发测试和纯算法演示。需要 AK/SK 但不需要 ROS2 backend。

```bash
# 1. 激活环境
conda activate unilab
cd /home/ubuntu/workspace/Uni-Lab-OS

# 2. 杀掉已有进程
fuser -k 8002/tcp 2>/dev/null; sleep 2

# 3. 用 unilab CLI 启动（Mock 模式为默认）
unilab \
  -g lab_with_arm.json \
  --backend simple \
  --port 8002 \
  --ak <你的AK> \
  --sk <你的SK>

# 4. 验证
curl -s http://localhost:8002/api/v1/layout/health | python3 -m json.tool
curl -s http://localhost:8002/api/v1/layout/checker_status | python3 -m json.tool
# → {"mode": "mock", ...}

# 5. 浏览器访问 Demo
# → http://<host>:8002/api/v1/layout/demo
```

### 10.4 MoveIt2 模式部署（需要 ROS2 + MoveIt2 + AK/SK）

适合生产环境和真实机械臂验证。

```bash
# 1. 激活环境
conda activate unilab
cd /home/ubuntu/workspace/Uni-Lab-OS

# 2. 杀掉已有进程
fuser -k 8002/tcp 2>/dev/null; sleep 2

# 3. 用实验室配置启动（包含 arm_slider 机械臂）
LAYOUT_CHECKER_MODE=moveit unilab \
  -g lab_with_arm.json \
  --backend ros \
  --port 8002 \
  --skip_env_check \
  --disable_browser \
  --ak <你的AK> \
  --sk <你的SK> &

# 4. 等待 ROS2 初始化完成（首次可能需 30-60 秒）
sleep 60

# 5. 验证 MoveIt2 启用
curl -s http://localhost:8002/api/v1/layout/checker_status | python3 -m json.tool
# 期望输出:
# {
#     "mode": "moveit",
#     "collision_checker": "MoveItCollisionChecker",
#     "reachability_checker": "IKFastReachabilityChecker"
# }
```

### 10.5 实验室配置文件 (lab_with_arm.json)

```json
{
    "nodes": [
        {
            "id": "arm_slider",
            "name": "arm_slider",
            "type": "device",
            "class": "robotic_arm.SCARA_with_slider.moveit.virtual",
            "position": {"x": 0, "y": 0, "z": 0},
            "config": {
                "moveit_type": "arm_slider",
                "joint_poses": {
                    "arm": {
                        "hotel_1": [1.05, 0.568, -1.0821, 0.0, 1.0821],
                        "home": [0.865, 0.09, 0.8727, 0.0, -0.8727]
                    }
                },
                "rotation": {"x": 0, "y": 0, "z": -1.5708, "type": "Rotation"},
                "device_config": {}
            },
            "data": {}
        },
        {
            "id": "workbench_1",
            "name": "Workbench",
            "type": "device",
            "class": "virtual_workbench",
            "position": {"x": 500, "y": 0, "z": 0},
            "config": {},
            "data": {}
        }
    ],
    "links": []
}
```

**关键字段说明**:
- `class`: 设备类型全名，Uni-Lab-OS 注册表中的键
- `moveit_type`: 对应 `moveit_interface.py` 中预定义的 MoveIt2 配置
- `joint_poses`: 命名关节位置（用于机械臂预定义动作）
- `rotation`: 设备初始旋转（弧度）

### 10.6 生成预计算体素图（可选，加速 IK 查询）

```bash
# 需要 MoveIt2 + move_group 正在运行
python3 -m unilabos.services.layout_optimizer.precompute_reachability \
    --arm-id arm_slider_arm \
    --resolution 0.05 \
    --reach-estimate 1.5

# 输出: unilabos/services/layout_optimizer/voxel_maps/arm_slider_arm.npz
# IKFastReachabilityChecker 启动时自动加载
```

**分辨率 vs 耗时权衡**:

| resolution | 精度 | 网格点数 (reach=1.5m) | 预计耗时 |
|-----------|------|----------------------|---------|
| 0.05 | 5cm | ~54K | ~5 分钟 |
| 0.02 | 2cm | ~1.7M | ~2.3 小时 |
| 0.01 | 1cm | ~13.5M | ~19 小时 |

推荐先用 0.05 快速验证，后续用 0.02 替换。

### 10.7 3D 模型路由部署（patch_layout_routes.py）

如果 `layout.py` 中尚未包含 `/mesh_manifest` 和 `/meshes/` 路由，需运行补丁脚本：

```bash
cd /home/ubuntu/workspace/Uni-Lab-OS

# 复制补丁脚本和 mesh_manifest.json
cp <来源>/patch_layout_routes.py .
cp <来源>/mesh_manifest.json unilabos/services/layout_optimizer/demo/

# 运行补丁脚本
python3 patch_layout_routes.py

# 验证路由注入成功
grep -c "mesh_manifest" unilabos/app/web/routers/layout.py
# → 应返回 >=1
```

**补丁脚本逻辑**: 
- 读取 `unilabos/app/web/routers/layout.py`
- 检查是否已存在 `mesh_manifest` 路由
- 如不存在，在文件末尾追加两个新的 `@layout_router.get(...)` 路由函数
- 路由函数内的路径使用 `Path(__file__)` 相对寻址

**已知坑点**: 补丁脚本中 `mesh_manifest.json` 的相对路径需要 3 级 `..`（从 `routers/layout.py` → `services/layout_optimizer/demo/`），检查方式：
```bash
grep "manifest_path" unilabos/app/web/routers/layout.py
# 应显示: manifest_path = Path(__file__).resolve().parent.parent.parent / "services" / "layout_optimizer" / "demo" / "mesh_manifest.json"
```

### 10.8 完整部署步骤速查

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. conda activate unilab                                        │
│ 2. cd /home/ubuntu/workspace/Uni-Lab-OS                         │
│ 3. 复制文件到正确目录:                                            │
│    - 核心模块 → unilabos/services/layout_optimizer/              │
│    - mesh_manifest.json → unilabos/services/layout_optimizer/demo/│
│    - lab3d_integrated.html → unilabos/services/layout_optimizer/demo/│
│ 4. python3 patch_layout_routes.py  (如路由尚未注入)               │
│ 5. fuser -k 8002/tcp 2>/dev/null; sleep 2                       │
│ 6. LAYOUT_CHECKER_MODE=moveit unilab -g lab_with_arm.json \     │
│      --backend ros --port 8002 --ak <AK> --sk <SK>              │
│ 7. 等待 30-60 秒，验证:                                          │
│    curl http://localhost:8002/api/v1/layout/checker_status       │
│    curl http://localhost:8002/api/v1/layout/mesh_manifest        │
│ 8. 浏览器: http://<host>:8002/api/v1/layout/demo                │
└─────────────────────────────────────────────────────────────────┘
```

### 10.9 AK/SK 获取方式

1. 访问 https://uni-lab.bohrium.com
2. 登录后进入实验室管理
3. 找到身份认证信息，获取 Access Key (AK) 和 Secret Key (SK)

---

## 11. Demo 展示

### 11.1 浏览器 3D Demo

**访问地址**: `http://<host>:8002/api/v1/layout/demo`

**操作步骤**:

1. **添加设备**: 左侧 Device Library 面板中，点击设备右侧 `+` 按钮添加到场景
2. **观察 3D 模型**: 有 STL 文件的设备（arm_slider, hplc_station 等）会显示真实的 3D 几何模型；没有 STL 的设备自动回退为彩色方块
3. **自然语言优化**:
   - 右侧面板 Natural Language 输入框
   - 输入如 "机械臂要能够到所有设备，HPLC 和 Slide 放近一点"
   - 点击 "Auto Layout" 按钮
4. **观察动画**: 设备平滑移动到最优位置
5. **查看结果**: 底部状态栏显示 cost 值和碰撞状态
6. **验证 MoveIt2**: 打开 F12 → Network → 查看 `optimize` 响应中的 `reachability_verification.mode` 是否为 `"moveit_ik"`

### 11.1.1 3D 模型加载架构

```
页面加载
  │
  ├─ loadMeshManifest()           ← GET /mesh_manifest → 获取 6 设备的零件清单
  ├─ loadDeviceCatalog()          ← GET /devices → 获取设备尺寸/属性
  │
  ▼ 用户点击 + 添加设备
  │
  ├─ createDeviceMesh(deviceId)   ← async
  │   ├─ 查找 MESH_MANIFEST[deviceId]
  │   ├─ 有清单 → loadDeviceSTL()
  │   │   ├─ 对每个 part: fetch GET /meshes/{deviceId}/{file}
  │   │   ├─ parseSTL(arrayBuffer) → BufferGeometry（内置二进制解析器）
  │   │   ├─ 设置位置 + 旋转（从清单读取）
  │   │   ├─ 整体旋转 -90°X（URDF Z-up → Three.js Y-up）
  │   │   └─ 自动居中（bounding box 中心对齐）
  │   └─ 加载失败 → addBoxFallback()（彩色方块回退）
  │
  └─ 无清单 → addBoxFallback()
```

**关键设计决策**:
- **内置 STL 解析器**: 不依赖外部 `STLLoader.js`，减少文件依赖。解析器仅 20 行代码，支持二进制 STL
- **并行加载**: 同一设备的多个 STL 零件使用 `Promise.all()` 并行下载
- **优雅回退**: 任何加载失败（网络错误、文件缺失）自动回退到彩色方块，不影响使用

**NL 关键词映射**（前端 `nlToIntents()` 内置）:
- "近/close/together" → `close_together`
- "远/apart/separate" → `far_apart`
- "够到/reach" → `reachable_by`
- "间距/spacing" → `min_spacing`
- "对齐/align" → `align_cardinal`

### 11.2 curl 命令行演示

**完整管线（NL → Interpret → Optimize）**:

```bash
# === Step 1: 意图解析 ===
curl -s -X POST http://localhost:8002/api/v1/layout/interpret \
  -H "Content-Type: application/json" \
  -d '{
    "intents": [
      {
        "intent": "close_together",
        "params": {"devices": ["hplc_station", "slide_w140"], "priority": "high"},
        "description": "HPLC 和 Slide 放近一点"
      },
      {
        "intent": "reachable_by",
        "params": {"arm": "arm_slider", "targets": ["hplc_station", "slide_w140"]},
        "description": "机械臂要能够到它们"
      }
    ]
  }' | python3 -m json.tool

# === Step 2: 带约束优化 ===
curl -s -X POST http://localhost:8002/api/v1/layout/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "devices": [
      {"id": "arm_slider", "name": "Arm Slider", "size": [0.6, 0.4], "device_type": "articulation"},
      {"id": "hplc_station", "name": "HPLC Station", "size": [0.6, 0.5]},
      {"id": "slide_w140", "name": "Slide W140", "size": [0.6, 0.4]}
    ],
    "lab": {"width": 4.0, "depth": 4.0},
    "constraints": [
      {"type": "hard", "rule_name": "min_spacing", "params": {"min_gap": 0.05}},
      {"type": "soft", "rule_name": "minimize_distance",
       "params": {"device_a": "hplc_station", "device_b": "slide_w140"}, "weight": 8.0},
      {"type": "hard", "rule_name": "reachability",
       "params": {"arm_id": "arm_slider", "target_device_id": "hplc_station"}},
      {"type": "hard", "rule_name": "reachability",
       "params": {"arm_id": "arm_slider", "target_device_id": "slide_w140"}}
    ],
    "seeder": "compact_outward",
    "run_de": true,
    "maxiter": 200
  }' | python3 -m json.tool
```

### 11.3 UniLab 系统状态页

**访问地址**: `http://<host>:8002/status`

该页面显示所有已注册的 ROS2 设备节点及其状态，用于确认 MoveIt2 所需的设备已在线。

**关键信息**:
- **设备列表**: 显示 `arm_slider`、`workbench_1` 等已注册设备
- **可用动作**: 每个设备的 ROS2 action（如 `pick_and_place`、`set_position`）
- **已订阅主题**: 包括 `arm_state`、`arm_current_task` 等
- **实时更新**: 右上角显示最后更新时间

> 如果 `arm_slider` 设备不在列表中，说明 ROS2 节点未成功启动，MoveIt2 模式将无法工作。

---

### 11.5 MoveIt2 模式对比展示

MoveIt2 模式下 `/optimize` 响应会多出 `reachability_verification` 字段：

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

**展示话术**: "这里 `all_passed: true` 表示我们不仅用数学模型优化了布局，还通过真实的逆运动学求解器验证了机械臂确实能到达每个目标设备。如果 IK 求解失败，`failures` 数组会列出哪些约束不满足，以及失败原因。"

### 11.6 快速验证命令

```bash
# 健康检查
curl -s http://localhost:8002/api/v1/layout/health

# 检测器状态（确认 MoveIt2 是否启用）
curl -s http://localhost:8002/api/v1/layout/checker_status

# 设备列表
curl -s http://localhost:8002/api/v1/layout/devices

# 意图类型元数据
curl -s http://localhost:8002/api/v1/layout/schema

# 3D 模型清单（确认 STL 路由可用）
curl -s http://localhost:8002/api/v1/layout/mesh_manifest | python3 -m json.tool

# 单个 STL 文件（确认文件下载可用，应返回二进制数据）
curl -sI http://localhost:8002/api/v1/layout/meshes/arm_slider/arm_slideway.STL

# UniLab 系统状态（确认 ROS2 设备在线）
# → http://localhost:8002/status （浏览器访问）
```

### 11.7 端到端验证 MoveIt2 完整链路

确认 **3D 真实模型渲染 + MoveIt2 碰撞检测 + IK 可达性判断** 全链路打通：

1. 浏览器访问 `http://<host>:8002/api/v1/layout/demo`
2. 添加设备: Arm Slider + HPLC Station + Slide W140（应看到真实 3D 模型）
3. 点击 **Run Auto Layout**
4. 状态栏观察结果：是否显示 `Collision-free` 及可达性信息
5. 按 **F12** → **Network** → 找到 `optimize` 请求 → 查看 **Response**
6. 确认 `reachability_verification.mode` 为 `"moveit_ik"`，`all_passed` 为 `true`

**预期结果**:
```json
{
    "success": true,
    "reachability_verification": {
        "mode": "moveit_ik",
        "all_passed": true,
        "failures": [],
        "checked_count": 2
    }
}
```

---

## 12. 测试体系

### 12.1 测试文件一览

| 测试文件 | 覆盖模块 | 说明 |
|---------|---------|------|
| `test_obb.py` | `obb.py` | OBB 几何: corners, overlap, distance, penetration |
| `test_mock_checkers.py` | `mock_checkers.py` | Mock 碰撞/可达性检测 |
| `test_constraints.py` | `constraints.py` | 约束评估: 硬约束/软约束/graduated penalty |
| `test_intent_interpreter.py` | `intent_interpreter.py` | 10 种意图 → 约束翻译 |
| `test_optimizer.py` | `optimizer.py` | DE 优化收敛性、种子注入、边界情况 |
| `test_seeders.py` | `seeders.py` | 力导向种子布局生成 |
| `test_device_catalog.py` | `device_catalog.py` | footprints 加载、registry 加载、合并 |
| `test_ros_checkers.py` | `ros_checkers.py` | MoveIt2 检测器（mock MoveIt2 实例） |
| `test_interpret_api.py` | API 路由 | /interpret 端点集成测试 |
| `test_llm_skill.py` | LLM Skill | Prompt 模板输出验证 |
| `test_bugfixes_v2.py` | 多模块 | 回归测试 |
| `test_e2e_pcr_pipeline.py` | 端到端 | PCR 工作流完整管线 |

### 12.2 运行测试

```bash
# Mock 模式测试（无 ROS2 依赖，CI/本地均可）
cd /home/ubuntu/workspace/Uni-Lab-OS
conda activate unilab
pytest unilabos/services/layout_optimizer/tests/ -v -k "not moveit"

# 全量测试（需 ROS2 + MoveIt2 运行中）
LAYOUT_CHECKER_MODE=moveit pytest unilabos/services/layout_optimizer/tests/ -v

# 单个测试
pytest unilabos/services/layout_optimizer/tests/test_optimizer.py -v
```

### 12.3 开发仓库运行测试

```bash
cd ~/Desktop/handover_layout_optimizer
pip install pytest scipy numpy
pytest tests/ -v
```

---

## 13. 扩展指南

### 13.1 添加新的约束规则

**需要修改 3 个文件**:

1. **`constraints.py`** — 在 `_evaluate_single()` 中添加新的 `if rule ==` 分支
```python
if rule == "my_new_rule":
    # 实现约束评估逻辑
    # 返回: 0.0 (满足) / penalty值 (soft) / inf (hard违反)
    return ...
```

2. **`intent_interpreter.py`** — 在 `_HANDLERS` 字典中注册对应的 intent handler
```python
def _handle_my_intent(intent: Intent, result: InterpretResult) -> None:
    c = Constraint(type="soft", rule_name="my_new_rule", params={...})
    result.constraints.append(c)

_HANDLERS["my_intent"] = _handle_my_intent
```

3. **`demo/lab3d_integrated.html`**（可选） — 在 `nlToIntents()` 中添加 NL 关键词匹配

### 13.2 添加新的设备类型

**方式 A**: 在 `footprints.json` 中添加:
```json
{
  "new_device_id": {
    "bbox": [0.5, 0.3],
    "height": 0.35,
    "openings": [{"direction": [0, -1], "label": "front"}],
    "model_file": "model.glb",
    "model_type": "glb"
  }
}
```

**方式 B**: 在 `device_catalog.py` 的 `KNOWN_SIZES` 中添加:
```python
KNOWN_SIZES["new_device_id"] = (0.5, 0.3)
```

**方式 C**: 通过 Uni-Lab-OS registry 注册（`registry/devices/` 下创建 YAML）

### 13.3 接入真实 LLM

当前 3D Demo 中的 NL 解析使用前端简单关键词匹配。接入真实 LLM：

1. 参考 `llm_skill/layout_intent_translator.md` 作为 system prompt
2. 将当前场景设备列表作为 context 传给 LLM
3. LLM 输出 JSON 格式的 `{"intents": [...]}` 
4. POST 到 `/api/v1/layout/interpret` 翻译为 constraints
5. 用户确认后 POST 到 `/api/v1/layout/optimize`

### 13.4 为新设备添加 3D 模型

**目标**: 在 3D Demo 中显示新设备的真实几何模型（而非默认的彩色方块）。

**步骤**:

1. **准备 STL 文件**: 将设备的 STL 网格文件放入 `device_mesh/devices/<new_device_id>/meshes/` 目录

2. **从 xacro 提取位姿**: 阅读 `device_mesh/devices/<new_device_id>/macro_device.xacro`，找到每个 `<visual>` 下的 `<mesh filename="..."/>` 和对应的 `<origin xyz="..." rpy="..."/>`

3. **更新 mesh_manifest.json**: 添加新设备条目
```json
{
    "new_device_id": {
        "parts": [
            {
                "file": "part_1.STL",
                "position": [x, y, z],
                "rotation": [rx, ry, rz],
                "color": [r, g, b]
            }
        ]
    }
}
```

4. **位姿计算要点**:
   - xacro 中的关节变换是级联的（每个关节相对于父关节）
   - `mesh_manifest.json` 中的 `position` 是**绝对坐标**（需手工累计关节链）
   - `rotation` 直接使用 xacro 中最近 `<origin>` 的 `rpy` 值
   - 对于有多个活动关节的设备（如机械臂），使用 **home 位姿** 下的关节值

5. **验证**: 重启服务后访问 Demo，添加新设备，确认 3D 模型正确显示

### 13.5 对接新的机械臂

1. 在 `device_mesh/devices/` 下创建新臂的 xacro + MoveIt config
2. 在 `registry/devices/` 注册设备类型 YAML
3. 在 `lab_with_arm.json` 中添加设备节点，配置 `moveit_type`
4. （可选）运行 `precompute_reachability.py --arm-id <new_arm_id>` 生成体素图
5. （可选）在 `mesh_manifest.json` 添加新臂的 STL 零件清单（参见 13.4）

### 13.6 自定义种子策略

在 `seeders.py` 的 `PRESETS` 字典中添加新的预设:
```python
PRESETS["my_strategy"] = SeederParams(
    boundary_attraction=-0.8,
    mutual_repulsion=0.3,
    edge_attraction=0.5,
    orientation_mode="outward",
)
```

---

## 14. 已知限制与风险

| 问题 | 影响 | 规避方式 |
|------|------|---------|
| MoveIt2 IK 可能返回 no solution | 虚拟臂运动学参数可能与优化坐标不完全匹配 | 调整实验室尺寸或降低约束优先级 |
| 体素图未生成时 IK 较慢 | 每次 `compute_ik` 约 5ms，DE 循环中不使用 | 运行 `precompute_reachability.py` 生成体素图 |
| 3D 前端需本地 Three.js | Ubuntu 网络环境可能无法访问外网 CDN | 已内置本地 JS 文件 + 专用路由 |
| `unilab` CLI 需要 AK/SK | 云平台注册密钥 | 从 uni-lab.bohrium.com 获取 |
| DE 优化时间与设备数正相关 | 10+ 设备时优化可能需 30s+ | 减少 maxiter 或 popsize |
| `pencil_integration` 已移除 | `seeders.py` 的 `row_fallback` 使用内置简单网格 | 使用 `compact_outward` 或 `spread_inward` |
| MoveIt2 实例异步初始化 | 启动后短暂时间内 checker 可能是 mock | service.py 有重试机制 |
| python-fcl 安装困难 | FCL 不可用时回退到 OBB SAT | 已内置 OBB 回退逻辑 |
| move_group 崩溃 | 碰撞同步失败 | `_sync_collision_objects` 有 try/except |
| mesh_manifest.json 需手工维护 | 新设备需手动从 xacro 提取位姿 | 未来可自动化 xacro 解析 |
| 直接 uvicorn 启动导致 404 | 路由不注册 | 必须用 `unilab` CLI 启动（见 10.2） |
| STL 文件较大时首次加载慢 | 多个 STL 零件串行下载 | 已用 `Promise.all()` 并行化 |

---

## 15. 环境变量速查

| 变量名 | 可选值 | 默认值 | 说明 |
|--------|--------|--------|------|
| `LAYOUT_CHECKER_MODE` | `mock` / `moveit` | `mock` | 选择检测器实现 |
| `LAYOUT_VOXEL_DIR` | 路径 | `./voxel_maps/` | 预计算体素图目录 |
| `UNI_LAB_ASSETS_DIR` | 路径 | (无) | uni-lab-assets 资产目录 |

---

## 16. 常见问题 FAQ

### Q: Mock 模式和 MoveIt2 模式的优化结果有什么区别？

A: Mock 模式下可达性用欧氏距离 < 臂展近似，优化结果可能在真实 IK 下不可达。MoveIt2 模式下会用 `compute_ik` 验证，响应中会包含 `reachability_verification` 字段标明哪些约束通过/失败。

### Q: 如何在没有 ROS2 环境的机器上开发？

A: 使用 Mock 模式即可。所有核心算法（DE 优化、约束评估、种子布局、OBB 碰撞检测）不依赖 ROS2。仅 `checker_bridge.py` 和 `ros_checkers.py` 的 MoveIt2 部分需要 ROS2。

### Q: 前端 Demo 的 NL 解析精度不够怎么办？

A: 当前前端使用简单关键词匹配，仅适合演示。生产环境应接入真实 LLM，使用 `llm_skill/layout_intent_translator.md` 作为 system prompt，LLM 输出结构化 intents 后调用 `/interpret` API。

### Q: `checker_status` 返回 `mock` 但我设置了 `LAYOUT_CHECKER_MODE=moveit`？

A: 可能原因：
1. ROS2 设备尚未初始化完成（等待 30-60 秒后重试）
2. 未使用 `unilab` CLI 启动（直接用 Python 启动不会初始化 ROS2 设备）
3. 实验室配置中没有包含机械臂设备（需要 `lab_with_arm.json`）

### Q: 优化很慢怎么办？

A: 调整参数：
- 减少 `maxiter`（200→100）
- 减少 `popsize`（15→10）
- 使用更好的种子策略（`compact_outward` 比 `row_fallback` 收敛更快）
- 设备数 > 10 时，考虑分区优化

### Q: `footprints.json` 里没有我的设备怎么办？

A: 在 `/optimize` 请求中通过 `size` 字段直接指定设备尺寸：
```json
{"id": "my_device", "name": "My Device", "size": [0.5, 0.3]}
```

### Q: 3D Demo 中设备显示为彩色方块而非真实模型？

A: 可能原因（按排查顺序）：
1. `mesh_manifest.json` 中没有该设备的条目 → 添加设备的 STL 零件清单
2. `/api/v1/layout/mesh_manifest` 返回 404 → 检查 `layout.py` 中是否包含 mesh_manifest 路由，运行 `patch_layout_routes.py`
3. STL 文件路径不存在 → 确认 `device_mesh/devices/{device_id}/meshes/` 下有对应文件
4. 补丁脚本中路径层级错误 → 检查 `manifest_path` 使用了正确数量的 `..`（需要 3 级）
5. 浏览器缓存 → 按 Ctrl+Shift+R 强制刷新

### Q: 直接用 `python3 -m uvicorn` 启动后所有 `/api/v1/layout/*` 返回 404？

A: 这是已知的架构限制。`layout_router` 的注册在 `setup_api_routes(app)` 中，该函数在 `start_web_server()` 内调用，而 uvicorn 直接导入时不会执行此函数。必须使用 `unilab` CLI 启动：
```bash
unilab -g lab_with_arm.json --backend ros --port 8002 --ak <AK> --sk <SK>
```

### Q: `/status` 页面显示什么信息？

A: `http://<host>:8002/status` 是 Uni-Lab-OS 的系统状态页，显示：
- 所有已注册的 ROS2 设备节点（名称、类型、状态）
- 每个设备支持的 ROS2 action（如 `pick_and_place`）
- 已订阅的 ROS2 topic
- 可以用来确认 `arm_slider` 设备是否在线，从而判断 MoveIt2 是否可用

### Q: mesh_manifest.json 中的位姿坐标怎么提取？

A: 从 xacro 文件中的关节链累计计算。每个 `<joint>` 的 `<origin xyz="..." rpy="..."/>` 定义了子链接相对于父链接的变换，需要沿关节链从 `base_link` 逐级累加：
```
绝对位置 = parent_pos + parent_rotation × child_origin_xyz
```
对于有活动关节的设备（如机械臂），使用 home 位姿（关节值全为 0 或 xacro 中的 default 值）计算。

---

## 17. 集成过程踩坑记录

记录集成过程中遇到的关键问题及其解决方案，供后续维护参考。

### 17.1 路由注册 404 问题

**现象**: 部署到 Ubuntu 后，`curl http://localhost:8002/api/v1/layout/health` 返回 404。

**根因**: 使用 `uvicorn unilabos.app.web.server:app` 直接启动。`server.py` 中 `app = FastAPI()` 创建了空应用，`setup_api_routes(app)` 在 `start_web_server()` 中调用但 uvicorn 不执行该函数。

**修复**: 改用 `unilab -g lab_with_arm.json --backend ros --port 8002 --ak <AK> --sk <SK>`。

### 17.2 mesh_manifest 路径层级错误

**现象**: `/api/v1/layout/mesh_manifest` 返回 404（文件找不到），但路由本身已注册。

**根因**: `patch_layout_routes.py` 中 `mesh_manifest.json` 的相对路径只用了 2 级 `..`，实际需要 3 级（从 `routers/layout.py` 到 `services/layout_optimizer/demo/`）。

**修复**: 将路径改为 `Path(__file__).resolve().parent.parent.parent / "services" / "layout_optimizer" / "demo" / "mesh_manifest.json"`。

### 17.3 MoveIt2 未激活（始终 mock 模式）

**现象**: 设置了 `LAYOUT_CHECKER_MODE=moveit` 但 `checker_status` 仍返回 mock。

**根因**: 环境变量在 shell 中设置后未传递给 `unilab` 进程。

**修复**: 将环境变量放在命令前面（同行）：
```bash
LAYOUT_CHECKER_MODE=moveit unilab -g lab_with_arm.json --backend ros ...
```

### 17.4 STL 坐标系不匹配

**现象**: 3D 模型加载成功但朝向错误（设备躺倒或翻转）。

**根因**: STL 和 xacro 使用 URDF 坐标系（Z 朝上），Three.js 使用 Y 朝上坐标系。

**修复**: 在前端加载 STL 后统一旋转整组 -90° 绕 X 轴：
```javascript
stlGroup.rotation.x = -Math.PI / 2; // URDF Z-up → Three.js Y-up
```

---

*本文档由项目集成过程中的完整对话记录整理生成，涵盖从架构设计、代码实现、Bug 修复到最终验证的全流程。v1.1 新增：3D 真实模型渲染、STL 加载架构、mesh 路由、踩坑记录。*
