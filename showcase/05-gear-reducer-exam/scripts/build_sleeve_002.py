# -*- coding: utf-8 -*-
"""XXJSQ-002 旋转套 — 套筒 phi118，孔系 phi110/phi108，端部 3 瓣 + 侧窗
axis = Z, top face z=0, total 69.5
Reading used (documented): OD phi118 constant; bores phi110 (0-28), phi108 (28-50);
solid end 50-69.5 carrying 3 lobe pockets phi26.5 + phi18.
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

def vol(model):
    model.ForceRebuild3(False)
    return R.collect_geometry_measurements(model).get("volume_mm3")

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "XXJSQ-002_旋转套.SLDPRT")

def cboss(model, plane, r, d, name):
    P.start_sketch(model, plane); P.sketch_circle(model, 0, 0, mm(r))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return P.extrude_boss(model, sk, mm(d), direction=False, name=name)

def ccut(model, plane, r, d, name):
    P.start_sketch(model, plane); P.sketch_circle(model, 0, 0, mm(r))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return P.extrude_cut(model, sk, mm(d), direction=True, name=name)

sw, _ = connect_solidworks(visible=True)
try: sw.CloseDoc("XXJSQ-002_旋转套.SLDPRT")
except Exception: pass
model = new_document(sw, "part")

L = 69.5
f1 = cboss(model, "Front Plane", 59.0, L, "01_BODY_D118")
print("body", f1, "V=", round(vol(model),1))

c1 = ccut(model, "Front Plane", 55.0, 28.0, "02_BORE_D110")
p28 = P.insert_offset_plane(model, "Front Plane", mm(28.0), "Plane_P28")
c2 = ccut(model, "Plane_P28", 54.0, 12.0, "03_BORE_D108")
print("bores", c1, c2, "V=", round(vol(model),1))

p_end = P.insert_offset_plane(model, "Front Plane", mm(L), "Plane_End")

# 6 x phi8.5, 24 deep, PCD phi36
P.start_sketch(model, "Plane_End")
model.SketchManager.AddToDB = True
for i in range(6):
    a = math.pi / 6 + i * math.pi / 3
    P.sketch_circle(model, mm(18 * math.cos(a)), mm(18 * math.sin(a)), mm(4.25))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
c6 = P.extrude_cut(model, sk, mm(24.0), direction=False, name="04_HOLES_6_D8.5")
print("d8.5", c6, "V=", round(vol(model),1))

# 3 lobe pockets phi26.5 x 19.5 from z=69.5
P.start_sketch(model, "Plane_End")
model.SketchManager.AddToDB = True
for i in range(3):
    a = math.pi / 2 + i * 2 * math.pi / 3
    P.sketch_circle(model, mm(37.5 * math.cos(a)), mm(37.5 * math.sin(a)), mm(13.25))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
c3 = P.extrude_cut(model, sk, mm(19.5), direction=False, name="05_LOBES_3_D26.5")
print("lobes", c3, "V=", round(vol(model),1))

# phi18 through the remaining 4.5 mm
p_lb = P.insert_offset_plane(model, "Front Plane", mm(50.0), "Plane_LobeBottom")
P.start_sketch(model, "Plane_LobeBottom")
model.SketchManager.AddToDB = True
for i in range(3):
    a = math.pi / 2 + i * 2 * math.pi / 3
    P.sketch_circle(model, mm(37.5 * math.cos(a)), mm(37.5 * math.sin(a)), mm(9.0))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
c4 = P.extrude_cut(model, sk, mm(10.0), direction=False, name="06_THRU_3_D18")
print("d18", c4, "V=", round(vol(model),1))

# side window 27 high x 40 wide through the sleeve wall, z = 8.5..35.5.
# Two true arcs + two radial lines form ONE closed annular-sector contour.
# Do NOT approximate this with a 60-segment polyline: SW2023 turns each chord
# into a separate sliver body (61 bodies measured on 2026-10-25).
half = math.asin(20.0 / 56.5)
a0, a1 = -half, half
o0 = (59.0 * math.cos(a0), 59.0 * math.sin(a0))
o1 = (59.0 * math.cos(a1), 59.0 * math.sin(a1))
i1 = (54.0 * math.cos(a1), 54.0 * math.sin(a1))
i0 = (54.0 * math.cos(a0), 54.0 * math.sin(a0))
p_win = P.insert_offset_plane(model, "Front Plane", mm(8.5), "Plane_Win")
P.start_sketch(model, "Plane_Win")
model.SketchManager.AddToDB = True
P.sketch_arc(model, 0, 0, mm(o0[0]), mm(o0[1]), mm(o1[0]), mm(o1[1]), direction=1)
P.sketch_line(model, mm(o1[0]), mm(o1[1]), mm(i1[0]), mm(i1[1]))
P.sketch_arc(model, 0, 0, mm(i1[0]), mm(i1[1]), mm(i0[0]), mm(i0[1]), direction=-1)
P.sketch_line(model, mm(i0[0]), mm(i0[1]), mm(o0[0]), mm(o0[1]))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
c5 = P.extrude_cut(model, sk, mm(27.0), direction=True, name="07_WINDOW_27X40")
print("window", c5, "V=", round(vol(model),1))

# 9 x M3 tap drill phi2.5 x 6 from the far end on phi75
P.start_sketch(model, "Plane_End")
model.SketchManager.AddToDB = True
for i in range(9):
    a = math.pi / 2 + math.radians(30) + i * 2 * math.pi / 9
    P.sketch_circle(model, mm(37.5 * math.cos(a)), mm(37.5 * math.sin(a)), mm(1.25))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
c7 = P.extrude_cut(model, sk, mm(6.0), direction=False, name="08_TAP_9_M3")
print("m3", c7, "V=", round(vol(model),1))

model.ForceRebuild3(False)
bb = model.GetPartBox(True)
print("bbox mm:", [round(v * 1000, 3) for v in bb])
vol = R.collect_geometry_measurements(model).get("volume_mm3")
win = half * (59**2 - 55**2) * 19.5 + half * (59**2 - 54**2) * 7.5
exp = (math.pi * 59**2 * L
       - math.pi * 55**2 * 28 - math.pi * 54**2 * 12
       - 6 * math.pi * 4.25**2 * 24
       - 3 * math.pi * 13.25**2 * 19.5 - 3 * math.pi * 9**2 * 10
       - win - 6 * math.pi * 1.25**2 * 6)
print("volume", round(vol, 1), "expected", round(exp, 1), "delta%", round((vol-exp)/exp*100, 3))
bodies = model.GetBodies2(0, False) or []
print("bodies", len(bodies))
if len(bodies) != 1:
    raise SystemExit(f"实体数 {len(bodies)} != 1：侧窗轮廓把筒壁切成了碎块")
R.save_preview(model, os.path.join(OUT, "XXJSQ-002_旋转套_preview.png"), view_name="isometric")
save_document(model, PATH)
