# Isaac Stable Drive UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add runtime stable drive tuning for MVPpkushengke joints and make Collision ON/OFF visibly distinct in the Isaac UI.

**Architecture:** Keep the USD asset unchanged by applying stable drive parameters at runtime through the Isaac worker adapter. Expose the same core operation through `JointControlService`, worker RPC, and an Isaac UI button; keep the collision mode visible through a dedicated status model.

**Tech Stack:** Python 3.11, Isaac Sim USD/DriveAPI, pytest, UniLabOS Isaac worker RPC.

---

### Task 1: Core Stable Drive API

**Files:**
- Modify: `unilabos/sim/backends/isaac/joint_control.py`
- Test: `tests/sim/backends/test_isaac_joint_control.py`

- [ ] Write failing tests for `apply_stable_drive_settings()` returning per-joint settings and exposing `drive_tuning` in state.
- [ ] Implement `DEFAULT_STABLE_DRIVE_SETTINGS`, adapter protocol method, and service method.
- [ ] Run `python3 -m pytest tests/sim/backends/test_isaac_joint_control.py -q`.

### Task 2: Worker RPC And Isaac UI

**Files:**
- Modify: `unilabos/sim/backends/isaac/worker.py`
- Modify: `unilabos/sim/backends/isaac_bridge.py`
- Test: `tests/sim/backends/test_isaac_worker_protocol.py`
- Test: `tests/sim/backends/test_isaac_bridge.py`

- [ ] Write failing tests for `apply_stable_drive_settings` RPC and UI collision-mode text.
- [ ] Implement worker/controller/adapter drive application and auto-apply on scene load.
- [ ] Add `Apply Stable Drive` UI button and visible collision mode model.
- [ ] Run Isaac backend tests locally and on the 4090.

### Task 3: 4090 Deployment Verification

**Files:**
- Remote sync target: `/home/ubuntu/Uni-Lab-OS-managed-codex`

- [ ] Sync changed files with `rsync`.
- [ ] Run server tests in `matterix`.
- [ ] Restart edge/worker on ports `8008/8098/50058`.
- [ ] Verify RPC reports stable drive settings and no new crash logs.
