# Isaac Collision 4090 Test Report

Date: 2026-07-13
Branch base: `deepmodeling/Uni-Lab-OS:lab_2_isacc_sim@a82b386a`
Development branch: `feat/isaac-collision-edge-report`

## Environment

- Ubuntu 22.04 / Linux 5.15
- NVIDIA RTX 4090 24 GB
- Driver 580.159.03
- Isaac Sim 5.1 runtime (`matterix`)
- ROS2 Humble / Python 3.11 (`unilab`)

## Automated tests

- Original targeted baseline: 20 passed
- Collision/WS/RViz targeted suite: 35 passed
- Action-lock targeted suite: 9 passed
- Gateway/package-resolution regression: 7 passed

## HOR model preparation

- 10 links
- 9 joints
- 7 movable joints
- 20 mesh references resolved
- `base_link`: 273,003 visual faces → 392 convex collision faces
- `box_Link`: 460,916 visual faces → 158 convex collision faces
- Generated xacro expansion: 11,676 bytes

## GPU smoke

Validated:

- Isaac Gateway connection
- World creation
- HOR URDF import
- Contact API enabled on 11 rigid prims
- PhysX contact points
- PhysX max impulse
- Prim → asset/link mapping
- Collision event normalization
- begin/update/end lifecycle
- Raw contact throttling

Deterministic overlapping fixture produced normalized `unexpected` events containing HOR link names.

## RViz

Validated:

- HOR model loaded with zero RViz mesh errors after stale ROS publishers were removed.
- MarkerArray topic received red MESH_RESOURCE markers.
- Marker frame matched the colliding HOR link.
- Marker used `frame_locked=true`.
- Contact point sphere markers were published.
- end event generated marker DELETE.

## Web workflow

Validated using the test environment:

- Registry upload succeeded.
- Schedule WebSocket connected.
- `virtual_hor_horizon.run_collision_demo` appeared in Web.
- Initial run exposed missing action-lock compatibility.
- Added `report_action_lock` full snapshot and direct `job_start` registration.
- Web workflow `case_id=arm_hits_box` completed successfully.
- Edge emitted terminal `job_status=success`.
- Collision events contained task/job/device/action context.
- Edge queued `push_collision_event` messages for Schedule WebSocket.

Example contextual result:

```text
classification = unexpected
device_id      = virtual_hor_horizon
action         = run_collision_demo
link           = virtual_hor_horizon_arm*_Link
fixture        = hor_workflow_collision_fixture
```

## Remaining external work

`uni-lab-backend` does not yet consume `push_collision_event`. The event is sent by Edge but is not persisted or broadcast to Uni-Lab-Cloud. Backend and frontend implementation are separate follow-up work.
