"""Pencil integration stub.

The original pencil_integration module has been removed from this package.
This stub provides the two functions that optimizer.py and seeders.py
reference, delegating to the built-in seeder as a simple row fallback.
"""

from __future__ import annotations

import math
from .models import Device, Lab, Placement


def generate_initial_layout(
    devices: list[Device], lab: Lab
) -> list[Placement]:
    """Generate a simple grid layout (used as seed when no seeder is specified)."""
    return _row_layout(devices, lab)


def generate_fallback(
    devices: list[Device], lab: Lab
) -> list[Placement]:
    """Fallback row layout for the ``row_fallback`` seeder preset."""
    return _row_layout(devices, lab)


def _row_layout(devices: list[Device], lab: Lab) -> list[Placement]:
    """Arrange devices in rows, centred in the lab."""
    if not devices:
        return []

    n = len(devices)
    cols = max(1, int(math.ceil(math.sqrt(n))))
    rows = max(1, math.ceil(n / cols))

    placements: list[Placement] = []
    margin = 0.3
    for i, dev in enumerate(devices):
        row, col = divmod(i, cols)
        x = margin + (col + 0.5) * (lab.width - 2 * margin) / cols
        y = margin + (row + 0.5) * (lab.depth - 2 * margin) / rows
        x = min(max(x, dev.bbox[0] / 2), lab.width - dev.bbox[0] / 2)
        y = min(max(y, dev.bbox[1] / 2), lab.depth - dev.bbox[1] / 2)
        placements.append(Placement(device_id=dev.id, x=x, y=y, theta=0.0))

    return placements
