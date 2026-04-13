# Matterix 复现指南（Windows 10 + RTX 4090）

## 环境信息

| 项目 | 版本 |
|------|------|
| 操作系统 | Windows 10 |
| GPU | NVIDIA RTX 4090 |
| CUDA 驱动 | 13.1 |
| Isaac Sim | 5.0.0（通过 pip 安装，见下方） |
| Isaac Lab | 2.3.0 |
| Python | 3.11 |
| 包管理器 | Miniforge3 / conda |

> **注意**：如果你已有 Isaac Sim 5.1.0 独立安装版，与本流程安装的 pip 版 Isaac Sim 5.0.0 互不冲突，可以共存。

---

## 前置准备

### 1. 安装 Miniforge3（conda）

前往 [Miniforge 官方发布页](https://github.com/conda-forge/miniforge/releases) 下载 Windows 版安装程序，安装后打开 **Miniforge Prompt**。

### 2. 确认 Git 和 Git LFS 已安装

```powershell
git --version
git lfs version
```

如果没有 Git LFS，前往 [git-lfs.github.com](https://git-lfs.github.com) 下载安装，然后执行：

```powershell
git lfs install
```

---

## 安装步骤

### 第一步：创建 conda 隔离环境

```powershell
conda create -n matterix python=3.11 -y
conda activate matterix
pip install --upgrade pip
```

### 第二步：安装 PyTorch（CUDA 12.8）

```powershell
pip install -U torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
```

### 第三步：安装 Isaac Lab 2.3.0（含 Isaac Sim 5.0.0）

> 此步骤会从 `pypi.nvidia.com` 下载约 10–20 GB 内容，需要确保网络可以访问 NVIDIA PyPI。

**预先修复构建工具**（避免后续报错）：

```powershell
conda install -c conda-forge setuptools -y
pip install --upgrade setuptools wheel pip
```

**安装 `flatdict`**（isaaclab 的依赖项，需特殊处理）：

```powershell
conda install -c conda-forge flatdict -y
```

如果 conda-forge 中没有 flatdict，改用：

```powershell
pip install flatdict --no-build-isolation --no-cache-dir
```

**安装 Isaac Lab**：

```powershell
pip install isaaclab[isaacsim,all]==2.3.0 --extra-index-url https://pypi.nvidia.com
```

**验证安装**：

```powershell
pip show isaaclab
# 应显示 Version: 2.3.0
```

### 第四步：克隆 Matterix 仓库

在 Windows 上重新克隆（**必须带子模块**）：

```powershell
git clone --recurse-submodules https://github.com/ac-rad/Matterix.git
cd Matterix
```

如果已经克隆但子模块为空：

```powershell
git submodule update --init --recursive
```

### 第五步：拉取 USD 资产文件（子模块 + LFS）

```powershell
git submodule foreach "git lfs pull"
```

验证资产文件存在：

```powershell
dir source\matterix_assets\data
# 应看到 labware\、robots\、infrastructure\ 等目录
```

### 第六步：安装 Matterix 四个子包

```powershell
conda activate matterix
cd Matterix
pip install -e source/*
```

此命令会按依赖顺序安装：
1. `matterix_sm`（状态机，可独立使用）
2. `matterix_assets`（资产库）
3. `matterix_tasks`（任务定义）
4. `matterix`（核心框架）

### 第七步：设置环境变量

```powershell
# 临时设置（当前会话有效）
$env:MATTERIX_PATH = "C:\你的路径\Matterix"

# 永久设置（推荐，重启后依然有效）
[System.Environment]::SetEnvironmentVariable("MATTERIX_PATH", "C:\你的路径\Matterix", "User")
```

将 `C:\你的路径\Matterix` 替换为实际克隆路径，例如 `C:\Users\Administrator\Matterix`。

---

## 验证安装

### 列出所有可用任务

```powershell
conda activate matterix
cd Matterix
python scripts\list_envs.py
```

### 零动作测试（最快验证方式）

```powershell
python scripts\zero_agent.py --task Matterix-Test-Beakers-Franka-v1 --num_envs 1
```

成功后应看到 Isaac Sim 启动，场景中有两条 Franka 机械臂、5 个烧杯和两张桌子。

### 随机动作测试

```powershell
python scripts\random_agent.py --task Matterix-Test-Beakers-Franka-v1 --num_envs 1
```

### 工作流测试

```powershell
# 列出可用工作流
python scripts\list_workflows.py --task Matterix-Test-Beaker-Lift-Franka-v1

# 运行抓取工作流（4 个并行环境）
python scripts\run_workflow.py --task Matterix-Test-Beaker-Lift-Franka-v1 --workflow pickup_beaker --num_envs 4
```

---

## 常见报错与解决方案

### 问题 1：SSL 证书错误，pypi.nvidia.com 无法访问

**报错特征**：
```
[SSL: UNEXPECTED_EOF_WHILE_READING]
Could not find a version that satisfies the requirement isaaclab==2.3.0 (from versions: none)
```

**解决方案**：
1. 确保网络可访问境外服务（需科学上网）
2. 设置代理后重试：
   ```powershell
   pip install isaaclab[isaacsim,all]==2.3.0 --extra-index-url https://pypi.nvidia.com --proxy http://127.0.0.1:7890
   ```
   （端口号换成你实际代理端口）

---

### 问题 2：ModuleNotFoundError: No module named 'pkg_resources'

**报错特征**：
```
ModuleNotFoundError: No module named 'pkg_resources'
ERROR: Failed to build 'flatdict' when getting requirements to build wheel
```

**原因**：`flatdict` 没有预编译 wheel，需从源码构建，但 pip 的隔离子进程里缺少 `setuptools`。

**解决方案**：

```powershell
# 方案 A：用 conda 安装（推荐）
conda install -c conda-forge flatdict -y

# 方案 B：绕过构建隔离
conda install -c conda-forge setuptools -y
pip install flatdict --no-build-isolation --no-cache-dir

# 方案 C：安装旧版本（有预编译 wheel）
pip install "flatdict<4.0.0"
```

装完后重新执行 Isaac Lab 安装命令。

---

### 问题 3：'Looking' 不是内部或外部命令

**原因**：误将 pip 的输出信息当成命令执行了。

**解决方案**：只运行真正的命令，不要复制 pip 的输出内容。

---

### 问题 4：环境变量未设置

**报错特征**：
```
OSError: Environment variable MATTERIX_PATH is not set.
```

**解决方案**：
```powershell
[System.Environment]::SetEnvironmentVariable("MATTERIX_PATH", "C:\你的路径\Matterix", "User")
# 重新打开 Miniforge Prompt 后生效
```

---

### 问题 5：data 子模块为空，USD 文件缺失

**报错特征**：运行时找不到 USD 文件路径。

**解决方案**：
```powershell
cd Matterix
git submodule update --init --recursive
git submodule foreach "git lfs pull"
```

---

## 目录结构说明

```
Matterix/
├── source/
│   ├── matterix/              # 核心框架（粒子系统、MDP 环境）
│   ├── matterix_assets/       # 资产配置
│   │   └── data/              # USD 模型文件（子模块，需单独拉取）
│   ├── matterix_sm/           # 状态机
│   └── matterix_tasks/        # 任务定义
├── scripts/
│   ├── zero_agent.py          # 零动作验证
│   ├── random_agent.py        # 随机动作验证
│   ├── run_workflow.py        # 运行工作流
│   ├── list_envs.py           # 列出任务
│   ├── list_workflows.py      # 列出工作流
│   └── rsl_rl/skrl/rl_games/sb3/  # RL 训练脚本
├── docker/                    # Docker + ROS2 部署配置
├── REPO_OVERVIEW.md           # 仓库介绍
└── REPRODUCTION_GUIDE.md      # 本文件
```

---

## 网络说明（中国大陆用户）

以下资源在国内可能需要科学上网：

| 资源 | 说明 |
|------|------|
| `pypi.nvidia.com` | Isaac Lab / Isaac Sim pip 包，**必须能访问** |
| `github.com` | 仓库克隆 |
| `objects.githubusercontent.com` | Git LFS 文件下载 |
| `pypi.org` | 普通 pip 包（可用国内镜像替代） |

普通 pip 包可配置清华镜像加速：

```powershell
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

但 `--extra-index-url https://pypi.nvidia.com` 这一条**不能**替换为国内镜像，必须直连 NVIDIA 服务器。
