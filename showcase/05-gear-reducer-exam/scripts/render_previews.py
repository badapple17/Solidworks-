# -*- coding: utf-8 -*-
"""05 实例预览：三套装配各出等轴测/前视/俯视/右视 PNG，并拼 2x2 联系表。

只读模型，不保存。BMP 是 SolidWorks SaveBMP 的原生格式，仓库只存压缩 PNG。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths

from PIL import Image

from sw_connect import connect_solidworks, open_document
from sw_review import save_preview

PREVIEWS = case_paths.CASE / "previews"
VIEWS = ("isometric", "front", "top", "right")
ASSEMBLIES = {
    "compact": case_paths.ASM / "XXJSQ_减速器.SLDASM",
    "exploded": case_paths.ASM / "XXJSQ_减速器_爆炸图.SLDASM",
    "transparent": case_paths.ASM / "XXJSQ_减速器_透明涂色.SLDASM",
}


def contact_sheet(paths, out_path):
    images = [Image.open(path) for path in paths]
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    sheet = Image.new("RGB", (width * 2, height * 2), "white")
    for index, image in enumerate(images[:4]):
        sheet.paste(image.convert("RGB"), ((index % 2) * width, (index // 2) * height))
    sheet = sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS)
    sheet.save(out_path, optimize=True)


def main():
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    sw, _ = connect_solidworks(visible=True)
    try:
        for key, path in ASSEMBLIES.items():
            asm = open_document(sw, str(path), raise_on_error=True)
            bmps = []
            for view in VIEWS:
                bmp = save_preview(asm, PREVIEWS / f"{key}_{view}.bmp", view)
                bmps.append(bmp)
                with Image.open(bmp) as image:
                    image.save(PREVIEWS / f"{key}_{view}.png", optimize=True)
                os.remove(bmp)
            contact_sheet([PREVIEWS / f"{key}_{view}.png" for view in VIEWS],
                          PREVIEWS / f"{key}_sheet.png")
            print(f"{key}: 4 视图 + 联系表 -> {PREVIEWS}")
            sw.CloseDoc(path.name)
    finally:
        sw.CloseAllDocuments(False)


if __name__ == "__main__":
    main()
