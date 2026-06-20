# Ubuntu 172.20.0.39 Phase 10/11/13 与 Phase 2 交接指南

日期：2026-06-05
主机：`ubuntu@172.20.0.39`

本文把当前 `LeapLab/Uni-Lab-OS` checkout、4090 Ubuntu 主机、Phase 10/11/13 query/sim 资产线，以及 Phase 2 Isaac Bridge 线集中成一份交接和使用指南。它不是新的实现计划；执行时优先以本文命令和现有 runbook 为准。

## 快速结论

- Phase 10：按 `10_phase1a_unified_sim_core` 计划落地 unified sim core，包括 `RuntimeContext`、`SimClock`、sim/twin mode、device pair/stub/twin bridge、physics backend contract。
- Phase 11：按 `phase10_11_13_status.md` 中的 OS-sim communication link 落地 CLI/runtime flags、自动 `/clock` 与 sim control services、edge runtime wiring；当前 `LeapLab` 又补齐了 query ROS2/gRPC service wiring。
- Phase 13：按 `13_phase3_robo_unilabos_query_api` overlay 落地 query/HAL/asset information layer，包括 `QueryEngine`、LabUtopia source、resource map、robot asset、Robo-UniLabOS CLI/client、HAL adapters、QueryService 与远程 transport。
- Phase 2：以 Isaac physics contract、Isaac HTTP worker、edge `--physics isaac`、physics live query、真实 PNG render 验收为核心，负责 Route A Isaac bridge。
- 2026-06-05 12:58 CST 已用 SSH 复核：`unilab`、`matterix`、Phase 2 `/tmp` 副本、Phase 13 目录、generated 目录、LabUtopia `lab_001.usd` 都存在。当前 `50052` 和 `8002` 在监听，`8092` 未监听，因此只看到 edge/query 端口不代表完整 Isaac 链路健康。

## 远端环境地图

### 固定入口

```bash
ssh ubuntu@172.20.0.39
```

关键路径：

```text
/home/ubuntu/miniforge3/envs/unilab
/home/ubuntu/miniforge3/envs/matterix
/tmp/Uni-Lab-OS-phase2-c3c5
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/Uni-Lab-OS
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated
/home/ubuntu/labsim/LabUtopia_repro
/home/ubuntu/labsim/LabUtopia_repro/assets/chemistry_lab/lab_001/lab_001.usd
```

环境分工：

- `unilab`：普通 Python、Uni-Lab-OS edge、pytest、query smoke。
- `matterix`：Isaac Sim / LabUtopia headless worker 和 Isaac-only smoke。
- `/tmp/Uni-Lab-OS-phase2-c3c5`：Phase 2 干净测试副本。
- `/home/ubuntu/lab4090/projects/robo-unilabos-phase13/Uni-Lab-OS`：Phase 13 历史/资产线 checkout。
- `/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated`：LabUtopia asset cards、task reports、asset packs 等生成物。

不要覆盖 `~/canonical/Uni-Lab-OS` 或其他可能 dirty 的长期 checkout。做新验收时优先同步到 `/tmp/Uni-Lab-OS-handoff` 或复用 `/tmp/Uni-Lab-OS-phase2-c3c5`。

### 常用端口

```text
8092   Phase 2 推荐 Isaac worker HTTP endpoint
8091   4090 上可能被旧 Isaac demo 占用，不作为默认
50052  Phase 2 C5 query gRPC
8002   Uni-Lab-OS FastAPI
19090  Phase 13 Feetech leader tunnel endpoint
```

检查端口：

```bash
ssh ubuntu@172.20.0.39 'ss -ltnp "( sport = :8092 or sport = :50052 or sport = :8002 or sport = :19090 )"'
```

## 本地同步到 4090

从本地 `LeapLab/Uni-Lab-OS` checkout 执行：

```bash
rsync -az --delete --exclude .git --exclude .pytest_cache ./ \
  ubuntu@172.20.0.39:/tmp/Uni-Lab-OS-handoff/
```

远端快速确认：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run -n unilab python --version
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. python -m pytest tests/sim/test_cli_runtime.py -q
'
```

## Phase 10/11/13 交接范围

### Plan 来源与当前对齐方式

历史 plan/status 入口：

```text
/Users/newtides/Robo-UniLabOS/10_phase1a_unified_sim_core/Uni-Lab-OS
/Users/newtides/Robo-UniLabOS/13_phase3_robo_unilabos_query_api/README.md
/Users/newtides/Robo-UniLabOS/13_phase3_robo_unilabos_query_api/Uni-Lab-OS/docs/phase10_11_13_status.md
/Users/newtides/Robo-UniLabOS/13_phase3_robo_unilabos_query_api/Uni-Lab-OS/docs/robo_unilabos_agent_handoff_2026-05-25.md
```

当前 `LeapLab/Uni-Lab-OS` 已经不是单纯的历史 overlay：它在 Phase 10/11/13 基础上继续合入了 Phase 2 Isaac bridge 和网络 query transport。因此本文采用这个判断口径：

- 历史 plan/status 用来解释“为什么要做”和“当时的完成标准”。
- 当前 `LeapLab` 代码用来解释“现在实际能用什么”和“应该怎么验收”。
- 旧文档中仍标为未完成但当前已有代码和测试的项，按当前代码更新状态；例如 ROS2/gRPC query service 在当前仓库已存在。

### Plan 到功能矩阵

| Phase | 计划目标 | 当前已落地功能 | 主要使用入口 | 仍需保留的边界 |
|---|---|---|---|---|
| 10 | 统一 real/sim/twin runtime core | `RuntimeContext`、`SimClock`、sim pause/rate、device stub、`TwinBridge`、physics contract、fake backend | `unilab --mode sim|twin`、`configure_runtime()`、`tests/sim/` | 不证明真实机器人动力学或真实执行安全 |
| 11 | OS-sim communication link | CLI runtime flags、自动 `/clock`、sim control services、twin poller、edge smoke；当前还接入 ROS2 `/unilabos/query` 与 gRPC query server | `scripts/smoke_sim_edge.py`、`_start_runtime_sim_nodes()`、`_start_query_services()` | 不等同 Cloud/VirtualLab scene sync |
| 13 | Robot-facing query/HAL/API | 六类 query API、LabUtopia source、resource map、robot asset/URDF source、action schemas、HAL registry、Mock/UR/Feetech adapters、local/remote SDK、Robo-UniLabOS CLI、asset pack | `python -m unilabos.robo_unilabos.cli ...`、`unilabos_client.RoboUniLabOS*`、`tests/queries/` | Feetech 仍主要是 read-only；不声明 follower actuation/teleop 已验证 |

### Phase 10：unified sim core

当前仓库入口：

```text
unilabos/app/main.py
unilabos/app/backend.py
unilabos/sim/context.py
unilabos/sim/runtime.py
unilabos/sim/clock.py
unilabos/sim/clock_control.py
unilabos/sim/clock_publisher.py
unilabos/sim/stub_device.py
unilabos/sim/twin_bridge.py
unilabos/sim/twin_runtime.py
unilabos/sim/physics_backend.py
unilabos/sim/backends/fake_physics.py
unilabos/sim/device_physics.py
unilabos/ros/initialize_device.py
scripts/smoke_sim_edge.py
tests/sim/
```

从 plan 已开发出来的能力：

- `RuntimeContext` 统一记录 `real`、`sim`、`twin` 运行模式，以及 clock、physics、query 相关配置。
- `SimClock` 支持加速、pause/resume；real/twin 模式保持实际时间倍率约束。
- `SimClockPublisher` 与 `SimClockControlNode` 可在 ROS runtime 中自动发布 `/clock` 并提供 sim rate/pause/resume 控制。
- `NullDeviceStub`、`TwinBridge`、`TwinDriverPair` 支持缺失 sim 设备 stub 和 real-to-virtual 单向同步。
- `PhysicsBackend` contract 已从早期 `step/get_observation/...` 扩展到 Phase 2 所需的 `load_scene()` 与 `render()`。
- `FakePhysicsBackend` 用于本地 deterministic physics wiring、虚拟设备 dispatch 和 CLI/runtime 测试。
- `initialize_device_from_dict()` 会按 mode-aware hooks 创建真实/虚拟/twin 设备组合。

使用方式：

```bash
unilab --graph <graph.json> \
  --config <config.py> \
  --backend ros \
  --mode sim \
  --sim_rate 10 \
  --physics fake \
  --app_bridges fastapi \
  --visual disable \
  --skip_env_check
```

能力边界：

- 这部分证明“edge 进程知道自己处于 sim/twin，且设备和 clock 能按 mode 接线”。
- `--physics fake` 只证明协议与 wiring，不代表 Isaac/真实物理。
- `TwinBridge` 是单向状态同步，不负责反向控制真实设备。

推荐验收：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python -m pytest \
      tests/sim/test_cli_runtime.py \
      tests/sim/test_runtime_configuration.py \
      tests/sim/test_clock_publisher_and_control.py \
      tests/sim/test_stub_and_twin.py \
      tests/sim/test_twin_runtime.py \
      tests/sim/test_backend_physics_configuration.py \
      tests/sim/test_device_physics.py \
      tests/sim/test_virtual_device_clock.py \
      tests/sim/test_physics_backend.py \
      tests/sim/backends/test_fake_physics.py \
      -q
'
```

### Phase 11：OS-sim communication link

当前仓库入口：

```text
unilabos/app/main.py
unilabos/ros/main_slave_run.py
unilabos/sim/runtime.py
unilabos/sim/clock_control.py
unilabos/sim/clock_publisher.py
unilabos/api/query_service.py
unilabos/api/ros2_query_service.py
unilabos/api/grpc_query_service.py
unilabos_client/remote.py
scripts/smoke_sim_edge.py
tests/integration/test_twin_poller_ros2.py
tests/integration/test_query_service_ros2.py
tests/integration/test_query_service_grpc.py
```

从 plan 已开发出来的能力：

- CLI/runtime flags：`--mode`、`--sim_rate`、`--sim_paused`、`--disable_sim_services`。
- Edge 启动时自动调用 runtime 配置入口，并在 sim/twin 模式启动 `/clock` 与 sim control services。
- Sim control services 同时兼容 legacy `/sim/*` 和 namespaced `/unilab/sim/*`。
- Twin 模式启动 `TwinPollerNode`，周期驱动 `TwinDriverPair.bridge.poll_once()`。
- 当前 `LeapLab` 已补齐信息层 transport：ROS2 `/unilabos/query` 和 gRPC query server 共享同一个 `QueryService/QueryEngine`。
- `RoboUniLabOSRemote` 可通过 `ros2_transport()`、`grpc_transport()` 或 `local_transport()` 调同一套 query API。

使用方式：

```bash
unilab --graph <graph.json> \
  --config <config.py> \
  --backend ros \
  --mode sim \
  --sim_rate 10 \
  --query_grpc_port 50052 \
  --app_bridges fastapi \
  --visual disable
```

运行后可用：

```python
from unilabos_client import RoboUniLabOSRemote, grpc_transport

client = RoboUniLabOSRemote(grpc_transport("127.0.0.1:50052"))
client.query_state("ur5")
```

能力边界：

- 这部分证明 OS edge 与 sim runtime、query transport 能通信，不代表 Cloud frontend/backend 已同步场景。
- gRPC/ROS2 query transport 是信息查询层，不执行 robot motion。
- 如果 gRPC 依赖缺失或端口占用，edge 会跳过 gRPC server；ROS2 query service 仍可独立存在。

推荐验收：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python -m pytest \
      tests/sim/test_twin_runtime.py \
      tests/integration/test_twin_poller_ros2.py \
      tests/integration/test_query_service_ros2.py \
      tests/integration/test_query_service_grpc.py \
      -q
'
```

如果环境有完整 ROS2/rclpy，也可以跑真实 smoke：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run --no-capture-output -n unilab env PYTHONPATH=. \
    python scripts/smoke_sim_edge.py
'
```

### Phase 13：query/HAL/asset information layer

当前仓库入口：

```text
unilabos/api/
unilabos/queries/
unilabos/queries/labutopia/
unilabos/action_schemas/
unilabos/hal/
unilabos/queries/resource_map_source.py
unilabos/queries/robot_asset.py
unilabos/queries/urdf_robot_model.py
unilabos/robo_unilabos/
unilabos_client/local.py
robot_assets/roboarm_chem_04/
scripts/demo_labutopia_query.py
tests/queries/
tests/robo_unilabos/
```

从 plan 已开发出来的能力：

- Query API core：`query_pose`、`query_state`、`query_affordance`、`query_action_schema`、`query_safety_zones`、`query_verification`。
- Query sources：resource map、LabUtopia asset cards、LabUtopia task YAML、direct USD prim reads、ROS live source、physics live source、URDF robot model source。
- Action schemas：内置 `weigh`、`press_button`、`open_lid`、`move_to`、`pour`，并支持 action catalog source。
- HAL：`RobotHAL`、`MockHAL`、UR RTDE adapter skeleton、Feetech/RDK read-only roboarm adapter。
- Service/SDK：`unilabos.api.QueryService`、ROS2/gRPC query service、`unilabos_client.RoboUniLabOS`、`RoboUniLabOSRemote`。
- Robo-UniLabOS CLI：`lab`、`query`、`labutopia`、`assets` command families，所有命令返回 machine-readable JSON。
- LabUtopia：scene-aware task config source、direct USD source、asset card generator、task readiness report、contract-level action smoke、Isaac headless smoke。
- Real-arm asset：`robot_assets/roboarm_chem_04/` 包含 source URDF、query URDF、STL meshes、frame metadata、workspace metadata 和 Feetech ticks 到 URDF logical joints 的 rough mapping。
- Asset pack：可从 LabUtopia cards、task report、robot assets、real asset cards、startup configs 等生成 canonical resource map/action catalog/manifest。

4090 资产入口：

```text
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_asset_cards_after_phase13_fixes_isaac
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_task_report_after_phase13_fixes_isaac.json
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_asset_cards_after_sim_expansion_isaac
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_task_report_after_sim_expansion_isaac_headless.json
/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/robo_unilabos_canonical_asset_pack_v2
/home/ubuntu/labsim/LabUtopia_repro/config
```

推荐验收：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python -m pytest tests/queries tests/robo_unilabos -q
'
```

LabUtopia in-process query demo：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python scripts/demo_labutopia_query.py \
      --asset_cards /home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_asset_cards_after_phase13_fixes_isaac \
      --labutopia_config /home/ubuntu/labsim/LabUtopia_repro/config
'
```

Robo-UniLabOS CLI 示例：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python -m unilabos.robo_unilabos.cli \
      --labutopia-config /home/ubuntu/labsim/LabUtopia_repro/config \
      --indent 2 \
      query action-schema press_button
'
```

生成 LabUtopia readiness report：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  timeout 240 /home/ubuntu/miniforge3/bin/conda run -n matterix env PYTHONPATH=. \
    python -m unilabos.queries.labutopia.task_report \
      --config-dir /home/ubuntu/labsim/LabUtopia_repro/config \
      --labutopia-root /home/ubuntu/labsim/LabUtopia_repro \
      --isaac-headless \
      --isaac-steps 1 \
      --output /home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_task_report_handoff.json \
      --indent 2
'
```

生成 LabUtopia asset cards：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-handoff
  timeout 240 /home/ubuntu/miniforge3/bin/conda run -n matterix env PYTHONPATH=. \
    python -m unilabos.queries.labutopia.asset_card_generator \
      --config-dir /home/ubuntu/labsim/LabUtopia_repro/config \
      --labutopia-root /home/ubuntu/labsim/LabUtopia_repro \
      --output-dir /home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_asset_cards_handoff \
      --isaac-headless \
      --isaac-steps 1 \
      --clean
'
```

检查关键 summary：

```bash
ssh ubuntu@172.20.0.39 'python3 - << "PY"
import json
from pathlib import Path

report = Path("/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_task_report_handoff.json")
if report.exists():
    data = json.loads(report.read_text())
    print(json.dumps(data.get("summary", {}), ensure_ascii=False, indent=2))

cards = Path("/home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated/labutopia_asset_cards_handoff")
summary = cards / "summary.json"
if summary.exists():
    data = json.loads(summary.read_text())
    print("card_count", data.get("card_count"), "runtime", data.get("runtime"))
    nav = json.loads((cards / "navigation__lab_3.json").read_text())
    print(nav.get("candidate_tasks"), nav.get("affordances"), nav.get("operation_hints", {}).get("action_primitives"))
PY'
```

Phase 13 边界：

- `robot_assets/roboarm_chem_04` 是 kinematic/query asset，不是高保真动力学模型。
- Feetech/RDK 相关历史验证主要是 read-only state query，不能据此宣称 torque enable、follower actuation、teleop 或 gripper command 已完成。
- `tool0`、joint signs、zero offsets、gripper semantics 和 workspace bounds 仍是早期验证假设，不是测量标定结论。
- LabUtopia `action_smoke` 是 contract plan，不执行真实 robot motion 或 physics contact。
- 普通 `unilab` 环境如果没有 `pxr`，LabUtopia report 会更多依赖 `position_range` fallback；不能把它当作 USD/Isaac 真值报告。
- 不要混用 `after_sim_expansion` 和 `after_phase13_fixes` 两套 generated 产物给出同一个验收结论。

## Phase 2 Isaac Bridge 交接范围

### C1/C2：physics contract 与 bridge

当前仓库入口：

```text
unilabos/sim/physics_backend.py
unilabos/sim/context.py
unilabos/sim/runtime.py
unilabos/sim/backends/fake_physics.py
unilabos/sim/backends/isaac_bridge.py
unilabos/sim/backends/isaac/protocol.py
tests/sim/backends/test_isaac_bridge.py
tests/sim/backends/test_isaac_protocol.py
```

功能：

- `PhysicsBackend` 支持 `load_scene()` 和 `render()`。
- `FakePhysicsBackend` 用于本地 wiring tests。
- `IsaacBridgeBackend` 把 edge 侧 physics 调用转为 worker HTTP `/rpc`。

### C3：Isaac worker

当前仓库入口：

```text
unilabos/sim/backends/isaac/worker.py
unilabos/sim/backends/isaac/worker_http.py
scripts/smoke_isaac_worker.py
tests/sim/backends/test_isaac_worker_*.py
```

启动 worker：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-phase2-c3c5
  nohup /home/ubuntu/miniforge3/bin/conda run -n matterix env PYTHONPATH=. \
    python -m unilabos.sim.backends.isaac.worker \
      --host 127.0.0.1 \
      --port 8092 \
      --headless \
      --scene /home/ubuntu/labsim/LabUtopia_repro/assets/chemistry_lab/lab_001/lab_001.usd \
      --camera /World/Camera \
      --rpc-timeout-s 600 \
    > /tmp/isaac_worker_phase2_c3c5_8092.log 2>&1 &
  echo $! > /tmp/isaac_worker_phase2_c3c5_8092.pid
'
```

检查 worker：

```bash
ssh ubuntu@172.20.0.39 '
  sleep 70
  ss -ltnp "( sport = :8092 )"
  curl -sS http://127.0.0.1:8092/health
  tail -n 80 /tmp/isaac_worker_phase2_c3c5_8092.log
'
```

单 worker smoke：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-phase2-c3c5
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python scripts/smoke_isaac_worker.py \
      --endpoint http://127.0.0.1:8092 \
      --scene /home/ubuntu/labsim/LabUtopia_repro/assets/chemistry_lab/lab_001/lab_001.usd \
      --entity /World \
      --camera /World/Camera \
      --timeout-s 300 \
      --out /tmp/labutopia-worker.png
  file /tmp/labutopia-worker.png
  ls -lh /tmp/labutopia-worker.png
'
```

### C4：edge 接入 physics

当前仓库入口：

```text
unilabos/app/main.py
unilabos/app/backend.py
unilabos/sim/backends/factory.py
unilabos/hal/adapters/ur_adapter.py
unilabos/devices/virtual/virtual_multiway_valve.py
```

关键 CLI：

```text
--mode sim
--physics none|fake|isaac
--physics_endpoint http://127.0.0.1:8092
--physics_scene /home/ubuntu/labsim/LabUtopia_repro/assets/chemistry_lab/lab_001/lab_001.usd
--physics_timeout 300
```

启动 edge：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-phase2-c3c5
  nohup /home/ubuntu/miniforge3/bin/conda run --no-capture-output -n unilab env PYTHONPATH=. \
    unilab --graph unilabos/test/experiments/mock_devices/mock_all.json \
      --config unilabos/config/example_config.py \
      --backend ros \
      --mode sim \
      --sim_rate 10 \
      --physics isaac \
      --physics_endpoint http://127.0.0.1:8092 \
      --physics_scene /home/ubuntu/labsim/LabUtopia_repro/assets/chemistry_lab/lab_001/lab_001.usd \
      --physics_timeout 300 \
      --query_labutopia_usd /home/ubuntu/labsim/LabUtopia_repro/assets/chemistry_lab/lab_001/lab_001.usd \
      --query_grpc_port 50052 \
      --app_bridges fastapi \
      --visual disable \
      --skip_env_check \
      --disable_browser \
      --test_mode \
      --port 8002 \
    > /tmp/unilab_edge_c5_50052.log 2>&1 &
  echo $! > /tmp/unilab_edge_c5_50052.pid
'
```

本地 graph + `--app_bridges fastapi` + 非 websocket 可以离线启动，不需要 `UNILAB_AK/UNILAB_SK`。启用 websocket 或远程资源时仍要配置云端凭证。

### C5：query + render 端到端验收

当前仓库入口：

```text
unilabos/queries/physics_live_source.py
unilabos/ros/main_slave_run.py
scripts/smoke_sim_isaac_edge.py
docs/demo/phase2_isaac_e2e_4090.md
docs/demo/phase2_isaac_project_summary.md
```

运行 E2E smoke：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-phase2-c3c5
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python scripts/smoke_sim_isaac_edge.py \
      --grpc 127.0.0.1:50052 \
      --physics-endpoint http://127.0.0.1:8092 \
      --state-target /World \
      --pose-target /World \
      --camera /World/Camera \
      --physics-timeout-s 300 \
      --poll-timeout-s 60 \
      --out /tmp/labutopia-c5-e2e.png
  file /tmp/labutopia-c5-e2e.png
  ls -lh /tmp/labutopia-c5-e2e.png
'
```

期望证据：

- `state.source` 是 `physics_live:isaac`。
- `pose.source` 是 `physics_live:isaac`。
- `/tmp/labutopia-c5-e2e.png` 是完整 PNG，通常为 `640 x 480, 8-bit/color RGBA`。
- worker log 无 Python traceback。

## 回归命令

Phase 2 已知目标切片：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-phase2-c3c5
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python -m pytest \
      tests/sim/backends/test_isaac_worker_protocol.py \
      tests/sim/backends/test_isaac_worker_http.py \
      tests/sim/backends/test_isaac_worker_cli.py \
      tests/sim/backends/test_isaac_worker_smoke_script.py \
      tests/sim/backends/test_factory.py \
      tests/sim/test_cli_runtime.py \
      tests/sim/test_runtime_configuration.py \
      tests/sim/test_backend_physics_configuration.py \
      tests/sim/test_device_physics.py \
      tests/sim/test_virtual_device_clock.py \
      tests/queries/test_ur_adapter.py \
      tests/queries/test_physics_live_source.py \
      tests/integration/test_smoke_sim_isaac_edge_script.py \
      tests/integration/test_edge_query_wiring.py \
      -q
'
```

更宽的 sim/query/integration 回归：

```bash
ssh ubuntu@172.20.0.39 '
  cd /tmp/Uni-Lab-OS-phase2-c3c5
  /home/ubuntu/miniforge3/bin/conda run -n unilab env PYTHONPATH=. \
    python -m pytest tests/sim tests/queries tests/robo_unilabos tests/integration -q
'
```

## 停止和清理

不要用过宽的 `pkill -f "unilabos.sim.backends.isaac.worker"`，它可能匹配到自己的 SSH shell。优先精确查 PID：

```bash
ssh ubuntu@172.20.0.39 '
  pgrep -af "[u]nilabos.sim.backends.isaac.worker.*8092" || true
  pgrep -af "[u]nilab .*--query_grpc_port 50052" || true
'
```

按 pid file 停止：

```bash
ssh ubuntu@172.20.0.39 '
  test -f /tmp/unilab_edge_c5_50052.pid && kill $(cat /tmp/unilab_edge_c5_50052.pid) || true
  test -f /tmp/isaac_worker_phase2_c3c5_8092.pid && kill $(cat /tmp/isaac_worker_phase2_c3c5_8092.pid) || true
'
```

## 常见问题

### 只看到 `50052` 和 `8002`，但 smoke 失败

这通常说明 edge/query 在跑，但 Isaac worker 没有在 `8092` 监听。先跑：

```bash
ssh ubuntu@172.20.0.39 'ss -ltnp "( sport = :8092 )"; curl -sS http://127.0.0.1:8092/health'
```

如果 `8092` 不通，先启动 C3 worker，再跑 C5 smoke。

### `8091` 有东西在跑

不要直接复用 `8091`。Phase 2 C5 默认使用 `8092`，因为 `8091` 曾被其他 Isaac demo 占用。

### Edge 已启动但 worker 后启动

如果 edge 启动时 `--physics isaac` 会立即 `load_scene()`，worker 不在时可能导致启动失败或后续 physics query 不健康。稳妥顺序是先 worker、再 edge、最后 smoke。

### LabUtopia 生成物结论不一致

先确认使用的是哪套目录：

```bash
ssh ubuntu@172.20.0.39 'ls -1 /home/ubuntu/lab4090/projects/robo-unilabos-phase13/generated'
```

同一次验收只使用一套 asset cards 和 task report，例如全部使用 `after_phase13_fixes_isaac`。

### Feetech/RDK 机械臂无法从 4090 直连

历史记录显示 4090 不能直接路由到 `192.168.1.x` 机械臂网络，需要从 Mac 建反向 tunnel：

```bash
ssh -fN -M -S /tmp/robo_unilabos_4090_tunnel.sock \
  -o ExitOnForwardFailure=yes \
  -R 127.0.0.1:19022:192.168.1.112:22 \
  -R 127.0.0.1:19122:192.168.1.110:22 \
  -R 127.0.0.1:19090:192.168.1.112:8090 \
  ubuntu@172.20.0.39
```

边界仍然是 read-only state query，不要把 tunnel 验证解释成真实执行闭环。

## 关联文档

- `docs/demo/phase2_isaac_project_summary.md`
- `docs/demo/phase2_isaac_e2e_4090.md`
- `docs/superpowers/plans/2026-06-02-phase2-isaac-c1-c2.md`
- `docs/superpowers/plans/2026-06-02-phase2-isaac-c3-worker.md`
- `docs/superpowers/plans/2026-06-02-phase2-isaac-c4-edge-integration.md`
- `docs/superpowers/plans/2026-06-02-phase2-isaac-c5-e2e-render.md`
- `docs/developer_guide/robo_unilabos_deferred_assets_handoff.md`
- `robot_assets/roboarm_chem_04/README.md`
