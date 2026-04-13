import * as THREE from 'three';
import { getCamera, getRenderer, is3DMode } from './scene-manager.js';
import { getDeviceMeshes, updateDevicePosition } from './device-renderer.js';
import { updateWorkspacePosition } from './workspace-overlay.js';

let isDragging = false;
let dragDeviceId = null;
let dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
let dragOffset = new THREE.Vector3();
let raycaster = new THREE.Raycaster();
let mouse = new THREE.Vector2();

let onSelectCallback = null;
let onDragEndCallback = null;

export function initInteraction(domElement) {
  domElement.addEventListener('pointerdown', onPointerDown);
  domElement.addEventListener('pointermove', onPointerMove);
  domElement.addEventListener('pointerup', onPointerUp);
}

export function onSelect(cb) { onSelectCallback = cb; }
export function onDragEnd(cb) { onDragEndCallback = cb; }

function updateMouse(e) {
  const rect = getRenderer().domElement.getBoundingClientRect();
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
}

function raycastDevices() {
  raycaster.setFromCamera(mouse, getCamera());
  const meshes = [];
  for (const [, group] of getDeviceMeshes()) {
    group.traverse(child => { if (child.isMesh) meshes.push(child); });
  }
  const hits = raycaster.intersectObjects(meshes, false);
  if (hits.length > 0) {
    let obj = hits[0].object;
    while (obj.parent && !getDeviceMeshes().has(obj.name)) obj = obj.parent;
    if (getDeviceMeshes().has(obj.name)) return { id: obj.name, point: hits[0].point };
  }
  return null;
}

function onPointerDown(e) {
  if (e.button !== 0) return;
  updateMouse(e);
  const hit = raycastDevices();
  if (hit) {
    isDragging = true;
    dragDeviceId = hit.id;

    const group = getDeviceMeshes().get(dragDeviceId);
    raycaster.setFromCamera(mouse, getCamera());
    const intersectPt = new THREE.Vector3();
    raycaster.ray.intersectPlane(dragPlane, intersectPt);
    dragOffset.subVectors(group.position, intersectPt);

    if (onSelectCallback) onSelectCallback(hit.id);
    getRenderer().domElement.style.cursor = 'grabbing';
  }
}

function onPointerMove(e) {
  updateMouse(e);
  if (isDragging && dragDeviceId) {
    raycaster.setFromCamera(mouse, getCamera());
    const intersectPt = new THREE.Vector3();
    raycaster.ray.intersectPlane(dragPlane, intersectPt);
    intersectPt.add(dragOffset);

    if (onDragEndCallback) {
      onDragEndCallback(dragDeviceId, intersectPt.x, intersectPt.z, true);
    }
  } else {
    const hit = raycastDevices();
    getRenderer().domElement.style.cursor = hit ? 'move' : 'crosshair';
  }
}

function onPointerUp() {
  if (isDragging && dragDeviceId) {
    if (onDragEndCallback) {
      const group = getDeviceMeshes().get(dragDeviceId);
      if (group) {
        onDragEndCallback(dragDeviceId, group.position.x, group.position.z, false);
      }
    }
    isDragging = false;
    dragDeviceId = null;
    getRenderer().domElement.style.cursor = 'crosshair';
  }
}
