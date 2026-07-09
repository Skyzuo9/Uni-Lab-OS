import { initScene, setViewMode, fitOrthoToLab, is3DMode, takeScreenshot } from './scene-manager.js';
import {
  createDeviceBox, updateDevicePosition, setDeviceSelected,
  clearAllDevices, loadURDF, loadURDFText, updateJointState, setBoxVisibility, setDeviceStatus,
  renderReachabilityCloud, clearReachabilityCloud, setReachabilityCloudVisible, showIKMarker, clearIKMarker,
} from './device-renderer.js';
import { drawWorkspace, updateWorkspacePosition, setWorkspaceVisible, removeWorkspace } from './workspace-overlay.js';
import { drawLinks, setLinksVisible } from './link-renderer.js';
import { initInteraction, onSelect, onDragEnd } from './interaction.js';
import { RosBridge } from './ros-bridge.js';
import { ResourceTracker } from './resource-tracker.js';
import { StatusOverlay } from './status-overlay.js';
import { TrajectoryPlayer } from './trajectory-player.js';

const state = {
  station: null, devices: [], links: [], selectedDevice: null,
  showWorkspace: true, showLinks: true, showLabels: true,
  labWidth: 2.0, labDepth: 2.0, workspace: null,
  intents: [], constraints: [], optimizing: false, cost: null,
  rosBridge: null, resourceTracker: null, statusOverlay: null,
  trajectoryPlayer: null, urdfLoaded: false, reachCloudVisible: false,
};

const DEFAULT_SIZES = {
  'robotic_arm': [0.20, 0.20], 'centrifuge': [0.40, 0.35],
  'rotavap': [0.50, 0.40], 'hplc_station': [0.60, 0.40],
  'heater': [0.30, 0.30], 'hotel': [0.40, 0.50],
  'container': [0.10, 0.10], 'workstation': [0.00, 0.00],
  'default': [0.30, 0.30],
};

document.addEventListener('DOMContentLoaded', () => {
  const container = document.querySelector('.canvas-panel');
  const oldCanvas = document.getElementById('layoutCanvas');
  if (oldCanvas) oldCanvas.remove();

  const { scene } = initScene(container);
  initInteraction(container.querySelector('canvas'));

  onSelect((deviceId) => {
    if (state.selectedDevice) setDeviceSelected(state.selectedDevice, false);
    state.selectedDevice = deviceId;
    setDeviceSelected(deviceId, true);
    updateDeviceList();
    log(`Selected: ${deviceId}`);
  });

  onDragEnd((deviceId, x, z, isMoving) => {
    const dev = state.devices.find(d => d.id === deviceId);
    if (dev) {
      dev.x = x; dev.y = z;
      updateDevicePosition(dev);
      if (state.workspace && deviceId === state.workspace.armId) {
        state.workspace.armX = x; state.workspace.armY = z;
        updateWorkspacePosition(x, z);
      }
      if (!isMoving) {
        const collides = checkLocalCollision(state, deviceId, x, z);
        setDeviceStatus(deviceId, collides ? 0xF44336 : 0x888888, collides ? 0.5 : 0);
        setTimeout(() => setDeviceStatus(deviceId, 0x888888, 0), collides ? 2500 : 1500);
        updateDeviceList();
        refreshScene();
      }
    }
  });

  document.getElementById('btnZoomFit')?.addEventListener('click', () => fitOrthoToLab(state.labWidth, state.labDepth));
  document.getElementById('btnToggleWorkspace')?.addEventListener('click', (e) => {
    state.showWorkspace = !state.showWorkspace;
    e.target.classList.toggle('active', state.showWorkspace);
    setWorkspaceVisible(state.showWorkspace);
  });
  document.getElementById('btnToggleLinks')?.addEventListener('click', (e) => {
    state.showLinks = !state.showLinks;
    e.target.classList.toggle('active', state.showLinks);
    setLinksVisible(state.showLinks);
  });
  document.getElementById('btnToggle3D')?.addEventListener('click', (e) => {
    const goTo3D = !is3DMode();
    setViewMode(goTo3D);
    e.target.textContent = goTo3D ? '3D' : '2D';
    e.target.classList.toggle('active', goTo3D);
    if (goTo3D && !state.urdfLoaded) tryLoadURDF();
    setBoxVisibility(!goTo3D || !state.urdfLoaded);
    if (goTo3D && !state.rosBridge) initRosBridge(scene);
    const rosSection = document.getElementById('rosStatusSection');
    if (rosSection) rosSection.style.display = goTo3D ? 'block' : 'none';
    const simSection = document.getElementById('simTestSection');
    if (simSection) simSection.style.display = goTo3D ? 'block' : 'none';
    const reachSection = document.getElementById('reachSection');
    if (reachSection) reachSection.style.display = goTo3D ? 'block' : 'none';
    const ikSection = document.getElementById('ikSection');
    if (ikSection) ikSection.style.display = goTo3D ? 'block' : 'none';
    if (!goTo3D) { clearReachabilityCloud(); state.reachCloudVisible = false; clearIKMarker(); }
  });
  document.getElementById('btnScreenshot')?.addEventListener('click', () => {
    takeScreenshot('uni-lab-layout.png');
    log('Screenshot saved.');
  });

  document.getElementById('stationSelect')?.addEventListener('change', onStationSelect);
  document.getElementById('stationFile')?.addEventListener('change', onStationFile);
  document.getElementById('labWidth')?.addEventListener('change', onLabResize);
  document.getElementById('labDepth')?.addEventListener('change', onLabResize);
  document.getElementById('btnAddIntent')?.addEventListener('click', onAddIntent);
  document.getElementById('btnAutoIntents')?.addEventListener('click', onAutoIntents);
  document.getElementById('btnOptimize')?.addEventListener('click', onOptimize);
  document.getElementById('btnExport')?.addEventListener('click', onExport);

  initStatusOverlay(scene);
  log('Unified layout app initialized.');
});

async function onStationSelect(e) {
  const path = e.target.value;
  if (!path) return;
  try {
    const resp = await fetch(`/api/v1/layout/station_file?path=${encodeURIComponent(path)}`);
    if (!resp.ok) {
      const resp2 = await fetch(path);
      if (resp2.ok) { loadStation(await resp2.json()); return; }
      throw new Error(`Failed: ${resp.status}`);
    }
    loadStation(await resp.json());
  } catch (err) { log(`ERROR: ${err.message}`); }
}

// --- AABB collision check for drag feedback ---
function checkLocalCollision(state, movedId, newX, newY) {
  const movedDev = state.devices.find(d => d.id === movedId);
  if (!movedDev) return false;
  const mw = ((movedDev.size && movedDev.size.w) || 0.3) / 2 + 0.02;
  const mh = ((movedDev.size && movedDev.size.h) || 0.3) / 2 + 0.02;
  for (const other of state.devices) {
    if (other.id === movedId) continue;
    const ow = ((other.size && other.size.w) || 0.3) / 2 + 0.02;
    const oh = ((other.size && other.size.h) || 0.3) / 2 + 0.02;
    const dx = Math.abs(newX - (other.x || 0));
    const dy = Math.abs(newY - (other.y || 0));
    if (dx < (mw + ow) && dy < (mh + oh)) return true;
  }
  return false;
}

function onStationFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try { loadStation(JSON.parse(ev.target.result)); }
    catch (err) { log(`ERROR: ${err.message}`); }
  };
  reader.readAsText(file);
}

function loadStation(data) {
  state.station = data; state.devices = []; state.links = [];
  state.intents = []; state.constraints = [];
  state.urdfLoaded = false;
  clearAllDevices(); removeWorkspace();
  for (const node of data.nodes || []) {
    const cls = node.class || ''; const type = node.type || 'device';
    if (cls === 'workstation') continue;
    let [w, d] = DEFAULT_SIZES.default;
    for (const [key, size] of Object.entries(DEFAULT_SIZES)) {
      if (cls.includes(key) || type === key) { [w, d] = size; break; }
    }
    const pos = node.position || { x: 0, y: 0 };
    const dev = {
      id: node.id, name: node.name || node.id, type, class: cls,
      x: pos.x / 1000, y: pos.y / 1000, theta: 0, w, d,
      config: node.config || {}, data: node.data || {},
    };
    state.devices.push(dev);
    createDeviceBox(dev);
  }
  for (const link of data.links || []) {
    state.links.push({ id: link.id, source: link.source, target: link.target, type: link.type || 'transport' });
  }
  generateArmWorkspace(); refreshScene(); updateDeviceList();
  document.getElementById('deviceCount').textContent = `(${state.devices.length})`;
  fitOrthoToLab(state.labWidth, state.labDepth);
  log(`Loaded: ${state.devices.length} devices, ${state.links.length} links`);
}

function generateArmWorkspace() {
  const arm = state.devices.find(d => d.class?.includes('arm') || d.class?.includes('robot'));
  if (!arm) { state.workspace = null; return; }
  const REACH = { 'cs63': 0.624, 'cs66': 0.914, 'cs612': 1.304, 'cs620': 1.800 };
  const maxReach = REACH[arm.config?.cs_type] || 0.914;
  const innerRadius = maxReach * 0.08;
  state.workspace = { armId: arm.id, armX: arm.x, armY: arm.y, maxReach, innerRadius };
  drawWorkspace(arm.x, arm.y, maxReach, innerRadius);
}

function refreshScene() {
  if (state.showLinks) drawLinks(state.devices, state.links);
}

function initRosBridge(scene) {
  state.rosBridge = new RosBridge('ws://' + window.location.hostname + ':8765');
  state.rosBridge.connect();
  state.rosBridge.on('/joint_states', (msg) => updateJointState(msg));
  state.resourceTracker = new ResourceTracker(scene, state.rosBridge);
  state.resourceTracker.startListening();
  state.trajectoryPlayer = new TrajectoryPlayer(null, document.body);
  state.rosBridge.on('/move_group/display_planned_path', (msg) => {
    state.trajectoryPlayer.loadTrajectory(msg);
  });
  const statusEl = document.getElementById('rosConnStatus');
  if (statusEl) statusEl.textContent = 'Foxglove: Connected';
  log('ROS Bridge connected (3D mode).');
}

function initStatusOverlay(scene) {
  state.statusOverlay = new StatusOverlay(scene);
  state.statusOverlay.connectWebSocket();
}

async function tryLoadURDF() {
  const path = document.getElementById('stationSelect')?.value || '';
  if (!path) { log('[3D] 请先从下拉菜单选择一个实验站 JSON 文件'); return; }
  log('[3D] 正在生成 URDF...');
  try {
    // Pass current 2D positions so 3D matches the dragged layout
    const posOverride = {};
    for (const dev of state.devices) {
      posOverride[dev.id] = { x: Math.round(dev.x * 1000), y: Math.round(dev.y * 1000), z: 0 };
    }
    const resp = await fetch('/api/v1/layout/urdf?station_path=' + encodeURIComponent(path)
      + '&positions=' + encodeURIComponent(JSON.stringify(posOverride)));
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    if (!data.urdf || data.device_count === 0) {
      log('[3D] 该实验站无可渲染的 3D 模型，使用 Box 占位模式');
      return;
    }
    const robot = loadURDFText(data.urdf, window.location.origin + '/meshes/');
    if (robot) {
      state.urdfLoaded = true;
      setBoxVisibility(false);
      if (state.statusOverlay) state.statusOverlay.registerDevices(state.devices.map(d => d.id));
      if (state.resourceTracker) state.resourceTracker.registerResources(
        state.devices.filter(d => d.type !== 'device').map(d => d.id));
      log('[3D] URDF 加载成功: ' + data.device_count + ' 设备, ' +
          Object.keys(robot.joints || {}).length + ' 关节');
    }
  } catch (e) { log('[3D] URDF 加载失败: ' + e.message); }
}

function onAddIntent() {
  const type = document.getElementById('intentType').value;
  if (type === 'reachable_by') {
    const arm = state.devices.find(d => d.class.includes('arm'));
    if (!arm) { log('ERROR: No arm device found.'); return; }
    if (!state.selectedDevice || state.selectedDevice === arm.id) {
      log('Select a non-arm device first.'); return;
    }
    addIntent({ type: 'reachable_by', params: { arm_id: arm.id, device_id: state.selectedDevice } });
  } else if (type === 'close_together' || type === 'far_apart') {
    if (!state.selectedDevice) { log('Select a device first.'); return; }
    addIntent({ type, params: { device_ids: [state.selectedDevice] } });
  } else if (type === 'min_spacing') {
    addIntent({ type: 'min_spacing', params: { distance: 0.1 } });
  } else if (type === 'max_distance') {
    if (!state.selectedDevice) { log('Select a device first.'); return; }
    addIntent({ type: 'max_distance', params: { device_id: state.selectedDevice, max_dist: 0.5 } });
  }
}

function addIntent(intent) {
  state.intents.push(intent);
  updateIntentList();
  log(`Added constraint: ${intent.type}`);
}

function updateIntentList() {
  const container = document.getElementById('intentList');
  container.innerHTML = '';
  state.intents.forEach((intent, idx) => {
    const item = document.createElement('div');
    item.className = 'intent-item';
    const desc = JSON.stringify(intent.params).slice(0, 40);
    item.innerHTML = `<span><span class="intent-tag">${intent.type}</span> ${desc}</span><button class="btn btn-sm btn-danger" onclick="window._removeIntent(${idx})">x</button>`;
    container.appendChild(item);
  });
}

window._removeIntent = function(idx) {
  state.intents.splice(idx, 1); updateIntentList();
};

function onAutoIntents() {
  const arm = state.devices.find(d => d.class.includes('arm'));
  if (!arm) { log('No arm device found.'); return; }
  let count = 0;
  for (const link of state.links) {
    if (link.type !== 'transport') continue;
    const targetId = link.source === arm.id ? link.target : link.source;
    const exists = state.intents.some(i => i.type === 'reachable_by' && i.params.device_id === targetId);
    if (!exists) { state.intents.push({ type: 'reachable_by', params: { arm_id: arm.id, device_id: targetId } }); count++; }
  }
  if (!state.intents.some(i => i.type === 'min_spacing')) {
    state.intents.push({ type: 'min_spacing', params: { distance: 0.05 } }); count++;
  }
  updateIntentList();
  log(`Auto-generated ${count} constraints from transport links.`);
}

async function onOptimize() {
  if (state.optimizing) { log('Optimization already running...'); return; }
  if (state.devices.length === 0) { log('No devices loaded.'); return; }
  state.optimizing = true;
  const btn = document.getElementById('btnOptimize');
  btn.textContent = 'Optimizing...'; btn.disabled = true;
  try {
    const devices = state.devices.map(d => ({
      id: d.id, name: d.name, type: d.type, class: d.class,
      bbox: [d.w, d.d], position: [d.x, d.y, d.theta],
    }));
    const lab = { width: state.labWidth, depth: state.labDepth };
    let constraints = [];
    if (state.intents.length > 0) {
      log('Interpreting intents...');
      try {
        const interpretResp = await fetch('/api/v1/layout/interpret', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intents: state.intents }),
        });
        if (interpretResp.ok) {
          const result = await interpretResp.json();
          constraints = result.constraints || [];
          log(`Interpreted ${state.intents.length} intents -> ${constraints.length} constraints`);
        }
      } catch (err) { log(`Intent API error: ${err.message}`); }
    }
    log('Running differential evolution optimizer...');
    const maxiter = parseInt(document.getElementById('maxIter').value) || 200;
    const popsize = parseInt(document.getElementById('popSize').value) || 30;
    const optimizeResp = await fetch('/api/v1/layout/optimize', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ devices, lab, constraints, maxiter, seed: 42, seeder: 'current', run_de: true }),
    });
    if (!optimizeResp.ok) {
      const err = await optimizeResp.text();
      throw new Error(`Optimizer returned ${optimizeResp.status}: ${err}`);
    }
    const result = await optimizeResp.json();
    if (result.solution) {
      for (const placement of result.solution) {
        const dev = state.devices.find(d => d.id === placement.id);
        if (dev) { dev.x = placement.pos[0]; dev.y = placement.pos[1]; dev.theta = placement.pos[2] || 0; }
      }
      for (const dev of state.devices) updateDevicePosition(dev);
      generateArmWorkspace(); updateDeviceList();
    }
    state.cost = result.cost;
    document.getElementById('costDisplay').textContent = state.cost != null ? state.cost.toFixed(4) : '--';
    log(`Optimization complete! Cost: ${state.cost?.toFixed(4) ?? 'N/A'}`);
    if (result.collisions?.length > 0) log(`  Collisions: ${result.collisions.map(c => c.join('<->')).join(', ')}`);
    if (result.unreachable?.length > 0) log(`  Unreachable: ${result.unreachable.join(', ')}`);
    refreshScene();
  } catch (err) { log(`ERROR: ${err.message}`); }
  finally { state.optimizing = false; btn.textContent = 'Optimize Layout'; btn.disabled = false; }
}

function onExport() {
  if (!state.station) { log('No station loaded.'); return; }
  const exportData = JSON.parse(JSON.stringify(state.station));
  for (const node of exportData.nodes || []) {
    const dev = state.devices.find(d => d.id === node.id);
    if (dev) node.position = { x: Math.round(dev.x * 1000), y: Math.round(dev.y * 1000), z: node.position?.z || 0 };
  }
  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'optimized_station.json'; a.click();
  URL.revokeObjectURL(url);
  log('Exported optimized station JSON.');
}

function onLabResize() {
  state.labWidth = parseFloat(document.getElementById('labWidth').value) || 2.0;
  state.labDepth = parseFloat(document.getElementById('labDepth').value) || 2.0;
  fitOrthoToLab(state.labWidth, state.labDepth);
}

function updateDeviceList() {
  const container = document.getElementById('deviceList');
  if (!container) return;
  container.innerHTML = '';
  for (const dev of state.devices) {
    const item = document.createElement('div');
    item.className = 'device-item' + (state.selectedDevice === dev.id ? ' selected' : '');
    item.innerHTML = `<div class="device-dot" style="background:${dev.class?.includes('arm') ? '#ef5350' : '#5c6bc0'}"></div><span>${dev.name}</span><span style="color:#999;font-size:10px;margin-left:auto;">(${dev.x.toFixed(2)}, ${dev.y.toFixed(2)})</span>`;
    item.addEventListener('click', () => {
      if (state.selectedDevice) setDeviceSelected(state.selectedDevice, false);
      state.selectedDevice = dev.id;
      setDeviceSelected(dev.id, true);
      updateDeviceList();
    });
    container.appendChild(item);
  }
}

function log(msg) {
  const el = document.getElementById('optimizeLog');
  if (!el) return;
  const time = new Date().toLocaleTimeString();
  el.textContent += `[${time}] ${msg}\n`;
  el.scrollTop = el.scrollHeight;
}


// ── 仿真测试（3D 模式下可用）──

// --- Reachability Cloud ---
async function toggleReachabilityCloud() {
  if (!is3DMode()) { log('[Cloud] 请先切换到 3D 模式'); return; }
  const arm = state.devices.find(d => d.class && (d.class.includes('arm') || d.class.includes('robot')));
  if (!arm) { log('[Cloud] 未找到机械臂设备'); return; }
  if (state.reachCloudVisible) {
    clearReachabilityCloud();
    state.reachCloudVisible = false;
    log('[Cloud] 已关闭可达空间点云');
    const btn = document.getElementById('btnCloudToggle');
    if (btn) btn.style.background = '';
    return;
  }
  log('[Cloud] 正在加载可达空间点云...');
  try {
    const url = '/api/v1/layout/workspace/' + arm.id + '?x=' + arm.x + '&y=' + arm.y + '&resolution=0.08&max_points=8000';
    const resp = await fetch(url);
    const data = await resp.json();
    const pts = data.points || [];
    if (pts.length === 0) { log('[Cloud] 无可达点数据，请确认 voxel map 存在'); return; }
    renderReachabilityCloud(pts);
    state.reachCloudVisible = true;
    const btn = document.getElementById('btnCloudToggle');
    if (btn) btn.style.background = '#1a6b3c';
    log('[Cloud] 已加载 ' + pts.length + ' 个可达点（蓝=低 → 绿 → 红=高）');
  } catch(e) { log('[Cloud] 加载失败: ' + e.message); }
}
window.toggleReachabilityCloud = toggleReachabilityCloud;

// --- IK Solver ---
async function solveIK() {
  if (!is3DMode()) { log('[IK] 请先切换到 3D 模式'); return; }
  const arm = state.devices.find(d => d.class && (d.class.includes('arm') || d.class.includes('robot')));
  if (!arm) { log('[IK] 未找到机械臂设备'); return; }
  const tx = parseFloat(document.getElementById('ikX') ? document.getElementById('ikX').value : '0') || 0;
  const ty = parseFloat(document.getElementById('ikY') ? document.getElementById('ikY').value : '0') || 0;
  const tz = parseFloat(document.getElementById('ikZ') ? document.getElementById('ikZ').value : '0.3') || 0.3;
  log('[IK] 求解目标: (' + tx.toFixed(3) + ', ' + ty.toFixed(3) + ', ' + tz.toFixed(3) + ') m');
  try {
    const url = '/api/v1/layout/ik/' + arm.id + '?x=' + tx + '&y=' + ty + '&z=' + tz;
    const resp = await fetch(url);
    const data = await resp.json();
    const up = data.used_point || {x: tx, y: ty, z: tz};
    showIKMarker(up.x, up.y, up.z, data.reachable);
    if (data.joint_names && data.joint_names.length > 0) {
      updateJointState({ name: data.joint_names, position: data.joint_values });
      const status = data.reachable ? '✅ 目标可达' : '⚠️ 已修正至最近可达点';
      log('[IK] ' + status + ': [' + data.joint_values.map(function(v){return v.toFixed(3);}).join(', ') + ']');
    } else {
      log('[IK] ❌ 超出可达范围，已标记最近可达点');
    }
  } catch(e) { log('[IK] 求解失败: ' + e.message); }
}
window.solveIK = solveIK;
window.clearIKMarker = clearIKMarker;

window._simTestJoints = function () {
  if (!state.urdfLoaded) { log('[Sim] 请先切换到 3D 并等待 URDF 加载完成'); return; }
  const names = ['dummy2_arm_Joint1','dummy2_arm_Joint2','dummy2_arm_Joint3',
                 'dummy2_arm_Joint4','dummy2_arm_Joint5','dummy2_arm_Joint6'];
  updateJointState({ name: names, position: names.map(() => (Math.random()-0.5)*2) });
  log('[Sim] 已发送随机 6 轴关节角');
};

window._simTestStatus = function () {
  const arm = state.devices.find(d => d.class && (d.class.includes('arm') || d.class.includes('robot')));
  if (!arm) { log('[Sim] 未找到机械臂设备'); return; }
  if (state.statusOverlay) state.statusOverlay.setStatus(arm.id, 'running');
  log('[Sim] 设备状态: ' + arm.id + ' = running');
};

window._simTestTrajectory = function () {
  if (!state.trajectoryPlayer) { log('[Sim] 请先切换 3D 模式以初始化轨迹播放器'); return; }
  const names = ['dummy2_arm_Joint1','dummy2_arm_Joint2','dummy2_arm_Joint3',
                 'dummy2_arm_Joint4','dummy2_arm_Joint5','dummy2_arm_Joint6'];
  state.trajectoryPlayer.loadTrajectory({ trajectory: [{ joint_trajectory: {
    joint_names: names,
    points: [
      { positions: [0,0,0,0,0,0],              time_from_start: {sec:0,nanosec:0} },
      { positions: [0.5,0.3,-0.2,0.4,-0.3,0.1], time_from_start: {sec:1,nanosec:0} },
      { positions: [1.0,0.6,-0.4,0.8,-0.6,0.2], time_from_start: {sec:2,nanosec:0} },
      { positions: [0,0,0,0,0,0],              time_from_start: {sec:3,nanosec:0} },
    ]
  }}]});
  log('[Sim] 已加载 4 路径点，点击底部 Play 按钮播放');
};
