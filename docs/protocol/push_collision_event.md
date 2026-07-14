# `push_collision_event` Edge → Schedule 协议

## 方向

Uni-Lab-OS Edge → `/api/v1/ws/schedule`

## Envelope

```json
{
  "action": "push_collision_event",
  "data": {
    "schema_version": "1.0",
    "event_id": "col_xxx_0",
    "event_phase": "begin",
    "timestamp_ms": 1783940774000,
    "sim_time_s": 12.34,
    "severity": "warning",
    "classification": "unexpected",
    "sim_engine": "isaac",
    "session_id": "sim_sess_xxx",
    "pairs": [
      {
        "asset_a": "full_dev",
        "asset_b": "hor_workflow_collision_fixture",
        "link_a": "virtual_hor_horizon_arm3_Link",
        "link_b": "fixture_link",
        "prim_a": "/full_dev/virtual_hor_horizon_arm3_Link",
        "prim_b": "/full_dev/hor_workflow_collision_fixture/fixture_link"
      }
    ],
    "contact": {
      "point_count": 8,
      "max_impulse": 123.4,
      "relative_velocity": null,
      "points": [{"x": 0.1, "y": 0.2, "z": 0.3}]
    },
    "workflow_context": {
      "task_id": "task-uuid",
      "job_id": "job-uuid",
      "node_id": "workflow-node-uuid",
      "device_id": "virtual_hor_horizon",
      "action": "run_collision_demo",
      "notebook_id": ""
    },
    "extra": {}
  }
}
```

## 字段约束

- `event_phase`: `begin | update | end`
- `severity`: `info | warning | critical`
- `classification`: `expected | unexpected | self_collision | environment | unknown`
- 同一接触生命周期的 `event_id` 保持稳定。
- `pairs` 内 asset 顺序已经归一化。
- PhysX 无法提供的数值使用 `null`，不能伪造为 `0`。
- 无法唯一关联 workflow 时，`workflow_context` 字段使用空字符串。

## 当前后端状态

截至 2026-07-13，Edge 已能发送该 action，但 `uni-lab-backend` 尚未注册处理器。完整 Web 展示需后端增加 `PushCollisionEvent`，并仿 `push_joint_state` 广播到 `material-modify`。
