"""Reusable modelling helpers for the gear-pump build (SW2023 late binding)."""
from __future__ import annotations

import math

from common import PARTS, bbox_mm, size_mm

from sw_connect import create_empty_dispatch_variant, get_com_member, mm
from sw_part import (
    extrude_boss,
    extrude_cut,
    insert_offset_plane,
    sketch,
    sketch_arc,
    sketch_circle,
    sketch_line,
    sketch_polygon,
)


# ---------------------------------------------------------------- revolve
def revolve_profile(part, pts, name=None):
    """Revolve a closed (x, radius) polygon about the X axis (Front plane)."""
    with sketch(part, "Front Plane", exact=True) as sk:
        xs = [p[0] for p in pts]
        part.SketchManager.CreateCenterLine(
            mm(min(xs) - 5), 0, 0, mm(max(xs) + 5), 0, 0
        )
        closed = list(pts) + [pts[0]]
        for (x1, r1), (x2, r2) in zip(closed, closed[1:]):
            sketch_line(part, mm(x1), mm(r1), mm(x2), mm(r2))
    part.ClearSelection2(True)
    part.Extension.SelectByID2(
        sk, "SKETCH", 0, 0, 0, False, 0, create_empty_dispatch_variant(), 0
    )
    feature = part.FeatureManager.FeatureRevolve2(
        True, True, False, False, False, False,
        0, 0, 2 * math.pi, 0,
        False, False, 0.0, 0.0, 0, 0, 0, True, True, True,
    )
    part.ClearSelection2(True)
    if feature is not None and name:
        try:
            feature.Name = name
        except Exception:
            pass
    return feature


# ---------------------------------------------------------------- planes
def plane_at_x(part, x_mm, name="Plane_X"):
    return insert_offset_plane(part, "Right Plane", mm(x_mm), name=name)


def circle_on_yz(part, plane_name, y, z, radius):
    """Sketch a circle on a plane parallel to YZ at world (Y=y, Z=z).

    Right-plane sketch axes measured by probe: u -> -Z, v -> +Y.
    """
    with sketch(part, plane_name, exact=True) as sk:
        sketch_circle(part, mm(-z), mm(y), mm(radius))
    return sk


def circle_on_xz(part, plane_name, x, z, radius):
    """Top-plane (XZ, normal +Y) sketch: u -> +X, v -> -Z (probed)."""
    with sketch(part, plane_name, exact=True) as sk:
        sketch_circle(part, mm(x), mm(-z), mm(radius))
    return sk


def circle_on_xy(part, plane_name, x, y, radius):
    """Front-plane (XY, normal +Z) sketch: u -> +X, v -> +Y."""
    with sketch(part, plane_name, exact=True) as sk:
        sketch_circle(part, mm(x), mm(y), mm(radius))
    return sk


def rect_on_xy(part, plane_name, x1, x2, y1, y2):
    with sketch(part, plane_name, exact=True) as sk:
        pts = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        for (a, b), (c, d) in zip(pts, pts[1:] + pts[:1]):
            sketch_line(part, mm(a), mm(b), mm(c), mm(d))
    return sk


def plane_at_y(part, y_mm, name="Plane_Y"):
    return insert_offset_plane(part, "Top Plane", mm(y_mm), name=name)


def plane_at_z(part, z_mm, name="Plane_Z"):
    return insert_offset_plane(part, "Front Plane", mm(z_mm), name=name)


def cut_cyl_y(part, y0, x, z, dia, depth, name=None, direction=False):
    """Cut a cylinder along Y from the XZ plane at Y=y0.

    Raw cut semantics (probed): direction=False -> -Y, True -> +Y.
    """
    pl = plane_at_y(part, y0, name=f"P_{name or 'cutY'}")
    sk = circle_on_xz(part, pl.Name, x, z, dia / 2.0)
    return extrude_cut(part, sk, mm(depth), direction=direction, name=name)


def boss_cyl_y(part, y0, x, z, dia, depth, name=None, direction=False):
    """Boss along Y. Raw boss semantics: direction=False -> +Y."""
    pl = plane_at_y(part, y0, name=f"P_{name or 'bossY'}")
    sk = circle_on_xz(part, pl.Name, x, z, dia / 2.0)
    return extrude_boss(part, sk, mm(depth), direction=direction, name=name)


def cut_cyl_z(part, z0, x, y, dia, depth, name=None, direction=False):
    """Cut a cylinder along Z from the XY plane at Z=z0.

    Raw cut semantics: direction=False -> -Z, True -> +Z.
    """
    pl = plane_at_z(part, z0, name=f"P_{name or 'cutZ'}")
    sk = circle_on_xy(part, pl.Name, x, y, dia / 2.0)
    return extrude_cut(part, sk, mm(depth), direction=direction, name=name)


def cut_cyl_x(part, x0, y, z, dia, depth, name=None, direction=False):
    """Cut a cylinder along X, starting at plane X=x0, going +X by `depth`."""
    pl = plane_at_x(part, x0, name=f"P_{name or 'cut'}")
    sk = circle_on_yz(part, pl.Name, y, z, dia / 2.0)
    feat = extrude_cut(part, sk, mm(depth), direction=direction, name=name)
    return feat


def boss_cyl_x(part, x0, y, z, dia, depth, name=None, direction=False):
    pl = plane_at_x(part, x0, name=f"P_{name or 'boss'}")
    sk = circle_on_yz(part, pl.Name, y, z, dia / 2.0)
    return extrude_boss(part, sk, mm(depth), direction=direction, name=name)


# ---------------------------------------------------------------- hex
def extrude_hex(part, x0, circumradius, length, bore_dia=None, name=None,
                direction=False):
    """Hex prism from plane X=x0 along +X (direction=False => +X)."""
    pl = plane_at_x(part, x0, name=f"P_{name or 'hex'}")
    with sketch(part, pl.Name, exact=True) as sk:
        sketch_polygon(part, 0, 0, mm(circumradius), sides=6)
        if bore_dia:
            sketch_circle(part, 0, 0, mm(bore_dia / 2.0))
    return extrude_boss(part, sk, mm(length), direction=direction, name=name)


def rect_in_yz(part, plane_name, u1, u2, v1, v2):
    """Axis-aligned rectangle in the (u,v) plane."""
    pts = [(u1, v1), (u2, v1), (u2, v2), (u1, v2), (u1, v1)]
    for (a1, b1), (a2, b2) in zip(pts, pts[1:]):
        sketch_line(part, mm(a1), mm(b1), mm(a2), mm(b2))


def reset_sw(sw, delete_names=()):
    """Close every open document and delete stale outputs before rebuilding.

    SolidWorks silently refuses SaveAs over a file that a still-open document
    holds, leaving the old geometry on disk; the returned False is easy to miss.
    """
    try:
        sw.CloseAllDocuments(True)
    except Exception:
        pass
    import glob
    for stale in glob.glob(str(PARTS / "~$*")):
        try:
            import os
            os.remove(stale)
        except Exception:
            pass
    for name in delete_names:
        p = PARTS / f"{name}.SLDPRT"
        if p.exists():
            try:
                import os
                os.remove(p)
            except Exception as exc:
                print(f"  !! cannot remove {p}: {exc}")


def capsule_sketch(part, c1_u, c2_u, radius):
    """True stadium contour: two tangent lines + two 180-degree arcs.

    `capsule_points` gives a closed polyline, but every segment becomes its own
    planar face: the housing then shows ~80 stripes across its curved surface.
    Probe-confirmed on SW2023: CreateArc(direction=1) sweeps from the start
    point to the end point the short way (left cap top->bottom passes the left
    extreme), so the contour below closes exactly.
    """
    u1, u2 = min(c1_u, c2_u), max(c1_u, c2_u)
    sketch_line(part, mm(u1), mm(-radius), mm(u2), mm(-radius))
    sketch_arc(part, mm(u2), 0, mm(u2), mm(-radius), mm(u2), mm(radius), 1)
    sketch_line(part, mm(u2), mm(radius), mm(u1), mm(radius))
    sketch_arc(part, mm(u1), 0, mm(u1), mm(radius), mm(u1), mm(-radius), 1)


def capsule_points(c1_u, c2_u, radius, seg=48, v_zero=0.0):
    """Closed polyline for a capsule (two lobes + tangents) in the (u,v) plane.

    c1_u < c2_u. Caps at u=c1_u-radius (left) and u=c2_u+radius (right).
    Deterministic points avoid sketch inference entirely.
    """
    u1, u2 = min(c1_u, c2_u), max(c1_u, c2_u)
    pts = []
    # left cap: 90deg -> 270deg (top -> left -> bottom)
    for k in range(seg + 1):
        a = math.pi / 2 + math.pi * k / seg
        pts.append((u1 + radius * math.cos(a), v_zero + radius * math.sin(a)))
    # right cap: -90deg -> +90deg (bottom -> right -> top)
    for k in range(seg + 1):
        a = -math.pi / 2 + math.pi * k / seg
        pts.append((u2 + radius * math.cos(a), v_zero + radius * math.sin(a)))
    return pts


def save_part(session, part, name, expect=None, tol=0.2):
    part.ForceRebuild3(False)
    info = {"size_mm": size_mm(part), "bbox_mm": bbox_mm(part)}
    path = PARTS / f"{name}.SLDPRT"
    ok = session.save(part, str(path))
    info["saved"] = bool(ok)
    info["path"] = str(path)
    if expect is not None:
        got = info["size_mm"]
        info["expect"] = list(expect)
        info["match"] = all(abs(g - e) <= tol for g, e in zip(got, expect))
        if not info["match"]:
            print(f"  !! {name} size {got} != expected {list(expect)}")
    print(f"[SAVE] {name}: {info['size_mm']}")
    return info
