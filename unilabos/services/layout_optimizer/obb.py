"""OBB (Oriented Bounding Box) geometry: corners, overlap (SAT), minimum distance."""
from __future__ import annotations
import math


def obb_corners(
    cx: float, cy: float, w: float, h: float, theta: float
) -> list[tuple[float, float]]:
    """Return 4 corners of the OBB as (x, y) tuples.

    Args:
        cx, cy: center position
        w, h: full width and height (not half-extents)
        theta: rotation angle in radians
    """
    hw, hh = w / 2, h / 2
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    dx_w, dy_w = hw * cos_t, hw * sin_t   # half-width vector
    dx_h, dy_h = -hh * sin_t, hh * cos_t  # half-height vector
    return [
        (cx + dx_w + dx_h, cy + dy_w + dy_h),
        (cx - dx_w + dx_h, cy - dy_w + dy_h),
        (cx - dx_w - dx_h, cy - dy_w - dy_h),
        (cx + dx_w - dx_h, cy + dy_w - dy_h),
    ]


def _get_axes(corners: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return 2 edge-normal axes for a rectangle (4 corners)."""
    axes = []
    for i in range(2):  # Only need 2 axes for a rectangle
        edge_x = corners[i + 1][0] - corners[i][0]
        edge_y = corners[i + 1][1] - corners[i][1]
        length = math.sqrt(edge_x**2 + edge_y**2)
        if length > 0:
            axes.append((-edge_y / length, edge_x / length))
    return axes


def _project(corners: list[tuple[float, float]], axis: tuple[float, float]) -> tuple[float, float]:
    """Project all corners onto axis, return (min, max) scalar projections."""
    dots = [c[0] * axis[0] + c[1] * axis[1] for c in corners]
    return min(dots), max(dots)


def obb_overlap(corners_a: list[tuple[float, float]], corners_b: list[tuple[float, float]]) -> bool:
    """Return True if two OBBs overlap using Separating Axis Theorem.

    Uses strict inequality (touching edges = no overlap).
    """
    for axis in _get_axes(corners_a) + _get_axes(corners_b):
        min_a, max_a = _project(corners_a, axis)
        min_b, max_b = _project(corners_b, axis)
        if max_a <= min_b or max_b <= min_a:
            return False
    return True


def _point_to_segment_dist_sq(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> float:
    """Squared distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len_sq))
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return (px - proj_x) ** 2 + (py - proj_y) ** 2


def obb_penetration_depth(
    corners_a: list[tuple[float, float]],
    corners_b: list[tuple[float, float]],
) -> float:
    """Minimum penetration depth between two OBBs (SAT-based).

    Returns 0.0 if not overlapping. Otherwise returns the minimum overlap
    along any separating axis — the smallest push needed to separate them.
    """
    min_overlap = float("inf")
    for axis in _get_axes(corners_a) + _get_axes(corners_b):
        min_a, max_a = _project(corners_a, axis)
        min_b, max_b = _project(corners_b, axis)
        overlap = min(max_a - min_b, max_b - min_a)
        if overlap <= 0:
            return 0.0  # Separated on this axis
        if overlap < min_overlap:
            min_overlap = overlap
    return min_overlap


def obb_min_distance(
    corners_a: list[tuple[float, float]],
    corners_b: list[tuple[float, float]],
) -> float:
    """Minimum distance between two OBBs (convex polygons).

    Returns 0.0 if overlapping or touching.
    """
    if obb_overlap(corners_a, corners_b):
        return 0.0

    min_dist_sq = float("inf")
    for poly, other in [(corners_a, corners_b), (corners_b, corners_a)]:
        n = len(other)
        for px, py in poly:
            for i in range(n):
                ax, ay = other[i]
                bx, by = other[(i + 1) % n]
                d_sq = _point_to_segment_dist_sq(px, py, ax, ay, bx, by)
                if d_sq < min_dist_sq:
                    min_dist_sq = d_sq
    return math.sqrt(min_dist_sq)
