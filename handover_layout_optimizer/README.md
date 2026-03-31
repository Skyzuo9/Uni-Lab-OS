# Layout Optimizer — 实验室设备自动布局系统

AI 驱动的实验室设备自动布局优化模块。给定设备列表 + 约束条件，使用差分进化算法计算最优摆放位置。支持 MoveIt2 碰撞检测和 IK 可达性验证。

## 快速开始（本地复现）

### 环境要求

- Python ≥ 3.10
- 操作系统：macOS / Linux / Windows

### 1. 安装

```bash
# 克隆或复制本项目
cd handover_layout_optimizer

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装包（开发模式 + 测试依赖）
pip install -e ".[dev]"
```

### 2. 启动开发服务器

```bash
uvicorn layout_optimizer.server:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 打开浏览器

- 3D Demo：http://localhost:8000/lab3d
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 4. 运行测试

```bash
# 运行所有测试（不含 LLM 测试）
pytest layout_optimizer/tests/ -v -k "not llm"

# 运行全部测试（需要 ANTHROPIC_API_KEY）
ANTHROPIC_API_KEY=sk-... pytest layout_optimizer/tests/ -v
```

---

## 项目结构

```
handover_layout_optimizer/
├── pyproject.toml                 # 包定义 + 依赖声明
├── README.md                      # ← 你正在看的文件
├── PROJECT_HANDOVER.md            # 详细对接文档（架构、API、算法、部署）
├── INTEGRATION_PLAN.md            # Uni-Lab-OS 集成方案（5 Phase）
├── UBUNTU_SETUP_GUIDE.md          # Ubuntu 生产环境部署手册
├── lab_with_arm.json              # MoveIt2 模式实验室配置示例
├── patch_layout_routes.py         # Uni-Lab-OS 集成补丁脚本
│
└── layout_optimizer/              # Python 包（pip install -e . 后可导入）
    ├── __init__.py                # 包入口
    │
    │  ── 核心模块 ──
    ├── models.py                  # 数据模型: Device, Lab, Placement, Constraint, Intent
    ├── optimizer.py               # 差分进化优化器 (scipy DE, 3N 维搜索空间)
    ├── constraints.py             # 约束评估引擎 (硬约束 + 软约束 + graduated penalty)
    ├── seeders.py                 # 力导向种子布局生成 (4 种预设)
    ├── obb.py                     # OBB 几何: 角点、SAT 重叠、穿透深度、边距
    ├── intent_interpreter.py      # 语义意图 → 约束翻译 (10 种 handler)
    ├── device_catalog.py          # 双源设备目录 (footprints + registry)
    ├── lab_parser.py              # 实验室配置解析
    ├── footprints.json            # 499 个设备的离线尺寸库
    │
    │  ── 检测器 ──
    ├── interfaces.py              # Protocol 接口定义
    ├── mock_checkers.py           # Mock 模式: OBB 碰撞 + 欧氏距离可达性
    ├── ros_checkers.py            # MoveIt2 模式: FCL 碰撞 + IK 可达性
    ├── pencil_integration.py      # 初始布局回退 stub
    │
    │  ── API 服务 ──
    ├── server.py                  # FastAPI 开发服务器 (端口 8000)
    ├── extract_footprints.py      # 离线工具: 从 STL/GLB 提取设备尺寸
    │
    │  ── 前端 ──
    ├── static/
    │   └── lab3d.html             # 原始 3D 前端 (Three.js)
    ├── demo/
    │   ├── lab3d_integrated.html  # Uni-Lab-OS 集成版前端 (支持 STL 模型加载)
    │   ├── mesh_manifest.json     # 6 设备的 STL 零件清单
    │   └── layout_demo.html       # 2D 简化版
    │
    │  ── LLM ──
    ├── llm_skill/
    │   └── layout_intent_translator.md  # LLM System Prompt 模板
    │
    │  ── 测试 ──
    └── tests/
        ├── __init__.py
        ├── fixtures/              # 测试数据
        │   ├── sample_devices.json
        │   └── sample_lab.json
        ├── test_optimizer.py      # DE 优化器测试
        ├── test_constraints.py    # 约束评估测试
        ├── test_intent_interpreter.py  # 意图翻译测试
        ├── test_seeders.py        # 种子布局测试
        ├── test_obb.py            # OBB 几何测试
        ├── test_mock_checkers.py  # Mock 检测器测试
        ├── test_ros_checkers.py   # MoveIt2 检测器测试
        ├── test_device_catalog.py # 设备目录测试
        ├── test_interpret_api.py  # /interpret API 测试
        ├── test_llm_skill.py      # LLM 技能测试 (需 API Key)
        ├── test_bugfixes_v2.py    # 回归测试
        └── test_e2e_pcr_pipeline.py  # 端到端 PCR 工作流测试
```

---

## 端到端演示 (curl)

```bash
# 1. 意图解析: 自然语言 → 结构化约束
curl -X POST http://localhost:8000/interpret \
  -H "Content-Type: application/json" \
  -d '{
    "intents": [
      {"intent": "close_together", "params": {"devices": ["hplc_station", "slide_w140"], "priority": "high"}},
      {"intent": "reachable_by", "params": {"arm": "arm_slider", "targets": ["hplc_station", "slide_w140"]}}
    ]
  }' | python3 -m json.tool

# 2. 布局优化: 约束 → 最优坐标
curl -X POST http://localhost:8000/optimize \
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
      {"type": "soft", "rule_name": "minimize_distance", "params": {"device_a": "hplc_station", "device_b": "slide_w140"}, "weight": 8.0},
      {"type": "hard", "rule_name": "reachability", "params": {"arm_id": "arm_slider", "target_device_id": "hplc_station"}},
      {"type": "hard", "rule_name": "reachability", "params": {"arm_id": "arm_slider", "target_device_id": "slide_w140"}}
    ],
    "seeder": "compact_outward",
    "run_de": true,
    "maxiter": 200
  }' | python3 -m json.tool
```

---

## Uni-Lab-OS 集成部署

在 Ubuntu 生产环境中将本模块集成到 Uni-Lab-OS（含 ROS2/MoveIt2）的完整指南，请参考：

- **集成方案**: [INTEGRATION_PLAN.md](INTEGRATION_PLAN.md)
- **部署手册**: [UBUNTU_SETUP_GUIDE.md](UBUNTU_SETUP_GUIDE.md)
- **对接文档**: [PROJECT_HANDOVER.md](PROJECT_HANDOVER.md)（最详细，含架构图、API 文档、踩坑记录）

### 快速集成步骤

```bash
# 在 Ubuntu 上
cd /home/ubuntu/workspace/Uni-Lab-OS

# 1. 复制核心模块
cp -r <本项目>/layout_optimizer/ unilabos/services/layout_optimizer/

# 2. 注入 API 路由（向 api.py 注册 layout_router）
# 参见 INTEGRATION_PLAN.md Phase 1

# 3. 运行补丁脚本（添加 3D 模型路由）
python3 <本项目>/patch_layout_routes.py

# 4. 启动（MoveIt2 模式）
LAYOUT_CHECKER_MODE=moveit unilab \
  -g lab_with_arm.json \
  --backend ros \
  --port 8002 \
  --ak <AK> --sk <SK>

# 5. 验证
curl http://localhost:8002/api/v1/layout/checker_status
# → {"mode": "moveit", "collision_checker": "MoveItCollisionChecker", ...}
```

---

## 核心依赖

| 包 | 版本 | 用途 |
|----|------|------|
| scipy | ≥ 1.10 | 差分进化优化器 |
| numpy | ≥ 1.24 | 数值计算 |
| fastapi | ≥ 0.100 | Web API |
| uvicorn | ≥ 0.20 | ASGI 服务器 |
| pydantic | ≥ 2.0 | 请求/响应模型 |
| pytest | ≥ 7.0 | 测试（可选） |
| httpx | ≥ 0.24 | API 测试客户端（可选） |
| python-fcl | ≥ 0.7 | 精确碰撞检测（可选，MoveIt2 模式） |

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LAYOUT_CHECKER_MODE` | `mock` | `mock` / `moveit` — 检测器模式 |
| `UNI_LAB_ASSETS_DIR` | `../uni-lab-assets` | uni-lab-assets 资产目录 |
| `UNI_LAB_OS_DEVICE_MESH_DIR` | `../Uni-Lab-OS/.../devices` | 设备网格目录 |
| `LAYOUT_VOXEL_DIR` | `./voxel_maps/` | 预计算体素图目录 |
| `ANTHROPIC_API_KEY` | (无) | LLM 技能测试用 |

---

## 详细文档

- **[PROJECT_HANDOVER.md](PROJECT_HANDOVER.md)** — 完整对接文档（1700+ 行），包含：
  - 系统架构图、数据流图
  - 全部 11 个 API 端点详细文档
  - 数据模型（Device, Constraint, Intent 等）
  - 10 种约束规则 + 10 种意图类型
  - DE 优化算法原理
  - Mock ↔ MoveIt2 双模式对比
  - 3D 模型渲染架构
  - 部署速查、扩展指南、FAQ、踩坑记录
