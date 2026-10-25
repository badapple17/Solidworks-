# -*- coding: utf-8 -*-
"""XXJSQ-006 下盖 — 方形法兰 + 圆筒 + 圆形法兰
axis = Z, left (square flange) face z=0, total 112.3
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "XXJSQ-006_下盖.SLDPRT")

def circle_boss(model, plane, r, d, name):
    P.start_sketch(model, plane); P.sketch_circle(model, 0, 0, mm(r))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return P.extrude_boss(model, sk, mm(d), direction=False, name=name)

def circle_cut(model, plane, r, d, name):
    P.start_sketch(model, plane); P.sketch_circle(model, 0, 0, mm(r))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return P.extrude_cut(model, sk, mm(d), direction=True, name=name)

def rounded_square_sketch(model, plane, side, rad):
    """square with filleted corners, approximated by a polyline (closed)."""
    h = side / 2.0
    c = h - rad
    pts = []
    for cx, cy, a0 in ((c, c, 0), (-c, c, 90), (-c, -c, 180), (c, -c, 270)):
        for i in range(19):
            a = math.radians(a0 + 90.0 * i / 18.0)
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    P.start_sketch(model, plane)
    model.SketchManager.AddToDB = True
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
    model.SketchManager.AddToDB = False
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return sk

sw, _ = connect_solidworks(visible=True)
try: sw.CloseDoc("XXJSQ-006_下盖.SLDPRT")
except Exception: pass
model = new_document(sw, "part")

# square flange 189 x 189, R20, 6 thick
sk = rounded_square_sketch(model, "Front Plane", 189.0, 20.0)
f1 = P.extrude_boss(model, sk, mm(6.0), direction=False, name="01_SQUARE_FLANGE")
print("square flange", f1)
p_body = P.insert_offset_plane(model, "Front Plane", mm(6.0), "Plane_Tube")
f2 = circle_boss(model, "Plane_Tube", 85.0, 100.3, "02_TUBE_D170")
print("tube", f2)
p_rf = P.insert_offset_plane(model, "Front Plane", mm(106.3), "Plane_RFlange")
f3 = circle_boss(model, "Plane_RFlange", 97.0, 6.0, "03_FLANGE_D194")
print("r flange", f3)

# bores
c1 = circle_cut(model, "Front Plane", 79.0, 10.0, "04_BORE_D158")
p150 = P.insert_offset_plane(model, "Front Plane", mm(10.0), "Plane_B150")
c2 = circle_cut(model, "Plane_B150", 75.0, 89.3, "05_BORE_D150")
p134 = P.insert_offset_plane(model, "Front Plane", mm(99.3), "Plane_134")
c3 = circle_cut(model, "Plane_134", 67.0, 7.0, "06_BORE_D134")
c4 = circle_cut(model, "Plane_RFlange", 65.0, 6.0, "07_BORE_D130")
print("bores", c1, c2, c3, c4)

# 24 x phi5 on phi182 through the round flange
P.start_sketch(model, "Plane_RFlange")
model.SketchManager.AddToDB = True
for i in range(24):
    a = i * math.pi / 12
    P.sketch_circle(model, mm(91 * math.cos(a)), mm(91 * math.sin(a)), mm(2.5))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
h2 = P.extrude_cut(model, sk, mm(6.0), direction=True, name="08_HOLES_24_D5")

# 4 x phi13.5 corner holes (square pattern 130)
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for sx in (-1, 1):
    for sy in (-1, 1):
        P.sketch_circle(model, mm(sx * 65), mm(sy * 65), mm(6.75))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
h1 = P.extrude_cut(model, sk, mm(6.0), direction=True, name="09_HOLES_4_D13.5")

# 24 x M4 tap drill phi3.3 on phi140 in the round flange
P.start_sketch(model, "Plane_RFlange")
model.SketchManager.AddToDB = True
for i in range(24):
    a = math.radians(7.5) + i * math.pi / 12
    P.sketch_circle(model, mm(70 * math.cos(a)), mm(70 * math.sin(a)), mm(1.65))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
h3 = P.extrude_cut(model, sk, mm(6.0), direction=True, name="10_HOLES_24_M4")
print("holes", h1, h2, h3)

model.ForceRebuild3(False)
bb = model.GetPartBox(True)
print("bbox mm:", [round(v * 1000, 3) for v in bb])
vol = R.collect_geometry_measurements(model).get("volume_mm3")
sq = 189**2 - (4 - math.pi) * 20**2
exp = (sq * 6 + math.pi * 85**2 * 100.3 + math.pi * 97**2 * 6
       - math.pi * 79**2 * 10 - math.pi * 75**2 * 89.3
       - math.pi * 67**2 * 7 - math.pi * 65**2 * 6
       - 24 * math.pi * 2.5**2 * 6 - 4 * math.pi * 6.75**2 * 6
       - 24 * math.pi * 1.65**2 * 6)
print("volume", round(vol, 1), "expected", round(exp, 1), "delta%", round((vol-exp)/exp*100, 3))
R.save_preview(model, os.path.join(OUT, "XXJSQ-006_下盖_preview.png"), view_name="isometric")
save_document(model, PATH)
