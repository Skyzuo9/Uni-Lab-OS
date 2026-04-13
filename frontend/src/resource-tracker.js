import * as THREE from 'three';

export class ResourceTracker {
  constructor(scene, rosBridge) {
    this.scene = scene;
    this.bridge = rosBridge;
    this.meshes = new Map();
    this.attachState = new Map();
  }

  registerResources(resourceIds) {
    for (const id of resourceIds) {
      const obj = this.scene.getObjectByName(id);
      if (obj) this.meshes.set(id, obj);
    }
    console.log(`[ResourceTracker] registered ${this.meshes.size} resources`);
  }

  startListening() {
    this.bridge.on('resource_pose', (msg) => {
      let changes;
      try {
        changes = typeof msg.data === 'string' ? JSON.parse(msg.data) : msg;
      } catch (e) { return; }
      this._applyPoseChanges(changes);
    });
  }

  _applyPoseChanges(changes) {
    for (const [resourceId, poseOrParent] of Object.entries(changes)) {
      const mesh = this.meshes.get(resourceId);
      if (!mesh) continue;
      if (typeof poseOrParent === 'object' && poseOrParent.position) {
        const p = poseOrParent.position;
        const r = poseOrParent.rotation;
        mesh.position.set(p.x, p.y, p.z);
        if (r) mesh.quaternion.set(r.x, r.y, r.z, r.w);
      }
      if (typeof poseOrParent === 'string') {
        const wasAttached = this.attachState.get(resourceId) !== 'world';
        const isAttached = poseOrParent !== 'world';
        this.attachState.set(resourceId, poseOrParent);
        if (isAttached !== wasAttached) {
          this._setAttachHighlight(mesh, isAttached);
        }
      }
    }
  }

  _setAttachHighlight(mesh, isAttached) {
    mesh.traverse(child => {
      if (child.isMesh && child.material) {
        if (isAttached) {
          child.material = child.material.clone();
          child.material.emissive = new THREE.Color(0x2196F3);
          child.material.emissiveIntensity = 0.3;
          child.material.transparent = true;
          child.material.opacity = 0.85;
        } else {
          child.material.emissiveIntensity = 0;
          child.material.transparent = false;
          child.material.opacity = 1.0;
        }
      }
    });
  }
}
