import * as THREE from 'three';
import { getScene } from './scene-manager.js';

let workspaceMesh = null;
let deadZoneMesh = null;

export function drawWorkspace(armX, armY, maxReach, innerRadius) {
  const scene = getScene();
  removeWorkspace();

  const outerGeo = new THREE.CircleGeometry(maxReach, 64);
  const outerMat = new THREE.MeshBasicMaterial({
    color: 0x00c8ff, transparent: true, opacity: 0.12,
    side: THREE.DoubleSide, depthWrite: false,
  });
  workspaceMesh = new THREE.Mesh(outerGeo, outerMat);
  workspaceMesh.rotation.x = -Math.PI / 2;
  workspaceMesh.position.set(armX, 0.001, armY);
  scene.add(workspaceMesh);

  const ringGeo = new THREE.RingGeometry(maxReach - 0.003, maxReach, 64);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x00c8ff, transparent: true, opacity: 0.4,
    side: THREE.DoubleSide, depthWrite: false,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(armX, 0.002, armY);
  workspaceMesh.add(ring);

  if (innerRadius > 0) {
    const innerGeo = new THREE.CircleGeometry(innerRadius, 32);
    const innerMat = new THREE.MeshBasicMaterial({
      color: 0x1a1a2e, transparent: true, opacity: 0.7,
      side: THREE.DoubleSide, depthWrite: false,
    });
    deadZoneMesh = new THREE.Mesh(innerGeo, innerMat);
    deadZoneMesh.rotation.x = -Math.PI / 2;
    deadZoneMesh.position.set(armX, 0.003, armY);
    scene.add(deadZoneMesh);
  }
}

export function updateWorkspacePosition(armX, armY) {
  if (workspaceMesh) workspaceMesh.position.set(armX, 0.001, armY);
  if (deadZoneMesh) deadZoneMesh.position.set(armX, 0.003, armY);
}

export function removeWorkspace() {
  const scene = getScene();
  if (workspaceMesh) { scene.remove(workspaceMesh); workspaceMesh = null; }
  if (deadZoneMesh) { scene.remove(deadZoneMesh); deadZoneMesh = null; }
}

export function setWorkspaceVisible(visible) {
  if (workspaceMesh) workspaceMesh.visible = visible;
  if (deadZoneMesh) deadZoneMesh.visible = visible;
}
