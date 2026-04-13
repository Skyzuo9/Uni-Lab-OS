export class RosBridge {
  constructor(foxgloveUrl = 'ws://localhost:8765') {
    this.url = foxgloveUrl;
    this.ws = null;
    this.callbacks = {};
    this.connected = false;
    this._reconnectTimer = null;
    this._channelMap = new Map();
    this._subId = 1;
    this._topicToSubId = new Map();
  }

  connect() {
    console.log('[RosBridge] connecting to', this.url);
    try {
      this.ws = new WebSocket(this.url, ['foxglove.websocket.v1']);
    } catch (e) {
      console.error('[RosBridge] WebSocket creation failed:', e);
      this._scheduleReconnect();
      return;
    }

    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      console.log('[RosBridge] connected');
      this.connected = true;
    };

    this.ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        try {
          const msg = JSON.parse(event.data);
          this._handleJsonMessage(msg);
        } catch (e) { }
      } else if (event.data instanceof ArrayBuffer) {
        this._handleBinaryMessage(event.data);
      }
    };

    this.ws.onclose = () => {
      console.log('[RosBridge] disconnected, reconnecting in 5s');
      this.connected = false;
      this._scheduleReconnect();
    };

    this.ws.onerror = (e) => {
      console.error('[RosBridge] error:', e);
    };
  }

  _scheduleReconnect() {
    if (this._reconnectTimer) return;
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      this.connect();
    }, 5000);
  }

  _handleJsonMessage(msg) {
    if (msg.op === 'advertise') {
      this._onAdvertise(msg.channels || []);
    }
  }

  _onAdvertise(channels) {
    const topicsWeWant = [
      '/joint_states', '/tf', 'resource_pose',
      '/move_group/display_planned_path',
    ];
    for (const ch of channels) {
      this._channelMap.set(ch.id, { topic: ch.topic, schema: ch.schemaName });
      if (topicsWeWant.includes(ch.topic)) {
        const subId = this._subId++;
        this._topicToSubId.set(ch.topic, subId);
        this.ws.send(JSON.stringify({
          op: 'subscribe',
          subscriptions: [{ id: subId, channelId: ch.id }],
        }));
        console.log(`[RosBridge] subscribed: ${ch.topic}`);
      }
    }
  }

  _handleBinaryMessage(buffer) {
    const view = new DataView(buffer);
    const opcode = view.getUint8(0);
    if (opcode !== 0x01) return;
    const subId = view.getUint32(1, true);
    let topic = null;
    for (const [t, sid] of this._topicToSubId) {
      if (sid === subId) { topic = t; break; }
    }
    if (!topic) return;
    try {
      const payloadBytes = new Uint8Array(buffer, 13);
      const payloadStr = new TextDecoder().decode(payloadBytes);
      const data = JSON.parse(payloadStr);
      this._dispatch(topic, data);
    } catch (e) { }
  }

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
