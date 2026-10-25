# 已有三维模型 → 三视图工程图 实操手册

适用：用户给出 `.SLDPRT` / `.SLDASM`，要求生成三视图、工程图、PDF/图纸。
主脚本：`scripts/sw_three_view.py`（第一角 GB 布局，复用 `sw_drawing.py` 的全部能力）。
制图规范（该标什么、公差/粗糙度/技术要求怎么写）见 `drawing-standards.md`；
标准件尺寸见 `standard-parts.md`。

## 1. 开工前确认（一次问清，最多 4 项）

| 项目 | 默认 | 备选 |
|---|---|---|
| 图幅 | A3 横放 | A4/A2/A1；大件自动建议 |
| 投影 | 第一角（GB/T） | 第三角（出口图纸） |
| 视图 | 主视图 + 俯视图 + 左视图 | 增加右视图/剖视图/局部放大/轴测图 |
| 标注 | 插入模型尺寸 | 不标注 / 只标关键尺寸 / 后续手工补标 |
| 输出 | `.SLDDRW` + `.pdf` + 预览 PNG | 追加 DWG/DXF（需 AutoCAD 或另存） |

不要问用户“比例多少”——比例由脚本按图幅和包围盒自动选标准比例（10,5,2,1,0.5,0.2,0.1…）。

## 2. 出图前检查模型

1. 文件真实存在，能被 SolidWorks 打开（不是改后缀的 STEP）。
2. `GetBodies2(0, False)` 实体数符合预期；多实体要在标题栏/说明中写清。
3. 关键特征有名字，`ForceRebuild3(False)` 无错误。
4. 模型里有可导入的尺寸：草图尺寸或特征尺寸。若模型全是无尺寸草图：
   - 先在草图里补尺寸（`sw_part.auto_dimension_sketch()`），或
   - 出图后手工标关键尺寸。
5. 记录包围盒（mm）：用于选图幅、比例和验收。

## 3. 一键出图

```bash
py -3.12 "<skill>\scripts\sw_three_view.py" \
  --part "<workdir>\bracket.SLDPRT" \
  --out-dir "<workdir>\drawing" \
  --paper A3 \
  --projection first \
  --dims \
  --iso
```

参数：
- `--paper`：A4/A3/A2/A1/A0。
- `--projection first|third`：第一角/第三角。
- `--dims`：调用 `InsertModelAnnotations4/3` 插入“标记为工程图”的模型尺寸。
- `--iso`：在工作区右上角附加等轴测图。

输出：
| 文件 | 说明 |
|---|---|
| `<part>.SLDDRW` | 原生工程图 |
| `<part>.pdf` | 交付 PDF |
| `<part>_drawing_preview.png` | PDF 第一页渲染，供目视检查 |
| `<part>_drawing_report.json` | 视图数、尺寸数、布局、审查结果 |

脚本内部顺序：读包围盒 → 规划布局（第一角）→ 找 GB 图幅模板 → `SetupSheet6` →
创建三视图 → 插尺寸 → 保存 → 导出 PDF → 渲染 PNG → 结构审查。

> **SW2023 图幅码（实测）**：A4=6、A3=8、A2=9、A1=10、A0=11。
> `SetupSheet6(Name, PaperSize, TemplateIn, ...)` 的第 3 个参数 `TemplateIn`
> 必须与 `PaperSize` 同码；传 12（自定义）且宽高为 0 时图幅不会变化。
> 脚本已回读 `Sheet.GetProperties()` 校验实际宽高，报告字段
> `sheet_setup.sheet_size_verified` / `actual_size_m`。

## 4. 布局规则（脚本已实现，人工复核用）

第一角（GB/T）：
```text
┌──────────────────────────────┐
│                              │
│   主视图        左视图        │
│   (Front)       (Left)       │
│   俯视图                      │
│   (Top)                       │
│                    ┌───────┐ │
│                    │标题栏 │ │
└────────────────────┴───────┴─┘
```
- 主视图与俯视图：长对正。
- 主视图与左视图：高平齐。
- 俯视图与左视图：宽相等。
- 视图之间留 ≥18 mm 间距；不侵入标题栏（脚本按 180×55 mm 预留）。

第三角：
```text
俯视图在上，右视图在右；其余相同。
```

## 5. 标注策略（重要）

`--dims` 只能导入模型里**已存在**的尺寸，不会凭空生成。因此：

1. 建模时养成习惯：每个草图用 `auto_dimension_sketch()` 或显式标注关键尺寸。
2. 出图后检查 `dimension_count`：
   - 0–2 个：模型缺尺寸，回模型补标或手工标。
   - ≥6 个：通常可交付，仍需目视检查重叠。
3. 必须标出的尺寸（按优先级）：
   - 总体外形：长、宽、高。
   - 主要特征：孔径、孔深、凸台直径/高度、槽宽/长。
   - 定位：孔距、边距、中心高。
   - 标准件：螺纹规格、沉孔/沉头规格。
4. 不要重复标注同一尺寸；不要用长引线替代尺寸链。
5. 尺寸文字避免压线、压中心线、侵入标题栏；用 `auto_arrange_drawing_dimensions()` 初排后再目视微调。

## 5.5 工程图是零件的派生物（document discipline）

图纸不是“另画一份文件”，而是从零件几何派生出来的文档。下面几条比排版更重要：

1. **尺寸必须量自几何**：图纸上的每个数值都要来自模型尺寸回读或 `collect_geometry_measurements()`；
   不许为了让图“看起来完整”手输一个数字。手输尺寸 = 量的是白纸，不是零件。
2. **图纸会过期**：改了模型，旧 PDF/SLDDRW 不会自动变成新零件的图。必须重新出图，
   不许把上一轮 PDF 当新零件图纸交付。
3. **标给加工者看的东西**：总体尺寸、特征定位（孔距/边距/中心高）、孔与螺纹标注
   （`4×M6`、`φ9 通孔`、`沉孔 φ15 深 6`）、必要技术要求。不要把所有模型尺寸一股脑倒上去，
   重复尺寸和封闭尺寸链都会给加工添乱。
4. **公差只能来自用户/设计文件/标准**：模型里没有公差信息时，不许自己发明 `±0.1`。
   没有依据就写“未注公差按 GB/T 1804-m”并**问用户确认等级**；用户没确认就在交付说明里
   标为未决项。
5. **失败要大声**：视图跑出图框、PDF 渲染为空、模板缺失、尺寸数为 0——这些都是
   “图纸没做成”，必须明说并停止交付，不许写一份看起来像图纸的错误文档。
6. **报告与实物不一致时以 PDF/预览为准**：报告说 4 个视图、PDF 只有 3 个框，
   先查结构采集和布局，再决定信谁；不许只挑对自己有利的那个数字。

## 6. 标题栏与技术要求

GB 模板（`gb_a3.drwdot`）自带标题栏。**交付用图纸的标题栏字段一个都不能靠猜**，交付前逐项确认/填写：

| 字段 | 来源 | 缺失时 |
|---|---|---|
| 零件名称 | 用户/任务卡 | 问用户；不许拿文件名顶替后当成已确认 |
| 图号 | 用户/设计文件 | 问用户；可先用 `待定-001` 占位并在交付说明标未决 |
| 材料 | 用户/设计文件 | 问用户；**不许默认“45 钢”** |
| 比例 | 脚本按图幅自动选，回读填 | 标题栏文字必须等于视图 `ScaleRatio` |
| 数量 | 任务卡 | 单件写 1；批量必须问 |
| 设计/审核/日期 | 用户 | 留空并在交付说明列为未完成项 |
| 单位、投影符号 | 固定 mm、第一角 | 第三角必须改投影符号 |
| 版本/张数 | 用户或版本规则 | 多页图纸必须写 `第 X 张 / 共 Y 张` |

- 技术要求（如未注圆角 R2、未注公差按 GB/T 1804-m、去毛刺）。
- 表面粗糙度/热处理按需；等级来自用户/设计文件，不许自己定 Ra 值。

COM 可写模型自定义属性；标题栏字段若已链接属性，会自动更新。没有链接时，在 SolidWorks 中手工填写或在图纸格式里编辑。

## 7. 验收（每次必做）

1. `report["status"] == "pass"`，且 `view_count >= 3`。
2. `sheet_setup.sheet_size_verified == True`，且 `actual_size_m` 与所选图幅一致
   （A3 = `[0.42, 0.297]`）。`configured == True` 不代表图幅真的变了。
3. `dimension_count` 符合预期（见第 5 节）。
4. 预览 PNG 非空白（`preview.not_blank == True`）。
5. 打开 PDF/PNG 目视：
   - 三视图方向正确（第一角：俯视图在下、左视图在右）。
   - 长对正/高平齐/宽相等。
   - 轮廓完整，无缺失特征、无多余线。
   - 尺寸不重叠、不压线、不侵入标题栏。
6. 视图比例一致；标题栏比例与视图 `ScaleRatio` 一致。
7. `.SLDDRW` 能重新打开；PDF 页数与图纸数一致。
8. **PDF 机器检查通过**（见 §7.5）；`pdf_check.status` 为 `fail` 时不许写“出图完成”。

## 7.5 PDF 机器检查（`scripts/check_drawing_pdf.py`）

目视之前先跑机器初筛，把“量白纸”和“标注挤在一起”这类问题变成可检查的证据：

```bash
py -3.12 "<skill>\scripts\check_drawing_pdf.py" "<workdir>\drawing\bracket.pdf" \
  --report "<workdir>\drawing\bracket_drawing_report.json" \
  --out "<workdir>\drawing\bracket_pdf_check.json"
```

- `--report`：同一轮 `sw_three_view.py` 生成的 `_drawing_report.json`，用来交叉核对
  尺寸数、视图数、图幅是否验证。
- 返回码：`0` = pass/warn，`2` = fail，`3` = PDF 读不了。

| 检查项 | 含义 | 处理 |
|---|---|---|
| `DIM_NO_LEADER` | 尺寸文字附近没有尺寸线/引出线（悬空数字） | 回 SolidWorks 补尺寸线；不许当“已标注”交付 |
| `DIM_FLOATING` | 尺寸文字离所有视图 > 25 mm | 重新排布或删除多余尺寸 |
| `OUT_OF_FRAME` | 文字/视图越出图框 | 重设图幅、缩比例、重排 |
| `VIEW_OVERLAP` | 视图轮廓互相重叠 | 调整视图位置，检查第一角布局 |
| `DIM_COUNT_MISMATCH` | PDF 尺寸数与报告不一致 | 以 PDF 为准，查结构采集或重跑出图 |
| `SHEET_NOT_VERIFIED` | 报告里 `sheet_size_verified` 非 true | 按失败分支重设图幅 |

已知限制（必须知道）：只认矢量 PDF；视图按最粗线宽识别；**不检查尺寸链是否完整、
基准是否合理**——那部分仍按 `drawing-standards.md` 人工自检。机器通过不等于图纸合格，
只是把最容易漏的悬空/重叠/越界问题拦在交付前。

## 8. 失败分支

| 症状 | 原因 | 处理 |
|---|---|---|
| `DRAWING_TEMPLATE_MISSING` | 本机没有 GB 模板 | 用 `find_drawing_template` 的候选列表；或指定 `--paper A4`；仍无则手工新建图纸 |
| 视图创建返回 `None` | 模型路径/文档状态异常 | 先单独打开零件确认可读；用 `GetModelViewNames()` 读本机视图名（中文版是 `*前视`/`*上视`/`*左视`/`*等轴测`，英文名无效）；重试一次仍失败就逐个视图单独创建并记录失败项 |
| 视图数量 < 3 | 某个方向创建失败 | 读 `view_creation.failures`，逐个重试；不要交付缺视图的图纸 |
| `dimension_count == 0` | 模型无尺寸 | 回模型补草图尺寸，或手工标注 |
| PDF 导出失败 | 导出数据/权限 | 用 `model.SaveAs` 的 PDF 路径重试；或先保存 SLDDRW 再导出 |
| 预览空白 | PDF 渲染失败/视图在纸外 | 检查 `layout.views` 坐标与图幅；检查视图是否被移到负坐标 |
| 尺寸重叠 | 自动排列不理想 | 手工拖动，或用 `auto_arrange_drawing_dimensions(mode="stagger")` |
| `DIM_NO_LEADER`（尺寸文字无尺寸线） | 导入的是注释文字或尺寸线被隐藏 | 删除手输注释，改用模型尺寸；检查 `InsertModelAnnotations` 返回值后重跑出图 |
| `DIM_FLOATING` / `OUT_OF_FRAME` | 尺寸被排到视图外或图框外 | 缩小比例、重排视图；仍失败就减少自动尺寸，改标关键尺寸 |
| `VIEW_OVERLAP` | 视图间距不足或布局参数被覆盖 | 检查 `layout.views` 坐标；按第一角规则重排，间距 ≥18 mm |
| 图纸打开是空白 | 模板/图框问题 | 换模板；检查 `SetupSheet6` 返回值 |

## 9. 手工兜底流程（脚本不可用时）

```python
import sys
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import find_template
from sw_session import SolidWorksSession
from sw_drawing import plan_standard_view_layout, _apply_view_layout, insert_dimensions
from sw_review import collect_geometry_measurements

session = SolidWorksSession()
part = session.open(r"<workdir>\bracket.SLDPRT", read_only=True)
box = collect_geometry_measurements(part)["envelope_mm"]
layout = plan_standard_view_layout(
    [box["length"]/1000, box["width"]/1000, box["height"]/1000],
    paper_size="A3", projection="first")
drawing = session.new_drawing(template_path=r"<模板路径>")  # 用 sw_connect.find_template(sw, "drawing") 自动查找，勿硬编码
for item in layout["views"]:
    view = drawing.CreateDrawViewFromModelView3(r"<workdir>\bracket.SLDPRT", item["name"],
                                                item["center"][0], item["center"][1], 0)
    _apply_view_layout(view, item, *layout["scale_ratio"])
insert_dimensions(drawing)
session.save(drawing, r"<workdir>\drawing\bracket.SLDDRW")
```

## 10. 反例

- ❌ 不检查模型实体数就出图（多实体图纸会缺件/重叠）。
- ❌ 用第三角布局交付给国内加工厂（视图位置反了）。
- ❌ 只导 PDF 不保存 SLDDRW（无法二次编辑）。
- ❌ 看到 `view_count=3` 就宣布成功，不看预览。
- ❌ 尺寸为 0 还说“已自动标注”。
- ❌ 把 PDF 当原生图纸交付而不给 `.SLDDRW`（用户要求原生时）。
