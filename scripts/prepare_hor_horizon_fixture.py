#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


XACRO_NS = "http://www.ros.org/wiki/xacro"
MESH_NAME = "hor_horizon_v2_1"
ROS_PACKAGE_NAME = "hor_horizon_v2_1_description"
REVOLUTE_EFFORT = "20"
REVOLUTE_VELOCITY = "1.0"
PRISMATIC_EFFORT = "100"
PRISMATIC_VELOCITY = "0.2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the HOR Horizon model as a Uni-Lab-OS xacro fixture.")
    parser.add_argument("--source", required=True, type=Path, help="Original SolidWorks URDF package directory.")
    parser.add_argument("--output", required=True, type=Path, help="Target device mesh directory.")
    return parser.parse_args()


def build_fixture(source: Path, output: Path) -> dict:
    urdf_files = sorted((source / "urdf").glob("*.urdf"))
    if len(urdf_files) != 1:
        raise RuntimeError(f"Expected exactly one URDF under {source / 'urdf'}, found {len(urdf_files)}")
    source_mesh_dir = source / "meshes"
    if not source_mesh_dir.is_dir():
        raise RuntimeError(f"Missing source mesh directory: {source_mesh_dir}")

    visual_dir = output / "meshes" / "visual"
    collision_dir = output / "meshes" / "collision"
    visual_dir.mkdir(parents=True, exist_ok=True)
    collision_dir.mkdir(parents=True, exist_ok=True)

    tree = ET.parse(urdf_files[0])
    source_root = tree.getroot()
    links = source_root.findall("link")
    joints = source_root.findall("joint")
    source_link_names = {link.attrib["name"] for link in links}

    mesh_report = []
    for source_mesh in sorted(source_mesh_dir.glob("*.[Ss][Tt][Ll]")):
        target_visual = visual_dir / source_mesh.name
        shutil.copy2(source_mesh, target_visual)
        target_collision = collision_dir / source_mesh.name
        report = _create_convex_collision(source_mesh, target_collision)
        mesh_report.append(report)

    ET.register_namespace("xacro", XACRO_NS)
    robot = ET.Element("robot", {"name": MESH_NAME})
    macro = ET.SubElement(
        robot,
        f"{{{XACRO_NS}}}macro",
        {
            "name": MESH_NAME,
            "params": "parent_link mesh_path device_name x:=0 y:=0 z:=0 rx:=0 ry:=0 r:=0",
        },
    )

    for source_link in links:
        link = copy.deepcopy(source_link)
        original_name = link.attrib["name"]
        link.attrib["name"] = f"${{device_name}}{original_name}"
        for visual_mesh in link.findall("./visual/geometry/mesh"):
            filename = Path(visual_mesh.attrib["filename"]).name
            visual_mesh.attrib["filename"] = (
                f"package://{ROS_PACKAGE_NAME}/meshes/visual/{filename}"
            )
        for collision_mesh in link.findall("./collision/geometry/mesh"):
            filename = Path(collision_mesh.attrib["filename"]).name
            collision_mesh.attrib["filename"] = (
                f"package://{ROS_PACKAGE_NAME}/meshes/collision/{filename}"
            )
        macro.append(link)

    for source_joint in joints:
        joint = copy.deepcopy(source_joint)
        original_name = joint.attrib["name"]
        joint.attrib["name"] = f"${{device_name}}{original_name}"
        for tag in ("parent", "child"):
            element = joint.find(tag)
            if element is not None and element.attrib.get("link") in source_link_names:
                element.attrib["link"] = f"${{device_name}}{element.attrib['link']}"
        limit = joint.find("limit")
        joint_type = joint.attrib.get("type")
        if joint_type == "fixed" and limit is not None:
            joint.remove(limit)
        elif limit is not None and joint_type == "revolute":
            limit.attrib["effort"] = REVOLUTE_EFFORT
            limit.attrib["velocity"] = REVOLUTE_VELOCITY
        elif limit is not None and joint_type == "prismatic":
            limit.attrib["effort"] = PRISMATIC_EFFORT
            limit.attrib["velocity"] = PRISMATIC_VELOCITY
        macro.append(joint)

    world_joint = ET.SubElement(
        macro,
        "joint",
        {"name": "${device_name}world_joint", "type": "fixed"},
    )
    ET.SubElement(world_joint, "parent", {"link": "${parent_link}"})
    ET.SubElement(world_joint, "child", {"link": "${device_name}base_link"})
    ET.SubElement(world_joint, "origin", {"xyz": "${x} ${y} ${z}", "rpy": "${rx} ${ry} ${r}"})

    output.mkdir(parents=True, exist_ok=True)
    ET.indent(robot, space="  ")
    xacro_path = output / "macro_device.xacro"
    ET.ElementTree(robot).write(xacro_path, encoding="utf-8", xml_declaration=True)
    (output / "package.xml").write_text(
        (
            '<?xml version="1.0"?>\n'
            '<package format="3">\n'
            f"  <name>{ROS_PACKAGE_NAME}</name>\n"
            "  <version>0.1.0</version>\n"
            "  <description>HOR Horizon collision development model.</description>\n"
            "  <maintainer email=\"noreply@example.com\">Uni-Lab</maintainer>\n"
            "  <license>BSD</license>\n"
            "</package>\n"
        ),
        encoding="utf-8",
    )
    ament_prefix = _create_ament_prefix(output)

    report = {
        "source_urdf": urdf_files[0].name,
        "output_xacro": xacro_path.name,
        "links": len(links),
        "joints": len(joints),
        "ament_prefix": str(ament_prefix.relative_to(output)),
        "mesh_report": mesh_report,
    }
    (output / "fixture_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _create_ament_prefix(output: Path) -> Path:
    prefix = output / ".ament_prefix"
    marker_dir = prefix / "share" / "ament_index" / "resource_index" / "packages"
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / ROS_PACKAGE_NAME).write_text("", encoding="utf-8")
    package_link = prefix / "share" / ROS_PACKAGE_NAME
    if package_link.is_symlink() or package_link.exists():
        if package_link.is_dir() and not package_link.is_symlink():
            shutil.rmtree(package_link)
        else:
            package_link.unlink()
    # 从 <output>/.ament_prefix/share/<package> 指回 <output>，保持跨机器可搬运。
    package_link.symlink_to(Path("../.."), target_is_directory=True)
    return prefix


def _create_convex_collision(source_mesh: Path, target_mesh: Path) -> dict:
    import trimesh

    mesh = trimesh.load_mesh(source_mesh, force="mesh")
    if mesh.is_empty:
        raise RuntimeError(f"Empty mesh: {source_mesh}")
    hull = mesh.convex_hull
    hull.export(target_mesh)
    return {
        "name": source_mesh.name,
        "visual_faces": int(len(mesh.faces)),
        "collision_faces": int(len(hull.faces)),
        "visual_size_bytes": source_mesh.stat().st_size,
        "collision_size_bytes": target_mesh.stat().st_size,
        "bounds": mesh.bounds.tolist(),
    }


if __name__ == "__main__":
    arguments = parse_args()
    result = build_fixture(arguments.source.resolve(), arguments.output.resolve())
    print(json.dumps(result, indent=2))
