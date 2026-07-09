#!/usr/bin/env python3
"""
MoveIt2 独立启动脚本 — 用于关节运动控制原型验证

自动处理:
1. 从运行中的 robot_state_publisher 获取 URDF
2. 修正 SRDF 关节/链接名前缀不匹配
3. 配置 OMPL 规划管线
4. 启动 move_group 节点
"""

import os
import sys
import yaml
import subprocess
from pathlib import Path

DEVICE_PREFIX = "dummy2_arm_"
DEVICE_MESH_ROOT = Path("/home/ubuntu/workspace/Uni-Lab-OS/unilabos/device_mesh")
DUMMY2_CONFIG = DEVICE_MESH_ROOT / "devices" / "dummy2_robot" / "config"
OMPL_DEFAULTS_DIR = Path("/home/ubuntu/miniforge3/envs/unilab/share/moveit_configs_utils/default_configs")
OUTPUT_DIR = Path("/home/ubuntu/workspace/Uni-Lab-OS/moveit2_launch_config")


def get_robot_description():
    """从 robot_state_publisher 获取当前 URDF"""
    result = subprocess.run(
        ["ros2", "param", "get", "/robot_state_publisher", "robot_description"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        print(f"ERROR: 无法获取 robot_description: {result.stderr}")
        sys.exit(1)
    urdf = result.stdout.replace("String value is: ", "").strip()
    print(f"[OK] 获取 URDF ({len(urdf)} chars), 关节数: {urdf.count('<joint name=')}")
    return urdf


def generate_corrected_srdf():
    """生成修正前缀后的 SRDF"""
    srdf = f"""<?xml version="1.0" encoding="UTF-8"?>
<robot name="full_dev">
    <group name="dummy2_arm">
        <joint name="dummy2_arm_virtual_joint"/>
        <joint name="dummy2_arm_Joint1"/>
        <joint name="dummy2_arm_Joint2"/>
        <joint name="dummy2_arm_Joint3"/>
        <joint name="dummy2_arm_Joint4"/>
        <joint name="dummy2_arm_Joint5"/>
        <joint name="dummy2_arm_Joint6"/>
    </group>

    <group_state name="home" group="dummy2_arm">
        <joint name="dummy2_arm_Joint1" value="0"/>
        <joint name="dummy2_arm_Joint2" value="0"/>
        <joint name="dummy2_arm_Joint3" value="0"/>
        <joint name="dummy2_arm_Joint4" value="0"/>
        <joint name="dummy2_arm_Joint5" value="0"/>
        <joint name="dummy2_arm_Joint6" value="0"/>
    </group_state>

    <virtual_joint name="dummy2_arm_virtual_joint" type="fixed" parent_frame="world" child_link="dummy2_arm_base_link"/>

    <disable_collisions link1="dummy2_arm_J1_1" link2="dummy2_arm_J2_1" reason="Adjacent"/>
    <disable_collisions link1="dummy2_arm_J1_1" link2="dummy2_arm_J3_1" reason="Never"/>
    <disable_collisions link1="dummy2_arm_J1_1" link2="dummy2_arm_J4_1" reason="Never"/>
    <disable_collisions link1="dummy2_arm_J1_1" link2="dummy2_arm_base_link" reason="Adjacent"/>
    <disable_collisions link1="dummy2_arm_J2_1" link2="dummy2_arm_J3_1" reason="Adjacent"/>
    <disable_collisions link1="dummy2_arm_J3_1" link2="dummy2_arm_J4_1" reason="Adjacent"/>
    <disable_collisions link1="dummy2_arm_J3_1" link2="dummy2_arm_J5_1" reason="Never"/>
    <disable_collisions link1="dummy2_arm_J3_1" link2="dummy2_arm_J6_1" reason="Never"/>
    <disable_collisions link1="dummy2_arm_J3_1" link2="dummy2_arm_base_link" reason="Never"/>
    <disable_collisions link1="dummy2_arm_J4_1" link2="dummy2_arm_J5_1" reason="Adjacent"/>
    <disable_collisions link1="dummy2_arm_J4_1" link2="dummy2_arm_J6_1" reason="Never"/>
    <disable_collisions link1="dummy2_arm_J5_1" link2="dummy2_arm_J6_1" reason="Adjacent"/>
</robot>"""
    print(f"[OK] 生成修正后的 SRDF (所有名称已加 '{DEVICE_PREFIX}' 前缀)")
    return srdf


def load_kinematics():
    """加载运动学配置"""
    kin_file = DUMMY2_CONFIG / "kinematics.yaml"
    with open(kin_file) as f:
        kin = yaml.safe_load(f)
    print(f"[OK] 加载 kinematics: solver={kin['dummy2_arm']['kinematics_solver']}")
    return kin


def load_planning_pipelines():
    """加载 OMPL 规划管线"""
    ompl_planning = {}
    with open(OMPL_DEFAULTS_DIR / "ompl_planning.yaml") as f:
        ompl_planning.update(yaml.safe_load(f))
    with open(OMPL_DEFAULTS_DIR / "ompl_defaults.yaml") as f:
        ompl_planning.update(yaml.safe_load(f))
    planning = {"ompl": ompl_planning}
    print(f"[OK] 加载 OMPL 规划配置 ({len(ompl_planning.get('planner_configs', {}))} planners)")
    return planning


def load_joint_limits():
    """加载关节限位"""
    limits_file = DUMMY2_CONFIG / "joint_limits.yaml"
    with open(limits_file) as f:
        raw = yaml.safe_load(f)

    fixed = {}
    if "joint_limits" in raw:
        for old_name, val in raw["joint_limits"].items():
            new_name = f"{DEVICE_PREFIX}{old_name}" if not old_name.startswith(DEVICE_PREFIX) else old_name
            fixed[new_name] = val
    result = {
        "default_velocity_scaling_factor": raw.get("default_velocity_scaling_factor", 0.1),
        "default_acceleration_scaling_factor": raw.get("default_acceleration_scaling_factor", 0.1),
        "joint_limits": fixed,
        "cartesian_limits": {
            "max_trans_vel": 1.0,
            "max_trans_acc": 2.25,
            "max_trans_dec": -5.0,
            "max_rot_vel": 1.57,
        },
    }
    print(f"[OK] 加载关节限位 ({len(fixed)} joints, 已修正前缀)")
    return result


def write_configs(urdf, srdf, kinematics, planning, joint_limits):
    """将所有配置写入临时目录"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUTPUT_DIR / "robot_description.urdf").write_text(urdf)
    (OUTPUT_DIR / "robot_description_semantic.srdf").write_text(srdf)
    with open(OUTPUT_DIR / "kinematics.yaml", "w") as f:
        yaml.safe_dump(kinematics, f)
    with open(OUTPUT_DIR / "planning_pipelines.yaml", "w") as f:
        yaml.safe_dump(planning, f)
    with open(OUTPUT_DIR / "joint_limits.yaml", "w") as f:
        yaml.safe_dump(joint_limits, f)

    print(f"[OK] 配置写入 {OUTPUT_DIR}")


def build_launch_command(urdf, srdf, kinematics, planning, joint_limits):
    """构建 move_group 启动命令"""
    import json

    params = {
        "robot_description": urdf,
        "robot_description_semantic": srdf,
        "robot_description_kinematics": kinematics,
        "robot_description_planning": joint_limits,
        "allow_trajectory_execution": False,
        "capabilities": "",
        "disable_capabilities": "",
        "monitor_dynamics": False,
        "publish_monitored_planning_scene": True,
        "publish_robot_description_semantic": True,
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
    }
    params.update(planning)

    params_file = OUTPUT_DIR / "move_group_params.yaml"
    move_group_yaml = {"move_group": {"ros__parameters": {}}}
    for k, v in params.items():
        if isinstance(v, (dict, list)):
            move_group_yaml["move_group"]["ros__parameters"][k] = v
        else:
            move_group_yaml["move_group"]["ros__parameters"][k] = v

    with open(params_file, "w") as f:
        yaml.safe_dump(move_group_yaml, f, default_flow_style=False, allow_unicode=True, width=200)

    print(f"[OK] move_group 参数文件: {params_file}")
    return str(params_file)


def main():
    print("=" * 60)
    print("MoveIt2 启动准备")
    print("=" * 60)

    urdf = get_robot_description()
    srdf = generate_corrected_srdf()
    kinematics = load_kinematics()
    planning = load_planning_pipelines()
    joint_limits = load_joint_limits()

    write_configs(urdf, srdf, kinematics, planning, joint_limits)
    params_file = build_launch_command(urdf, srdf, kinematics, planning, joint_limits)

    print()
    print("=" * 60)
    print("准备完成! 启动 move_group:")
    print("=" * 60)
    print()
    print(f"ros2 run moveit_ros_move_group move_group --ros-args --params-file {params_file}")
    print()
    print("或在 Python 中直接启动:")
    print("  from launch_moveit2 import start_move_group")
    print("  start_move_group()")


def start_move_group():
    """直接在 Python 中启动 move_group"""
    main()
    params_file = str(OUTPUT_DIR / "move_group_params.yaml")
    print("\n[STARTING] move_group ...")
    os.execvp("ros2", [
        "ros2", "run", "moveit_ros_move_group", "move_group",
        "--ros-args", "--params-file", params_file
    ])


if __name__ == "__main__":
    if "--start" in sys.argv:
        start_move_group()
    else:
        main()
