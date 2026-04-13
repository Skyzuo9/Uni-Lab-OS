# 安装指令详解：每一步为什么这样做

本文档对 `REPRODUCTION_GUIDE.md` 中每一条安装指令的**背景原因、解决的问题、以及不这样做会发生什么**做详细说明。

---

## 前置准备

---

### 为什么要用 Miniforge3 而不是直接用系统 Python？

```powershell
# 你已有系统 Python 3.11，为什么还要装 conda？
conda create -n matterix python=3.11 -y
conda activate matterix
```

**根本原因：依赖隔离**

Isaac Sim + Isaac Lab 会安装数百个依赖包，版本要求非常严格（例如指定 `torch==2.7.0`、`numpy` 特定版本等）。如果直接装进系统 Python：

- 可能与你已有的其他项目的依赖冲突（版本撞车）
- 一旦出问题，整个系统 Python 环境就坏了，难以恢复
- Isaac Sim 需要 Python **精确为 3.11**，系统 Python 版本难以保证

conda 创建的虚拟环境是一个完全隔离的沙盒，`conda activate matterix` 之后所有的 `python`、`pip` 命令都只作用在这个沙盒里，不影响系统其他部分。

**为什么选 Miniforge 而不是 Anaconda？**

Miniforge 默认使用 `conda-forge` 频道，包更新更及时，并且不含商业授权限制（Anaconda 的默认频道对商业用途有付费要求）。本项目后续需要从 `conda-forge` 安装 `setuptools` 和 `flatdict`，用 Miniforge 更顺畅。

---

### 为什么需要 `pip install --upgrade pip`？

```powershell
pip install --upgrade pip
```

**解决的问题：旧版 pip 的兼容性缺陷**

conda 新建环境时自带的 pip 版本可能较旧（如 22.x）。旧版 pip 在处理以下情况时容易出错：

- `pyproject.toml` 构建系统（较新的包格式）
- `--extra-index-url` 与主 index 的优先级逻辑
- SSL 握手重试策略

升级到最新 pip（24.x+）可以避免一类和包格式、索引解析相关的莫名报错。

---

## 第二步：安装 PyTorch

---

### 为什么指定 `torch==2.7.0` 和 `--index-url https://download.pytorch.org/whl/cu128`？

```powershell
pip install -U torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
```

**原因一：版本锁定，避免与 Isaac Lab 冲突**

Isaac Lab 2.3.0 在内部对 PyTorch 的版本有硬性依赖。如果先装错版本的 PyTorch（比如 `torch==2.5.0`），后续安装 Isaac Lab 时 pip 会尝试重新安装/降级 PyTorch，导致：
- 重复下载几 GB 的文件
- 或者版本冲突导致安装失败

提前锁定版本可以一步到位，节省时间。

**原因二：`cu128` 是 CUDA 12.8 的 PyTorch 构建**

PyTorch 官方为不同 CUDA 版本分别编译了二进制包：
- `cu121` → CUDA 12.1 版本的 PyTorch
- `cu124` → CUDA 12.4 版本的 PyTorch
- `cu128` → CUDA 12.8 版本的 PyTorch（本项目 README 指定）

你的 GPU 驱动支持 CUDA 13.1，**CUDA 驱动向下兼容**，所以驱动 13.1 完全可以运行 CUDA 12.8 编译的程序。如果装成 `cpu` 版本的 PyTorch，Isaac Sim 的 GPU 仿真加速就无法使用了。

**`--index-url` 而不是 `--extra-index-url` 的原因**

这里用的是 `--index-url`（替换主索引），而不是 `--extra-index-url`（追加副索引）。因为 PyTorch 的 CUDA 版本包**只在 PyTorch 自己的 whl 服务器上**，标准 PyPI 上只有 CPU 版。用 `--index-url` 直接指向正确的源，避免 pip 先在 PyPI 找到 CPU 版然后下错。

---

## 第三步：安装 Isaac Lab（最复杂的步骤）

---

### 为什么要先修复构建工具？

```powershell
conda install -c conda-forge setuptools -y
pip install --upgrade setuptools wheel pip
```

**背景：pip 的构建隔离机制**

当 pip 安装一个**没有预编译 wheel 文件**的包（只有源码 `.tar.gz`）时，它会：

1. 创建一个临时的**隔离子进程环境**（Build Isolation）
2. 在这个隔离环境里安装构建工具（setuptools、wheel 等）
3. 用这些工具把源码编译成 wheel
4. 再把 wheel 装进你的主环境

问题在于，这个隔离子进程**从零开始创建**，不继承你主环境的任何包。如果 conda 新建环境时没有随 Python 一起装好 `setuptools`，隔离子进程就会因为找不到 `pkg_resources`（`setuptools` 的一部分）而失败。

```
# 你遇到的报错来自这个隔离子进程：
File "...\pip\_vendor\pyproject_hooks\_in_process\_in_process.py"
ModuleNotFoundError: No module named 'pkg_resources'
```

**为什么用 `conda install` 而不只用 `pip install`？**

在 conda 环境里，有些基础工具（如 `setuptools`）更适合用 conda 而不是 pip 来安装，原因是：
- conda 会同时处理 C 库等底层依赖
- conda 安装的包会被注册在 conda 的包数据库里，不会被 conda 的环境更新覆盖
- 混用两种方式时，conda 版本更稳定

---

### 为什么要单独先安装 `flatdict`？

```powershell
conda install -c conda-forge flatdict -y
```

**`flatdict` 是什么？**

`flatdict` 是 Isaac Lab 依赖链中的一个小型工具库，功能是把嵌套字典"拍平"成单层字典。它本身并不重要，但它是问题根源。

**为什么它特别麻烦？**

大多数流行 Python 包都会在 PyPI 上发布**预编译 wheel 文件**（`.whl`），pip 直接下载解压即可，无需任何构建工具。但 `flatdict 4.0.1` **只有源码包**（`.tar.gz`），必须在你的机器上现场编译。

编译过程依赖 `setup.py` → `setup.py` 依赖 `pkg_resources` → `pkg_resources` 在 pip 隔离子进程里找不到 → 报错。

这形成了一个死循环：
```
安装 isaaclab
  → 需要 flatdict
    → 需要编译 flatdict
      → 需要 pkg_resources
        → 隔离子进程里没有
          → 报错
```

**`conda install -c conda-forge flatdict` 为什么能解决？**

conda-forge 上的 `flatdict` 是**已经编译好的二进制包**，conda 直接解压安装，完全绕过 pip 的构建流程，自然不会触发 `pkg_resources` 的问题。

当后续 pip 安装 isaaclab 时，发现 `flatdict` 已经满足版本要求，直接跳过，不再尝试构建。

---

### `pip install isaaclab[isaacsim,all]==2.3.0` 中每个参数的含义

```powershell
pip install isaaclab[isaacsim,all]==2.3.0 --extra-index-url https://pypi.nvidia.com
```

| 部分 | 含义 |
|------|------|
| `isaaclab` | 包名 |
| `[isaacsim,all]` | 安装"extras"：`isaacsim` 表示同时安装 Isaac Sim 本体；`all` 表示安装全部可选依赖（如 RL 库接口、传感器等） |
| `==2.3.0` | 精确锁定版本，Isaac Sim 5.0 对应 Isaac Lab 2.3.x，版本错了整个框架可能无法运行 |
| `--extra-index-url https://pypi.nvidia.com` | 追加 NVIDIA 的私有 PyPI 作为**副索引**。`isaaclab` 和 `isaacsim` 这两个包**只在 NVIDIA 的服务器上**，标准 PyPI 上找不到，必须告诉 pip 去哪里找 |

**为什么是 `--extra-index-url` 而不是 `--index-url`？**

这里用"追加"而不是"替换"，因为 `isaaclab` 的其他普通依赖（numpy、scipy 等）还是要从标准 PyPI 获取。用 `--extra-index-url` 让 pip 同时查询两个来源：先查标准 PyPI，再查 NVIDIA 的源。

**为什么在中国大陆会失败？**

`pypi.nvidia.com` 未在国内备案，被防火长城干扰。SSL 握手在连接到这个服务器时被中断，导致 `[SSL: UNEXPECTED_EOF_WHILE_READING]` 错误，pip 无法获取包列表，自然报 `from versions: none`（连有哪些版本都不知道）。

---

## 第四步：克隆仓库

---

### 为什么要加 `--recurse-submodules`？

```powershell
git clone --recurse-submodules https://github.com/ac-rad/Matterix.git
```

**Git 子模块的工作方式**

Matterix 的 USD 资产文件（几何模型、材质等）体积庞大（可能达到数 GB），不直接存放在主仓库里，而是通过 **Git 子模块**机制引用另一个独立仓库（`AccelerationConsortium/Matterix_assets`）。

`.gitmodules` 文件记录了这个引用关系：
```
[submodule "source/matterix_assets/data"]
    path = source/matterix_assets/data
    url = https://github.com/AccelerationConsortium/Matterix_assets.git
```

如果只用 `git clone`（不加 `--recurse-submodules`），克隆完成后 `source/matterix_assets/data/` 目录会存在但是**空的**——只有一个指向特定 commit 的指针，没有实际文件。后续运行仿真时找不到 USD 文件就会报路径错误。

`--recurse-submodules` 告诉 git：克隆完主仓库后，自动继续克隆所有子模块仓库，并 checkout 到主仓库指定的那个 commit。

---

## 第五步：拉取 USD 文件

---

### 为什么还需要 `git lfs pull`？

```powershell
git submodule foreach "git lfs pull"
```

**Git LFS 的工作方式**

即使子模块克隆成功，USD 文件也不一定真的下载下来了——这是因为 `.gitattributes` 里配置了 **Git LFS（Large File Storage）**：

```
*.usd  filter=lfs diff=lfs merge=lfs -text
*.usda filter=lfs diff=lfs merge=lfs -text
```

Git LFS 是一种大文件处理机制：
- 在 git 仓库里，大文件实际上只存储了一个**指针文件**（几十字节的文本，记录文件哈希值）
- 真正的大文件存储在 LFS 服务器（通常是 GitHub 的 LFS 存储）上
- 只有执行 `git lfs pull` 时，才会真正把大文件从 LFS 服务器下载下来，替换掉本地的指针文件

`git submodule foreach "..."` 表示对每个子模块分别执行引号里的命令，等价于进入每个子模块目录执行 `git lfs pull`。

**如果不执行这步会怎样？**

`data/labware/beaker500ml/beaker-500ml.usda` 等文件会存在，但内容只是一个 120 字节左右的文本（LFS 指针），而不是真正的 USD 场景文件。Isaac Sim 尝试加载时会解析失败，报 USD 格式错误。

---

## 第六步：安装 Matterix 子包

---

### 为什么用 `pip install -e`（可编辑模式）而不是普通安装？

```powershell
pip install -e source/*
```

**`-e`（editable）模式的含义**

普通 `pip install` 会把包的源码**复制**到 Python 环境的 `site-packages` 目录里。之后如果你修改了原始源码，Python 不会感知到，因为它用的是副本。

`-e` 模式不复制文件，而是在 `site-packages` 里创建一个**符号链接**（指向 `source/matterix/`、`source/matterix_sm/` 等），Python 直接从原始路径导入代码。

这样做的好处：
- **修改即时生效**：改了 `source/matterix_sm/matterix_sm/state_machine.py`，下次 `import matterix_sm` 就会用新版本，无需重新安装
- **调试方便**：可以直接在源码里加断点、打印调试信息
- **符合开发惯例**：Matterix 是一个研究项目，你大概率需要修改代码来适配自己的实验

**`source/*` 的展开规则**

`source/*` 会被 shell 展开为 `source/` 目录下所有的子目录，实际效果等同于：

```powershell
pip install -e source/matterix_sm
pip install -e source/matterix_assets
pip install -e source/matterix_tasks
pip install -e source/matterix
```

pip 会根据每个包的 `pyproject.toml` 或 `setup.py` 中声明的依赖关系，自动决定安装顺序（`matterix` 依赖 `matterix_sm`，所以 `matterix_sm` 先装）。

---

## 第七步：设置环境变量

---

### 为什么 Matterix 需要 `MATTERIX_PATH`？

```powershell
[System.Environment]::SetEnvironmentVariable("MATTERIX_PATH", "C:\...\Matterix", "User")
```

**原因：资产路径无法硬编码**

`source/matterix_assets/matterix_assets/constants.py` 里有：

```python
MATTERIX_PATH = os.getenv("MATTERIX_PATH")
MATTERIX_ASSETS_DATA_DIR = os.path.join(MATTERIX_PATH, "source/matterix_assets/data")
```

整个资产系统的 USD 路径都基于这个变量构建，比如：
```python
usd_path = f"{MATTERIX_ASSETS_DATA_DIR}/labware/beaker500ml/beaker-500ml.usda"
```

为什么不用相对路径或 `__file__`？因为安装包后，Python 导入 `matterix_assets` 时，`__file__` 指向的是 conda 环境中的路径，而不是你克隆仓库的路径。用环境变量让用户显式指定仓库根目录，是解决这个问题最简洁的方式。

**两种设置方式的区别**

```powershell
# 临时：只对当前 PowerShell 窗口有效，关掉就没了
$env:MATTERIX_PATH = "C:\...\Matterix"

# 永久：写入 Windows 注册表的用户环境变量，重启后依然有效
[System.Environment]::SetEnvironmentVariable("MATTERIX_PATH", "C:\...\Matterix", "User")
```

第三个参数 `"User"` 表示写入当前用户的环境变量（不需要管理员权限）；如果改成 `"Machine"` 则是写入系统级环境变量（需要管理员权限，对所有用户生效）。

---

## 整体依赖关系图

```
RTX 4090 显卡驱动（CUDA 13.1）
    └── 兼容运行 CUDA 12.8 编译的程序
            └── PyTorch 2.7.0 (cu128)
                    └── Isaac Sim 5.0.0 (通过 isaaclab[isaacsim] 安装)
                            └── Isaac Lab 2.3.0
                                    └── Matterix 四个子包
                                            └── USD 资产文件 (Git LFS 子模块)
```

每一层都对上一层有版本绑定，这也是为什么每个步骤都要精确指定版本号——任何一层用了不匹配的版本，整个栈就可能无法正常运行。

---

## 遇到的问题汇总与根本原因

| 报错 | 根本原因 | 解决思路 |
|------|---------|---------|
| `SSL: UNEXPECTED_EOF_WHILE_READING` | `pypi.nvidia.com` 被防火长城干扰，SSL 握手中断 | 使用代理/科学上网让流量绕过封锁 |
| `No module named 'pkg_resources'` | pip 构建隔离子进程里没有 `setuptools`，conda 新建环境不自带 | 用 conda 安装 `setuptools` 或直接用 conda 安装 `flatdict` 跳过构建 |
| `Failed to build 'flatdict'` | `flatdict 4.0.1` 无预编译 wheel，必须从源码构建，而构建环境缺工具 | 改用 conda 安装已编译好的二进制包 |
| `'Looking' 不是内部命令` | 误把 pip 的**输出内容**当成命令输入 | 只执行真正的命令行，不复制 pip 的日志输出 |
| `MATTERIX_PATH is not set` | 未配置环境变量，资产路径无法解析 | 用 `SetEnvironmentVariable` 永久写入用户环境变量 |
| `data/` 目录为空 | git clone 未带 `--recurse-submodules`，或 LFS 文件未拉取 | 补执行 `git submodule update` 和 `git lfs pull` |
