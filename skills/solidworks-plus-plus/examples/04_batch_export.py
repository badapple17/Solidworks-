"""
示例 4: 批量导出文件
演示如何批量将 SolidWorks 文件导出为 STEP 格式
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from sw_connect import connect_solidworks
from sw_export import batch_export
import glob

def main():
    sw, _ = connect_solidworks()

    # 获取所有零件文件
    base_dir = Path(__file__).parent / "_output"
    input_dir = str(base_dir)
    output_dir = str(base_dir / "step")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    print(f"从 {input_dir} 批量导出...")

    # 获取所有 .sldprt 文件
    part_files = glob.glob(f"{input_dir}\\*.sldprt")

    if not part_files:
        print("未找到零件文件!")
        return

    print(f"找到 {len(part_files)} 个文件")

    # 批量导出为 STEP
    results = batch_export(sw, part_files, output_dir, ".step")

    # 显示结果
    print("\n导出结果:")
    for result in results:
        status = "✓" if result["success"] else "✗"
        print(f"{status} {result['file']}")
        if result["success"]:
            print(f"   → {result['output']}")

if __name__ == "__main__":
    main()
