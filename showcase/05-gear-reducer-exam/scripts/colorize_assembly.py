# -*- coding: utf-8 -*-
"""Make a transparent, colour-coded copy of the reducer assembly.

Original assembly is left untouched: the file is copied first, then coloured.
Housings (006/010) become translucent so the internal train stays readable.
"""
import sys, os, shutil, pythoncom
import win32com.client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, open_document, save_document
from PIL import Image

OUT = str(case_paths.ASM)
SRC = os.path.join(OUT, "XXJSQ_减速器.SLDASM")
DST = os.path.join(OUT, "XXJSQ_减速器_透明涂色.SLDASM")

# name fragment -> (RGB 0..1, transparency 0=opaque 1=invisible)
PALETTE = {
    "下盖":   ((0.70, 0.75, 0.82), 0.82),
    "上盖":   ((0.82, 0.78, 0.71), 0.82),
    "旋转套": ((0.20, 0.52, 0.90), 0.35),
    "齿圈":   ((0.95, 0.72, 0.15), 0.10),
    "齿轮":   ((0.90, 0.30, 0.16), 0.00),
    "传动轴": ((0.18, 0.64, 0.34), 0.00),
    "固定轴": ((0.55, 0.34, 0.80), 0.00),
    "垫块":   ((0.12, 0.70, 0.75), 0.00),
    "密封圈": ((0.10, 0.10, 0.10), 0.40),
}


def set_component_color(comp, rgb, transparency):
    vals = [rgb[0], rgb[1], rgb[2], 0.30, 0.70, 0.60, 0.40, transparency, 0.0]
    mat = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)
    names = win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [])
    comp.SetMaterialPropertyValues2(mat, 2, names)   # 2 = swAllConfiguration


def shot(asm, path_bmp, view="*Isometric", w=2200, h=1500):
    try:
        asm.ShowNamedView2(view, 7)
    except Exception as e:
        print("view warn", view, e)
    asm.ViewZoomtofit2()
    ok = asm.SaveBMP(path_bmp, w, h)
    print("savebmp", os.path.basename(path_bmp), ok, os.path.exists(path_bmp))


sw, _ = connect_solidworks(visible=True)
if not os.path.exists(DST):
    shutil.copy2(SRC, DST)
    print("copied ->", os.path.basename(DST))
else:
    print("reuse", os.path.basename(DST))

asm = open_document(sw, DST)
print("title", asm.GetTitle)

comps = asm.GetComponents(False) or []
print("components", len(comps))

# the assembly is stored with every component suppressed -> resolve them first,
# otherwise the model has an empty bounding box and renders blank
for c in comps:
    st = c.SetSuppression2(2)          # 2 = swComponentFullyResolved
    if st != 2:                        # 2 = swSuppressionChangeOk
        print("  resolve status", st, c.Name2)

def apply_colours(components):
    """Apply palette and verify the readback. Returns [(name, rgb, tr), ...]."""
    bad = []
    for c in components:
        nm = str(c.Name2)
        hit = next((k for k in PALETTE if k in nm), None)
        if hit is None:
            print("  no colour for", nm)
            continue
        rgb, tr = PALETTE[hit]
        try:
            c.Visible = True
        except Exception:
            pass
        try:
            set_component_color(c, rgb, tr)
            back = c.MaterialPropertyValues
            good = (
                max(abs(back[i] - rgb[i]) for i in range(3)) <= 0.02
                and abs(back[7] - tr) <= 0.02
            )
            print(f"  {nm:26s} rgb={rgb} trans={tr} -> readback "
                  f"{[round(v,3) for v in back[:3]]} t={round(back[7],3)}"
                  f"{'' if good else '  <-- RETRY'}")
            if not good:
                bad.append((nm, rgb, tr))
        except Exception as e:
            print("  ERR", nm, type(e).__name__, e)
            bad.append((nm, rgb, tr))
    return bad

try:
    asm.ForceRebuild3(False)
except Exception as e:
    print("rebuild warn", e)

bad = apply_colours(comps)
if bad:
    # SW2023: the first components coloured before the assembly finishes
    # resolving silently keep their part colour. Re-fetch and re-apply.
    try:
        asm.ForceRebuild3(False)
    except Exception:
        pass
    wanted = {nm: (rgb, tr) for nm, rgb, tr in bad}
    for c in asm.GetComponents(False) or []:
        nm = str(c.Name2)
        if nm in wanted:
            rgb, tr = wanted[nm]
            set_component_color(c, rgb, tr)
            back = c.MaterialPropertyValues
            print(f"  retry {nm:24s} -> {[round(v,3) for v in back[:3]]} t={round(back[7],3)}")
            if abs(back[7] - tr) > 0.02:
                raise SystemExit(f"上色回读失败: {nm}")

print("box mm", [round(v * 1000, 1) for v in asm.GetBox(0)])
shot(asm, os.path.join(OUT, "_asm_colored_iso.bmp"), "*Isometric")
shot(asm, os.path.join(OUT, "_asm_colored_front.bmp"), "*Front")
shot(asm, os.path.join(OUT, "_asm_colored_top.bmp"), "*Top")
save_document(asm, DST)

for nm in ("_asm_colored_iso", "_asm_colored_front", "_asm_colored_top"):
    b = os.path.join(OUT, nm + ".bmp")
    if os.path.exists(b):
        Image.open(b).convert("RGB").save(os.path.join(OUT, nm + ".jpg"), quality=92)
        print("jpg", nm)
print("done")
