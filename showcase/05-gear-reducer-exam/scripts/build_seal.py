# -*- coding: utf-8 -*-
"""唇形密封圈 120x150x12 — 回转唇形截面
axis = Z, air side z=0, oil side z=12
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "唇形密封圈120X150.SLDPRT")

sw, _ = connect_solidworks(visible=True)
try: sw.CloseDoc("唇形密封圈120X150.SLDPRT")
except Exception: pass
model = new_document(sw, "part")

R_OUT = 75.0
bands = [(0.0, 3.3, 67.5, "01_CASE_D135"),
         (3.3, 5.0, 62.0, "02_LIP_CONE"),
         (5.0, 8.0, 60.0, "03_LIP_D120"),
         (8.0, 12.0, 63.0, "04_DUST_LIP")]
for i, (z0, z1, r_in, name) in enumerate(bands):
    if i == 0:
        plane = "Front Plane"
    else:
        P.insert_offset_plane(model, "Front Plane", mm(z0), f"Pl_{i}")
        plane = f"Pl_{i}"
    P.start_sketch(model, plane)
    P.sketch_circle(model, 0, 0, mm(R_OUT))
    P.sketch_circle(model, 0, 0, mm(r_in))
    sk = P.current_sketch_name(model); P.end_sketch(model)
    f = P.extrude_boss(model, sk, mm(z1 - z0), direction=False, name=name)
    print(name, f)

model.ForceRebuild3(False)
bb = model.GetPartBox(True)
print("bbox mm:", [round(v * 1000, 3) for v in bb])
vol = R.collect_geometry_measurements(model).get("volume_mm3")
exp = sum(math.pi * (R_OUT**2 - r**2) * (z1 - z0) for z0, z1, r, _ in bands)
print("volume", round(vol, 1), "expected", round(exp, 1), "delta%", round((vol-exp)/exp*100, 3))
R.save_preview(model, os.path.join(OUT, "唇形密封圈120X150_preview.png"), view_name="isometric")
save_document(model, PATH)
