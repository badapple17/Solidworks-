"""
示例 6: 使用友好 Session API 创建并导出零件

运行前提:
    SolidWorks 已安装，可手动启动也可由脚本启动。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from sw_connect import mm
from sw_part import extrude_boss, sketch, sketch_circle
from sw_session import SolidWorksSession


def main():
    """创建一个圆柱体并导出 STEP。"""
    session = SolidWorksSession()
    model = session.new_part()

    with sketch(model, "Front Plane") as sketch_name:
        sketch_circle(model, 0, 0, mm(25))

    extrude_boss(model, sketch_name, mm(50))

    out_dir = Path(__file__).parent / "_output"
    out_dir.mkdir(parents=True, exist_ok=True)
    session.save(model, str(out_dir / "friendly_cylinder.sldprt"))
    session.export(model, str(out_dir / "friendly_cylinder.step"))
    print(f"完成: {out_dir / 'friendly_cylinder.sldprt'} / .step")


if __name__ == "__main__":
    main()

