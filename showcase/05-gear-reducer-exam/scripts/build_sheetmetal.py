# -*- coding: utf-8 -*-
"""第二题 盖板 — 纯钣金特征建模 (基体法兰 + 边线法兰 + 切除)，板厚 0.5，折弯半径 0.5
Base panel 120 x 52, 45 deg corner cut; side walls 18 / end walls 12.
"""
import sys, os, math, pythoncom, win32com.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, get_com_member, mm
import sw_part as P
import sw_review as R

OUT = str(case_paths.PARTS); os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, "盖板_钣金.SLDPRT")
T = 0.5

def say(*a): print(*a, flush=True)

sw, _ = connect_solidworks(visible=True)
try: sw.CloseDoc("盖板_钣金.SLDPRT")
except Exception: pass
model = new_document(sw, "part")
fm = model.FeatureManager
nul = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

# ---------- base flange: 120 x 52 panel with 45 deg corner ----------
W, Hh = 120.0, 52.0
pts = [(-W/2, -Hh/2), (-W/2, Hh/2), (W/2, Hh/2), (W/2, -Hh/2), (-W/2 + 14, -Hh/2), (-W/2, -Hh/2 + 14), (-W/2, -Hh/2)]
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
model.SketchManager.AddToDB = False
sk = P.current_sketch_name(model); P.end_sketch(model)
model.ClearSelection2(True)
P._select_by_id(model.Extension, sk, "SKETCH")
base = fm.InsertSheetMetalBaseFlange(mm(T), False, mm(0.5), 0.0, 0.0, False, 0, 0, 0,
                                     nul, True, 0, 0.0, 0.0, 0.0, False)
say("base flange:", base.Name if base else None)
if base is None:
    raise SystemExit("base flange failed")
model.ForceRebuild3(False)
say("bbox", [round(v*1000,3) for v in model.GetPartBox(True)])

# ---------- edge flanges ----------
def edge_points(e):
    v1 = get_com_member(e, "GetStartVertex"); v2 = get_com_member(e, "GetEndVertex")
    p1 = get_com_member(v1, "GetPoint") if v1 else None
    p2 = get_com_member(v2, "GetPoint") if v2 else None
    return p1, p2

body = model.GetBodies2(0, False)[0]
edges = body.GetEdges()
say("edges", len(edges))
groups = {"y+": [], "y-": [], "x+": [], "x-": []}
for e in edges:
    p1, p2 = edge_points(e)
    if not p1 or not p2: continue
    z0, z1 = p1[2]*1000, p2[2]*1000
    if abs(z0 - z1) > 1e-6: continue
    if abs(z0 + T) > 1e-6 and abs(z0) > 1e-6:
        continue
    y0, y1 = p1[1]*1000, p2[1]*1000
    x0, x1 = p1[0]*1000, p2[0]*1000
    if abs(y0 - 26) < 1e-3 and abs(y1 - 26) < 1e-3 and abs(x1 - x0) > 50:
        groups["y+"].append(e)
    elif abs(y0 + 26) < 1e-3 and abs(y1 + 26) < 1e-3 and abs(x1 - x0) > 50:
        groups["y-"].append(e)
    elif abs(x0 - 60) < 1e-3 and abs(x1 - 60) < 1e-3 and abs(y1 - y0) > 20:
        groups["x+"].append(e)
    elif abs(x0 + 60) < 1e-3 and abs(x1 + 60) < 1e-3 and abs(y1 - y0) > 20:
        groups["x-"].append(e)
say({k: len(v) for k, v in groups.items()})

def add_flange(edge_list, height, bend_pos=1):
    arr = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, edge_list)
    empty = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [])
    return fm.InsertSheetMetalEdgeFlange2(arr, empty, 0, math.pi/2, mm(0.5), bend_pos,
                                          mm(height), 1, 0.5, mm(0.5), mm(0.5), 0, nul)

for key, hgt in (("y+", 18.0), ("y-", 18.0), ("x+", 12.0), ("x-", 12.0)):
    if not groups[key]:
        say("no edge for", key); continue
    f = add_flange(groups[key], hgt)
    say("flange", key, "->", f)
    model.ForceRebuild3(False)
    say("   bbox", [round(v*1000,3) for v in model.GetPartBox(True)])

save_document(model, PATH)
