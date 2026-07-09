import * as THREE from 'three';
import URDFLoader from 'urdf-loader';
import { getScene, is3DMode } from './scene-manager.js';

const deviceMeshes = new Map();
let urdfRobot = null;

const COLOR_MAP = {
  device:    0x5c6bc0,
  container: 0x66bb6a,
  arm:       0xef5350,
  selected:  0xffab40,
};

export function createDeviceBox(dev) {
  const scene = getScene();
  const existing = deviceMeshes.get(dev.id);
  if (existing) scene.remove(existing);

  const group = new THREE.Group();
  group.name = dev.id;

  const boxH = 0.05;
  const geo = new THREE.BoxGeometry(dev.w, boxH, dev.d);
  const mat = new THREE.MeshStandardMaterial({
    color: getDeviceColor(dev),
    transparent: true,
    opacity: 0.8,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.position.y = boxH / 2;
  group.add(mesh);

  const edgeGeo = new THREE.BoxGeometry(dev.w, boxH + 0.002, 0.005);
  const edgeMat = new THREE.MeshBasicMaterial({ color: 0xffffff, opacity: 0.6, transparent: true });
  const edge = new THREE.Mesh(edgeGeo, edgeMat);
  edge.position.set(0, boxH / 2, -dev.d / 2);
  group.add(edge);

  const label = makeTextSprite(dev.name);
  label.position.set(0, 0.08, dev.d / 2 + 0.04);
  label.name = 'label';
  group.add(label);

  group.position.set(dev.x, 0, dev.y);
  group.rotation.y = -dev.theta;

  scene.add(group);
  deviceMeshes.set(dev.id, group);

  return group;
}

export function updateDevicePosition(dev) {
  const group = deviceMeshes.get(dev.id);
  if (!group) return;
  group.position.set(dev.x, 0, dev.y);
  group.rotation.y = -dev.theta;
}

export function setDeviceSelected(deviceId, selected) {
  const group = deviceMeshes.get(deviceId);
  if (!group) return;
  group.traverse(child => {
    if (child.isMesh && child.material && child !== group.children[1]) {
      child.material.emissive = selected
        ? new THREE.Color(COLOR_MAP.selected)
        : new THREE.Color(0x000000);
      child.material.emissiveIntensity = selected ? 0.4 : 0;
    }
  });
}

export function clearAllDevices() {
  const scene = getScene();
  for (const [, group] of deviceMeshes) {
    scene.remove(group);
  }
  deviceMeshes.clear();
}

export function getDeviceMeshes() { return deviceMeshes; }
export function getURDFRobot() { return urdfRobot; }

export async function loadURDF(urdfUrl, meshBaseUrl) {
  const scene = getScene();
  try {
    const resp = await fetch(urdfUrl);
    const urdfContent = await resp.text();

    const loader = new URDFLoader();
    loader.parseVisual = true;
    loader.packages = '';
    loader.workingPath = meshBaseUrl;

    urdfRobot = loader.parse(urdfContent);
    scene.add(urdfRobot);
    return urdfRobot;
  } catch (e) {
    console.error('[DeviceRenderer] URDF load failed:', e);
    return null;
  }
}

// 接受 URDF XML 字符串（而不是 URL），供合并页 tryLoadURDF 使用
export function loadURDFText(urdfContent, meshBaseUrl = "/meshes/") {
  const scene = getScene();
  if (urdfRobot) { scene.remove(urdfRobot); urdfRobot = null; }
  const loader = new URDFLoader();
  loader.parseVisual = true;
  loader.packages = "";
  loader.workingPath = meshBaseUrl;
  urdfRobot = loader.parse(urdfContent);
  scene.add(urdfRobot);
  return urdfRobot;
}

export function updateJointState(jointState) {
  if (!urdfRobot || !urdfRobot.joints) return;
  const { name, position } = jointState;
  for (let i = 0; i < name.length; i++) {
    const joint = urdfRobot.joints[name[i]];
    if (joint) joint.setJointValue(position[i]);
  }
}

export function setBoxVisibility(visible) {
  for (const [, group] of deviceMeshes) {
    group.visible = visible;
  }
}

function getDeviceColor(dev) {
  if (dev.class?.includes('arm') || dev.class?.includes('robot')) return COLOR_MAP.arm;
  if (dev.type === 'container') return COLOR_MAP.container;
  return COLOR_MAP.device;
}

function makeTextSprite(text) {
  const canvas = document.createElement('canvas');
  const size = 256;
  canvas.width = size;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.font = '24px Arial';
  ctx.fillStyle = 'rgba(255,255,255,0.85)';
  ctx.textAlign = 'center';
  ctx.fillText(text, size / 2, 40);

  const texture = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({ map: texture, depthTest: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(0.4, 0.1, 1);
  return sprite;
}

export function setDeviceStatus(deviceId, statusColor, intensity) {
  const group = deviceMeshes.get(deviceId);
  if (group) {
    group.traverse(child => {
      if (child.isMesh && child.material) {
        child.material.emissive = new THREE.Color(statusColor);
        child.material.emissiveIntensity = intensity;
      }
    });
  }
}

// ─── 可达工作空间点云渲染 ──────────────────────────────────────────────
let reachabilityCloud = null;
let ikMarker = null;

export function renderReachabilityCloud(points) {
  const scene = getScene();
  clearReachabilityCloud();
  if (!points || points.length === 0) return null;

  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(points.length * 3);
  const colors = new Float32Array(points.length * 3);

  const zValues = points.map(p => p[2]);
  const zMin = Math.min(...zValues);
  const zMax = Math.max(...zValues);
  const zRange = zMax - zMin || 1;

  const color = new THREE.Color();
  for (let i = 0; i < points.length; i++) {
    const [px, py, pz] = points[i];
    // ROS frame → Three.js frame: (x, y_height, z_forward) = (px, pz, py)
    positions[i * 3]     = px;
    positions[i * 3 + 1] = pz;
    positions[i * 3 + 2] = py;
    // Color: blue (low z) → cyan → green → yellow → red (high z)
    const t = (pz - zMin) / zRange;
    color.setHSL(0.66 - t * 0.66, 1.0, 0.5);
    colors[i * 3] = color.r; colors[i * 3 + 1] = color.g; colors[i * 3 + 2] = color.b;
  }

  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const material = new THREE.PointsMaterial({
    size: 0.025, vertexColors: true,
    transparent: true, opacity: 0.75, sizeAttenuation: true,
  });

  reachabilityCloud = new THREE.Points(geometry, material);
  scene.add(reachabilityCloud);
  return reachabilityCloud;
}

export function clearReachabilityCloud() {
  const scene = getScene();
  if (reachabilityCloud) { scene.remove(reachabilityCloud); reachabilityCloud = null; }
  clearIKMarker();
}

export function setReachabilityCloudVisible(visible) {
  if (reachabilityCloud) reachabilityCloud.visible = visible;
}

export function showIKMarker(x, y, z, reachable) {
  const scene = getScene();
  clearIKMarker();
  const geo = new THREE.SphereGeometry(0.04, 16, 16);
  const mat = new THREE.MeshBasicMaterial({
    color: reachable ? 0x00ff88 : 0xff3300,
    transparent: true, opacity: 0.9,
  });
  ikMarker = new THREE.Mesh(geo, mat);
  // ROS (x,y,z) → Three.js (x, z, y)
  ikMarker.position.set(x, z, y);
  // Pulsing ring
  const ringGeo = new THREE.RingGeometry(0.04, 0.055, 32);
  const ringMat = new THREE.MeshBasicMaterial({
    color: reachable ? 0x00ff88 : 0xff3300,
    transparent: true, opacity: 0.5, side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = -Math.PI / 2;
  ring.position.set(x, 0.002, y);
  ikMarker.add(ring);
  scene.add(ikMarker);
  return ikMarker;
}

export function clearIKMarker() {
  const scene = getScene();
  if (ikMarker) { scene.remove(ikMarker); ikMarker = null; }
}
