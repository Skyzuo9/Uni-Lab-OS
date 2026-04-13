import * as THREE from 'three';

/**
 * 耗材位姿追踪器。
 * 后端 ResourceMeshManager 已经：
 * 1. 实现了 tf_update Action（attach/detach 到 PlanningScene）
 * 2. 以 50Hz 发布 resource_pose 话题（JSON 格式位姿变化）
 *
 * 本模块只需订阅该话题，更新 Three.js mesh 位置。
 */
export class ResourceTracker {
    constructor(scene, rosBridge) {
        this.scene = scene;
        this.bridge = rosBridge;
        this.meshes = new Map();      // resourceId -> THREE.Mesh
        this.attachState = new Map();  // resourceId -> parentFrame
    }

    /**
     * 注册可追踪的耗材。
     * 在 URDF 加载后调用，从 scene 中查找对应 mesh。
     */
    registerResources(resourceIds) {
        for (const id of resourceIds) {
            const obj = this.scene.getObjectByName(id);
            if (obj) {
                this.meshes.set(id, obj);
            }
        }
        console.log(`[ResourceTracker] registered ${this.meshes.size} resources`);
    }

    /**
     * 开始监听 resource_pose 话题。
     */
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

            // resource_pose 有两种格式：
            // 1. resource_pose 模式: { position: {x,y,z}, rotation: {x,y,z,w} }
            // 2. resource_status 模式: 直接是 parent_frame 字符串
            if (typeof poseOrParent === 'object' && poseOrParent.position) {
                const p = poseOrParent.position;
                const r = poseOrParent.rotation;
                mesh.position.set(p.x, p.y, p.z);
                if (r) mesh.quaternion.set(r.x, r.y, r.z, r.w);
            }

            // 附着状态追踪（用于视觉反馈）
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
