# 结果自审查参考

## 必做检查

生成、修改或导出 SolidWorks 文件后，至少检查：

1. COM 调用返回值不是 `None`，关键特征对象创建成功。
2. `save_document()`、`session.save()`、`session.export()` 返回成功。
3. 输出 `.sldprt` / `.sldasm` / `.slddrw` / `.step` / `.stl` 等文件真实存在且大小合理。
4. 模型已重建：`model.ForceRebuild3(False)`。
5. 模型已缩放到适合窗口：`model.ViewZoomtofit2()`。
6. 至少导出一张等轴测 BMP，复杂模型导出前视、俯视、右视。

## 结构化自审查报告

```python
import sys
sys.path.insert(0, r"SKILL_DIR/scripts")

from sw_review import run_review

model.ForceRebuild3(False)
report, report_path = run_review(
    model,
    r"<workdir>\solidworks_review",
    basename="model",
    views=("isometric", "front", "top", "right"),
    expected_outputs=[r"<workdir>\model.sldprt", r"<workdir>\model.step"],
)
print(report_path)
print(report["checks"])
```

`run_review()` 会输出：

- 多视角 BMP 预览图。
- `*_review_report.json` 结构化报告。
- `*_review_summary.md` 可读摘要，适合贴到交付说明、Issue 或 PR。
- `evaluation.status`：`pass` / `warn` / `fail`。
- `evaluation.score`：规则评分，满分 100。
- `evaluation.issues`：机器可读的问题列表。
- `evaluation.recommendations`：修复建议。
- `checks.previews_created`：预览图是否生成。
- `checks.previews_not_blank`：预览图是否疑似非空白。
- `checks.expected_outputs_exist`：期望输出文件是否真实存在且大小大于 0。
- `checks.feature_summary_available`：是否能读取特征树摘要。

注意：结构化报告只能抓明显失败，不能替代人工或视觉模型对几何意图的判断。

制造级任务还必须单独输出机器可读规格证据，例如：

```json
{
  "cad_spec": {
    "envelope_mm": {"length": 60, "width": 40, "thickness": 12},
    "holes": [
      {"diameter_mm": 10, "count": 1, "positions_xy_mm": [[0, 0]]},
      {"diameter_mm": 4, "count": 4, "positions_xy_mm": [[-24, -14], [24, -14], [-24, 14], [24, 14]]}
    ]
  },
  "measurement_source": "SolidWorks API/B-Rep/参数回读",
  "units": "mm"
}
```

任务中明确给出外形或孔径，但交付物没有独立 JSON 证据时，Reviewer Gate 必须失败；代理的文字总结和“执行器自报通过”不能替代证据。孔数量、孔位、边距、中心距、圆角、壁厚和装配自由度也应按任务逐项记录。

复杂孔槽使用 `collect_geometry_measurements()` 时还会输出：

- `hole_groups`：按空间轴线归并的孔段。
- `compound_holes`：同轴但直径不同的沉孔/复合孔候选。
- `slot_arc_candidates`：内部圆柱面具有多条边界边的槽端圆弧，不计入圆孔数量。
- `validate_hole_positions()`：按孔轴线距离和孔径公差逐孔验收。

```python
from sw_review import collect_geometry_measurements, validate_hole_positions

measurements = collect_geometry_measurements(model)
position_checks = validate_hole_positions(
    measurements,
    [{"id": "H1", "diameter_mm": 8, "position_mm": [20, 20, 0]}],
    position_tolerance_mm=0.1,
    diameter_tolerance_mm=0.05,
)
assert position_checks["status"] == "pass"
```

注意：圆柱面 B-Rep 可以证明孔径、轴线和圆柱段长度，但不能单独可靠区分盲孔/通孔。盲孔深度、沉头角度和孔型必须与 `sw_hole_features.py` 返回的创建参数证据或特征定义回读交叉验证。

## 命令行一键审查

```bash
python scripts/sw_review.py ^
  --file <workdir>\model.sldprt ^
  --output-dir <workdir>\solidworks_review ^
  --basename model ^
  --expected <workdir>\model.sldprt ^
  --expected <workdir>\model.step
```

返回码：

- `0`：`pass` 或 `warn`，报告已生成。
- `1`：传入 `--fail-on-warn` 且状态为 `warn`。
- `2`：`fail`，存在必须修复的问题。

## 目视自查清单

- 主体是否出现在画面中，是否为空白或只剩草图。
- 关键部件是否齐全，例如车轮、孔、轴、外壳、支架、BOM 表等。
- 特征树成功的切除/孔/槽是否在预期表面真实可见；`feature is not None` 不等于几何意图正确。
- 比例是否明显错误，例如毫米误当米导致模型巨大。
- 方向是否正确，例如轮子是否在侧面而不是车顶。
- 部件是否明显重叠、悬空、穿模或缺少约束。装配体的穿模不要靠看图判断：小于 1 mm 的
  切入在预览里看不出来，用 `get_interference_detection()` 的组件对 + 体积作证据。
- **标准视图按 Y 轴向上**：模型若按 Z 向上建（底座在 XY 平面），等轴测/前视里底座会显示成竖立的圆盘，
  这是视图约定，不是几何错。判断姿态以位姿/包围盒数值为准，或在交付说明里注明“模型 Z 向上”。
- 文件名、输出目录、导出格式是否符合用户要求。

## 证据纪律（Evidence discipline）

1. **检查已保存并重新打开的文件**，不是内存里的对象；SolidWorks 保存失败但文件已写入、
   或内存对象与磁盘不一致的情况都出现过。文件大小 > 0 只是最低条件。
2. **“计算失败”不是“通过”**：体积断言没算、PDF 没渲染、尺寸表没回读——这些检查记
   `not_run`，不许因为“看起来没问题”写成 `pass`。报告里的每个 `pass` 都要能指向
   证据路径或回读数值。
3. **报告测的是什么、单位、阈值**：写“尺寸正确”不算证据；写“包围盒 120.000×80.000×12.000 mm，
   与图纸差 0.000 mm，阈值 0.1 mm”才算。
4. **包围盒 ≠ 孔径**：包围盒只能证明外形。孔的数量、孔径、孔位要用
   `collect_geometry_measurements()` 的 `hole_groups` / `compound_holes` 单独核对；
   “包围盒对上了”不能推出“孔也对”。
5. **失败可以存在，隐瞒不行**：检查 fail 时在交付说明如实写出（`disclosed: true`）
   并说明影响范围；把 fail 藏起来比 fail 本身严重。

## 快照纪律（Snapshot policy）

- 每次**可见变更**至少留一张审查快照（BMP/PNG），快照选择要能暴露本次改动的特征：
  改孔就看孔所在的面，改筋就看筋与主体的结合处。
- 快照是给人看的证据，不是通过条件：不许用“我截了 6 张图”代替数值检查，
  也不许为了凑数循环截图。
- 视角要覆盖：等轴测（整体）+ 改动方向的正视图/剖视；装配体加干涉检查数值，
  小于 1 mm 的穿模在图上通常看不见。
- 快照和报告一起归档，交付说明引用相对路径，不用“桌面上的那张图”这种说法。

## 修复循环（Repair loop）

检查失败时按固定顺序修，不许“全部推倒重来”：

1. **定位**：用失败的那条命令/检查缩小范围（哪一步返回 `None`、哪个尺寸对不上、
   哪个视图缺），不要凭感觉重跑整个流程。
2. **改源头**：修改建模/出图脚本的参数或调用，不在交付物上手工打补丁；
   手工补的尺寸/特征下一轮会丢。
3. **只重跑受影响的部分**，然后过一遍全量门禁（几何、体积、实体数、孔、预览、图纸）。
4. **保留用户指定的特征**：修 A 不许把 B 删了；不得已删改（如圆角失败）必须在
   交付说明写清。
5. **修复前后对比不变量**：包围盒、体积、实体数、孔数、视图数——数字没变才说明
   只修了目标问题。
6. **修不好就披露**：连续两次修复仍失败，停止叠加特征，向用户说明现状、已尝试的
   修复和剩余偏差，不许静默降级交付。

## 发现问题时

1. 不要只报告“文件已保存”。
2. 先定位是草图、选择、拉伸方向、单位、基准面还是导出失败。
3. 修改脚本后重新生成并再次导出预览图。
4. 最终回复中说明已检查的预览图和仍有限制的地方。
