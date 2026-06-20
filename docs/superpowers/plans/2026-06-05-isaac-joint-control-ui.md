# Isaac Sim Joint Control UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Isaac-worker-owned joint control core, RPC API, and optional Isaac Sim UI for `MVPpkushengke.usd` joint target planning, collision checking, and safe execution.

**Architecture:** Keep the pure planning/state machine in `unilabos/sim/backends/isaac/joint_control.py`, then adapt Isaac-specific USD/PhysX/UI calls in `worker.py`. UI and RPC call the same `JointControlService`; edge only passes CLI options and exposes bridge methods.

**Tech Stack:** Python 3.11, pytest, Isaac Sim 5.1 runtime APIs loaded lazily, existing worker HTTP JSON RPC.

---

### Task 1: Pure Joint Control Service

**Files:**
- Create: `unilabos/sim/backends/isaac/joint_control.py`
- Test: `tests/sim/backends/test_isaac_joint_control.py`

- [ ] **Step 1: Write failing tests**

Cover default joint discovery, unit/limit validation, linear interpolation, check-before-execute gating, unsafe collision rejection, and stop state.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/sim/backends/test_isaac_joint_control.py -q`
Expected: import failure for `unilabos.sim.backends.isaac.joint_control`.

- [ ] **Step 3: Implement pure service**

Add dataclasses for `JointSpec`, `JointState`, `PlanOptions`, `TrajectoryPlan`, `CollisionCheckResult`, `ExecutionResult`; implement `JointControlService` with injected adapter.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/sim/backends/test_isaac_joint_control.py -q`
Expected: pass.

### Task 2: Worker RPC Wiring

**Files:**
- Modify: `unilabos/sim/backends/isaac/worker.py`
- Modify: `unilabos/sim/backends/isaac_bridge.py`
- Test: `tests/sim/backends/test_isaac_worker_protocol.py`
- Test: `tests/sim/backends/test_isaac_bridge.py`

- [ ] **Step 1: Write failing tests**

Assert worker dispatch supports `list_joint_controls`, `get_joint_control_state`, `plan_joint_targets`, `check_joint_plan`, `execute_joint_plan`, and `stop_joint_motion`; assert bridge forwards those methods.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/sim/backends/test_isaac_worker_protocol.py tests/sim/backends/test_isaac_bridge.py -q`
Expected: missing dispatch/bridge methods.

- [ ] **Step 3: Implement RPC methods**

Wire `IsaacWorkerState._dispatch_direct` to `IsaacController` methods and add bridge wrappers.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/sim/backends/test_isaac_worker_protocol.py tests/sim/backends/test_isaac_bridge.py -q`
Expected: pass.

### Task 3: Managed CLI Option

**Files:**
- Modify: `unilabos/app/main.py`
- Modify: `unilabos/app/backend.py`
- Modify: `unilabos/sim/backends/isaac/managed.py`
- Test: `tests/sim/test_cli_runtime.py`
- Test: `tests/sim/backends/test_isaac_managed.py`
- Test: `tests/sim/test_backend_physics_configuration.py`

- [ ] **Step 1: Write failing tests**

Assert `--isaac_joint_control_ui` defaults false, parses true, and is passed to `ManagedIsaacWorkerConfig` and worker command as `--joint-control-ui`.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/sim/test_cli_runtime.py tests/sim/backends/test_isaac_managed.py tests/sim/test_backend_physics_configuration.py -q`
Expected: missing CLI/config fields.

- [ ] **Step 3: Implement option propagation**

Add the CLI flag, config field, backend mapping, and worker argument.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/sim/test_cli_runtime.py tests/sim/backends/test_isaac_managed.py tests/sim/test_backend_physics_configuration.py -q`
Expected: pass.

### Task 4: Isaac Adapter And UI

**Files:**
- Modify: `unilabos/sim/backends/isaac/worker.py`
- Test: `tests/sim/backends/test_isaac_worker_cli.py`

- [ ] **Step 1: Write failing tests**

Assert worker CLI accepts `--joint-control-ui`, and fake controller methods expose the joint control service without importing Isaac at test time.

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/sim/backends/test_isaac_worker_cli.py tests/sim/backends/test_isaac_worker_protocol.py -q`
Expected: missing CLI option/UI wiring.

- [ ] **Step 3: Implement lazy Isaac adapter and UI**

Add IsaacController adapter methods for USD DriveAPI read/write, conservative contact checking with fail-closed handling, and optional `omni.ui` window creation.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/sim/backends/test_isaac_worker_cli.py tests/sim/backends/test_isaac_worker_protocol.py -q`
Expected: pass.

### Task 5: Verification And 4090 Smoke

**Files:**
- Modify docs only if commands change.

- [ ] **Step 1: Run local target tests**

Run: `python3 -m pytest tests/sim/backends/test_isaac_joint_control.py tests/sim/backends/test_isaac_worker_protocol.py tests/sim/backends/test_isaac_bridge.py tests/sim/backends/test_isaac_worker_cli.py tests/sim/backends/test_isaac_managed.py tests/sim/test_cli_runtime.py tests/sim/test_backend_physics_configuration.py -q`

- [ ] **Step 2: Run syntax check**

Run: `PYTHONPYCACHEPREFIX=/tmp/unilabos-pycache python3 -m compileall -q unilabos/sim/backends/isaac unilabos/app/backend.py unilabos/app/main.py`

- [ ] **Step 3: Sync and test on 4090**

Use `rsync` to `/tmp/Uni-Lab-OS-managed-codex` and run the same pytest target under the 4090 `unilab` env.

- [ ] **Step 4: Run GUI smoke**

Launch managed non-headless worker with `--isaac_joint_control_ui` and `MVPpkushengke.usd`; verify `/health`, `list_joint_controls`, and Isaac window tree contains `UniLab Joint Control` or `Isaac Sim Python`.
