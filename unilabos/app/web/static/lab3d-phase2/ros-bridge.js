/**
 * ROS Bridge 模块（阶段二）。
 * 通过 Foxglove Bridge WebSocket 订阅 ROS2 话题。
 *
 * 支持的话题：
 * - /joint_states (sensor_msgs/JointState)
 * - /tf (tf2_msgs/TFMessage)
 * - resource_pose (std_msgs/String)
 * - /move_group/display_planned_path (moveit_msgs/DisplayTrajectory)
 */

export class RosBridge {
    constructor(foxgloveUrl = 'ws://localhost:8765') {
        this.url = foxgloveUrl;
        this.ws = null;
        this.callbacks = {};
        this.connected = false;
        this._reconnectTimer = null;
    }

    connect() {
        console.log('[RosBridge] 正在连接', this.url);

        try {
            this.ws = new WebSocket(this.url, ['foxglove.websocket.v1']);
        } catch (e) {
            console.error('[RosBridge] WebSocket 创建失败:', e);
            this._scheduleReconnect();
            return;
        }

        this.ws.binaryType = 'arraybuffer';

        this.ws.onopen = () => {
            console.log('[RosBridge] ✓ 已连接');
            this.connected = true;
        };

        this.ws.onmessage = (event) => {
            if (typeof event.data === 'string') {
                try {
                    const msg = JSON.parse(event.data);
                    this._handleServerMessage(msg);
                } catch (e) { /* ignore */ }
            }
        };

        this.ws.onclose = () => {
            console.log('[RosBridge] 连接断开，5s 后重连');
            this.connected = false;
            this._scheduleReconnect();
        };

        this.ws.onerror = (e) => {
            console.error('[RosBridge] 错误:', e);
        };
    }

    _scheduleReconnect() {
        if (this._reconnectTimer) return;
        this._reconnectTimer = setTimeout(() => {
            this._reconnectTimer = null;
            this.connect();
        }, 5000);
    }

    _handleServerMessage(msg) {
        if (msg.op === 'advertise') {
            this._subscribeToKnownTopics(msg.channels || []);
        }
    }

    _subscribeToKnownTopics(channels) {
        const topicsWeWant = [
            '/joint_states',
            '/tf',
            'resource_pose',
            '/move_group/display_planned_path',
        ];

        for (const ch of channels) {
            if (topicsWeWant.includes(ch.topic)) {
                const subMsg = JSON.stringify({
                    op: 'subscribe',
                    subscriptions: [{
                        id: ch.id,
                        channelId: ch.id,
                    }],
                });
                this.ws.send(subMsg);
                console.log(`[RosBridge] 已订阅 ${ch.topic}`);
            }
        }
    }

    /**
     * 注册话题回调。
     * @param {string} topic - 话题名
     * @param {Function} callback - 回调函数，参数为解析后的消息对象
     */
    on(topic, callback) {
        if (!this.callbacks[topic]) this.callbacks[topic] = [];
        this.callbacks[topic].push(callback);
    }

    _dispatch(topic, data) {
        (this.callbacks[topic] || []).forEach(cb => {
            try { cb(data); } catch (e) { console.error(e); }
        });
    }

    disconnect() {
        if (this.ws) this.ws.close();
    }
}
