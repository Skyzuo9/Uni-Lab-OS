#!/bin/bash
# 启动 Uni-Lab 3D 仿真环境
# 包括：robot_state_publisher + Foxglove Bridge + 关节状态仿真发布器 + 耗材位姿仿真发布器
#
# 使用方法：
#   bash ~/workspace/Uni-Lab-OS/scripts/start_simulation.sh

set -e

PROJ="$HOME/workspace/Uni-Lab-OS"
SESSION="unilab"
ENV_SETUP="source ~/miniforge3/etc/profile.d/conda.sh && conda activate unilab"

echo "=== 启动 Uni-Lab 3D 仿真环境 ==="

# 生成 dummy2_robot URDF（使用 macro_device.xacro，不依赖 dummy2_description 包）
echo "生成仿真机器人 URDF..."
source ~/miniforge3/etc/profile.d/conda.sh && conda activate unilab

URDF_FILE="/tmp/dummy2_sim.urdf"

python3 << 'GENEOF'
import xacro
from pathlib import Path

PROJ = "/home/ubuntu/workspace/Uni-Lab-OS"
mesh_path = f"{PROJ}/unilabos/device_mesh"
template = f"""<?xml version="1.0" ?><robot name="full_dev" xmlns:xacro="http://ros.org/wiki/xacro">
<link name="world"/>
<xacro:include filename="{mesh_path}/devices/dummy2_robot/macro_device.xacro"/>
<xacro:dummy2_robot parent_link="world" mesh_path="{mesh_path}" device_name="dummy2_arm_" station_name="" x="0" y="0" z="0" rx="0" ry="0" r="0"/>
</robot>"""
doc = xacro.parse(template)
xacro.process_doc(doc)
Path("/tmp/dummy2_sim.urdf").write_text(doc.toxml())
print(f"URDF written: {Path('/tmp/dummy2_sim.urdf').stat().st_size} bytes")
GENEOF

echo "URDF 生成完毕: $URDF_FILE"

# window rsp: robot_state_publisher
tmux new-window -t $SESSION: -n "rsp" 2>/dev/null || true
tmux send-keys -t $SESSION:rsp "$ENV_SETUP && ros2 run robot_state_publisher robot_state_publisher --ros-args -p robot_description:=\"\$(cat $URDF_FILE)\"" Enter
echo "robot_state_publisher 启动中..."
sleep 3

# window foxglove: Foxglove Bridge
tmux new-window -t $SESSION: -n "foxglove" 2>/dev/null || true
tmux send-keys -t $SESSION:foxglove "$ENV_SETUP && ros2 launch foxglove_bridge foxglove_bridge_launch.xml port:=8765" Enter
echo "Foxglove Bridge 启动中 (ws://localhost:8765)..."
sleep 3

# window sim_joints: 关节状态仿真
tmux new-window -t $SESSION: -n "sim_joints" 2>/dev/null || true
tmux send-keys -t $SESSION:sim_joints "$ENV_SETUP && python3 $PROJ/scripts/sim_joint_publisher.py" Enter
echo "关节状态仿真发布器启动..."
sleep 2

# window sim_resources: 耗材位姿仿真
tmux new-window -t $SESSION: -n "sim_resources" 2>/dev/null || true
tmux send-keys -t $SESSION:sim_resources "$ENV_SETUP && python3 $PROJ/scripts/sim_resource_pose.py" Enter
echo "耗材位姿仿真发布器启动..."

echo ""
echo "=== 仿真环境启动完毕 ==="
echo "访问测试页面：http://172.20.0.39:8002/static/lab3d-phase2/dev-test.html"
echo ""
echo "tmux 窗口："
echo "  unilab:0            - FastAPI 服务器 :8002"
echo "  unilab:rsp          - robot_state_publisher"
echo "  unilab:foxglove     - Foxglove Bridge :8765"
echo "  unilab:sim_joints   - 关节状态仿真 (20Hz)"
echo "  unilab:sim_resources - 耗材位姿仿真 (50Hz)"
