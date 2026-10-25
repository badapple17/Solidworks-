# -*- coding: utf-8 -*-
"""干涉检查 + 爆炸视图 + JPG"""
import sys, os, pythoncom, win32com.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, open_document, save_document, get_com_member, mm
import sw_assembly as A
from PIL import Image

def say(*a): print(*a, flush=True)
ASM = str(case_paths.ASM)
sw, _ = connect_solidworks(visible=True)
asm = open_document(sw, os.path.join(ASM, "XXJSQ_减速器.SLDASM"))
say("opened", get_com_member(asm, "GetTitle"))

# ---- interference ----
try:
    report = A.get_interference_detection(asm)
    say("interference:", report.get("status"), "count:", report.get("interference_count"))
    for it in (report.get("items") or [])[:5]:
        say("   ", it)
except Exception as ex:
    say("interference ERR", type(ex).__name__, ex)

def comps():
    d = {}
    for c in (get_com_member(asm, "GetComponents", True) or []):
        nm = str(get_com_member(c, "Name2"))
        for k in ("下盖","上盖","密封圈","齿圈","齿轮","传动轴","固定轴","垫块","旋转套"):
            if k in nm: d[k] = c
    return d

def arr(rot, t):
    vals = [v for row in rot for v in row] + [mm(t[0]), mm(t[1]), mm(t[2]), 1.0, 0.0, 0.0, 0.0]
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)

def move(c, rot, t):
    tr = c.Transform2
    tr.ArrayData = arr(rot, t)
    try: c.SetTransformAndSolve2(tr)
    except Exception: c.Transform2 = tr

def shot(path_bmp):
    for nm in ("*Isometric", "*Trimetric", "等轴测"):
        try:
            asm.ShowNamedView2(nm, 7); break
        except Exception: continue
    asm.ViewZoomtofit2()
    ok = asm.SaveBMP(path_bmp, 2000, 1400)
    say("savebmp", path_bmp, ok, os.path.exists(path_bmp))

# ---- assembled shot ----
shot(os.path.join(ASM, "_asm_iso.bmp"))

# ---- explode ----
IDENT = [[1.0,0,0],[0,1.0,0],[0,0,1.0]]
RY = [[0.0,0,1.0],[0,1.0,0],[-1.0,0,0]]
D = {
 "下盖":   (IDENT, (0, 0, 0)),
 "密封圈": (IDENT, (0, 0, -80)),
 "齿圈":   (IDENT, (0, 0, 55)),
 "固定轴": (RY,    (-37.5, 0, 110)),
 "垫块":   (RY,    (-37.5, 0, 185)),
 "传动轴": (RY,    (37.5, 0, 110)),
 "齿轮":   (IDENT, (37.5, 0, 235)),
 "旋转套": (IDENT, (0, 0, 300)),
 "上盖":   (IDENT, (0, 0, 400)),
}
cs = comps()
say("found comps", sorted(cs.keys()))
for k, (rot, t) in D.items():
    if k in cs: move(cs[k], rot, t)
get_com_member(asm, "EditRebuild3")
bb = get_com_member(asm, "GetBox", 0)
say("exploded bbox", [round(v*1000,1) for v in bb])
shot(os.path.join(ASM, "_asm_exploded.bmp"))
save_document(asm, os.path.join(ASM, "XXJSQ_减速器_爆炸图.SLDASM"))

for nm in ("_asm_iso", "_asm_exploded"):
    b = os.path.join(ASM, nm + ".bmp")
    if os.path.exists(b):
        Image.open(b).convert("RGB").save(os.path.join(ASM, nm + ".jpg"), quality=92)
        say("jpg", nm)
say("done")
