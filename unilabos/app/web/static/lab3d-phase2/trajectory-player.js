import { updateJointState } from './urdf-scene.js';

/**
 * MoveIt2 轨迹预览播放器。
 * 订阅 /move_group/display_planned_path (DisplayTrajectory)，
 * 按时间戳线性插值逐帧回放规划动画。
 */
export class TrajectoryPlayer {
    constructor(robot, container) {
        this.robot = robot;
        this.trajectory = null;
        this.isPlaying = false;
        this.playbackSpeed = 1.0;
        this._startTime = 0;
        this._animFrameId = null;

        this._buildUI(container);
    }

    loadTrajectory(displayTrajectory) {
        const trajs = displayTrajectory.trajectory;
        if (!trajs || trajs.length === 0) return;

        const jt = trajs[0].joint_trajectory;
        if (!jt || !jt.points || jt.points.length === 0) return;

        this.trajectory = {
            jointNames: jt.joint_names,
            points: jt.points.map(pt => ({
                positions: pt.positions,
                timeFromStart: (pt.time_from_start?.sec || 0)
                    + (pt.time_from_start?.nanosec || 0) * 1e-9,
            })),
        };

        const total = this.trajectory.points.at(-1).timeFromStart;
        this._showPanel(total);
        console.log(`[TrajectoryPlayer] loaded ${this.trajectory.points.length} waypoints, ${total.toFixed(2)}s`);
    }

    /** 手动加载轨迹数据（测试用） */
    loadFromRawPoints(jointNames, points) {
        this.trajectory = { jointNames, points };
        this._showPanel(points.at(-1).timeFromStart);
    }

    play() {
        if (!this.trajectory) return;
        this.isPlaying = true;
        this._startTime = performance.now();
        this._loop();
        this._updateBtn(true);
    }

    pause() {
        this.isPlaying = false;
        if (this._animFrameId) cancelAnimationFrame(this._animFrameId);
        this._updateBtn(false);
    }

    _loop() {
        if (!this.isPlaying) return;

        const elapsed = (performance.now() - this._startTime) / 1000 * this.playbackSpeed;
        const total = this.trajectory.points.at(-1).timeFromStart;

        if (elapsed >= total) {
            this._applyFrame(this.trajectory.points.length - 1);
            this.pause();
            return;
        }

        const { index, alpha } = this._findSegment(elapsed);
        this._applyInterpolated(index, alpha);
        this._animFrameId = requestAnimationFrame(() => this._loop());
    }

    _findSegment(time) {
        const pts = this.trajectory.points;
        for (let i = 0; i < pts.length - 1; i++) {
            if (time >= pts[i].timeFromStart && time < pts[i + 1].timeFromStart) {
                const dur = pts[i + 1].timeFromStart - pts[i].timeFromStart;
                return { index: i, alpha: (time - pts[i].timeFromStart) / dur };
            }
        }
        return { index: pts.length - 1, alpha: 0 };
    }

    _applyInterpolated(index, alpha) {
        const pts = this.trajectory.points;
        const p0 = pts[index].positions;
        const p1 = pts[Math.min(index + 1, pts.length - 1)].positions;
        const interp = p0.map((v, i) => v + (p1[i] - v) * alpha);
        updateJointState({ name: this.trajectory.jointNames, position: interp });
    }

    _applyFrame(idx) {
        updateJointState({
            name: this.trajectory.jointNames,
            position: this.trajectory.points[idx].positions,
        });
    }

    _buildUI(container) {
        const div = document.createElement('div');
        div.id = 'traj-panel';
        div.style.cssText = 'position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.85);color:#fff;padding:10px 20px;border-radius:8px;display:none;align-items:center;gap:10px;z-index:100;font-family:monospace;';
        div.innerHTML = '<span style="color:#4fc3f7;font-weight:bold;">Trajectory Preview</span> '
            + '<button id="traj-play-btn" style="padding:4px 12px;cursor:pointer;border:none;border-radius:4px;background:#4fc3f7;">Play</button> '
            + '<select id="traj-speed" style="padding:2px;">'
            + '<option value="0.25">0.25x</option>'
            + '<option value="0.5">0.5x</option>'
            + '<option value="1" selected>1x</option>'
            + '<option value="2">2x</option>'
            + '</select> '
            + '<span id="traj-info"></span>';
        container.appendChild(div);

        div.querySelector('#traj-play-btn')?.addEventListener('click', () => {
            this.isPlaying ? this.pause() : this.play();
        });
        div.querySelector('#traj-speed')?.addEventListener('change', (e) => {
            this.playbackSpeed = parseFloat(e.target.value);
        });
    }

    _showPanel(totalTime) {
        const panel = document.getElementById('traj-panel');
        if (panel) {
            panel.style.display = 'flex';
            panel.querySelector('#traj-info').textContent = totalTime.toFixed(1) + 's';
        }
    }

    _updateBtn(playing) {
        const btn = document.getElementById('traj-play-btn');
        if (btn) btn.textContent = playing ? 'Pause' : 'Play';
    }
}
