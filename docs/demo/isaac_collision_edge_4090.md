# 4090：HOR Horizon Web Workflow → Isaac PhysX → RViz 碰撞联调

## 环境

- Edge：`/home/ubuntu/miniforge3/envs/unilab`
- Isaac：`/home/ubuntu/miniforge3/envs/matterix`
- Worktree：`/home/ubuntu/lab4090/projects/isaac-collision-edge-report`
- Isaac Gateway：`ws://127.0.0.1:9003/edge-sim/v1`
- RViz marker：`/unilabos/sim/collision_markers`

## 1. 准备 HOR 模型

原始 SolidWorks 导出包不提交仓库。首次在机器上执行：

```bash
cd /home/ubuntu/lab4090/projects/isaac-collision-edge-report

conda run --no-capture-output -n unilab env PYTHONPATH=. \
  python scripts/prepare_hor_horizon_fixture.py \
    --source /home/ubuntu/lab4090/assets/hor_horizon_v2_1_source \
    --output unilabos/device_mesh/devices/hor_horizon_v2_1
```

该脚本会：

- 规范化 xacro。
- 将 visual/collision mesh 分离。
- 为 collision mesh 生成 convex hull。
- 建立本地 ament package index，供 RViz 解析 `package://`。

## 2. 启动 Isaac Bridge

```bash
cd /home/ubuntu/lab4090/projects/isaac-collision-edge-report

conda run --no-capture-output -n matterix env PYTHONPATH=. \
  python scripts/isaac_sim_bridge.py \
    --host 127.0.0.1 \
    --port 9003 \
    --path /edge-sim/v1 \
    --headless \
    --contact-publish-hz 20
```

等待日志出现：

```text
[bridge] listening ws://127.0.0.1:9003/edge-sim/v1
```

## 3. 配置凭证

在仓库外创建权限为 `600` 的私有 config：

```python
class BasicConfig:
    ak = "<LAB_AK>"
    sk = "<LAB_SK>"

class WSConfig:
    reconnect_interval = 5
    max_reconnect_attempts = 999
    ws_ping_interval = 5
    ws_ping_timeout = 8
```

禁止提交该文件。

## 4. 启动 Edge + RViz

在 4090 图形桌面为 `:0` 时：

```bash
cd /home/ubuntu/lab4090/projects/isaac-collision-edge-report

env DISPLAY=:0 \
  XAUTHORITY=/run/user/1000/gdm/Xauthority \
  https_proxy= http_proxy= all_proxy= \
  HTTPS_PROXY= HTTP_PROXY= ALL_PROXY= \
  conda run --no-capture-output -n unilab env PYTHONPATH=. \
  unilab \
    -g unilabos/test/experiments/hor_horizon_collision_sim.json \
    --config /path/to/private_config.py \
    --backend ros \
    --mode sim \
    --sim_engine isaac \
    --visual rviz \
    --sim_gateway \
    --sim_gateway_endpoint ws://127.0.0.1:9003/edge-sim/v1 \
    --collision_reporting \
    --collision_cloud_reporting \
    --app_bridges websocket fastapi \
    --skip_env_check \
    --disable_browser \
    --disable_query_api \
    --upload_registry \
    --addr test
```

成功标志：

- `websocket connected`
- `report_action_lock sent`
- `Host node initialized`
- `IsaacSimGateway 已发送整场景 scene.urdf`
- RViz 无 mesh load error

## 5. Web workflow

在 test Web 实验室中新建单节点 workflow：

- Device：`virtual_hor_horizon`
- Action：`run_collision_demo`
- `case_id`：
  - `safe_path`：无 fixture
  - `arm_hits_box`：注入确定性 PhysX collision fixture

运行 `arm_hits_box` 后预期：

1. device lock 成功。
2. Edge 收到 `job_start`。
3. HOR 关节运动。
4. PhysX 产生 `CONTACT_FOUND/PERSIST/LOST`。
5. RViz 将碰撞 link 红色高亮并显示接触点。
6. JSONL 写入 workflow task/job/node 上下文。
7. Edge 发送 `push_collision_event`。
8. workflow 返回 success。

## 6. 自动 GPU Smoke

```bash
conda run --no-capture-output -n unilab env PYTHONPATH=. \
  python scripts/smoke_hor_horizon_collision.py \
    --endpoint ws://127.0.0.1:9003/edge-sim/v1
```

预期最终输出：

```json
{"result": "passed"}
```

## 7. 已知边界

- RViz 是显示层；碰撞事实来自 Isaac PhysX。
- 目前 Go 后端尚不消费 `push_collision_event`，因此 Web 页面不会显示碰撞。
- HOR 原始 STL 的公开分发许可尚未确认，不应上传公开仓库。
- `run_collision_demo` 是测试动作，不代表真实 HOR 硬件通信协议。
