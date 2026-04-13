# MoveIt2 能力集成到 Uni-Lab 3D 的完整架构图

> 本文档说明如何将 `moveit2.py`、`moveit_interface.py`、`resource_mesh_manager.py` 中**已有的** MoveIt2 能力，通过 API 层桥接到 Uni-Lab 3D 前端。
>
> 核心原则：不重写任何算法，只建"桥梁层"。

---

## 1. 全局架构总览

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                        Uni-Lab 3D 前端 (浏览器)                          ║
║                                                                          ║
║  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────────┐   ║
║  │ urdf-scene  │ │layout-editor │ │ trajectory-  │ │ reachability-  │   ║
║  │   .js       │ │   .js        │ │ player.js    │ │ overlay.js     │   ║
║  │             │ │              │ │              │ │ (阶段三新增)    │   ║
║  │ Three.js    │ │ 拖拽+OBB     │ │ 轨迹回放     │ │ 可达域可视化   │   ║
║  │ URDF渲染    │ │ 碰撞高亮     │ │ 播放/暂停    │ │ FK/IK 标记点   │   ║
║  └──────┬──────┘ └──────┬───────┘ └──────┬───────┘ └───────┬────────┘   ║
║         │               │                │                  │            ║
║    fetch /urdf    POST /layout    Foxglove WS         POST /fk /ik      ║
╚═════════╪═══════════════╪════════════════╪══════════════════╪════════════╝
          │               │                │                  │
──────────┼───────────────┼────────────────┼──────────────────┼────────────
          │               │                │                  │
╔═════════╪═══════════════╪════════════════╪══════════════════╪════════════╗
║         ▼               ▼                ▼                  ▼            ║
║  ┌─────────────────────────────────────────────────────────────────┐     ║
║  │                    FastAPI Web API 层（桥梁）                    │     ║
║  │                                                                 │     ║
║  │  GET  /api/v1/urdf              ← A1                            │     ║
║  │  GET  /api/v1/lab/layout        ← A2                            │     ║
║  │  POST /api/v1/lab/layout        ← B1 碰撞场景                   │     ║
║  │  POST /api/v1/lab/plan-preview  ← C1 运动规划                   │     ║
║  │  POST /api/v1/lab/execute       ← C2 运动执行                   │     ║
║  │  POST /api/v1/lab/fk            ← D1 正运动学                   │     ║
║  │  POST /api/v1/lab/ik            ← D2 逆运动学                   │     ║
║  │  POST /api/v1/lab/layout/save   ← A3                            │     ║
║  │  POST /api/v1/lab/layout/load   ← A4                            │     ║
║  │  POST /api/v1/job/add           ← C3 (已有)                     │     ║
║  └────────────┬────────────────────────────┬───────────────────────┘     ║
║               │                            │                             ║
║       ┌───────▼────────┐          ┌────────▼───────────┐                 ║
║       │ visualization  │          │   layout_service   │                 ║
║       │ _state.py      │          │       .py          │                 ║
║       │ (全局实例托管)  │          │ (坐标转换/碰撞封装) │                 ║
║       └───────┬────────┘          └────────┬───────────┘                 ║
║               │                            │                             ║
╚═══════════════╪════════════════════════════╪═════════════════════════════╝
                │                            │
────────────────┼────────────────────────────┼─────────────────────────────
                │                            │
╔═══════════════╪════════════════════════════╪═════════════════════════════╗
║               ▼                            ▼                             ║
║  ┌──────────────────────────────────────────────────────────────────┐    ║
║  │              已有 MoveIt2 后端能力（不需要改动）                   │    ║
║  │                                                                   │    ║
║  │  ┌─────────────────────────────────────────────────────────┐      │    ║
║  │  │  resource_visalization.py                                │      │    ║
║  │  │  • URDF/SRDF 动态拼装                                   │      │    ║
║  │  │  • 启动 robot_state_publisher / move_group / rviz2       │      │    ║
║  │  │  • get_web_urdf() ← 新增方法                             │      │    ║
║  │  │  • update_device_pose() ← 新增方法                       │      │    ║
║  │  └─────────────────────────────────────────────────────────┘      │    ║
║  │                                                                   │    ║
║  │  ┌─────────────────────────────────────────────────────────┐      │    ║
║  │  │  resource_mesh_manager.py                                │      │    ║
║  │  │  • add_resource_collision_meshes() — 启动时批量注册       │      │    ║
║  │  │  • move_collision()  — 移动碰撞体位置                    │      │    ║
║  │  │  • tf_update()       — attach/detach 到 PlanningScene    │      │    ║
║  │  │  • add/remove_collision_object()                         │      │    ║
║  │  │  • allow_collisions() — 碰撞白名单                       │      │    ║
║  │  │  • /get_planning_scene  /apply_planning_scene            │      │    ║
║  │  └─────────────────────────────────────────────────────────┘      │    ║
║  │                                                                   │    ║
║  │  ┌─────────────────────────────────────────────────────────┐      │    ║
║  │  │  moveit_interface.py                                     │      │    ║
║  │  │  • pick_and_place()  — 完整抓放工作流                    │      │    ║
║  │  │  • set_position()    — 笛卡尔位姿控制                    │      │    ║
║  │  │  • set_status()      — 预定义关节配置切换                │      │    ║
║  │  │  • resource_manager() — 触发 tf_update                   │      │    ║
║  │  │  • moveit_task() / moveit_joint_task()                   │      │    ║
║  │  └─────────────────────────────────────────────────────────┘      │    ║
║  │                                                                   │    ║
║  │  ┌─────────────────────────────────────────────────────────┐      │    ║
║  │  │  moveit2.py (2443 行底层封装)                            │      │    ║
║  │  │                                                          │      │    ║
║  │  │  碰撞场景 ─────────────────────────────────────          │      │    ║
║  │  │  • add_collision_box/sphere/cylinder/cone/mesh()         │      │    ║
║  │  │  • move_collision() / remove_collision_object()          │      │    ║
║  │  │  • attach_collision_object() / detach_collision_object() │      │    ║
║  │  │  • allow_collisions() / clear_all_collision_objects()    │      │    ║
║  │  │  • update_planning_scene()                               │      │    ║
║  │  │                                                          │      │    ║
║  │  │  运动规划 ─────────────────────────────────────          │      │    ║
║  │  │  • move_to_pose() / move_to_configuration()              │      │    ║
║  │  │  • plan() / plan_async() / execute()                     │      │    ║
║  │  │  • wait_until_executed() / cancel_execution()            │      │    ║
║  │  │                                                          │      │    ║
║  │  │  运动学 ───────────────────────────────────────          │      │    ║
║  │  │  • compute_fk() / compute_fk_async()                     │      │    ║
║  │  │  • compute_ik() / compute_ik_async()                     │      │    ║
║  │  │                                                          │      │    ║
║  │  │  约束与安全 ───────────────────────────────────          │      │    ║
║  │  │  • set_position_goal / set_orientation_goal              │      │    ║
║  │  │  • set_joint_goal / set_pose_goal                        │      │    ║
║  │  │  • set_path_joint/position/orientation_constraint        │      │    ║
║  │  │  • MoveIt2State 状态机 (IDLE/REQUESTING/EXECUTING)       │      │    ║
║  │  │  • ignore_new_calls_while_executing                      │      │    ║
║  │  └─────────────────────────────────────────────────────────┘      │    ║
║  └───────────────────────────────────────────────────────────────────┘    ║
║                                                                          ║
║  ┌───────────────────────────────────────────────────────────────────┐    ║
║  │  MoveIt2 ROS 2 节点（由 resource_visalization.py 启动）            │    ║
║  │  • move_group          — 规划核心 + FCL 碰撞引擎                  │    ║
║  │  • ros2_control_node   — 关节控制器                               │    ║
║  │  • robot_state_publisher — /tf + /robot_description               │    ║
║  │  • joint_state_broadcaster — /joint_states                        │    ║
║  └───────────────────────────────────────────────────────────────────┘    ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## 2. 四大能力域的详细数据流

### 域 A：碰撞场景（阶段一核心）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 用户在前端拖拽设备到新位置                                            │
└─────────────────────────┬────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 前端 layout-editor.js                                                │
│                                                                      │
│ mousedown → Raycast 命中设备 mesh                                    │
│ mousemove → 投影到地面平面, 实时移动 mesh                             │
│           → Box3 OBB 粗碰撞 (60fps, 纯前端)                          │
│           → 碰撞时红色高亮 (不调后端)                                  │
│ mouseup   → 发送最终位置到后端                                        │
└─────────────────────────┬────────────────────────────────────────────┘
                          │
            POST /api/v1/lab/layout
            { device_id, pose: {x_mm, y_mm, z_mm, rz_rad} }
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│ FastAPI: layout_service.py                                           │
│                                                                      │
│ 1. 坐标转换: mm → m                                                  │
│ 2. 调用 ResourceVisualization.update_device_pose(id, pose)           │
│ 3. 调用 ResourceMeshManager.move_collision(id, new_position, quat)   │
│ 4. 调用 _get_planning_scene_service → 获取当前所有碰撞体             │
│ 5. 遍历碰撞体 AABB, 检测重叠对                                       │
│ 6. 返回 { collision, colliding_pairs }                               │
└─────────────────────────┬────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 前端收到响应                                                          │
│                                                                      │
│ collision == true  → 碰撞设备标红, 显示冲突列表                       │
│ collision == false → 清除高亮, 布局确认                               │
└──────────────────────────────────────────────────────────────────────┘
```

### 域 B：运动规划与执行（阶段二核心）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 两条触发路径（前端可选）                                              │
│                                                                      │
│ 路径①: 执行工作流（规划+立刻执行）                                    │
│   POST /api/v1/job/add { device_id, action:"pick_and_place", ... }   │
│                                                                      │
│ 路径②: 仅预览轨迹（规划但不执行）                                     │
│   POST /api/v1/lab/plan-preview { device_id, target_pose, ... }      │
└────────────┬──────────────────────────────────┬──────────────────────┘
             │                                  │
             ▼                                  ▼
┌────────────────────────────┐   ┌─────────────────────────────────────┐
│ 路径① 已有链路               │   │ 路径② 新增 API                      │
│                              │   │                                     │
│ HostNode.send_goal()         │   │ moveit2.set_pose_goal(target)       │
│   → MoveitInterface          │   │ trajectory = moveit2.plan()         │
│     .pick_and_place()        │   │ return { joint_names, points }      │
│       → MoveIt2              │   │                                     │
│         .move_to_pose()      │   │ (不调 execute, 只返回轨迹数据)       │
│       → resource_manager()   │   │                                     │
│         (attach/detach)      │   └──────────────┬──────────────────────┘
│                              │                   │
│ move_group 规划过程中自动     │                   │
│ 发布到 ROS Topic:            │                   │
│                              │                   │
│ /move_group/                 │         JSON response
│   display_planned_path       │         { joint_names, points[] }
│                              │                   │
└──────────┬───────────────────┘                   │
           │                                       │
           ▼                                       ▼
┌──────────────────────────┐          ┌────────────────────────────────┐
│ Foxglove Bridge          │          │ 前端 trajectory-player.js      │
│ ws://localhost:8765       │          │                                │
│                          │          │ loadFromRawPoints(names, pts)  │
│ 自动转发 DisplayTrajectory│          │ 或 loadTrajectory(msg)         │
└──────────┬───────────────┘          └────────────┬───────────────────┘
           │                                       │
           ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│ trajectory-player.js 播放引擎                                        │
│                                                                      │
│ 1. 解析路点: joint_names + points[].positions + time_from_start      │
│ 2. requestAnimationFrame 循环                                        │
│ 3. _findSegment(elapsed) → 找到当前两路点间                           │
│ 4. _applyInterpolated(index, alpha) → 线性插值关节角                  │
│ 5. updateJointState({ name, position }) → URDF 关节动画              │
│ 6. UI: 播放/暂停 + 0.25x/0.5x/1x/2x 速度 + 时长显示                 │
└──────────────────────────────────────────────────────────────────────┘
```

### 域 C：运动学能力（阶段二增强/阶段三核心）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 正运动学 (FK): "当前关节角 → 末端在哪"                                │
│                                                                      │
│ 前端: 用户想知道机械臂末端当前位置                                     │
│   POST /api/v1/lab/fk { device_id, joint_positions: [j1,j2,...] }    │
│     → layout_service 调用 moveit2.compute_fk(joint_positions)        │
│     → 返回 { position: [x,y,z], quaternion: [x,y,z,w] }            │
│   前端: 在 3D 场景中画一个球/标记显示末端位置                          │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ 逆运动学 (IK): "目标点 → 机械臂能不能到"                             │
│                                                                      │
│ 前端: 用户在 3D 场景中点击一个目标位置                                 │
│   POST /api/v1/lab/ik { device_id, position, quaternion }            │
│     → layout_service 调用 moveit2.compute_ik(position, quat_xyzw)   │
│     → 成功: { reachable:true, joint_positions:[...] }                │
│     → 失败: { reachable:false }                                      │
│   前端: 目标点显示绿色(可达) / 红色(不可达)                            │
│                                                                      │
│ 阶段三扩展: AI 排布迭代时批量调 IK 判断交接点可达性                    │
│   → 优化: 预计算可达性体素图, O(1) 查表替代实时 IK                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 域 D：约束与安全控制（贯穿所有阶段）

```
┌──────────────────────────────────────────────────────────────────────┐
│ 约束体系 (不直接暴露给前端, 作为规划参数内嵌)                         │
│                                                                      │
│                     前端请求                                          │
│   POST /api/v1/lab/plan-preview {                                    │
│     device_id: "arm_slider_1",                                       │
│     target_pose: {...},                                               │
│     constraints: [                              ← 可选参数             │
│       { type:"joint", joint:"joint_3",                                │
│         position:0.5, tolerance:0.3 },                                │
│       { type:"orientation", tolerance:[0.1,0.1,0.1] }                │
│     ]                                                                 │
│   }                                                                   │
│                         │                                             │
│                         ▼                                             │
│   layout_service.py:                                                  │
│     for c in constraints:                                             │
│       if c.type == "joint":                                           │
│         moveit2.set_path_joint_constraint(...)                        │
│       elif c.type == "position":                                      │
│         moveit2.set_path_position_constraint(...)                     │
│       elif c.type == "orientation":                                   │
│         moveit2.set_path_orientation_constraint(...)                  │
│     trajectory = moveit2.plan()                                       │
│                                                                      │
│ 约束的作用:                                                           │
│   • 关节约束: 限制肘关节范围, 避免"奇怪姿态"                          │
│   • 位置约束: 限制末端移动范围 (如不能低于桌面)                        │
│   • 姿态约束: 保持杯子水平 (搬运液体时)                               │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ 安全控制 (后端自动生效, 前端无需干预)                                 │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ MoveIt2State 状态机                                        │      │
│  │                                                            │      │
│  │   IDLE ──send_goal──▶ REQUESTING ──accepted──▶ EXECUTING   │      │
│  │    ▲                                              │        │      │
│  │    └──────────── done/cancelled ◀─────────────────┘        │      │
│  │                                                            │      │
│  │ ignore_new_calls_while_executing = True                    │      │
│  │   → 执行中的新规划请求被静默丢弃, 防止运动冲突              │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ Allowed Collision Matrix (ACM)                             │      │
│  │                                                            │      │
│  │ allow_collisions("beaker_1", True)                         │      │
│  │   → 抓取前: 允许夹爪与烧杯碰撞 (否则无法抓取)              │      │
│  │                                                            │      │
│  │ allow_collisions("beaker_1", False)                        │      │
│  │   → 抓取后: 恢复碰撞检测, 搬运过程中自动避障               │      │
│  │                                                            │      │
│  │ 已在 MoveitInterface.pick_and_place() 中自动处理            │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ 规划重试机制                                               │      │
│  │                                                            │      │
│  │ moveit_task() 内部: 最多 retry+1 次规划尝试                │      │
│  │ pick_and_place() 内部: 任一步失败即中止并返回 False         │      │
│  │ 异常时自动重置 cartesian_flag, 防止残留影响后续操作         │      │
│  └────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 按阶段的接入路线图

```
时间轴 ──────────────────────────────────────────────────────────▶

阶段一                    阶段二                    阶段三
(静态布局)                (动态联动)                (AI排布)

  碰撞场景                  运动规划                  运动学
  ┌────────┐                ┌────────┐                ┌────────┐
  │ 后端   │                │ 后端   │                │ 后端   │
  │        │                │        │                │        │
  │ move_  │                │ plan() │                │compute │
  │ colli- │                │execute │                │_fk()   │
  │ sion() │                │pick_   │                │compute │
  │ get_   │                │and_    │                │_ik()   │
  │ plan-  │                │place() │                │        │
  │ ning_  │                │        │                │        │
  │ scene  │                │        │                │        │
  └───┬────┘                └───┬────┘                └───┬────┘
      │                        │                          │
      ▼                        ▼                          ▼
  ┌────────┐                ┌────────┐                ┌────────┐
  │ API    │                │ API    │                │ API    │
  │        │                │        │                │        │
  │ POST   │                │ POST   │                │ POST   │
  │/layout │                │/job/add│                │/fk /ik │
  │        │                │/plan-  │                │        │
  │        │                │preview │                │        │
  └───┬────┘                └───┬────┘                └───┬────┘
      │                        │                          │
      ▼                        ▼                          ▼
  ┌────────┐                ┌────────┐                ┌────────┐
  │ 前端   │                │ 前端   │                │ 前端   │
  │        │                │        │                │        │
  │layout- │                │traject-│                │reacha- │
  │editor  │                │ory-    │                │bility- │
  │.js     │                │player  │                │overlay │
  │        │                │.js     │                │.js     │
  │OBB碰撞 │                │轨迹回放 │                │可达域   │
  │红色高亮 │                │播放控制 │                │着色     │
  └────────┘                └────────┘                └────────┘

  需要新建:                  需要新建:                  需要新建:
  • /api/v1/lab/layout      • /api/v1/lab/plan-preview • /api/v1/lab/fk
  • layout-editor.js        • ros-bridge 消息派发补全   • /api/v1/lab/ik
  • layout_service.py       • (job/add 已有)            • reachability-overlay.js
  • visualization_state.py

  已有可复用:                已有可复用:                已有可复用:
  • move_collision()        • MoveitInterface 全部      • moveit2.compute_fk()
  • get_planning_scene      • trajectory-player.js      • moveit2.compute_ik()
  • add_collision_mesh()    • MoveIt2.plan()/execute()
  • ResourceMeshManager     • Foxglove Bridge
```

---

## 4. 新增文件与修改文件一览

```
新增文件 (共 ~8 个)
─────────────────────────────────────────────────────────

unilabos/app/web/utils/
  ├── visualization_state.py     ← 全局实例托管
  └── layout_service.py          ← 碰撞检查/坐标转换/FK/IK 封装

unilabos/app/web/static/lab3d/
  ├── index.html                 ← /lab3d 页面
  ├── main.js                    ← 前端入口
  ├── urdf-scene.js              ← 从 lab3d-phase2 复制并增强
  ├── layout-editor.js           ← 拖拽 + OBB + 后端提交
  └── layout-api.js              ← API 调用封装

unilabos/app/web/templates/
  └── lab3d.html                 ← Jinja2 模板

修改文件 (共 ~5 个)
─────────────────────────────────────────────────────────

unilabos/device_mesh/resource_visalization.py
  + get_web_urdf()
  + update_device_pose()

unilabos/app/main.py
  + set_resource_visualization() 调用

unilabos/app/web/api.py
  + GET  /api/v1/urdf
  + GET  /api/v1/lab/layout
  + POST /api/v1/lab/layout
  + POST /api/v1/lab/layout/save
  + POST /api/v1/lab/layout/load
  + POST /api/v1/lab/plan-preview    (阶段二)
  + POST /api/v1/lab/fk              (阶段二/三)
  + POST /api/v1/lab/ik              (阶段二/三)

unilabos/app/web/server.py
  + app.mount("/meshes", ...)

unilabos/app/web/pages.py
  + @router.get("/lab3d")
```

---

## 5. API 到后端方法的映射速查表

| API 端点 | 阶段 | 调用的后端方法 | 返回给前端 |
|----------|------|---------------|-----------|
| `GET /api/v1/urdf` | 一 | `ResourceVisualization.get_web_urdf()` | URDF XML 文本 |
| `POST /api/v1/lab/layout` | 一 | `move_collision()` + `_get_planning_scene` | 碰撞结果 |
| `POST /api/v1/lab/layout/save` | 一 | 写 JSON 文件 | 文件路径 |
| `POST /api/v1/lab/layout/load` | 一 | 读 JSON → 重建场景 | 完整布局 |
| `POST /api/v1/job/add` | 二 | `HostNode.send_goal()` → `MoveitInterface` | 任务状态 |
| `POST /api/v1/lab/plan-preview` | 二 | `moveit2.plan()` (不执行) | 轨迹路点 |
| `POST /api/v1/lab/fk` | 二/三 | `moveit2.compute_fk()` | 末端位姿 |
| `POST /api/v1/lab/ik` | 二/三 | `moveit2.compute_ik()` | 可达性+关节角 |
