import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let renderer, scene;
let orthoCamera, perspCamera, controls;
let currentCamera;
let container;
let is3D = false;

const BG_COLOR = 0x1a1a2e;

export function initScene(domContainer) {
  container = domContainer;
  const w = container.clientWidth;
  const h = container.clientHeight;

  renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(w, h);
  renderer.setPixelRatio(window.devicePixelRatio);
  container.appendChild(renderer.domElement);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(BG_COLOR);

  const aspect = w / h;
  const frustumH = 3;
  orthoCamera = new THREE.OrthographicCamera(
    -frustumH * aspect / 2, frustumH * aspect / 2,
    frustumH / 2, -frustumH / 2,
    0.1, 100
  );
  orthoCamera.position.set(1, 10, 1);
  orthoCamera.lookAt(1, 0, 1);

  perspCamera = new THREE.PerspectiveCamera(60, aspect, 0.01, 100);
  perspCamera.position.set(3, 3, 4);

  controls = new OrbitControls(perspCamera, renderer.domElement);
  controls.target.set(1, 0, 1);
  controls.enabled = false;

  currentCamera = orthoCamera;

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(5, 10, 7);
  scene.add(dirLight);

  const grid = new THREE.GridHelper(10, 50, 0x333333, 0x262626);
  scene.add(grid);

  window.addEventListener('resize', onResize);
  animate();

  return { scene, renderer };
}

function onResize() {
  const w = container.clientWidth;
  const h = container.clientHeight;
  renderer.setSize(w, h);

  const aspect = w / h;
  if (is3D) {
    perspCamera.aspect = aspect;
    perspCamera.updateProjectionMatrix();
  } else {
    const frustumH = orthoCamera.top - orthoCamera.bottom;
    orthoCamera.left = -frustumH * aspect / 2;
    orthoCamera.right = frustumH * aspect / 2;
    orthoCamera.updateProjectionMatrix();
  }
}

function animate() {
  requestAnimationFrame(animate);
  if (is3D) controls.update();
  renderer.render(scene, currentCamera);
}

export function setViewMode(mode3D) {
  is3D = mode3D;
  if (is3D) {
    currentCamera = perspCamera;
    controls.enabled = true;
  } else {
    currentCamera = orthoCamera;
    controls.enabled = false;
  }
}

export function is3DMode() { return is3D; }
export function getScene() { return scene; }
export function getCamera() { return currentCamera; }
export function getRenderer() { return renderer; }
export function getContainer() { return container; }

export function fitOrthoToLab(labW, labD) {
  const aspect = container.clientWidth / container.clientHeight;
  const margin = 0.5;
  const frustumH = Math.max(labD, labW / aspect) + margin * 2;
  orthoCamera.top = frustumH / 2;
  orthoCamera.bottom = -frustumH / 2;
  orthoCamera.left = -frustumH * aspect / 2;
  orthoCamera.right = frustumH * aspect / 2;
  orthoCamera.position.set(labW / 2, 10, labD / 2);
  orthoCamera.lookAt(labW / 2, 0, labD / 2);
  orthoCamera.updateProjectionMatrix();
}

export function takeScreenshot(filename = 'lab-screenshot.png') {
  renderer.render(scene, currentCamera);
  const dataUrl = renderer.domElement.toDataURL('image/png');
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  a.click();
}
