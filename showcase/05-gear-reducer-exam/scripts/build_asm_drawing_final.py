# -*- coding: utf-8 -*-
"""XXJSQ reducer assembly drawing — final A2 sheet.

Layout: first-angle front / left / top + isometric, GB 明细栏 above the title block,
技术要求 top-left, data-gap note under the isometric.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths
from sw_connect import connect_solidworks, new_document, save_document, get_com_member, open_document
import sw_drawing as D
import sw_three_view as TV

ASM = os.path.join(str(case_paths.ASM), "XXJSQ_减速器.SLDASM")
OUTDIR = os.path.join(str(case_paths.DRAWINGS), "装配图")
os.makedirs(OUTDIR, exist_ok=True)
DRW = os.path.join(OUTDIR, "XXJSQ_减速器_装配图.SLDDRW")
PDF = os.path.join(OUTDIR, "XXJSQ_减速器_装配图.pdf")
GB_BOM = case_paths.find_bom_template()

sw, _ = connect_solidworks(visible=True)
asm = open_document(sw, ASM)

spec = TV.find_drawing_template("A2")
draft = new_document(sw, "drawing", template_path=spec["template"])
TV.setup_sheet(draft, "A2", spec["sheet_format"], (1, 2))


def note_at(dr, x, y, text, char_h=0.0032):
    n = dr.InsertNote(text)
    if n is None:
        return None
    try:
        ann = n.GetAnnotation
        ann.SetPosition(x, y, 0)
        tf = n.GetTextFormat
        tf.CharHeight = char_h
    except Exception as e:
        print("note err", e)
    return n


layout = [("*Front", 0.145, 0.295),
          ("*Left",  0.305, 0.295),
          ("*Top",   0.145, 0.145),
          ("*Isometric", 0.455, 0.300)]
views = {}
for name, x, y in layout:
    v = D.add_view(draft, ASM, name, x, y)
    print("view", name, v is not None)
    if v is not None:
        views[name] = v

front = views.get("*Front")
bom = None
if front is not None:
    try:
        bom = front.InsertBomTable4(False, 0.402, 0.160, 1, 1, "", GB_BOM, False, 1, False)
        print("BOM ok", bom is not None)
    except Exception as e:
        print("BOM ERR", type(e).__name__, e)

TECH = ("技术要求\n"
        "1. 装配前各零件清洗干净，去除毛刺、铁屑。\n"
        "2. 齿轮与齿圈啮合侧隙 0.05~0.10，齿面涂锂基润滑脂。\n"
        "3. 旋转套与上盖配合面涂密封胶，唇形密封圈唇口朝内。\n"
        "4. 装配后各轴转动灵活，无卡滞、无异响。\n"
        "5. 未注圆角 R1，未注倒角 C1。")
note_at(draft, 0.035, 0.392, TECH)

note_at(draft, 0.398, 0.205,
        "说明：XXJSQ-001 连接法兰轴、XXJSQ-005 挡板\n"
        "原始资料（STEP/DWG）缺失，本次未建模、未装配。")

get_com_member(draft, "EditRebuild3")
time.sleep(2.0)
draft.ViewZoomtofit2()
time.sleep(0.8)
save_document(draft, DRW)
D.export_sheet_to_pdf(draft, PDF, sw_app=sw)
time.sleep(0.8)
D.export_sheet_to_pdf(draft, PDF, sw_app=sw)

rep = {"file": DRW, "pdf": PDF, "views": list(views.keys()),
       "bom": bom is not None, "sheet": "A2", "scale": "1:2"}
print(json.dumps(rep, ensure_ascii=False, indent=2))
with open(os.path.join(OUTDIR, "_asm_drawing_report.json"), "w", encoding="utf-8") as f:
    json.dump(rep, f, ensure_ascii=False, indent=2)
