"""
示例 3: 创建装配体
演示如何添加组件并创建配合关系
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from sw_connect import connect_solidworks, new_document, mm
from sw_assembly import (
    add_component,
    add_mate_coincident,
    add_mate_concentric,
    get_components
)

def main():
    sw, _ = connect_solidworks()

    # 创建新装配体
    print("创建装配体...")
    asm = new_document(sw, "assembly")

    # 添加第一个零件(固定)
    print("添加零件...")
    # 先把两个零件文件放到 _output/（或改成你自己的路径）
    part1_path = str(Path(__file__).parent / "_output" / "base.sldprt")
    part2_path = str(Path(__file__).parent / "_output" / "shaft.sldprt")

    comp1 = add_component(asm, part1_path, 0, 0, 0)
    comp2 = add_component(asm, part2_path, mm(50), 0, 0)

    # 添加配合关系
    print("添加配合...")
    # 重合配合 - 将两个平面对齐
    add_mate_coincident(
        asm,
        "Front Plane@base-1", "PLANE",
        "Front Plane@shaft-1", "PLANE"
    )

    # 同心配合 - 将两个圆柱面对齐
    add_mate_concentric(
        asm,
        "Face1@base-1",
        "Face1@shaft-1"
    )

    # 列出所有组件
    print("\n装配体组件:")
    components = get_components(asm)
    for comp in components:
        print(f"  - {comp['name']}: {comp['path']}")

    print("\n装配体创建完成!")

if __name__ == "__main__":
    main()
