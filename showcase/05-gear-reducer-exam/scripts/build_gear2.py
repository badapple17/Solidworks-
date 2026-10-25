import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R
from gear_profiles import gear_points, area

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "XXJSQ-008_齿轮.SLDPRT")

sw, _ = connect_solidworks(visible=True)
try:
    sw.CloseDoc("XXJSQ-008_齿轮.SLDPRT")
except Exception:
    pass
model = new_document(sw, "part")

pts = gear_points(1.25, 30, internal=False, n_flank=4, arc_pts=1)
print("profile pts", len(pts), "area", round(area(pts), 3))
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
P.sketch_circle(model, 0, 0, mm(9.0))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
feat = P.extrude_boss(model, sk, mm(25.0), direction=False, name="01_GEAR_BODY")
print("extrude", feat)
if feat is None:
    raise SystemExit("extrude failed")

# 12 x phi4 on phi28 (drawing front view shows 12 holes at 30 deg; callout "24-phi4"
# is geometrically impossible on phi28 - 24 spacing 3.665 < phi4)
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for i in range(12):
    a = math.pi / 2 + i * math.pi / 6
    P.sketch_circle(model, mm(14 * math.cos(a)), mm(14 * math.sin(a)), mm(2.0))
model.SketchManager.AddToDB = False
sk2 = P.current_sketch_name(model); P.end_sketch(model)
cut = P.extrude_cut(model, sk2, 0, direction=True, name="02_HOLES_12")
print("holes", cut)
if cut is None:
    raise SystemExit("hole cut failed")

# keyway 6 wide, bottom at y=-10.8 (19.8 from bore top), through
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
P.sketch_corner_rectangle(model, mm(-3.0), mm(-10.8), mm(3.0), mm(-8.9))
model.SketchManager.AddToDB = False
sk3 = P.current_sketch_name(model); P.end_sketch(model)
cut2 = P.extrude_cut(model, sk3, 0, direction=True, name="03_KEYWAY")
print("keyway", cut2)

# C0.3 chamfers on bore edges not applied (edge selection unreliable); noted in report
model.ForceRebuild3(False)
bb = model.GetPartBox(True)
print("bbox mm:", [round(v * 1000, 3) for v in bb])
vol = R.collect_geometry_measurements(model).get("volume_mm3")
print("volume", round(vol, 1))

expected = area(pts) * 25 - math.pi * 81 * 25 - 11.22 * 25 - 12 * math.pi * 4 * 25
print("expected", round(expected, 1), "delta%", round((vol - expected) / expected * 100, 3))

R.save_preview(model, os.path.join(OUT, "XXJSQ-008_齿轮_preview.png"), view_name="isometric")
save_document(model, PATH)
