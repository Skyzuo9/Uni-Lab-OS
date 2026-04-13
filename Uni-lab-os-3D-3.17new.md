# # Uni-Lab云端3D实验室搭建与运行演示

## 1. 背景与目标

自动化实验室规模化建设和工作流编排过程中，涉及大量对多设备精准空间布局、机械臂动态路径预留以及复杂作业流直观验证的需求。

Uni-Lab 云端 3D 实验室搭建与可视化运行方案用于实现：

* **设备尺寸自动化获取与AI智能排布**：确保仪器规格与实验室空间精准匹配，通过 AI 辅助设计实现建设方案的快速迭代与低成本试错。

* **全流程动作仿真与物理碰撞预检**：提供直观的设备运行可视化方法，在实机操作前排除工作流中的逻辑错误与空间冲突。

* **直观 3D 方案展示与开源生态构建**：以直观的视觉效果增强客户信任并促成合作；同时通过降低技术门槛，鼓励用户参与建设，打造开源自动化实验室生态。

## 2. 时间节点

a为主要目标优先完成，b为进阶目标。阶段二、三在时间上可并行。

* **阶段一：支持云端手动搭建静态3D实验室**

  * 对已有建模文件的设备跑通云端3D可视化搭建流程（3D/Rviz实现）

  * 对尚无建模文件、但Uni-Lab OS已经/计划支持的设备添加3D建模

* **阶段二：对Uni-Lab OS下发的工作流实现3D模拟同步**

  * 初步跑通流程：Uni-Lab OS -> ROS交互 (Topic/Action) -> ROSBridge (WebSocket) -> 前端

  * 针对中间态计算和展示速度、通讯协议等进行优化（MoveIt2 的时间参数化算法可以实现速度的展示）

* **阶段三：AI自动实现实验室布局排布**

  * 根据所选设备和实验室已有布局（尺寸、电源、排气等）进行ai自动排布

  * 对接deploy master的设备筛选功能，根据用户选择场景/实验自动推荐设备列表

## 3. 交付形式

集成在Uni-Lab OS云端，在目前2D实验室构建和工作流模拟的基础上实现3D可视化+AI自动编排升级。具体操作流程：

* 根据用户选定的使用场景或具体实验筛选出相关仪器

* 对选中仪器拉取精确尺寸3D模型，进行手动或AI自动排布

  * 受实验室已有布局约束

  * 支持添加硬规则指导排布

* 对Uni-Lab OS工作流实现3D模拟动态同步

## 4. 实现方法（阶段一）

### 4.1 实验室场景配置 [待开发]

* 提供简单开始选项：仅定义矩形地面（长×宽）即可开始放置设备

* 支持用户定义实验室平面图（尺寸、电源/排气等固定设施位置、可用/不可用区域）

* 场景配置保存为 JSON 布局文件，供后端 ResourceVisualization 和前端渲染共同使用

### 4.2 设备资产准备 [待开发]

资产按 Matterix 框架分为三类基类，影响 URDF 结构和碰撞注册方式：

* ArticulationCfg（关节型）：有可动关节（revolute/prismatic），Xacro 含非 fixed joint，运动过程中的碰撞检测由 MoveIt2 实时规划处理。阶段二作为工作流 Action 执行体

* StaticObjectCfg（静态物体）：固定仪器/家具，仅 fixed joint，作为 PlanningScene 碰撞障碍物

* RigidObjectCfg（刚体可抓取）：耗材/板/管等，阶段二需支持 Attached Collision Object（抓取/释放跟随）

* 统一模型零点规范：Z=0落地面，XY中心投影，+X正面朝向。不符合的通过 Xacro `<origin>` 偏移修正 [待规范化]

* Visual/Collision 模型拆分：高面数模型（≥5万顶点）需拆分，Visual 保留原模型用于前端渲染，Collision 用 Blender 生成简化凸包用于 MoveIt2 PlanningScene 碰撞检测。阶段一即需完成，供碰撞检测和阶段二运动规划复用 [待处理]

* 编写资产盘点脚本，遍历 registry 对照 device_mesh 输出缺失清单 [待开发]

* 已有3D资产 [已有]：Elite CS系列机械臂、OT-2液体处理器、SCARA臂+滑轨、Toyo XYZ龙门架、HPLC分析站、Thermo Orbitor RS2酒店、耗材（96孔板、TipRack等）

* 补充建模优先级：P0 实验台/机柜（桌面需支持设备吸附）；P1 UniLab OS 已对接但缺模型的设备 [待建模]

* 工作站组装：许多大型设备由多个子部件组成（如 Tecan Fluent = Cabinet + Grid Segments + Modules） [待开发]

  * Level 1：工作站主体（Cabinet+框架）作为整体在地面拖放

  * Level 2：甲板模块安装在主体框架的预定义槽位上，位置受父级约束

  * 在 registry 中定义工作站模板，声明子部件组合及槽位关系，由 Xacro 宏组装为完整 URDF

### 4.3 设备选择与上架 [对接已有方法]

* 用户选择场景/实验 → 从 registry 筛选出相关设备列表（对接 deploy_master） [deploy_master 即将上线]

* 选取设备后，从 device_mesh 或阿里云 OSS 拉取 Xacro+STL/DAE 资产 [OSS路径已规划，拉取逻辑待开发]

* ResourceVisualization 将新设备拼入整体 URDF，robot_state_publisher 重新发布，前端自动加载 [ResourceVisualization 已有，需扩展]

### 4.4 手动布局交互 [待开发]

* 拖拽定位 + 旋转朝向，设备自动吸附到地面或桌面/柜面

* 碰撞检测：直接使用 MoveIt2 PlanningScene + FCL 碰撞库，所有设备注册为 CollisionObject。拖拽时前端发送新位姿到后端 → 更新 PlanningScene → 返回碰撞对列表 → 前端将碰撞设备标红高亮。阶段二机械臂运动规划直接复用同一套碰撞环境

* 自动放置（后期由ai自动排版代替，可以跳过）：添加新设备时，取其 AABB 的 XY 投影作为 2D 占用域，在实验室地面网格上用 bottom-left 算法扫描第一个无重叠位置自动放入。精确碰撞验证仍由 PlanningScene 完成

* 布局变更通过 POST /api/lab/layout 提交后端，触发 URDF 重建，前端自动刷新

* 布局结果保存为配置文件（JSON），支持加载复用

### 4.5 3D预览渲染 [对接已有方法]

* 在 ResourceVisualization 的 launch 中增加 ROSBridge2 节点，ROS Topic 通过 WebSocket 暴露给浏览器 [ResourceVisualization 已有RViz2启动，ROSBridge2待集成]

* 前端技术栈：ros3djs + Three.js + ROSLIB.js，订阅 /robot_description 加载 URDF 渲染场景 [待开发]

* STL/DAE 网格文件通过 FastAPI 静态路由映射到阿里云 OSS [FastAPI已有，静态路由待加]

* 多设备通过 fixed joint 挂载到统一 world 坐标系，共享同一个 robot_state_publisher [已有布局拼接逻辑，需扩展]

* 支持 2D/3D 一键切换：3D 走 Three.js + ROS；2D 走 SVG 平面图直接从布局 JSON 渲染，断开 ROS 数据流 [待开发]

## 5. 实现方法（阶段二）

### 5.1 Uni-Lab OS → ROS 数据流 [待开发]

* 已有基础：BaseROS2DeviceNode 的 PropertyPublisher 已在持续发布设备状态（如 arm_pose）到 ROS Topic [已有]；ROS2 消息体系（unilabos_msgs/，~80个 .action 文件、Resource.msg 含 geometry_msgs/Pose）已覆盖全部实验室操作语义 [已有]

* 新建 JointStateAdapterNode：订阅各设备的 PropertyPublisher Topic（如 /devices/elite_arm_1/arm_pose），解析为标准 sensor_msgs/JointState 发布到 /joint_states，供 robot_state_publisher 消费驱动 /tf 更新

* 完整数据链路：Uni-Lab OS POST /api/job/add → HostNode 发送 ROS2 Action Goal → 设备执行 → PropertyPublisher → JointStateAdapterNode → /joint_states → robot_state_publisher → /tf → ROSBridge2 → 前端动画 [HostNode + FastAPI 工作流调度已有，含 /api/job/add、/api/ws/device_status 等接口]

### 5.2 性能优化 [待开发]

* 新建 ThrottlerNode：将 /joint_states（~100Hz）降频到 25Hz、/tf（~100Hz）降频到 20Hz 后转发为 throttled topic，保护前端浏览器性能

* 前端订阅 /joint_states_throttled 和 /tf_throttled 而非原始 topic

### 5.3 耗材附着与释放 [待开发]

* 基于阶段一已建好的 PlanningScene 碰撞环境，实现 Attached Collision Object 完整流程

* 以96孔板为例：初始作为 CollisionObject 在工作台上 → 机械臂抓取时从场景移除并附着到末端执行器 → 跟随机械臂移动并参与全局避障 → 释放后重新注册为 CollisionObject 在新位置

* 通过扩展 PlanningSceneManager 实现 attach/detach 操作，MoveIt2 规划自动考虑附着物体积

### 5.4 轨迹预览与状态指示 [待开发]

* 前端订阅 /move_group/display_planned_path（moveit_msgs/DisplayTrajectory），按轨迹点的时间戳逐帧回放规划动画，工作流执行前可预览路径

* 前端订阅 /api/ws/device_status（FastAPI WebSocket），用颜色/图标实时反映设备运行状态（空闲/执行中/异常）

* 目标帧率 ≥ 20fps，工作流下发到前端动画延迟 < 150ms

## 6. 实现方法（阶段三）

整体流程：用户选定设备列表 + 实验室场景 → 生成候选布局 → 约束验证 → 不通过则迭代修正 → 输出最终方案

### 6.1 AI 初始布局生成 [待开发]

* 将设备 2D 占用域投影 + 实验室平面图交给 Pencil AI 生成初版布局

* 约束验证层逐条检查：硬约束 pass/fail，软约束算 cost → 通过则采用

* 无解处理：逐一松弛最可能冲突的硬约束降级为软约束，标记警告提示用户人工确认

### 6.2 差分进化优化 [待开发]

* Pencil 方案不可行时，回退到差分进化求解器（scipy differential_evolution）做全局优化

* 布局编码：每个设备 3 个参数 (x, y, θ)，N 个设备编码为 3N 维向量。随机生成一批候选布局（种群），每轮迭代通过个体间差值变异生成新候选，cost 更低则替换，重复直到收敛

* cost function：硬约束违反返回 inf 直接淘汰，软约束按权重累加 penalty

* Pencil 方案作为种群种子个体注入加速收敛，其余随机初始化保证全局搜索

### 6.3 约束体系 [待开发]

* **硬约束（违反则方案无效）：**

  * `distance_less_than(A, B, d)` / `distance_greater_than(A, B, d)`：如机械臂交接点距离限制、有交叉污染风险的场景物理隔离

  * 可达性约束：设备交接点必须落在机械臂工作空间内（查离线可达性地图）

  * 免碰撞约束：复用阶段一 PlanningScene 碰撞检测

* **软约束（优化目标，影响 cost 但不淘汰方案）：**

  * `minimize_distance(A, B)` / `maximize_distance(A, B)`：如频繁传递样本的设备对越近越好，振动隔离（高精度天平远离离心机）越远越好

  * 走道预留、线缆走线空间等

### 6.4 机械臂离线可达性地图 [待开发]

* 目的：AI 排布时需要快速判断"某设备的交接点是否在机械臂工作空间内"，不能每次实时算运动学

* 预计算方法：对每个机械臂型号（如 Elite CS 系列），用离线运动学求解器（IKFast）枚举底座候选位置，对每个位置计算末端可达的 3D 空间范围，保存为体素文件（.npz）。一次性离线预计算

* 使用方式：排布迭代时 O(1) 查表判断目标坐标是否在体素有效区域内

## 7. 验收指标

* 阶段一：场景加载时间（5台设备）< 10秒；支持同时展示的最大设备数 ≥ 15台

* 阶段二：工作流下发 → 前端关节动画延迟 < 150ms；前端渲染帧率 ≥ 20fps；MoveIt2 规划时间（5台设备场景）< 500ms

* 阶段三：AI 布局单次迭代 < 5秒；可达性查表 < 1ms；输出方案硬约束满足率 100%

## 8. 实现方法（Legacy，准备删掉)

### 8.1 拉取仪器信息（尺寸、3D模型、动作模式）

* 获取3D模型所有可行性空间的并集（占用域），用于硬编码避免碰撞

* 分为三类资产基类

* （点击图片可查看完整电子表格）

### 8.2 3D可视化渲染

* 先试一下不拆分模型的效果，看看碰撞检测的时间是否在容许范围内，不在的话将模型文件拆分 Visual 与 Collision 模型，Visual文件进行展示，Collision进行碰撞检测。（目前估计如果不拆分的话，cpu会过载）

* 需要标准化 URDF/Xacro 语义定义：参考unilab现有xacro文件，提取出一个标准化的xacro文件。利用脚本实现对现有xacro文件的标准化重写。

* 对耗材引入 Attached Collision Object。举例：当机械臂抓取一块96孔板时，这块板必须从工作台的碰撞环境中剥离，并“附着”到机械臂的末端执行器上，随着机械臂一起移动并参与全局的防碰撞计算。完成后再执行释放。

### 8.3 工作流过程中同步到3D动态

* ros里面避免碰撞的算法已经包括了其他仪器么还是只有本仪器？只有本仪器的话可能还是要上Isaac?

* ROS 的 MoveIt 规划框架原生支持全局环境碰撞检测。只要将其他仪器作为 CollisionObject 注册到 MoveIt 的 PlanningScene 中，底层的 FCL会自动计算机械臂与所有环境仪器之间的避障路径。

#### 8.3.1 UnilabOS -> ROS

#### 8.3.2 Ros -> 渲染

### 8.4 AI自动排布

需注意：要添加两个高级约束：

1. 生化环境约束：细化如防交叉污染流向（PCR实验室的试剂准备区、标本制备区需要物理隔离排序）、震动隔离（高精度天平 `mettler_toledo_xpr` 不能与大型离心机靠得太近）等实际生化实验室独有的规则。（对应增加硬编码规则）

2. 运动学可达性空间约束：两个设备（如自动移液工作站与离心机）如果需要依靠复合机器人（AGV+Arm）或滑轨机械臂传递样本，AI排布时必须确保两个设备的交接点（Transfer Port）都落在机械臂的运动学工作空间内。

* 可以写一个 ROS 脚本，利用离线运动学求解器（如 IKFast）对每个基座位置提前生成一个 3D 体素化的“可达性空间图”（Reachability Map）。AI 在进行 2D/3D 排布迭代时 ()，只需进行 O(1) 的查表操作，判断交接点的 XYZ 坐标是否落在该体素地图的有效区域内即可。

* 目前首先尝试取占用域的二维投影，使用平面设计ai（pensil）进行编排 目前感觉这部分要想真正按期望实现的话，可能真要我们重新写一个算法，因为一旦引入一些硬规则的话就可能带来无解情况，有可能可以用到语义代价地图，寻找一个全局最小cost。

* 拉取3D模型，增加机械臂等，切换多视角截图，进行迭代

* 一键2D/3D切换照顾网差选手（=我自己）

* （机械臂实际执行或 MoveIt 规划的 JointState 更新频率可能高达 100Hz 以上。可能需要在 ROS 端写一个专门的 Throttler Node（节流节点），将下发给前端的 TF 和 Joint 状态降频至 20-30Hz，以保证前端浏览器的流畅度）

**增加硬编码规则**

* `distance_less_than(object, dist)`

* `distance_greater_than(object, dist)`

**现有模型分类库：**

* [Matterix_Asset_[Classification.md](http://Classification.md)]

**注意问题：**

* 留出一个机械臂运动的空间，暂时不考虑三维和可达工作空间

* 模型零点转换问题