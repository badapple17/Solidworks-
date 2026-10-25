# -*- coding: utf-8 -*-
"""诊断：列出紧凑装配每个组件在装配坐标系下的包围盒（mm）。只读，不保存。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths

from sw_connect import connect_solidworks, get_com_member, open_document

asm_path = case_paths.ASM / "XXJSQ_减速器.SLDASM"
sw, _ = connect_solidworks(visible=True)
try:
    asm = open_document(sw, str(asm_path), raise_on_error=True)
    for comp in asm.GetComponents(False) or []:
        name = str(get_com_member(comp, "Name2"))
        box = comp.GetBox(False, False)
        values = [round(float(v) * 1000.0, 2) for v in box]
        print(f"{name:32s} x[{values[0]:8.2f},{values[3]:8.2f}] "
              f"y[{values[1]:8.2f},{values[4]:8.2f}] z[{values[2]:8.2f},{values[5]:8.2f}]")
finally:
    sw.CloseAllDocuments(False)
