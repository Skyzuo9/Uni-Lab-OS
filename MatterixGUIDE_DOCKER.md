# Matterix 复现指南 —— Docker 方式

## 适用环境 

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 20.04 / 22.04（Linux 原生，**不支持 Windows Docker Desktop**） |
| GPU | NVIDIA RTX 4090 |
| NVIDIA 驱动 | >= 525 |
| Docker | >= 24.0 |
| NVIDIA Container Toolkit | 最新版 |
| NGC 账号 | 需要（免费注册，用于拉取 Isaac Sim 镜像） |

## ⚠️ 重要说明：版本差异

项目 `docker/.env.base` 里配置的是 **Isaac Sim 4.5.0**，而主 README 要求 5.0.0。两者 API 有差异，Docker 方式目前存在**版本落后**的问题。

本指南提供两条路径：
- **路径 A**：使用原始配置（Isaac Sim 4.5.0），快速启动但可能与部分代码不兼容
- **路径 B**：修改配置后使用 Isaac Sim 5.0.0，与主代码匹配

---

## 第一步：安装 NVIDIA 驱动

```bash
# 检查是否已有驱动
nvidia-smi

# 没有则安装
sudo apt update
sudo ubuntu-drivers autoinstall
sudo reboot
```

---

## 第二步：安装 Docker

```bash
# 卸载旧版本（如果有）
sudo apt remove docker docker-engine docker.io containerd runc 2>/dev/null

# 安装 Docker Engine
curl -fsSL https://get.docker.com | sudo sh

# 将当前用户加入 docker 组（避免每次 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker --version
# Docker version 24.x.x 或更新
```

---

## 第三步：安装 NVIDIA Container Toolkit

这是让 Docker 容器能访问 GPU 的关键组件：

```bash
# 添加 NVIDIA 软件源
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 安装
sudo apt update
sudo apt install -y nvidia-container-toolkit

# 配置 Docker 使用 NVIDIA 运行时
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 验证（应能看到 GPU 信息）
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

---

## 第四步：注册 NGC 账号并获取 API Key

1. 前往 [https://ngc.nvidia.com](https://ngc.nvidia.com) 注册（免费）
2. 登录后点击右上角头像 → **Setup** → **Generate API Key**
3. 复制生成的 API Key（只显示一次，妥善保存）

登录 NVIDIA 容器镜像仓库：

```bash
docker login nvcr.io
# Username: $oauthtoken        ← 固定填这个，不是你的账号名
# Password: <你的 NGC API Key>
```

---

## 第五步：安装 Git 和 Git LFS

```bash
sudo apt install -y git git-lfs
git lfs install
```

---

## 第六步：克隆 Matterix 仓库

```bash
git clone --recurse-submodules https://github.com/ac-rad/Matterix.git
cd Matterix

# 拉取 USD 资产文件
git submodule foreach 'git lfs pull'
```

---

## 第七步：配置版本（二选一）

### 路径 A：使用原始配置（Isaac Sim 4.5.0）

无需修改，直接跳到第八步。但注意部分 5.0.0 的新 API 可能报错。

---

### 路径 B：修改为 Isaac Sim 5.0.0（推荐）

编辑 `docker/.env.base`，将版本号改为 5.0.0：

```bash
# 原始内容：ISAACSIM_VERSION=4.5.0
# 修改为：
sed -i 's/ISAACSIM_VERSION=4.5.0/ISAACSIM_VERSION=5.0.0/' docker/.env.base

# 验证修改
grep ISAACSIM_VERSION docker/.env.base
# ISAACSIM_VERSION=5.0.0
```

同时检查 NGC 上是否有 5.0.0 的镜像：

```bash
# 可用镜像版本列表
# https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-sim/tags
```

---

## 第八步：构建并启动容器

进入 docker 目录，使用 `container.py` 管理容器：

```bash
cd docker

# 构建镜像并启动容器（首次运行会下载 Isaac Sim 镜像，约 20-30 GB）
python3 container.py start base
```

> `start` 命令会：
> 1. 从 NGC 拉取 Isaac Sim 基础镜像
> 2. 在镜像上叠加 Matterix 的依赖（运行 `matterix.sh --install`）
> 3. 以 detached 模式启动容器

查看构建进度：

```bash
docker logs -f isaac-lab-base
```

---

## 第九步：进入容器

```bash
# 在 docker/ 目录下执行
python3 container.py enter base
```

进入后，终端提示符会变为容器内的 root shell：

```
root@hostname:/workspace/MATTERIX#
```

容器内已预设别名：
- `python` → Isaac Sim 的 Python
- `pip` → Isaac Sim 的 pip

---

## 第十步：容器内验证安装

```bash
# 列出可用任务
python scripts/list_envs.py

# 无头模式零动作测试（容器内无显示，必须加 --headless）
python scripts/zero_agent.py \
    --task Matterix-Test-Beakers-Franka-v1 \
    --num_envs 1 \
    --headless

# 工作流测试
python scripts/run_workflow.py \
    --task Matterix-Test-Beaker-Lift-Franka-v1 \
    --workflow pickup_beaker \
    --num_envs 4 \
    --headless
```

---

## 容器管理命令

```bash
# 进入 docker/ 目录后执行以下命令

# 启动容器
python3 container.py start base

# 进入已启动的容器
python3 container.py enter base

# 停止并删除容器
python3 container.py stop base

# 查看当前 docker-compose 配置
python3 container.py config base

# 从容器复制构建产物到宿主机
python3 container.py copy base
```

---

## 带 ROS2 的容器（可选）

如果需要真实机器人部署，使用 ROS2 版本：

```bash
# 启动带 ROS2 Humble 的容器
python3 container.py start ros2

# 进入
python3 container.py enter ros2
```

---

## 图形界面（可选，宿主机有显示器时）

容器默认以无头模式运行。如果宿主机连了显示器，可以启用 X11 转发查看 Isaac Sim GUI：

```bash
# 在宿主机上允许 Docker 访问 X11
xhost +local:docker

# container.py 会自动检测 X11 并配置转发
python3 container.py start base
```

---

## 挂载说明：代码修改即时生效

`docker-compose.yaml` 中已配置 bind mount：

```yaml
- type: bind
  source: ../source      # 宿主机的 source/ 目录
  target: /workspace/MATTERIX/source  # 容器内路径

- type: bind
  source: ../scripts
  target: /workspace/MATTERIX/scripts
```

这意味着：**在宿主机上修改 `source/` 或 `scripts/` 里的代码，容器内立即生效**，无需重建镜像。

---

## 常见问题

### docker login 失败

```bash
# 确认用户名是 $oauthtoken（字面量，不是变量）
docker login nvcr.io -u '$oauthtoken' -p <你的API Key>
```

### 构建时提示找不到镜像

```bash
# 检查 .env.base 里的版本号是否在 NGC 上存在
# 前往 https://catalog.ngc.nvidia.com/orgs/nvidia/containers/isaac-sim/tags 查看
```

### 容器启动后 GPU 不可用

```bash
# 容器内检查
nvidia-smi

# 若报错，检查宿主机
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
# 若这条也失败，重新安装 nvidia-container-toolkit 并重启 Docker
```

### 容器内 python 命令找不到

```bash
# 容器内的 python 通过 bashrc alias 设置
# 重新加载
source ~/.bashrc
python --version
```

### NGC 在中国大陆无法访问

需要代理。在宿主机上配置好代理后，Docker pull 也会走代理：

```bash
# 设置 Docker 走代理
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/proxy.conf << EOF
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1"
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker
```

---

## Docker 方式 vs 直装方式对比

| 对比项 | Docker | Ubuntu 直装 |
|--------|--------|-------------|
| 环境隔离 | ✅ 完全隔离，不污染宿主机 | ⚠️ 共享宿主机环境（conda 隔离） |
| 安装难度 | ⚠️ 需要 NGC 账号，配置略多 | ✅ 流程更直接 |
| 代码修改 | ✅ bind mount，改了立即生效 | ✅ -e 安装，改了立即生效 |
| 图形界面 | ⚠️ 需要配置 X11 转发 | ✅ 直接显示 |
| Isaac Sim 版本 | ⚠️ 当前配置为 4.5.0（需手动改为 5.0.0） | ✅ pip 安装精确为 5.0.0 |
| 镜像大小 | ⚠️ 约 20–30 GB | ✅ pip 按需下载 |
| 集群部署 | ✅ 支持 Slurm/PBS/Singularity | ❌ 需要额外配置 |
| 推荐场景 | 多人协作、CI/CD、集群训练 | 个人开发、快速验证 |
