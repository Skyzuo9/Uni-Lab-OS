# Uni-Lab OS Xacro 设备描述文件标准规范

## 必要参数（macro params）

所有 `macro_device.xacro` 文件的主宏必须接受以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `mesh_path` | string | `''` | device_mesh 目录绝对路径，由系统注入 |
| `parent_link` | string | `''` | 父坐标系 link 名称 |
| `station_name` | string | `''` | 实验站名称前缀（可为空） |
| `device_name` | string | `''` | 设备实例 ID 前缀（末尾有 `_`） |
| `x` | float | `0` | X 位置（m） |
| `y` | float | `0` | Y 位置（m） |
| `z` | float | `0` | Z 位置（m） |
| `rx` | float | `0` | Roll 角（rad） |
| `ry` | float | `0` | Pitch 角（rad） |
| `r` | float | `0` | Yaw 角（rad） |

## Link 命名规范

- base link：`${station_name}${device_name}device_link`
- 关节 link：`${station_name}${device_name}joint_N_link`
- 语义帧：`${station_name}${device_name}FRAMENAME_frame`（末尾加 `_frame`）

## Mesh 路径格式

使用相对 `mesh_path` 的路径，不要硬编码绝对路径：

```xml
<mesh filename="${mesh_path}/devices/YOUR_DEVICE/meshes/YOUR_MESH.STL"/>
```

## Visual / Collision 拆分

- Visual 文件：`meshes/visual/XXX.STL`（高精度，面数不限）
- Collision 文件：`meshes/collision/XXX.STL`（凸包简化，面数 < 200）
- 当前 elite_robot 已完成此拆分，可作为参考

## 标准 macro_device.xacro 模板

```xml
<?xml version="1.0"?>
<robot xmlns:xacro="http://ros.org/wiki/xacro">
  <xacro:macro name="YOUR_DEVICE_NAME" params="
    mesh_path:=''
    parent_link:=''
    station_name:=''
    device_name:=''
    x:=0 y:=0 z:=0
    rx:=0 ry:=0 r:=0">

    <link name="${station_name}${device_name}device_link">
      <visual>
        <geometry>
          <mesh filename="${mesh_path}/devices/YOUR_DEVICE/meshes/visual/base.STL"/>
        </geometry>
        <material name="white"><color rgba="0.9 0.9 0.9 1"/></material>
      </visual>
      <collision>
        <geometry>
          <mesh filename="${mesh_path}/devices/YOUR_DEVICE/meshes/collision/base.STL"/>
        </geometry>
      </collision>
    </link>

    <joint name="${station_name}${device_name}base_joint" type="fixed">
      <parent link="${parent_link}"/>
      <child link="${station_name}${device_name}device_link"/>
      <origin xyz="${x} ${y} ${z}" rpy="${rx} ${ry} ${r}"/>
    </joint>

  </xacro:macro>
</robot>
```

## 现有设备规范合规情况

| 设备 | 规范参数 | mesh_path | collision 拆分 |
|------|---------|-----------|--------------|
| elite_robot | ✅ | ✅ | ✅ 已完成 |
| dummy2_robot | ✅ | ✅ | ❌ 未拆分 |
| arm_slider | ✅ | ✅ | ❌ 未拆分 |
| hplc_station | ✅ | ✅ | ❌ 未拆分 |
| liquid_transform_xyz | ✅ | ✅ | ❌ 未拆分 |
| opentrons_liquid_handler | ✅ | ✅ | ❌ 未拆分 |
| slide_w140 | ✅ | ✅ | ❌ 未拆分 |
| thermo_orbitor_rs2_hotel | ✅ | ✅ | ❌ 未拆分 |
| toyo_xyz | ✅ | ✅ | ❌ 未拆分 |

## 盒体降级机制

当设备 YAML 注册表中 `model.mesh` 字段缺失或对应 `macro_device.xacro` 不存在时，
`/api/v1/layout/urdf` 端点自动使用 `<box size="0.3 0.3 0.3"/>` 占位，
确保场景渲染不因单个设备缺失模型而失败。
