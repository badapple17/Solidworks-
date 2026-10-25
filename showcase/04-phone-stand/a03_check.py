# -*- coding: utf-8 -*-
"""装配体验收：干涉检查 + 预览/review。py -3.12 a03_check.py"""

import json

from PIL import Image

from stand_common import OUT
from sw_session import SolidWorksSession
from sw_connect import open_document
from sw_assembly import get_interference_detection
from sw_review import run_review

REVIEW = OUT.parent / "previews"
SHEET_ORDER = (
    ("a01_deployed_isometric", "a01_deployed_right"),
    ("a02_folded_isometric", "a02_folded_right"),
)
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
        # 关文档 + 退出本会话启动的实例：否则被引用的零件还占着文件锁，
        # 用户双击交付文件打不开，只能重启电脑。
        session.finish()

(REVIEW / "a03_check.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                       encoding="utf-8")

# run_review 在本机只写 1600×1000 BMP（每张 4.8 MB）；仓库只存压缩 PNG。
for bmp in REVIEW.glob("*.bmp"):
    with Image.open(bmp) as im:
        im.save(bmp.with_suffix(".png"), optimize=True)
    bmp.unlink()

sheet = Image.new("RGB", (1600, 1000), "white")
for row, pair in enumerate(SHEET_ORDER):
    for col, name in enumerate(pair):
        with Image.open(REVIEW / f"{name}.png") as im:
            sheet.paste(im.convert("RGB").resize((800, 500), Image.LANCZOS),
                        (col * 800, row * 500))
sheet.save(REVIEW / "preview_sheet.png", optimize=True)
print(f"预览: 8 张 PNG + preview_sheet.png -> {REVIEW}")
