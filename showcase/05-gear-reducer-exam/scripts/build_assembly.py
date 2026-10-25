# -*- coding: utf-8 -*-
"""XXJSQ 减速器 装配体"""
import sys, os, math, pythoncom, win32com.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, get_com_member, mm
import sw_assembly as A
import sw_review as R

def say(*a): print(*a, flush=True)
PARTS = str(case_paths.PARTS); ASM = str(case_paths.ASM)
os.makedirs(ASM, exist_ok=True)
sw, _ = connect_solidworks(visible=True)
try: sw.CloseDoc("XXJSQ_减速器.SLDASM")
except Exception: pass
asm = new_document(sw, "assembly")
mu = get_com_member(sw, "GetMathUtility")

def arr(rot, t):
    vals = [v for row in rot for v in row] + [mm(t[0]), mm(t[1]), mm(t[2]), 1.0, 0.0, 0.0, 0.0]
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)

IDENT = [[1.0,0,0],[0,1.0,0],[0,0,1.0]]
RY = [[0.0,0,1.0],[0,1.0,0],[-1.0,0,0]]      # +X -> +Z (row-vector convention)

def place(fname, rot, t, tag):
    comp = A.add_component(asm, os.path.join(PARTS, fname), 0, 0, 0, sw=sw)
    if comp is None:
        say("!! failed", fname); return None
    ok = False
    try:
        tr = comp.Transform2
        tr.ArrayData = arr(rot, t)
        try:
            ok = bool(comp.SetTransformAndSolve2(tr))
        except Exception:
            comp.Transform2 = tr; ok = True
    except Exception as ex:
        say("   transform ERR", type(ex).__name__, ex)
    if not ok:
        say("   !! transform failed")
    get_com_member(asm, "EditRebuild3")
    pose = A.get_component_pose(comp)
    say(tag, fname, "pose t=", [round(v*1000,1) for v in pose[0]])
    return comp

inserted = []
inserted.append(place("XXJSQ-006_下盖.SLDPRT", IDENT, (0,0,0), "下盖"))
inserted.append(place("XXJSQ-010_上盖.SLDPRT", IDENT, (0,0,112.3), "上盖"))
inserted.append(place("唇形密封圈120X150.SLDPRT", IDENT, (0,0,10.0), "密封圈"))
inserted.append(place("XXJSQ-009_齿圈.SLDPRT", IDENT, (0,0,20.0), "齿圈"))
GC = 37.5
inserted.append(place("XXJSQ-008_齿轮.SLDPRT", IDENT, (GC,0,20.0), "齿轮"))
inserted.append(place("XXJSQ-007_传动轴.SLDPRT", RY, (GC,0,15.0), "传动轴"))
inserted.append(place("XXJSQ-004_固定轴.SLDPRT", RY, (-GC,0,20.0), "固定轴"))
inserted.append(place("XXJSQ-003_垫块.SLDPRT", RY, (-GC,0,77.0), "垫块"))
inserted.append(place("XXJSQ-002_旋转套.SLDPRT", IDENT, (0,0,130.0), "旋转套"))

get_com_member(asm, "EditRebuild3")
say("components:", get_com_member(asm, "GetComponentCount", False))
bb = get_com_member(asm, "GetBox", 0)
say("asm bbox mm", [round(v*1000,1) for v in bb])
save_document(asm, os.path.join(ASM, "XXJSQ_减速器.SLDASM"))
say("saved")
