# -*- coding: utf-8 -*-
"""XXJSQ-010 上盖  — 回转壳体 + 端壁扇形观察窗 + 24-M5 法兰孔
axis = Z, left face z=0, total length 101
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "XXJSQ-010_上盖.SLDPRT")

def circle_boss(model, plane, r, z0, z1, name):
    P.start_sketch(model, plane)
    P.sketch_circle(model, 0, 0, mm(r))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return P.extrude_boss(model, sk, mm(z1 - z0), direction=False, name=name)

def circle_cut(model, plane, r, z0, z1, name):
    P.start_sketch(model, plane)
    P.sketch_circle(model, 0, 0, mm(r))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    return P.extrude_cut(model, sk, mm(z1 - z0), direction=True, name=name)

sw, _ = connect_solidworks(visible=True)
try: sw.CloseDoc("XXJSQ-010_上盖.SLDPRT")
except Exception: pass
model = new_document(sw, "part")

# ---- material ----
f1 = circle_boss(model, "Front Plane", 97.0, 0, 6, "01_FLANGE_D194")
print("flange", f1)
p_spig = P.insert_offset_plane(model, "Front Plane", mm(6.0), "Plane_Spigot")
f2 = circle_boss(model, "Plane_Spigot", 94.0, 6, 14.7, "02_SPIGOT_D188")
print("spigot", f2)
p_body = P.insert_offset_plane(model, "Front Plane", mm(14.7), "Plane_Body")
f3 = circle_boss(model, "Plane_Body", 85.0, 14.7, 101.0, "03_BODY_D170")
print("body", f3)

# ---- bores ----
c1 = circle_cut(model, "Front Plane", 79.0, 0, 6, "04_BORE_D158")
print("bore158", c1)
c2 = circle_cut(model, "Plane_Spigot", 75.0, 6, 93.0, "05_BORE_D150")
print("bore150", c2)

# ---- central boss on the end wall ----
p_boss = P.insert_offset_plane(model, "Front Plane", mm(88.0), "Plane_Boss42")
f4 = circle_boss(model, "Plane_Boss42", 21.0, 88, 93, "06_BOSS_D42")
p_b30 = P.insert_offset_plane(model, "Front Plane", mm(81.0), "Plane_Boss30")
f5 = circle_boss(model, "Plane_Boss30", 15.0, 81, 88, "07_BOSS_D30")
p_b27 = P.insert_offset_plane(model, "Front Plane", mm(81.0), "Plane_Boss30")
c3 = circle_cut(model, "Plane_Boss30", 13.5, 81, 101, "08_BORE_D27")
print("boss", f4, f5, c3)

# ---- fan window in the end wall: annulus r 25..58, 154.3 deg centred on -X ----
p_end = P.insert_offset_plane(model, "Front Plane", mm(93.0), "Plane_EndWall")
a_c = math.pi                      # centred on -X
half = math.radians(154.3 / 2)
r1, r2 = 25.0, 58.0
N = 180
pts = []
for i in range(N + 1):
    a = a_c - half + 2 * half * i / N
    pts.append((r2 * math.cos(a), r2 * math.sin(a)))
for i in range(N + 1):
    a = a_c + half - 2 * half * i / N
    pts.append((r1 * math.cos(a), r1 * math.sin(a)))
P.start_sketch(model, "Plane_EndWall")
model.SketchManager.AddToDB = True
for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
f6 = P.extrude_cut(model, sk, mm(8.0), direction=True, name="09_FAN_WINDOW")
print("window", f6)

# ---- 24 x M5 tap drill phi4.2 on phi182 ----
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for i in range(24):
    a = math.radians(7.5) + i * math.pi / 12
    P.sketch_circle(model, mm(91 * math.cos(a)), mm(91 * math.sin(a)), mm(2.1))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
f7 = P.extrude_cut(model, sk, mm(6.0), direction=True, name="10_HOLES_24_M5")
print("holes", f7)

model.ForceRebuild3(False)
bb = model.GetPartBox(True)
print("bbox mm:", [round(v * 1000, 3) for v in bb])
vol = R.collect_geometry_measurements(model).get("volume_mm3")
sector = 154.3 / 360.0
exp = (math.pi * 97**2 * 6 + math.pi * 94**2 * 8.7 + math.pi * 85**2 * 86.3
       - math.pi * 79**2 * 6 - math.pi * 75**2 * 87
       + math.pi * 21**2 * 5 + math.pi * 15**2 * 7 - math.pi * 13.5**2 * 20
       - sector * math.pi * (58**2 - 25**2) * 8
       - 24 * math.pi * 2.1**2 * 6)
print("volume", round(vol, 1), "expected", round(exp, 1), "delta%", round((vol-exp)/exp*100, 3))
R.save_preview(model, os.path.join(OUT, "XXJSQ-010_上盖_preview.png"), view_name="isometric")
save_document(model, PATH)
