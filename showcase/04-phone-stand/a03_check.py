# -*- coding: utf-8 -*-
"""装配体验收：干涉检查 + 预览/review。py -3.12 a03_check.py"""

import json

from stand_common import OUT
from sw_session import SolidWorksSession
from sw_connect import open_document
from sw_assembly import get_interference_detection
from sw_review import run_review

REVIEW = OUT.parent / "previews"
EXPECTED = [str(OUT / f) for f in (
    "01_base.SLDPRT", "02_turntable.SLDPRT", "03_arm.SLDPRT", "04_pin_bottom.SLDPRT",
    "05_pin_top.SLDPRT", "06_plate.SLDPRT", "07_hook.SLDPRT", "08_phone_reno14.SLDPRT",
    "a01_deployed.SLDASM", "a02_folded.SLDASM")]

session = SolidWorksSession(visible=True, wait_seconds=20)
summary = {}
for name in ("a01_deployed", "a02_folded"):
    asm = open_document(session.sw, str(OUT / f"{name}.SLDASM"), silent=True)
    try:
        inter = get_interference_detection(asm)
        print(f"[{name}] 干涉 {inter['status']} {inter['interference_count']} 处")
        for it in inter["items"]:
            print("   ", it)
        report, path = run_review(asm, REVIEW, basename=name, expected_outputs=EXPECTED)
        ev = report["evaluation"]
        print(f"[{name}] review {ev['status']} / {ev['score']}  -> {path}")
        for issue in ev["issues"]:
            print(f"    - [{issue['severity']}] {issue['code']}: {issue['message']}")
        summary[name] = {"interference": inter, "review": ev["status"], "score": ev["score"]}
    finally:
        session.close(asm)
        session.sw.CloseAllDocuments(True)   # 引用零件也要卸载，否则下次存零件报错码 1

(REVIEW / "a03_check.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
