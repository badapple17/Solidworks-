import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS)
os.makedirs(OUT, exist_ok=True)

sw, _ = connect_solidworks(visible=True)
model = new_document(sw, "part")

# ---- revolve profile: shaft axis X, radial Y ----
pts = [
    (0.0, 0.0), (0.0, 7.0), (0.5, 7.5),          # left chamfer C0.5 on phi15
    (18.0, 7.5), (18.0, 9.0),
    (50.0, 9.0), (50.0, 12.5),
    (58.5, 12.5), (58.5, 15.5),
    (65.5, 15.5), (65.5, 12.5),
    (89.5, 12.5), (89.5, 9.0),
    (105.0, 9.0), (105.5, 8.5), (105.5, 0.0),
]
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1,y1),(x2,y2) in zip(pts, pts[1:]+pts[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
cl = model.SketchManager.CreateLine(mm(-5), 0, 0, mm(110), 0, 0)
cl.ConstructionGeometry = True
cl.Select2(False, 0)
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model)
P.end_sketch(model)
feat = P.revolve_boss(model, sk, 2*math.pi)
print("revolve:", feat, "sketch", sk)
if feat is None:
    raise SystemExit("revolve failed")

# ---- keyway on phi18 section: 6 wide x 2.5 deep x 16 long, starts 7 mm from shoulder ----
plane = P.insert_offset_plane(model, "Top Plane", mm(9.0), "Plane_Keyway")
P.start_sketch(model, "Plane_Keyway")
model.SketchManager.AddToDB = True
P.sketch_slot(model, mm(28.0), 0.0, mm(38.0), 0.0, mm(3.0))
model.SketchManager.AddToDB = False
sk2 = P.current_sketch_name(model)
P.end_sketch(model)
cut = P.extrude_cut(model, sk2, mm(2.5), direction=False, name="02_KEYWAY")
print("keyway cut:", cut)
model.ClearSelection2(True)
model.ForceRebuild3(False)

bb = model.GetPartBox(True)
print("bbox mm:", [round(v*1000,3) for v in bb])
R.save_preview(model, os.path.join(OUT, "XXJSQ-007_传动轴_preview.png"), view_name="isometric")
save_document(model, os.path.join(OUT, "XXJSQ-007_传动轴.SLDPRT"))
