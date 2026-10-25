import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
sw, _ = connect_solidworks(visible=True)
model = new_document(sw, "part")

# ring profile: axis X, radial Y; phi33 x5, phi27 x2, bore phi18
pts = [(0.0,9.0),(0.0,16.5),(5.0,16.5),(5.0,13.5),(7.0,13.5),(7.0,9.0)]
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1,y1),(x2,y2) in zip(pts, pts[1:]+pts[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
cl = model.SketchManager.CreateLine(mm(-3),0,0,mm(10),0,0)
cl.ConstructionGeometry = True
cl.Select2(False,0)
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model)
P.end_sketch(model)
feat = P.revolve_boss(model, sk, 2*math.pi)
print("revolve", feat)
if feat is None: raise SystemExit("revolve failed")

# keyway in bore: 6 wide x 1.8 deep, through 7 mm along X
P.start_sketch(model, "Right Plane")
model.SketchManager.AddToDB = True
P.sketch_corner_rectangle(model, mm(-3.0), mm(-10.8), mm(3.0), mm(-8.9))
model.SketchManager.AddToDB = False
sk2 = P.current_sketch_name(model)
P.end_sketch(model)
cut = P.extrude_cut(model, sk2, 0, direction=True, name="02_KEYWAY")
print("keyway", cut)
model.ForceRebuild3(False)

bb = model.GetPartBox(True)
print("bbox mm:", [round(v*1000,3) for v in bb])
R.save_preview(model, os.path.join(OUT, "XXJSQ-003_垫块_preview.png"), view_name="isometric")
save_document(model, os.path.join(OUT, "XXJSQ-003_垫块.SLDPRT"))
