/**
 * Layout Optimizer — interactive 2D canvas + REST API integration.
 *
 * Features:
 *  - 2D lab floorplan with pan/zoom (mouse wheel + drag)
 *  - Devices rendered as colored rectangles (drag to reposition)
 *  - Arm workspace overlay (radial cross-section from voxel map)
 *  - Transport links drawn as curves
 *  - Constraint editor → POST /api/v1/layout/interpret + /optimize
 *  - Export modified station JSON
 */

// ============================================================
// Global State
// ============================================================

const state = {
  // Station data
  station: null,        // parsed station JSON { nodes, links }
  devices: [],          // [{ id, name, type, class, x, y, theta, w, d, color }]
  links: [],            // [{ source, target, type }]

  // Canvas state
  canvas: null,
  ctx: null,
  panX: 0, panY: 0,
  zoom: 1,
  isDragging: false,
  isPanning: false,
  dragDevice: null,
  dragOffsetX: 0,
  dragOffsetY: 0,
  lastMouseX: 0,
  lastMouseY: 0,
  selectedDevice: null,

  // Toggles
  showWorkspace: true,
  showLinks: true,
  showLabels: true,
  showGrid: true,

  // Lab dimensions (meters)
  labWidth: 2.0,
  labDepth: 2.0,

  // Arm workspace (2D radial profile)
  workspace: null,  // { r_max, z_min, z_max, resolution, reachable_2d }

  // Constraints
  intents: [],
  constraints: [],

  // Optimizer
  optimizing: false,
  cost: null,
};

// ============================================================
// Color Palette
// ============================================================

const COLORS = {
  device:     '#5c6bc0',
  container:  '#66bb6a',
  arm:        '#ef5350',
  workstation: '#78909c',
  workspace:  'rgba(0, 200, 255, 0.12)',
  workspaceStroke: 'rgba(0, 200, 255, 0.4)',
  link:       'rgba(255, 193, 7, 0.5)',
  linkArrow:  'rgba(255, 193, 7, 0.8)',
  grid:       'rgba(255, 255, 255, 0.06)',
  gridMajor:  'rgba(255, 255, 255, 0.12)',
  labBorder:  'rgba(255, 255, 255, 0.3)',
  text:       'rgba(255, 255, 255, 0.85)',
  textDim:    'rgba(255, 255, 255, 0.4)',
  selected:   '#ffab40',
  background: '#1a1a2e',
};

// Default device sizes (meters) when not specified
const DEFAULT_SIZES = {
  'robotic_arm':   [0.20, 0.20],
  'centrifuge':    [0.40, 0.35],
  'rotavap':       [0.50, 0.40],
  'hplc_station':  [0.60, 0.40],
  'heater':        [0.30, 0.30],
  'hotel':         [0.40, 0.50],
  'container':     [0.10, 0.10],
  'workstation':   [0.00, 0.00],
  'default':       [0.30, 0.30],
};

// ============================================================
// Initialization
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
  state.canvas = document.getElementById('layoutCanvas');
  state.ctx = state.canvas.getContext('2d');

  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  // Canvas events
  state.canvas.addEventListener('mousedown', onMouseDown);
  state.canvas.addEventListener('mousemove', onMouseMove);
  state.canvas.addEventListener('mouseup', onMouseUp);
  state.canvas.addEventListener('wheel', onWheel, { passive: false });
  state.canvas.addEventListener('dblclick', onDoubleClick);

  // Toolbar
  document.getElementById('btnZoomFit').addEventListener('click', zoomFit);
  document.getElementById('btnToggleWorkspace').addEventListener('click', (e) => {
    state.showWorkspace = !state.showWorkspace;
    e.target.classList.toggle('active', state.showWorkspace);
    draw();
  });
  document.getElementById('btnToggleLinks').addEventListener('click', (e) => {
    state.showLinks = !state.showLinks;
    e.target.classList.toggle('active', state.showLinks);
    draw();
  });
  document.getElementById('btnToggleLabels').addEventListener('click', (e) => {
    state.showLabels = !state.showLabels;
    e.target.classList.toggle('active', state.showLabels);
    draw();
  });
  document.getElementById('btnGrid').addEventListener('click', (e) => {
    state.showGrid = !state.showGrid;
    e.target.classList.toggle('active', state.showGrid);
    draw();
  });

  // Station loader
  document.getElementById('stationSelect').addEventListener('change', onStationSelect);
  document.getElementById('stationFile').addEventListener('change', onStationFile);
  document.getElementById('labWidth').addEventListener('change', onLabResize);
  document.getElementById('labDepth').addEventListener('change', onLabResize);

  // Constraints
  document.getElementById('btnAddIntent').addEventListener('click', onAddIntent);
  document.getElementById('btnAutoIntents').addEventListener('click', onAutoIntents);

  // Optimizer
  document.getElementById('btnOptimize').addEventListener('click', onOptimize);

  // Export
  document.getElementById('btnExport').addEventListener('click', onExport);

  draw();
  log('Layout optimizer initialized.');
});

function resizeCanvas() {
  const rect = state.canvas.parentElement.getBoundingClientRect();
  state.canvas.width = rect.width * window.devicePixelRatio;
  state.canvas.height = rect.height * window.devicePixelRatio;
  state.canvas.style.width = rect.width + 'px';
  state.canvas.style.height = rect.height + 'px';
  state.ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
  draw();
}

// ============================================================
// Station Loading
// ============================================================

async function onStationSelect(e) {
  const path = e.target.value;
  if (!path) return;
  try {
    const resp = await fetch(`/api/v1/layout/station_file?path=${encodeURIComponent(path)}`);
    if (!resp.ok) {
      // Try loading directly as static file
      const resp2 = await fetch(path);
      if (resp2.ok) {
        const data = await resp2.json();
        loadStation(data);
        return;
      }
      throw new Error(`Failed to load: ${resp.status}`);
    }
    const data = await resp.json();
    loadStation(data);
  } catch (err) {
    log(`ERROR: ${err.message}`);
  }
}

function onStationFile(e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const data = JSON.parse(ev.target.result);
      loadStation(data);
    } catch (err) {
      log(`ERROR parsing JSON: ${err.message}`);
    }
  };
  reader.readAsText(file);
}

function loadStation(data) {
  state.station = data;
  state.devices = [];
  state.links = [];
  state.intents = [];
  state.constraints = [];

  // Parse nodes
  for (const node of data.nodes || []) {
    const cls = node.class || '';
    const type = node.type || 'device';

    // Skip workstation root node for display
    if (cls === 'workstation') continue;

    // Determine color
    let color = COLORS.device;
    if (type === 'container') color = COLORS.container;
    if (cls.includes('arm') || cls.includes('robot')) color = COLORS.arm;

    // Determine size
    let [w, d] = DEFAULT_SIZES.default;
    for (const [key, size] of Object.entries(DEFAULT_SIZES)) {
      if (cls.includes(key) || type === key) {
        [w, d] = size;
        break;
      }
    }

    // Position: convert from station coords to meters
    // Station JSON uses pixel-like coords, normalize to lab space
    const pos = node.position || { x: 0, y: 0 };
    const x = pos.x / 1000;  // assume mm or scale factor
    const y = pos.y / 1000;

    state.devices.push({
      id: node.id,
      name: node.name || node.id,
      type,
      class: cls,
      x, y,
      theta: 0,
      w, d,
      color,
      config: node.config || {},
      data: node.data || {},
    });
  }

  // Parse links
  for (const link of data.links || []) {
    state.links.push({
      id: link.id,
      source: link.source,
      target: link.target,
      type: link.type || 'transport',
    });
  }

  // Generate arm workspace
  generateArmWorkspace();

  // Update UI
  updateDeviceList();
  document.getElementById('deviceCount').textContent = `(${state.devices.length})`;
  log(`Loaded station: ${state.devices.length} devices, ${state.links.length} links`);

  zoomFit();
}

// ============================================================
// Arm Workspace Visualization (2D radial projection)
// ============================================================

function generateArmWorkspace() {
  // Find arm device
  const arm = state.devices.find(d => d.class.includes('arm') || d.class.includes('robot'));
  if (!arm) {
    state.workspace = null;
    return;
  }

  // Use arm reach from config or default
  const csType = arm.config?.cs_type || 'cs66';
  const REACH_MAP = {
    'cs63': 0.624,
    'cs66': 0.914,
    'cs612': 1.304,
    'cs620': 1.800,
  };
  const maxReach = REACH_MAP[csType] || 0.914;

  // Simple annular workspace model:
  // Inner dead zone ~ 10% of max reach, outer limit = max reach
  const innerRadius = maxReach * 0.08;

  state.workspace = {
    armId: arm.id,
    armX: arm.x,
    armY: arm.y,
    maxReach,
    innerRadius,
  };
}

// ============================================================
// Canvas Rendering
// ============================================================

function draw() {
  const ctx = state.ctx;
  const w = state.canvas.width / window.devicePixelRatio;
  const h = state.canvas.height / window.devicePixelRatio;

  // Clear
  ctx.fillStyle = COLORS.background;
  ctx.fillRect(0, 0, w, h);

  ctx.save();
  ctx.translate(state.panX, state.panY);
  ctx.scale(state.zoom, state.zoom);

  // Grid
  if (state.showGrid) drawGrid(ctx);

  // Lab bounds
  drawLabBounds(ctx);

  // Arm workspace
  if (state.showWorkspace && state.workspace) drawWorkspace(ctx);

  // Links
  if (state.showLinks) drawLinks(ctx);

  // Devices
  drawDevices(ctx);

  ctx.restore();

  // Info
  updateCanvasInfo();
}

function drawGrid(ctx) {
  const step = 0.1;  // 10cm grid
  const majorStep = 0.5;  // 50cm major grid
  const extent = Math.max(state.labWidth, state.labDepth) * 1.5;

  const s2w = metersToPx(1);

  for (let x = -extent; x <= extent * 2; x += step) {
    const isMajor = Math.abs(x % majorStep) < 0.001;
    ctx.strokeStyle = isMajor ? COLORS.gridMajor : COLORS.grid;
    ctx.lineWidth = isMajor ? 0.5 / state.zoom : 0.3 / state.zoom;
    ctx.beginPath();
    ctx.moveTo(x, -extent);
    ctx.lineTo(x, extent * 2);
    ctx.stroke();
  }
  for (let y = -extent; y <= extent * 2; y += step) {
    const isMajor = Math.abs(y % majorStep) < 0.001;
    ctx.strokeStyle = isMajor ? COLORS.gridMajor : COLORS.grid;
    ctx.lineWidth = isMajor ? 0.5 / state.zoom : 0.3 / state.zoom;
    ctx.beginPath();
    ctx.moveTo(-extent, y);
    ctx.lineTo(extent * 2, y);
    ctx.stroke();
  }
}

function drawLabBounds(ctx) {
  ctx.strokeStyle = COLORS.labBorder;
  ctx.lineWidth = 2 / state.zoom;
  ctx.setLineDash([0.05, 0.03]);
  ctx.strokeRect(0, 0, state.labWidth, state.labDepth);
  ctx.setLineDash([]);

  // Dimension labels
  const fontSize = 12 / state.zoom;
  ctx.font = `${fontSize}px Arial`;
  ctx.fillStyle = COLORS.textDim;
  ctx.textAlign = 'center';
  ctx.fillText(`${state.labWidth.toFixed(1)}m`, state.labWidth / 2, -0.03);
  ctx.save();
  ctx.translate(-0.03, state.labDepth / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText(`${state.labDepth.toFixed(1)}m`, 0, 0);
  ctx.restore();
}

function drawWorkspace(ctx) {
  const ws = state.workspace;

  // Outer reachable circle
  ctx.beginPath();
  ctx.arc(ws.armX, ws.armY, ws.maxReach, 0, Math.PI * 2);
  ctx.fillStyle = COLORS.workspace;
  ctx.fill();
  ctx.strokeStyle = COLORS.workspaceStroke;
  ctx.lineWidth = 1.5 / state.zoom;
  ctx.stroke();

  // Inner dead zone (cut out)
  if (ws.innerRadius > 0) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(ws.armX, ws.armY, ws.innerRadius, 0, Math.PI * 2);
    ctx.fillStyle = COLORS.background;
    ctx.globalAlpha = 0.7;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = 'rgba(255, 80, 80, 0.3)';
    ctx.lineWidth = 1 / state.zoom;
    ctx.setLineDash([0.02, 0.02]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
  }

  // Reach label
  const fontSize = 10 / state.zoom;
  ctx.font = `${fontSize}px Arial`;
  ctx.fillStyle = COLORS.workspaceStroke;
  ctx.textAlign = 'left';
  ctx.fillText(
    `R=${ws.maxReach.toFixed(3)}m`,
    ws.armX + ws.maxReach + 0.02,
    ws.armY,
  );
}

function drawLinks(ctx) {
  for (const link of state.links) {
    const src = state.devices.find(d => d.id === link.source);
    const tgt = state.devices.find(d => d.id === link.target);
    if (!src || !tgt) continue;

    ctx.strokeStyle = COLORS.link;
    ctx.lineWidth = 1.5 / state.zoom;
    ctx.beginPath();
    ctx.moveTo(src.x, src.y);

    // Quadratic curve for visual clarity
    const mx = (src.x + tgt.x) / 2;
    const my = (src.y + tgt.y) / 2;
    const dx = tgt.x - src.x;
    const dy = tgt.y - src.y;
    const cx = mx - dy * 0.15;
    const cy = my + dx * 0.15;
    ctx.quadraticCurveTo(cx, cy, tgt.x, tgt.y);
    ctx.stroke();

    // Arrow head
    const arrowSize = 0.02;
    const angle = Math.atan2(tgt.y - cy, tgt.x - cx);
    ctx.fillStyle = COLORS.linkArrow;
    ctx.beginPath();
    ctx.moveTo(tgt.x, tgt.y);
    ctx.lineTo(
      tgt.x - arrowSize * Math.cos(angle - 0.4),
      tgt.y - arrowSize * Math.sin(angle - 0.4),
    );
    ctx.lineTo(
      tgt.x - arrowSize * Math.cos(angle + 0.4),
      tgt.y - arrowSize * Math.sin(angle + 0.4),
    );
    ctx.closePath();
    ctx.fill();
  }
}

function drawDevices(ctx) {
  for (const dev of state.devices) {
    const isSelected = state.selectedDevice === dev.id;
    const halfW = dev.w / 2;
    const halfD = dev.d / 2;

    ctx.save();
    ctx.translate(dev.x, dev.y);
    ctx.rotate(dev.theta);

    // Device body
    ctx.fillStyle = dev.color;
    ctx.globalAlpha = isSelected ? 1.0 : 0.75;
    ctx.fillRect(-halfW, -halfD, dev.w, dev.d);
    ctx.globalAlpha = 1;

    // Border
    ctx.strokeStyle = isSelected ? COLORS.selected : 'rgba(255,255,255,0.3)';
    ctx.lineWidth = (isSelected ? 2.5 : 1) / state.zoom;
    ctx.strokeRect(-halfW, -halfD, dev.w, dev.d);

    // Orientation indicator (front edge)
    ctx.strokeStyle = 'rgba(255,255,255,0.6)';
    ctx.lineWidth = 2 / state.zoom;
    ctx.beginPath();
    ctx.moveTo(-halfW, -halfD);
    ctx.lineTo(halfW, -halfD);
    ctx.stroke();

    ctx.restore();

    // Label
    if (state.showLabels) {
      const fontSize = Math.max(9, 11 / state.zoom);
      ctx.font = `${fontSize / state.zoom}px Arial`;
      ctx.fillStyle = COLORS.text;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillText(dev.name, dev.x, dev.y + halfD + 0.015);
    }
  }
}

function metersToPx(m) {
  return m * state.zoom;
}

function updateCanvasInfo() {
  const info = document.getElementById('canvasInfo');
  const mx = ((state.lastMouseX - state.panX) / state.zoom).toFixed(3);
  const my = ((state.lastMouseY - state.panY) / state.zoom).toFixed(3);
  info.textContent = `Pos: (${mx}, ${my})m | Zoom: ${state.zoom.toFixed(1)}x`;
  if (state.selectedDevice) {
    const dev = state.devices.find(d => d.id === state.selectedDevice);
    if (dev) {
      info.textContent += ` | Selected: ${dev.name} (${dev.x.toFixed(3)}, ${dev.y.toFixed(3)})`;
    }
  }
}

// ============================================================
// Mouse Interaction
// ============================================================

function screenToWorld(sx, sy) {
  return {
    x: (sx - state.panX) / state.zoom,
    y: (sy - state.panY) / state.zoom,
  };
}

function hitTest(wx, wy) {
  // Reverse order — top-most first
  for (let i = state.devices.length - 1; i >= 0; i--) {
    const dev = state.devices[i];
    const halfW = dev.w / 2;
    const halfD = dev.d / 2;
    // Simple AABB (ignoring rotation for hit testing)
    if (wx >= dev.x - halfW && wx <= dev.x + halfW &&
        wy >= dev.y - halfD && wy <= dev.y + halfD) {
      return dev;
    }
  }
  return null;
}

function onMouseDown(e) {
  const rect = state.canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;
  const { x: wx, y: wy } = screenToWorld(sx, sy);

  state.lastMouseX = sx;
  state.lastMouseY = sy;

  const dev = hitTest(wx, wy);
  if (dev && e.button === 0) {
    state.isDragging = true;
    state.dragDevice = dev;
    state.dragOffsetX = wx - dev.x;
    state.dragOffsetY = wy - dev.y;
    state.selectedDevice = dev.id;
    updateDeviceList();
    draw();
    return;
  }

  // Pan with middle button or left on empty area
  if (e.button === 0 || e.button === 1) {
    state.isPanning = true;
    state.canvas.style.cursor = 'grabbing';
  }
}

function onMouseMove(e) {
  const rect = state.canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;

  if (state.isDragging && state.dragDevice) {
    const { x: wx, y: wy } = screenToWorld(sx, sy);
    state.dragDevice.x = wx - state.dragOffsetX;
    state.dragDevice.y = wy - state.dragOffsetY;

    // Update workspace if arm is being dragged
    if (state.workspace && state.dragDevice.id === state.workspace.armId) {
      state.workspace.armX = state.dragDevice.x;
      state.workspace.armY = state.dragDevice.y;
    }
    draw();
  } else if (state.isPanning) {
    const dx = sx - state.lastMouseX;
    const dy = sy - state.lastMouseY;
    state.panX += dx;
    state.panY += dy;
    draw();
  }

  state.lastMouseX = sx;
  state.lastMouseY = sy;

  // Update cursor
  if (!state.isDragging && !state.isPanning) {
    const { x: wx, y: wy } = screenToWorld(sx, sy);
    const dev = hitTest(wx, wy);
    state.canvas.style.cursor = dev ? 'move' : 'crosshair';
  }
}

function onMouseUp(e) {
  if (state.isDragging) {
    state.isDragging = false;
    state.dragDevice = null;
  }
  if (state.isPanning) {
    state.isPanning = false;
    state.canvas.style.cursor = 'crosshair';
  }
}

function onWheel(e) {
  e.preventDefault();
  const rect = state.canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;

  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const newZoom = Math.max(10, Math.min(5000, state.zoom * factor));

  // Zoom towards cursor
  state.panX = sx - (sx - state.panX) * (newZoom / state.zoom);
  state.panY = sy - (sy - state.panY) * (newZoom / state.zoom);
  state.zoom = newZoom;

  draw();
}

function onDoubleClick(e) {
  const rect = state.canvas.getBoundingClientRect();
  const sx = e.clientX - rect.left;
  const sy = e.clientY - rect.top;
  const { x: wx, y: wy } = screenToWorld(sx, sy);

  const dev = hitTest(wx, wy);
  if (dev) {
    state.selectedDevice = dev.id;
    updateDeviceList();
    log(`Selected: ${dev.name} (${dev.id}) at (${dev.x.toFixed(3)}, ${dev.y.toFixed(3)})`);
    draw();
  }
}

function zoomFit() {
  const cw = state.canvas.width / window.devicePixelRatio;
  const ch = state.canvas.height / window.devicePixelRatio;
  const padding = 60;

  if (state.devices.length === 0) {
    // Fit to lab bounds
    const scaleX = (cw - 2 * padding) / state.labWidth;
    const scaleY = (ch - 2 * padding) / state.labDepth;
    state.zoom = Math.min(scaleX, scaleY);
    state.panX = padding;
    state.panY = padding;
  } else {
    // Fit to device bounds (with workspace margin)
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;

    for (const dev of state.devices) {
      minX = Math.min(minX, dev.x - dev.w);
      maxX = Math.max(maxX, dev.x + dev.w);
      minY = Math.min(minY, dev.y - dev.d);
      maxY = Math.max(maxY, dev.y + dev.d);
    }

    // Include workspace
    if (state.workspace) {
      minX = Math.min(minX, state.workspace.armX - state.workspace.maxReach);
      maxX = Math.max(maxX, state.workspace.armX + state.workspace.maxReach);
      minY = Math.min(minY, state.workspace.armY - state.workspace.maxReach);
      maxY = Math.max(maxY, state.workspace.armY + state.workspace.maxReach);
    }

    // Include lab bounds
    minX = Math.min(minX, 0);
    maxX = Math.max(maxX, state.labWidth);
    minY = Math.min(minY, 0);
    maxY = Math.max(maxY, state.labDepth);

    const spanX = maxX - minX || 1;
    const spanY = maxY - minY || 1;

    const scaleX = (cw - 2 * padding) / spanX;
    const scaleY = (ch - 2 * padding) / spanY;
    state.zoom = Math.min(scaleX, scaleY);
    state.panX = padding - minX * state.zoom;
    state.panY = padding - minY * state.zoom;
  }

  draw();
}

// ============================================================
// Device List UI
// ============================================================

function updateDeviceList() {
  const container = document.getElementById('deviceList');
  container.innerHTML = '';

  for (const dev of state.devices) {
    const item = document.createElement('div');
    item.className = 'device-item' + (state.selectedDevice === dev.id ? ' selected' : '');
    item.innerHTML = `
      <div class="device-dot" style="background:${dev.color}"></div>
      <span>${dev.name}</span>
      <span style="color:#999;font-size:10px;margin-left:auto;">(${dev.x.toFixed(2)}, ${dev.y.toFixed(2)})</span>
    `;
    item.addEventListener('click', () => {
      state.selectedDevice = dev.id;
      updateDeviceList();
      draw();
    });
    container.appendChild(item);
  }
}

// ============================================================
// Lab Dimensions
// ============================================================

function onLabResize() {
  state.labWidth = parseFloat(document.getElementById('labWidth').value) || 2.0;
  state.labDepth = parseFloat(document.getElementById('labDepth').value) || 2.0;
  draw();
}

// ============================================================
// Constraints / Intents
// ============================================================

function onAddIntent() {
  const type = document.getElementById('intentType').value;

  if (type === 'reachable_by') {
    const arm = state.devices.find(d => d.class.includes('arm'));
    if (!arm) { log('ERROR: No arm device found.'); return; }
    if (!state.selectedDevice || state.selectedDevice === arm.id) {
      log('Select a non-arm device first, then add reachable_by.');
      return;
    }
    addIntent({
      type: 'reachable_by',
      params: { arm_id: arm.id, device_id: state.selectedDevice },
    });
  } else if (type === 'close_together' || type === 'far_apart') {
    if (!state.selectedDevice) { log('Select a device first.'); return; }
    addIntent({
      type,
      params: { device_ids: [state.selectedDevice] },
    });
  } else if (type === 'min_spacing') {
    addIntent({
      type: 'min_spacing',
      params: { distance: 0.1 },
    });
  } else if (type === 'max_distance') {
    if (!state.selectedDevice) { log('Select a device first.'); return; }
    addIntent({
      type: 'max_distance',
      params: { device_id: state.selectedDevice, max_dist: 0.5 },
    });
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
    item.innerHTML = `
      <span><span class="intent-tag">${intent.type}</span> ${desc}</span>
      <button class="btn btn-sm btn-danger" onclick="removeIntent(${idx})">x</button>
    `;
    container.appendChild(item);
  });
}

window.removeIntent = function(idx) {
  state.intents.splice(idx, 1);
  updateIntentList();
};

function onAutoIntents() {
  // Auto-generate reachable_by constraints from transport links
  const arm = state.devices.find(d => d.class.includes('arm'));
  if (!arm) { log('No arm device found.'); return; }

  let count = 0;
  for (const link of state.links) {
    if (link.type !== 'transport') continue;
    const targetId = link.source === arm.id ? link.target : link.source;
    // Check if constraint already exists
    const exists = state.intents.some(i =>
      i.type === 'reachable_by' && i.params.device_id === targetId
    );
    if (!exists) {
      state.intents.push({
        type: 'reachable_by',
        params: { arm_id: arm.id, device_id: targetId },
      });
      count++;
    }
  }

  // Add min_spacing if not exists
  if (!state.intents.some(i => i.type === 'min_spacing')) {
    state.intents.push({ type: 'min_spacing', params: { distance: 0.05 } });
    count++;
  }

  updateIntentList();
  log(`Auto-generated ${count} constraints from transport links.`);
}

// ============================================================
// Optimizer
// ============================================================

async function onOptimize() {
  if (state.optimizing) { log('Optimization already running...'); return; }
  if (state.devices.length === 0) { log('No devices loaded.'); return; }

  state.optimizing = true;
  const btn = document.getElementById('btnOptimize');
  btn.textContent = 'Optimizing...';
  btn.disabled = true;

  try {
    // 1. Build device descriptors
    const devices = state.devices.map(d => ({
      id: d.id,
      name: d.name,
      type: d.type,
      class: d.class,
      bbox: [d.w, d.d],
      position: [d.x, d.y, d.theta],
    }));

    const lab = { width: state.labWidth, depth: state.labDepth };

    // 2. Interpret intents → constraints
    let constraints = [];
    if (state.intents.length > 0) {
      log('Interpreting intents...');
      try {
        const interpretResp = await fetch('/api/v1/layout/interpret', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intents: state.intents }),
        });
        if (interpretResp.ok) {
          const result = await interpretResp.json();
          constraints = result.constraints || [];
          log(`Interpreted ${state.intents.length} intents → ${constraints.length} constraints`);
        } else {
          log(`Intent interpretation failed: ${interpretResp.status}`);
        }
      } catch (err) {
        log(`Intent API error: ${err.message}. Using direct constraints.`);
      }
    }

    // 3. Run optimizer
    log('Running differential evolution optimizer...');
    const maxiter = parseInt(document.getElementById('maxIter').value) || 200;
    const popsize = parseInt(document.getElementById('popSize').value) || 30;

    const optimizeResp = await fetch('/api/v1/layout/optimize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        devices,
        lab,
        constraints,
        maxiter,
        seed: 42,
        seeder: 'current',
        run_de: true,
      }),
    });

    if (!optimizeResp.ok) {
      const err = await optimizeResp.text();
      throw new Error(`Optimizer returned ${optimizeResp.status}: ${err}`);
    }

    const result = await optimizeResp.json();

    // 4. Apply results
    if (result.solution) {
      for (const placement of result.solution) {
        const dev = state.devices.find(d => d.id === placement.id);
        if (dev) {
          dev.x = placement.pos[0];
          dev.y = placement.pos[1];
          dev.theta = placement.pos[2] || 0;
        }
      }
      generateArmWorkspace();
      updateDeviceList();
    }

    state.cost = result.cost;
    document.getElementById('costDisplay').textContent =
      state.cost != null ? state.cost.toFixed(4) : '--';

    log(`Optimization complete! Cost: ${state.cost?.toFixed(4) ?? 'N/A'}`);
    if (result.collisions?.length > 0) {
      log(`  Collisions: ${result.collisions.map(c => c.join('↔')).join(', ')}`);
    }
    if (result.unreachable?.length > 0) {
      log(`  Unreachable: ${result.unreachable.join(', ')}`);
    }

    draw();

  } catch (err) {
    log(`ERROR: ${err.message}`);
  } finally {
    state.optimizing = false;
    btn.textContent = 'Optimize Layout';
    btn.disabled = false;
  }
}

// ============================================================
// Export
// ============================================================

function onExport() {
  if (!state.station) { log('No station loaded.'); return; }

  // Update positions in original station data
  const exportData = JSON.parse(JSON.stringify(state.station));
  for (const node of exportData.nodes || []) {
    const dev = state.devices.find(d => d.id === node.id);
    if (dev) {
      node.position = {
        x: Math.round(dev.x * 1000),  // back to station coords
        y: Math.round(dev.y * 1000),
        z: node.position?.z || 0,
      };
    }
  }

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'optimized_station.json';
  a.click();
  URL.revokeObjectURL(url);
  log('Exported optimized station JSON.');
}

// ============================================================
// Logging
// ============================================================

function log(msg) {
  const logEl = document.getElementById('optimizeLog');
  const time = new Date().toLocaleTimeString();
  logEl.textContent += `[${time}] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}
