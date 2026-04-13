# Matterix 复现指南 —— Ubuntu 22.04 直装（推荐）

## 适用环境

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 22.04 LTS |
| GPU | NVIDIA RTX 4090 |
| CUDA 驱动 | >= 525（推荐最新版） |
| Python | 3.11（通过 conda 管理） |
| Isaac Sim | 5.0.0（通过 pip 自动安装） |
| Isaac Lab | 2.3.0 |

---

## 第零步：安装 NVIDIA 驱动和 CUDA

```bash
# 检查驱动是否已安装
nvidia-smi
# 若能看到 GPU 信息和 CUDA Version 则跳过此步
```

如果没有驱动，安装推荐驱动：

```bash
sudo apt update
sudo ubuntu-drivers autoinstall
sudo reboot
```

重启后验证：

```bash
nvidia-smi
# 应看到 RTX 4090 信息，CUDA Version >= 12.0
```

---

## 第一步：安装基础工具

```bash
sudo apt update && sudo apt install -y \
    git \
    git-lfs \
    curl \
    wget \
    build-essential
```

初始化 Git LFS（USD 模型文件需要）：

```bash
git lfs install
```

---

## 第二步：安装 Miniforge（conda）

```bash
# 下载安装脚本
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh

# 执行安装
bash Miniforge3-Linux-x86_64.sh -b -p $HOME/miniforge3

# 初始化 conda
$HOME/miniforge3/bin/conda init bash
source ~/.bashrc
```

验证：

```bash
conda --version
# conda 24.x.x 或更新
```

---

## 第三步：创建隔离环境

```bash
conda create -n matterix python=3.11 -y
conda activate matterix
pip install --upgrade pip setuptools wheel
```

验证 Python 路径正确（应指向 conda 环境）：

```bash
which python
# 输出应为 ~/miniforge3/envs/matterix/bin/python
```

---

## 第四步：安装 PyTorch（CUDA 12.8）

```bash
pip install -U torch==2.7.0 torchvision==0.22.0 \
    --index-url https://download.pytorch.org/whl/cu128
```

验证 GPU 可用：

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# 输出：True  NVIDIA GeForce RTX 4090
```

---

## 第五步：安装 Isaac Lab 2.3.0（含 Isaac Sim 5.0.0）

> 需要访问 `pypi.nvidia.com`，中国大陆需要代理。下载量约 10–20 GB，耐心等待。

```bash
pip install isaaclab[isaacsim,all]==2.3.0 \
    --extra-index-url https://pypi.nvidia.com
```

> 在 Ubuntu 上，Linux 原生有 gcc 等构建工具，`flatdict` 等包会**直接编译成功**，不会出现 Windows 上的 `pkg_resources` 错误。

验证：

```bash
pip show isaaclab
# Version: 2.3.0
```

---

## 第六步：克隆 Matterix 仓库

```bash
# 带子模块克隆（USD 资产文件在子模块里）
git clone --recurse-submodules https://github.com/ac-rad/Matterix.git
cd Matterix
```

如果已克隆但子模块为空：

```bash
git submodule update --init --recursive
```

---

## 第七步：拉取 USD 资产文件（Git LFS）

```bash
# 进入子模块目录拉取大文件
git submodule foreach 'git lfs pull'
```

验证文件存在：

```bash
ls source/matterix_assets/data/
# 应看到 labware/  robots/  infrastructure/ 等目录

ls source/matterix_assets/data/labware/beaker500ml/
# 应看到 .usda 文件（几百 KB 到几 MB，不是几十字节的指针文件）
```

---

## 第八步：安装 Matterix 四个子包

```bash
conda activate matterix
cd Matterix

# -e 可编辑模式安装（修改源码后无需重装）
pip install -e source/*
```

---

## 第九步：设置环境变量

`matterix.sh` 可以**自动完成这一步**：

```bash
cd ~/Matterix
bash matterix.sh --install
source ~/.bashrc
```

`matterix.sh --install` 会把 `export MATTERIX_PATH="~/Matterix"` 追加到 `~/.bashrc`，并完成 Isaac Lab 扩展的安装。

手动验证：

```bash
echo $MATTERIX_PATH
# 应输出 Matterix 的绝对路径
```

---

## 第十步：验证安装

### 列出所有任务

```bash
conda activate matterix
cd ~/Matterix
python scripts/list_envs.py
```

### 零动作测试（最快验证）

```bash
python scripts/zero_agent.py --task Matterix-Test-Beakers-Franka-v1 --num_envs 1
```

成功后 Isaac Sim 会启动，渲染出两条 Franka 机械臂 + 5 个烧杯 + 两张桌子的场景。

### 工作流测试

```bash
# 查看可用工作流
python scripts/list_workflows.py --task Matterix-Test-Beaker-Lift-Franka-v1

# 运行抓取工作流（4 个并行环境）
python scripts/run_workflow.py \
    --task Matterix-Test-Beaker-Lift-Franka-v1 \
    --workflow pickup_beaker \
    --num_envs 4
```

---

## 无头模式（服务器 / 无显示器）

如果机器没有接显示器，加 `--headless` 参数：

```bash
python scripts/zero_agent.py \
    --task Matterix-Test-Beakers-Franka-v1 \
    --num_envs 1 \
    --headless
```

---

## 常见问题

### pypi.nvidia.com 无法访问

```bash
# 使用代理（把端口换成实际代理端口）
pip install isaaclab[isaacsim,all]==2.3.0 \
    --extra-index-url https://pypi.nvidia.com \
    --proxy http://127.0.0.1:7890
```

### `MATTERIX_PATH is not set`

```bash
export MATTERIX_PATH=$(pwd)   # 在 Matterix 目录下执行
echo 'export MATTERIX_PATH=~/Matterix' >> ~/.bashrc
source ~/.bashrc
```

### USD 文件是几十字节的文本（LFS 指针未替换）

```bash
cd ~/Matterix
git submodule foreach 'git lfs pull'
```

### NVIDIA 驱动与 CUDA 版本不兼容

```bash
# 查看驱动支持的最高 CUDA 版本
nvidia-smi | grep "CUDA Version"

# 驱动版本对应关系（RTX 4090）
# 驱动 >= 525  →  CUDA 12.0+（满足要求）
# 驱动 >= 545  →  CUDA 12.3+
# 驱动 >= 560  →  CUDA 12.6+
```

---

## 每次使用前的标准流程

```bash
conda activate matterix
cd ~/Matterix
python scripts/run_workflow.py --task ... --workflow ... --num_envs ...
```
