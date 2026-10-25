import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
sw, _ = connect_solidworks(visible=True)
model = new_document(sw, "part")

# ---- shaft body: x=7..57, phi18 with groove phi16.5 x2 near right end ----
pts = [(7.0,0.0),(7.0,9.0),(54.0,9.0),(54.0,8.25),(56.0,8.25),(56.0,9.0),(56.5,9.0),(57.0,8.5),(57.0,0.0)]
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1,y1),(x2,y2) in zip(pts, pts[1:]+pts[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
cl = model.SketchManager.CreateLine(mm(2),0,0,mm(62),0,0)
cl.ConstructionGeometry = True; cl.Select2(False,0)
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
feat = P.revolve_boss(model, sk, 2*math.pi)
print("shaft revolve", feat)
if feat is None: raise SystemExit("revolve failed")

# ---- head outline: convex hull of 3 circles R8 at bolt circle R12, angles 180/70/-40 ----
def hull(points):
    pts = sorted(set(points))
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower=[]
    for p in pts:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0: lower.pop()
        lower.append(p)
    upper=[]
    for p in reversed(pts):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0: upper.pop()
        upper.append(p)
    return lower[:-1]+upper[:-1]
centers=[(12*math.cos(math.radians(a)),12*math.sin(math.radians(a))) for a in (180,70,-40)]
samples=[]
for cx,cy in centers:
    for k in range(72):
        a=2*math.pi*k/72
        samples.append((round(cx+8*math.cos(a),5),round(cy+8*math.sin(a),5)))
h=hull(samples)
print("head hull points",len(h),"extent",round(max(x for x,y in h)-min(x for x,y in h),2),round(max(y for x,y in h)-min(y for x,y in h),2))
P.start_sketch(model, "Right Plane")
model.SketchManager.AddToDB = True
for (x1,y1),(x2,y2) in zip(h, h[1:]+h[:1]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
model.SketchManager.AddToDB = False
sk2 = P.current_sketch_name(model); P.end_sketch(model)
head = P.extrude_boss(model, sk2, mm(7.0), direction=False, name="02_HEAD")
print("head boss", head)
if head is None: raise SystemExit("head failed")

# ---- head holes: 3x phi3 through + phi5.5 c'bore 3 deep; central M8 tap drill phi6.8 through head into shaft 24 deep ----
P.start_sketch(model, "Right Plane")
model.SketchManager.AddToDB = True
for cx,cy in centers:
    P.sketch_circle(model, mm(cx), mm(cy), mm(1.5))
model.SketchManager.AddToDB = False
sk3 = P.current_sketch_name(model); P.end_sketch(model)
cut = P.extrude_cut(model, sk3, 0, direction=False, name="03_SCREW_HOLES")
print("screw holes", cut)

# counterbores: sketch on head front face at x=0, circles phi5.5, cut 3 deep
P.start_sketch(model, "Right Plane")
model.SketchManager.AddToDB = True
for cx,cy in centers:
    P.sketch_circle(model, mm(cx), mm(cy), mm(2.75))
model.SketchManager.AddToDB = False
sk4 = P.current_sketch_name(model); P.end_sketch(model)
cb = P.extrude_cut(model, sk4, mm(3.0), direction=False, name="04_CBORE")
print("cbore", cb)

# central M8 tap drill through head + 17 into shaft = 24 total
P.start_sketch(model, "Right Plane")
model.SketchManager.AddToDB = True
P.sketch_circle(model, 0, 0, mm(3.4))
model.SketchManager.AddToDB = False
sk5 = P.current_sketch_name(model); P.end_sketch(model)
ctr = P.extrude_cut(model, sk5, mm(24.0), direction=False, name="05_M8_TAP")
print("center hole", ctr)

model.ForceRebuild3(False)
bb=model.GetPartBox(True)
print("bbox mm:", [round(v*1000,3) for v in bb])
R.save_preview(model, os.path.join(OUT,"XXJSQ-004_固定轴_preview.png"), view_name="isometric")
save_document(model, os.path.join(OUT,"XXJSQ-004_固定轴.SLDPRT"))
