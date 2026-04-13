# Ubuntu 开发机环境配置指南
## Uni-Lab-OS 3D 可视化项目 × RTX 4090

> **当前机器状态（已确认）**
> - OS: Ubuntu 22.04 LTS
> - GPU: NVIDIA GeForce RTX 4090（24564 MiB）
> - Driver: 580.126.09 ✅ 已安装
> - CUDA: 13.0 ✅ 已安装
> - VPN: Clash ✅ 已运行（香港节点，网络畅通）
>
> **本指南从 Miniforge3 开始，跳过 NVIDIA/CUDA 安装部分。**
>
> **预计剩余配置耗时**: 1 ~ 2 小时

---

## 目录

1. [系统基础工具确认](#1-系统基础工具确认)
2. [Miniforge3 / Mamba 安装](#2-miniforge3--mamba-安装)
3. [Uni-Lab-OS 开发环境安装](#3-uni-lab-os-开发环境安装)
4. [Foxglove Bridge 安装](#4-foxglove-bridge-安装)
5. [Node.js 前端工具链安装](#5-nodejs-前端工具链安装)
6. [开发工具配置](#6-开发工具配置)
7. [安装验证](#7-安装验证)
8. [常见问题排查](#8-常见问题排查)
9. [快速启动测试](#9-快速启动测试)

---

## 1. 系统基础工具确认

### 1.1 确认当前环境

```bash
# 验证已安装的组件
nvidia-smi                          # 应显示 Driver 580.x，RTX 4090
nvcc --version 2>/dev/null || echo "nvcc 未在 PATH，但 CUDA 已安装"
lsb_release -a                      # 应为 Ubuntu 22.04 LTS
```

> **关于 nvcc**: CUDA 13.0 的 `nvcc` 可能路径不在默认 PATH 中。如果 `nvcc --version` 报错，执行：
> ```bash
> ls /usr/local/cuda*/bin/nvcc      # 找到 nvcc 路径
> echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
> echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
> source ~/.bashrc
> ```

### 1.2 安装基础构建工具

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y \
    build-essential \
    curl \
    wget \
    git \
    git-lfs \
    vim \
    htop \
    net-tools \
    ca-certificates \
    gnupg \
    lsb-release \
    software-properties-common \
    pkg-config \
    libssl-dev \
    libffi-dev \
    libgl1-mesa-glx \
    libglib2.0-0

# 初始化 git-lfs
git lfs install
```

### 1.3 配置 Git

```bash
git config --global user.name "你的姓名"
git config --global user.email "your@email.com"
git config --global core.autocrlf input
```

### 1.4 确认 VPN 代理对终端生效

Clash 默认仅代理系统级流量，终端命令（`curl`、`wget`、`pip` 等）可能不走代理。确认方法：

```bash
# 测试终端网络是否走代理
curl -s https://api.github.com/zen
# 若返回一句英文格言，说明可以访问 GitHub

# 如果不通，在终端手动设置代理（Clash 默认端口 7890）
export http_proxy=http://127.0.0.1:7890
export https_proxy=http://127.0.0.1:7890
export all_proxy=socks5://127.0.0.1:7890

# 建议写入 ~/.bashrc 使其永久生效
echo 'export http_proxy=http://127.0.0.1:7890' >> ~/.bashrc
echo 'export https_proxy=http://127.0.0.1:7890' >> ~/.bashrc
echo 'export all_proxy=socks5://127.0.0.1:7890' >> ~/.bashrc
source ~/.bashrc

# 再次测试
curl -s https://api.github.com/zen
```

---

## 2. Miniforge3 / Mamba 安装

> 项目通过 **conda + RoboStack** 管理 ROS2 和所有 Python 依赖，**不使用** apt 安装 ROS2。

### 2.1 下载并安装 Miniforge3

```bash
# 下载 Miniforge3（包含 mamba，比 conda 快 5-10 倍）
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"

# 运行安装（-b 静默安装，-p 指定路径）
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3

# 初始化 shell（bash 和 zsh 都初始化）
~/miniforge3/bin/conda init bash
source ~/.bashrc

# 验证
conda --version
mamba --version
```

安装成功后，终端提示符会出现 `(base)` 前缀：

```
(base) ubuntu@ubuntu:~$
```

### 2.2 关闭 base 环境自动激活（推荐）

```bash
# 防止每次开终端都自动进入 base 环境
conda config --set auto_activate_base false
```

### 2.3 确认 mamba 可用

```bash
mamba --version
# 预期输出: mamba 1.x.x  或  2.x.x
```

---

## 3. Uni-Lab-OS 开发环境安装

> 由于需要修改源码（Phase 1 的核心工作），选择**开发者安装模式**，安装 `unilabos-full` 以获得完整的 RViz2 + MoveIt2 + ROSBridge 可视化能力。

### 3.1 克隆项目仓库

> **必须先配置 git 代理**，否则 GitHub 连接会因 GnuTLS TLS 中断报错（`GnuTLS recv error (-110)`）。

```bash
# 第一步：配置 git 走 Clash 代理（必须在 clone 之前执行）
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# 第二步：克隆仓库
mkdir -p ~/workspace
cd ~/workspace
git clone https://github.com/deepmodeling/Uni-Lab-OS.git
cd Uni-Lab-OS

# 第三步：切换到 dev 分支（推荐开发时使用）
git checkout dev
git pull
```

> **备选方案**：如果网络持续失败，可以从 Mac 本地直接传输代码：
> ```bash
> # 在 Mac 本地终端执行
> scp -r /Users/newtides/Downloads/Uni-Lab-OS-main ubuntu@<服务器IP>:~/workspace/Uni-Lab-OS
> ```

### 3.2 创建 unilab conda 环境

```bash
# 创建 Python 3.11 环境（项目指定版本）
mamba create -n unilab python=3.11.14 -y

# 激活环境
conda activate unilab

# 确认 Python 版本
python --version  # 应输出: Python 3.11.14
```

### 3.3 安装 Uni-Lab-OS 完整包

`unilabos-full` 包含 ROS2 Humble Desktop + MoveIt2，是 Phase 1 开发的推荐选项。

> **注意**：`unilabos-full` 不一定包含 `rosbridge_server` 和 `foxglove_bridge`，安装完成后需在 3.3b 中单独补装这两个包。

```bash
conda activate unilab

# 安装完整版（含 RViz2 + MoveIt2，约 8-10 GB，耗时 20-40 分钟）
mamba install uni-lab::unilabos-full \
    -c robostack-staging \
    -c conda-forge \
    -y
```

> **下载进度参考**: 在香港 VPN 节点下，下载速度通常在 5-20 MB/s，总耗时约 20-40 分钟。

### 3.3b 补装 ROSBridge + Foxglove Bridge（必须）

`unilabos-full` 安装完成后，验证并补装 Phase 1 必须的两个通信包：

```bash
conda activate unilab

# 检查是否已包含
ros2 pkg list | grep -E "rosbridge_server|foxglove_bridge"

# 如果没有输出，补装（实际测试中 unilabos-full 不包含这两个包）
mamba install \
    ros-humble-rosbridge-server \
    ros-humble-foxglove-bridge \
    -c robostack-staging \
    -c conda-forge \
    -y

# 验证
ros2 pkg list | grep -E "rosbridge_server|foxglove_bridge"
# 应分别输出: rosbridge_server  foxglove_bridge
```

**如果 `unilabos-full` 安装遇到依赖冲突，改用分步安装**：

```bash
conda activate unilab

# Step 1: 安装开发者环境依赖
mamba install uni-lab::unilabos-env \
    -c robostack-staging \
    -c conda-forge -y

# Step 2: 补充安装可视化组件
mamba install \
    ros-humble-desktop-full \
    ros-humble-moveit \
    ros-humble-moveit-servo \
    ros-humble-ros2-control \
    ros-humble-robot-state-publisher \
    ros-humble-joint-state-publisher \
    ros-humble-rosbridge-server \
    ros-humble-xacro \
    ros-humble-tf2 \
    ros-humble-tf-transformations \
    ros-humble-foxglove-bridge \
    -c robostack-staging \
    -c conda-forge -y
```

### 3.4 以可编辑模式安装 Uni-Lab-OS 源码

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS

# 使用官方自动安装脚本（推荐）
python scripts/dev_install.py

# 或手动安装
pip install -e .
uv pip install -r unilabos/utils/requirements.txt
```

`-e`（editable mode）使代码修改**立即生效**，无需重新安装，是开发调试的关键。

### 3.4b 修复 AMENT_PREFIX_PATH 与 PYTHONPATH（必须执行）

RoboStack conda 安装后，ROS2 环境变量有时未自动配置，导致 `AMENT_PREFIX_PATH` 为空或 `unilabos_msgs` 无法导入。以下修复一次解决两个问题：

```bash
conda activate unilab

# 创建 conda 激活钩子（每次激活 unilab 环境时自动执行）
mkdir -p ~/miniforge3/envs/unilab/etc/conda/activate.d/

cat > ~/miniforge3/envs/unilab/etc/conda/activate.d/ros2_setup.sh << 'EOF'
#!/bin/bash
# 修复 AMENT_PREFIX_PATH
if [ -f "$CONDA_PREFIX/setup.bash" ]; then
    source "$CONDA_PREFIX/setup.bash"
fi
# 修复 unilabos_msgs 等 ROS2 Python 包的导入路径
export PYTHONPATH=$CONDA_PREFIX/lib/python3.11/site-packages:$PYTHONPATH
EOF

chmod +x ~/miniforge3/envs/unilab/etc/conda/activate.d/ros2_setup.sh

# 重新激活使修复立即生效
conda deactivate && conda activate unilab

# 验证
echo "AMENT_PREFIX_PATH = $AMENT_PREFIX_PATH"    # 应非空
python -c "from unilabos_msgs.action import Wait; print('✓ unilabos_msgs OK')"
```

### 3.5 安装 Phase 1 额外依赖

```bash
conda activate unilab

# 3D 网格处理（碰撞 mesh 简化脚本需要）
pip install trimesh

# lxml（URDF/XML 处理）
mamba install lxml -c conda-forge -y

# 验证 trimesh
python -c "import trimesh; print('trimesh:', trimesh.__version__)"
```

### 3.6 验证 ROS2 + Uni-Lab-OS 安装

```bash
conda activate unilab

# ROS2 环境
ros2 --version
# 预期: ros2 cli version: humble

# MoveIt2
ros2 pkg list | grep -c moveit
# 预期: 显示数字 >= 5（moveit_ros_planning 等多个包）

# ROSBridge
ros2 pkg list | grep rosbridge
# 预期: rosbridge_library  rosbridge_server  rosbridge_msgs

# unilabos_msgs（自定义消息包）
ros2 interface list | grep unilabos_msgs | head -5

# Uni-Lab-OS 版本
python -c "import unilabos; print('Uni-Lab-OS:', unilabos.__version__)"

# unilab 命令
unilab --help | head -3
```

---

## 4. Foxglove Bridge 安装

> Phase 1 使用 Foxglove Bridge 替代有兼容性问题的 `tf2_web_republisher`，用于前端实时获取 `/tf` 和 `/joint_states`。

### 4.1 通过 conda 安装（若 Step 3.3 分步安装时尚未安装）

```bash
conda activate unilab
mamba install ros-humble-foxglove-bridge -c robostack-staging -c conda-forge -y
```

### 4.2 验证 Foxglove Bridge

```bash
conda activate unilab

# 检查包是否存在
ros2 pkg list | grep foxglove
# 预期: foxglove_bridge

# 测试能否启动（3 秒后退出）
timeout 3 ros2 run foxglove_bridge foxglove_bridge 2>&1 | head -5
# 预期包含: "Listening on port 8765"
```

### 4.3 安装 Foxglove Studio 桌面客户端（调试利器）

> **注意**：GitHub `/releases/latest/download/` 的重定向在代理环境下容易失败（下载只有 9 字节），必须使用 **固定版本号 + curl 代理参数**。

```bash
# 使用固定版本号 + curl 代理（实测可用）
curl -L \
     --proxy http://127.0.0.1:7890 \
     --retry 3 \
     -o foxglove-studio.deb \
     "https://github.com/foxglove/studio/releases/download/v2.9.0/foxglove-studio-2.9.0-linux-amd64.deb"

# 检查文件大小（正常约 81 MB）
ls -lh foxglove-studio.deb

sudo apt install -y ./foxglove-studio.deb
rm foxglove-studio.deb

# 启动
foxglove-studio &
```

> **如果不想安装桌面版**，直接用浏览器访问 [https://studio.foxglove.dev](https://studio.foxglove.dev)，连接 `ws://localhost:8765` 效果完全相同。

Foxglove Studio 可在浏览器中实时查看 ROS2 话题、TF 树、3D 场景，极大方便调试。

---

## 5. Node.js 前端工具链安装

> Phase 1 前端（Three.js + urdf-loader）需要 Node.js 20 LTS。

### 5.1 安装 nvm（Node Version Manager）

```bash
# 安装 nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

# 重新加载 shell 配置
source ~/.bashrc

# 验证 nvm 安装
nvm --version
```

### 5.2 安装 Node.js 20 LTS

```bash
nvm install 20
nvm use 20
nvm alias default 20

# 验证
node --version   # 预期: v20.x.x
npm --version    # 预期: 10.x.x
```

### 5.3 安装全局开发工具

```bash
# 本地调试服务器
npm install -g http-server live-server

# 并行进程管理
npm install -g concurrently
```

### 5.4 创建前端项目依赖

```bash
# 创建 Phase 1 前端目录
mkdir -p ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d
cd ~/workspace/Uni-Lab-OS/unilabos/app/web/static/lab3d

# 初始化 npm 项目
npm init -y

# 安装核心依赖
npm install three urdf-loader roslib @foxglove/ws-protocol

# 安装开发构建工具
npm install --save-dev vite

# 验证安装
node -e "require('three'); console.log('three OK')"
```

---

## 6. 开发工具配置

### 6.1 安装 VS Code

```bash
# 方法 1: 下载 .deb（推荐）
wget -O code.deb "https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64"
sudo apt install -y ./code.deb
rm code.deb

# 方法 2: snap
sudo snap install --classic code
```

### 6.2 安装推荐 VS Code 插件

```bash
# Python 开发
code --install-extension ms-python.python
code --install-extension ms-python.pylance
code --install-extension ms-python.debugpy

# ROS 开发支持
code --install-extension ms-iot.vscode-ros

# 前端开发
code --install-extension dbaeumer.vscode-eslint
code --install-extension esbenp.prettier-vscode

# 配置文件
code --install-extension redhat.vscode-yaml

# Git 增强
code --install-extension mhutchie.git-graph
code --install-extension eamodio.gitlens

# Markdown 文档预览（查看本项目的规划文档）
code --install-extension yzhang.markdown-all-in-one
```

### 6.3 配置 VS Code Python 解释器

打开项目目录后，创建工作区配置：

```bash
mkdir -p ~/workspace/Uni-Lab-OS/.vscode
cat > ~/workspace/Uni-Lab-OS/.vscode/settings.json << 'EOF'
{
    "python.defaultInterpreterPath": "${env:HOME}/miniforge3/envs/unilab/bin/python",
    "python.analysis.extraPaths": [
        "${env:HOME}/miniforge3/envs/unilab/lib/python3.11/site-packages"
    ],
    "editor.formatOnSave": true,
    "editor.tabSize": 4,
    "files.trimTrailingWhitespace": true,
    "[python]": {
        "editor.defaultFormatter": "ms-python.python"
    },
    "ros.distro": "humble"
}
EOF
```

VS Code 打开后按 `Ctrl+Shift+P` → `Python: Select Interpreter`，选择 `unilab` 环境中的 Python。

### 6.4 添加 Shell 快捷命令

```bash
cat >> ~/.bashrc << 'EOF'

# ===== Uni-Lab-OS 开发快捷命令 =====
alias unilab-dev='conda activate unilab && cd ~/workspace/Uni-Lab-OS'
alias ros-topics='ros2 topic list'
alias ros-tf='ros2 run tf2_tools view_frames'
alias rviz='ros2 run rviz2 rviz2'
EOF

source ~/.bashrc
```

---

## 7. 安装验证

### 7.1 运行官方验证脚本

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS

python scripts/verify_installation.py
# 如有缺失包，自动修复：
python scripts/verify_installation.py --auto-install
```

### 7.2 完整环境检查脚本

将以下内容一次性粘贴到终端运行：

```bash
conda activate unilab

echo "================================================"
echo "  Uni-Lab-OS Phase 1 环境完整性检查"
echo "================================================"

echo ""
echo "[ GPU & CUDA ]"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader \
    && echo "✓ NVIDIA 驱动正常" || echo "✗ NVIDIA 驱动异常"

echo ""
echo "[ Python 环境 ]"
python --version && echo "✓ Python OK" || echo "✗ Python 异常"
which python | grep miniforge && echo "✓ 使用 conda 环境 Python" || echo "⚠ 可能使用系统 Python"

echo ""
echo "[ ROS2 ]"
# 注意：ros2 --version 是无效命令，用 --help 检查 ros2 是否可用
ros2 --help > /dev/null 2>&1 && echo "✓ ROS2 OK" || echo "✗ ROS2 未找到"
ros2 pkg list 2>/dev/null | grep -q "rviz2"       && echo "✓ RViz2 已安装"     || echo "✗ RViz2 未安装"
ros2 pkg list 2>/dev/null | grep -q "moveit_ros"  && echo "✓ MoveIt2 已安装"   || echo "✗ MoveIt2 未安装"
ros2 pkg list 2>/dev/null | grep -q "rosbridge"   && echo "✓ ROSBridge 已安装" || echo "✗ ROSBridge 未安装"
ros2 pkg list 2>/dev/null | grep -q "foxglove"    && echo "✓ Foxglove 已安装"  || echo "✗ Foxglove 未安装"

echo ""
echo "[ Uni-Lab-OS ]"
python -c "import unilabos; print('✓ unilabos', unilabos.__version__)" \
    || echo "✗ unilabos 导入失败"
# 注意：当前版本 unilabos_msgs 没有 DeviceCmd，使用实际存在的 Wait action
python -c "from unilabos_msgs.action import Wait; print('✓ unilabos_msgs OK')" \
    2>/dev/null || echo "✗ unilabos_msgs 导入失败（检查 PYTHONPATH 或 conda 包）"

echo ""
echo "[ 关键 Python 包 ]"
python -c "import fastapi;  print('✓ FastAPI',  fastapi.__version__)"
python -c "import rclpy;    print('✓ rclpy OK')"
python -c "import numpy;    print('✓ numpy',    numpy.__version__)"
python -c "import trimesh;  print('✓ trimesh',  trimesh.__version__)" \
    2>/dev/null || echo "⚠ trimesh 未安装（运行: pip install trimesh）"

echo ""
echo "[ Node.js ]"
node --version && echo "✓ Node.js OK" || echo "✗ Node.js 未安装"
npm  --version && echo "✓ npm OK"     || echo "✗ npm 未安装"

echo ""
echo "================================================"
echo "  检查完成"
echo "================================================"
```

### 7.3 RViz2 界面验证（需要图形界面）

```bash
conda activate unilab

# 启动 RViz2（有桌面环境时）
rviz2

# 若是远程 SSH，需开启 X11 转发
# 本地: ssh -X ubuntu@your-server-ip
# 然后: conda activate unilab && rviz2
```

---

## 8. 常见问题排查

### 问题 1: `ros2` 命令找不到

```bash
# 确认已激活 conda 环境
conda activate unilab
which ros2  # 应指向 ~/miniforge3/envs/unilab/bin/ros2

# 如果仍找不到，重新安装 ros2cli
mamba install ros-humble-ros2cli -c robostack-staging -c conda-forge -y
```

### 问题 2: mamba 安装包速度慢或超时

VPN（Clash）香港节点已经比较稳定，但 mamba 可能未走代理。检查：

```bash
# 测试 mamba 是否走代理
curl -s --proxy http://127.0.0.1:7890 \
    "https://conda.anaconda.org/robostack-staging/linux-64/repodata.json" \
    | head -c 100

# 如果 mamba 不走系统代理，在 ~/.condarc 中设置
cat >> ~/.condarc << 'EOF'
proxy_servers:
  http: http://127.0.0.1:7890
  https: http://127.0.0.1:7890
EOF
```

### 问题 3: `unilabos_msgs` 导入失败

此问题分两种情况：

**情况 A：包文件不存在**
```bash
conda activate unilab

# 检查文件是否存在
find ~/miniforge3/envs/unilab -path "*unilabos_msgs*" -name "__init__.py" 2>/dev/null

# 如果无输出，重新安装包
mamba install uni-lab::ros-humble-unilabos-msgs \
    -c uni-lab -c robostack-staging -c conda-forge --force-reinstall -y
```

**情况 B：包文件存在但导入失败（PYTHONPATH 问题，实测更常见）**
```bash
# 文件存在但 Python 找不到它，永久修复 PYTHONPATH
echo 'export PYTHONPATH=$CONDA_PREFIX/lib/python3.11/site-packages:$PYTHONPATH' \
    >> ~/miniforge3/envs/unilab/etc/conda/activate.d/ros2_setup.sh

conda deactivate && conda activate unilab
```

**验证（注意：当前版本无 `DeviceCmd`，使用实际存在的 action 名）**
```bash
# 查看实际可用的 action 列表
ros2 interface list | grep "unilabos_msgs/action"

# 验证导入（使用实际存在的 action，如 Wait、Transfer、Stir 等）
python -c "from unilabos_msgs.action import Wait; print('✓ OK')"
python -c "from unilabos_msgs.msg import Resource; print('✓ msg OK')"
```

### 问题 4: `pip install -e .` 失败

```bash
# 确认在正确的 conda 环境中（不要用 sudo）
conda activate unilab
which pip  # 必须指向 ~/miniforge3/envs/unilab/bin/pip

# 清除缓存后重试
pip cache purge
pip install -e . --no-cache-dir
```

### 问题 5: RViz2 在远程服务器无法显示

```bash
# 方法 1: SSH X11 转发
# 本地执行: ssh -X ubuntu@server-ip
# 服务器端: conda activate unilab && rviz2

# 方法 2: 安装 VNC（推荐长期使用）
sudo apt install -y tigervnc-standalone-server tigervnc-common
vncserver :1 -geometry 1920x1080 -depth 24
# 然后用 VNC 客户端连接 server-ip:5901

# 方法 3: 安装 xrdp（Windows 远程桌面协议）
sudo apt install -y xrdp
sudo systemctl enable xrdp
sudo systemctl start xrdp
# 用 Windows 远程桌面连接 server-ip:3389
```

### 问题 6: VPN 代理对 git clone 不生效

```bash
# 配置 git 走代理
git config --global http.proxy http://127.0.0.1:7890
git config --global https.proxy http://127.0.0.1:7890

# 验证
git config --global --list | grep proxy

# 测试 git 速度
time git ls-remote https://github.com/deepmodeling/Uni-Lab-OS.git HEAD
```

---

## 9. 快速启动测试

完成安装后，使用以下命令验证整体功能：

### 9.1 基础功能验证

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS

# 查看帮助
unilab --help

# 验证注册表加载
python -c "
from unilabos.registry.registry import DeviceRegistry
reg = DeviceRegistry()
devices = list(reg.devices.keys())
print(f'已注册 {len(devices)} 种设备类型，前 5 个: {devices[:5]}')
"
```

### 9.2 启动 Uni-Lab-OS 并验证 Web UI

```bash
conda activate unilab
cd ~/workspace/Uni-Lab-OS

# 查找可用的示例图文件
find . -name "*.json" -path "*/examples/*" 2>/dev/null | head -5
find . -name "stirteststation.json" 2>/dev/null | head -3

# 用示例图文件启动（替换为实际路径）
unilab -g <找到的json文件路径>

# 启动后在浏览器访问:
# http://localhost:8000  →  Web UI 主界面
```

### 9.3 验证 ROS2 TF 话题（3D 可视化核心）

```bash
# 终端 1: 启动 unilab
conda activate unilab && unilab -g your_graph.json

# 终端 2: 检查 ROS2 话题
conda activate unilab
ros2 topic list | grep -E "/tf|/joint_states|/robot_description"

# 查看 TF 数据
ros2 topic echo /tf --once

# 查看 TF 树（需要有 /tf 数据）
ros2 run tf2_tools view_frames
```

### 9.4 验证 Foxglove Bridge 连接

```bash
# 终端 1: 启动 Foxglove Bridge
conda activate unilab
ros2 run foxglove_bridge foxglove_bridge --ros-args \
    -p port:=8765 \
    -p send_buffer_limit:=10000000
# 预期输出: "Listening on port 8765"

# 打开 Foxglove Studio 桌面版或访问 https://studio.foxglove.dev
# 连接: ws://localhost:8765
# 即可实时查看 /tf、/joint_states 等话题
```

---

## 附录 A：环境完整性检查清单

在开始 Phase 1 代码开发前，确认以下所有项均已通过：

| 检查项 | 状态 | 验证命令 |
|--------|------|----------|
| Ubuntu 22.04 LTS | ✅ 已确认 | `lsb_release -a` |
| NVIDIA Driver 580 | ✅ 已安装 | `nvidia-smi` |
| CUDA 13.0 | ✅ 已安装 | `nvidia-smi` |
| VPN (Clash) | ✅ 已运行 | 香港节点 |
| 终端代理配置 | ☐ 待确认 | `curl https://api.github.com/zen` |
| Miniforge3 / mamba | ☐ 待安装 | `mamba --version` |
| conda unilab 环境 | ☐ 待创建 | `conda env list` |
| ROS2 Humble | ☐ 待安装 | `ros2 --version` |
| RViz2 | ☐ 待安装 | `ros2 pkg list \| grep rviz2` |
| MoveIt2 | ☐ 待安装 | `ros2 pkg list \| grep moveit_ros` |
| ROSBridge Server | ☐ 待安装 | `ros2 pkg list \| grep rosbridge` |
| Foxglove Bridge | ☐ 待安装 | `ros2 pkg list \| grep foxglove` |
| unilabos_msgs | ☐ 待安装 | `ros2 interface list \| grep unilabos` |
| Uni-Lab-OS (editable) | ☐ 待安装 | `python -c "import unilabos"` |
| Node.js 20 LTS | ☐ 待安装 | `node --version` |
| 前端依赖 (three.js 等) | ☐ 待安装 | `ls lab3d/node_modules/three` |

---

## 附录 B：工作目录结构参考

配置完成后，主要工作目录结构如下：

```
~/
├── miniforge3/                        # conda 基础环境
│   └── envs/unilab/                   # unilab 开发环境（约 8-10 GB）
│       ├── bin/python                 # Python 3.11.14
│       ├── bin/ros2                   # ROS2 CLI
│       └── lib/python3.11/site-packages/unilabos/  # 软链接到源码
│
├── workspace/
│   └── Uni-Lab-OS/                    # 项目源码（可编辑安装）
│       ├── unilabos/                  # 核心 Python 包
│       │   ├── app/web/
│       │   │   ├── server.py          # Phase 1 修改：挂载 /meshes 静态路由
│       │   │   ├── api.py             # Phase 1 修改：添加 /api/v1/urdf 接口
│       │   │   └── static/lab3d/      # Phase 1 新建：Three.js 前端
│       │   │       ├── package.json
│       │   │       ├── lab3d.html
│       │   │       ├── urdf-scene.js
│       │   │       ├── ros-bridge.js
│       │   │       └── main.js
│       │   └── device_mesh/
│       │       └── resource_visalization.py  # Phase 1 修改：bridge 启动 + URDF 转换
│       ├── scripts/
│       │   └── generate_collision_meshes.py  # Phase 1 新建：碰撞 mesh 生成
│       └── Ubuntu-DevEnv-Setup-Guide.md      # 本文档
│
└── foxglove-studio                    # Foxglove Studio 桌面版（可选）
```

---

**完成所有配置后，即可按照 `Uni-Lab-3D-Phase1-Guide.md` 开始 Phase 1 的代码开发工作。**
