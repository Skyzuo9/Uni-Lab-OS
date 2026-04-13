import * as THREE from 'three';

/**
 * 设备状态实时着色。
 * 订阅 FastAPI /ws/device_status WebSocket（已有，1Hz 推送）。
 * 根据状态改变设备 mesh 的发光颜色。
 */

const STATUS_COLORS = {
    idle:       0x888888,
    running:    0x2196F3,
    completed:  0x4CAF50,
    error:      0xF44336,
    warning:    0xFF9800,
};

export class StatusOverlay {
    constructor(scene) {
        this.scene = scene;
        this.ws = null;
        this.deviceMeshes = new Map();
    }

    registerDevices(deviceIds) {
        for (const id of deviceIds) {
            const mesh = this.scene.getObjectByName(id);
            if (mesh) this.deviceMeshes.set(id, mesh);
        }
        console.log(`[StatusOverlay] registered ${this.deviceMeshes.size} devices`);
    }

    connectWebSocket(baseUrl = '') {
        const host = baseUrl || window.location.host;
        const wsUrl = `ws://${host}/api/v1/ws/device_status`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'device_status') {
                    this._apply(msg.data.device_status);
                }
            } catch (e) { /* ignore */ }
        };

        this.ws.onclose = () => {
            setTimeout(() => this.connectWebSocket(baseUrl), 3000);
        };
    }

    _apply(statusMap) {
        for (const [deviceId, status] of Object.entries(statusMap)) {
            const mesh = this.deviceMeshes.get(deviceId);
            if (!mesh) continue;

            const color = STATUS_COLORS[status] || STATUS_COLORS.idle;
            const intensity = (status === 'idle') ? 0 : 0.3;

            mesh.traverse(child => {
                if (child.isMesh && child.material) {
                    child.material = child.material.clone();
                    if (child.material.emissive) {
                        child.material.emissive.setHex(color);
                        child.material.emissiveIntensity = intensity;
                    }
                }
            });
        }
    }

    /** 手动设置状态（测试用） */
    setStatus(deviceId, status) {
        this._apply({ [deviceId]: status });
    }
}
