import * as THREE from 'three';
import { getScene } from './scene-manager.js';

const linkLines = [];

export function drawLinks(devices, links) {
  clearLinks();
  const scene = getScene();

  for (const link of links) {
    const src = devices.find(d => d.id === link.source);
    const tgt = devices.find(d => d.id === link.target);
    if (!src || !tgt) continue;

    const sx = src.x, sy = src.y;
    const tx = tgt.x, ty = tgt.y;
    const mx = (sx + tx) / 2;
    const my = (sy + ty) / 2;
    const dx = tx - sx;
    const dy = ty - sy;
    const cx = mx - dy * 0.15;
    const cy = my + dx * 0.15;

    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(sx, 0.01, sy),
      new THREE.Vector3(cx, 0.01, cy),
      new THREE.Vector3(tx, 0.01, ty)
    );
    const curvePoints = curve.getPoints(20);

    const geo = new THREE.BufferGeometry().setFromPoints(curvePoints);
    const mat = new THREE.LineBasicMaterial({
      color: 0xffc107, transparent: true, opacity: 0.5,
    });
    const line = new THREE.Line(geo, mat);
    scene.add(line);
    linkLines.push(line);

    const lastPt = curvePoints[curvePoints.length - 1];
    const prevPt = curvePoints[curvePoints.length - 2];
    const dir = new THREE.Vector3().subVectors(lastPt, prevPt).normalize();
    const arrowHelper = new THREE.ArrowHelper(dir, prevPt, 0.04, 0xffc107, 0.02, 0.015);
    scene.add(arrowHelper);
    linkLines.push(arrowHelper);
  }
}

export function clearLinks() {
  const scene = getScene();
  for (const obj of linkLines) scene.remove(obj);
  linkLines.length = 0;
}

export function setLinksVisible(visible) {
  for (const obj of linkLines) obj.visible = visible;
}
