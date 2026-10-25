import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R
from gear_profiles import gear_points, area

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "XXJSQ-009_齿圈.SLDPRT")

sw, _ = connect_solidworks(visible=True)
try:
    sw.CloseDoc("XXJSQ-009_齿圈.SLDPRT")
except Exception:
    pass
model = new_document(sw, "part")

# body phi130 x 21.5 (front z=0)
P.start_sketch(model, "Front Plane")
P.sketch_circle(model, 0, 0, mm(65.0))
sk = P.current_sketch_name(model); P.end_sketch(model)
f1 = P.extrude_boss(model, sk, mm(21.5), direction=False, name="01_BODY_D130")
print("body", f1)

# flange phi150 x 3.5 at back (z=21.5..25)
pl = P.insert_offset_plane(model, "Front Plane", mm(21.5), "Plane_Flange")
P.start_sketch(model, "Plane_Flange")
P.sketch_circle(model, 0, 0, mm(75.0))
sk = P.current_sketch_name(model); P.end_sketch(model)
f2 = P.extrude_boss(model, sk, mm(3.5), direction=False, name="02_FLANGE_D150")
print("flange", f2)

# internal teeth m1.25 z90, z=0..17.5
pts = gear_points(1.25, 90, internal=True, n_flank=4, arc_pts=1)
print("teeth pts", len(pts), "bore area", round(area(pts), 3))
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
f3 = P.extrude_cut(model, sk, mm(17.5), direction=True, name="03_TEETH_Z90")
print("teeth cut", f3)

# phi124 relief bore z=17.5..25
pl2 = P.insert_offset_plane(model, "Front Plane", mm(17.5), "Plane_Relief")
P.start_sketch(model, "Plane_Relief")
P.sketch_circle(model, 0, 0, mm(62.0))
sk = P.current_sketch_name(model); P.end_sketch(model)
f4 = P.extrude_cut(model, sk, 0, direction=True, name="04_BORE_D124")
print("relief", f4)

# 24 x phi4 through flange + phi6 counterbore 3 deep, from back face z=25
pl3 = P.insert_offset_plane(model, "Front Plane", mm(25.0), "Plane_Back")
P.start_sketch(model, "Plane_Back")
model.SketchManager.AddToDB = True
for i in range(24):
    a = math.pi / 2 + i * math.pi / 12
    P.sketch_circle(model, mm(70 * math.cos(a)), mm(70 * math.sin(a)), mm(2.0))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
f5 = P.extrude_cut(model, sk, mm(3.5), direction=False, name="05_HOLES_24_D4")
print("holes", f5)

P.start_sketch(model, "Plane_Back")
model.SketchManager.AddToDB = True
for i in range(24):
    a = math.pi / 2 + i * math.pi / 12
    P.sketch_circle(model, mm(70 * math.cos(a)), mm(70 * math.sin(a)), mm(3.0))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
f6 = P.extrude_cut(model, sk, mm(3.0), direction=False, name="06_CBORE_24_D6X3")
print("cbore", f6)

model.ForceRebuild3(False)
bb = model.GetPartBox(True)
print("bbox mm:", [round(v * 1000, 3) for v in bb])
vol = R.collect_geometry_measurements(model).get("volume_mm3")
print("volume", round(vol, 1))
exp = (math.pi * 65**2 - area(pts)) * 17.5 \
    + (math.pi * 65**2 - math.pi * 62**2) * 4.0 \
    + (math.pi * 75**2 - math.pi * 62**2) * 3.5 \
    - 24 * math.pi * 2**2 * 3.5 - 24 * math.pi * (3**2 - 2**2) * 3.0
print("expected", round(exp, 1), "delta%", round((vol - exp) / exp * 100, 3))

R.save_preview(model, os.path.join(OUT, "XXJSQ-009_齿圈_preview.png"), view_name="isometric")
save_document(model, PATH)
