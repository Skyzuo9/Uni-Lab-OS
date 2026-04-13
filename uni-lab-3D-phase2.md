5. 实现方法（阶段二）
5.1 Uni-Lab OS → ROS 数据流 [待开发]
- 已有基础：BaseROS2DeviceNode 的 PropertyPublisher 已在持续发布设备状态（如 arm_pose）到 ROS Topic [已有]；ROS2 消息体系（unilabos_msgs/，~80个 .action 文件、Resource.msg 含 geometry_msgs/Pose）已覆盖全部实验室操作语义 [已有]
- 新建 JointStateAdapterNode：订阅各设备的 PropertyPublisher Topic（如 /devices/elite_arm_1/arm_pose），解析为标准 sensor_msgs/JointState 发布到 /joint_states，供 robot_state_publisher 消费驱动 /tf 更新
- 完整数据链路：Uni-Lab OS POST /api/job/add → HostNode 发送 ROS2 Action Goal → 设备执行 → PropertyPublisher → JointStateAdapterNode → /joint_states → robot_state_publisher → /tf → ROSBridge2 → 前端动画 [HostNode + FastAPI 工作流调度已有，含 /api/job/add、/api/ws/device_status 等接口]
5.2 性能优化 [待开发]
- 新建 ThrottlerNode：将 /joint_states（~100Hz）降频到 25Hz、/tf（~100Hz）降频到 20Hz 后转发为 throttled topic，保护前端浏览器性能
- 前端订阅 /joint_states_throttled 和 /tf_throttled 而非原始 topic
5.3 耗材附着与释放 [待开发]
- 基于阶段一已建好的 PlanningScene 碰撞环境，实现 Attached Collision Object 完整流程
- 以96孔板为例：初始作为 CollisionObject 在工作台上 → 机械臂抓取时从场景移除并附着到末端执行器 → 跟随机械臂移动并参与全局避障 → 释放后重新注册为 CollisionObject 在新位置
- 通过扩展 PlanningSceneManager 实现 attach/detach 操作，MoveIt2 规划自动考虑附着物体积
- 如果不用支持本地rviz则云端moveit2就够，目前已有初步实现
5.4 轨迹预览与状态指示 [待开发]
- 前端订阅 /move_group/display_planned_path（moveit_msgs/DisplayTrajectory），按轨迹点的时间戳逐帧回放规划动画，工作流执行前可预览路径
- 前端订阅 /api/ws/device_status（FastAPI WebSocket），用颜色/图标实时反映设备运行状态（空闲/执行中/异常）
- 目标帧率 ≥ 20fps，工作流下发到前端动画延迟 < 150ms