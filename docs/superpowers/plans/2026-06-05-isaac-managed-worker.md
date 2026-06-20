# Isaac Managed Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a v1 managed Isaac mode where Uni-Lab-OS edge starts and owns the Isaac worker process before connecting the existing Isaac HTTP physics backend.

**Architecture:** Keep the existing manual worker path unchanged. Add a small Isaac worker process manager that builds the worker command, starts it, waits for `/health`, exposes the endpoint, and stops the process at edge shutdown. The manager is wired into `app/backend.py` before `build_physics_backend()` so `--physics isaac --isaac_managed` can inject `physics_endpoint`.

**Tech Stack:** Python 3.11, stdlib `subprocess`, `urllib.request`, argparse, pytest.

---

### Task 1: CLI Surface

**Files:**
- Modify: `unilabos/app/main.py`
- Modify: `tests/sim/test_cli_runtime.py`

- [ ] Add failing tests for `--isaac_managed`, `--isaac_host`, `--isaac_port`, `--isaac_conda_env`, `--isaac_conda_executable`, `--isaac_python`, `--isaac_log_path`, `--isaac_start_timeout`, `--isaac_headless`, `--isaac_camera`, and `--isaac_rpc_timeout_s`.
- [ ] Implement parser options after the existing physics options.
- [ ] Run `python -m pytest tests/sim/test_cli_runtime.py -q`.

### Task 2: Worker Process Manager

**Files:**
- Create: `unilabos/sim/backends/isaac/managed.py`
- Create: `tests/sim/backends/test_isaac_managed.py`

- [ ] Add failing tests for endpoint derivation, plain Python command construction, conda command construction for `matterix`, health polling, and shutdown behavior.
- [ ] Implement `ManagedIsaacWorkerConfig`, `ManagedIsaacWorker`, and `IsaacWorkerHealthError`.
- [ ] Run `python -m pytest tests/sim/backends/test_isaac_managed.py -q`.

### Task 3: Backend Startup Wiring

**Files:**
- Modify: `unilabos/app/backend.py`
- Modify: `tests/sim/test_backend_physics_configuration.py`

- [ ] Add failing tests proving `--isaac_managed` starts a manager, injects `physics_endpoint`, and rejects non-Isaac physics.
- [ ] Start the managed worker before `build_physics_backend()`, register cleanup with `atexit`, and stop it if runtime initialization fails.
- [ ] Run `python -m pytest tests/sim/test_backend_physics_configuration.py tests/sim/backends/test_factory.py -q`.

### Task 4: 4090 Usage Docs

**Files:**
- Modify: `docs/demo/phase2_isaac_e2e_4090.md`
- Modify: `docs/demo/phase2_isaac_project_summary.md`

- [ ] Add the managed edge command for `ubuntu@172.20.0.39`, using `--isaac_conda_env matterix`, `--isaac_port 8092`, and the existing LabUtopia USD path.
- [ ] Keep the existing manual runbook for fallback.

### Task 5: Verification

- [ ] Run `python -m pytest tests/sim/test_cli_runtime.py tests/sim/backends/test_isaac_managed.py tests/sim/test_backend_physics_configuration.py tests/sim/backends/test_factory.py -q`.
- [ ] Run `git diff --check`.
