from types import SimpleNamespace

from unilabos.app.ws_client import HostNode, JobInfo, JobStatus, WebSocketClient


def test_publish_collision_event_uses_schedule_action() -> None:
    client = WebSocketClient()
    sent: list[dict] = []
    client.message_processor.connected = True
    client.message_processor.send_message = lambda message: sent.append(message) or True

    assert client.publish_collision_event({"event_id": "col_1", "pairs": []}) is True
    assert sent == [
        {
            "action": "push_collision_event",
            "data": {"event_id": "col_1", "pairs": []},
        }
    ]


def test_collision_context_requires_unique_device_match() -> None:
    client = WebSocketClient()
    job = JobInfo(
        job_id="job-1",
        task_id="task-1",
        device_id="hor_horizon",
        notebook_id="notebook-1",
        action_name="run_collision_demo",
        device_action_key="hor_horizon/run_collision_demo",
        status=JobStatus.STARTED,
        start_time=1.0,
        node_id="node-1",
    )
    client.device_manager.active_jobs[job.device_action_key] = job
    client.device_manager.all_jobs[job.job_id] = job

    context = client.get_collision_workflow_context(["full_dev/hor_horizon", "fixture_box"])
    assert context["job_id"] == "job-1"
    assert context["task_id"] == "task-1"
    assert context["node_id"] == "node-1"
    assert context["action"] == "run_collision_demo"

    assert client.get_collision_workflow_context(["unrelated", "fixture_box"]) == {}


def test_report_all_action_locks_includes_json_command_actions(monkeypatch) -> None:
    client = WebSocketClient()
    sent: list[dict] = []
    client.message_processor.connected = True
    client.message_processor.send_message = lambda message: sent.append(message) or True
    fake_host = SimpleNamespace(
        devices_names={"virtual_hor_horizon": "/devices"},
        _action_value_mappings={
            "virtual_hor_horizon": {
                "run_collision_demo": {"type": "UniLabJsonCommand"},
                "_execute_driver_command": {"type": "StrSingleInput"},
            }
        },
    )
    monkeypatch.setattr(HostNode, "get_instance", classmethod(lambda cls, timeout=None: fake_host))

    client.report_all_action_locks()

    assert sent[-1]["action"] == "report_action_lock"
    assert sent[-1]["data"]["locks"] == [
        {
            "device_id": "virtual_hor_horizon",
            "action_name": "run_collision_demo",
            "free": True,
        }
    ]


def test_action_busy_tracks_started_job() -> None:
    client = WebSocketClient()
    key = "/devices/virtual_hor_horizon/run_collision_demo"
    job = JobInfo(
        job_id="job-2",
        task_id="task-2",
        device_id="virtual_hor_horizon",
        notebook_id="",
        action_name="run_collision_demo",
        device_action_key=key,
        status=JobStatus.STARTED,
        start_time=1.0,
    )
    client.device_manager.active_jobs[key] = job
    assert client.device_manager.is_action_busy(key) is True
