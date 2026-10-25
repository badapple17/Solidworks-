# 工程图 API 参考

## 创建视图

### 标准三视图

SW2023 类型库里第一角方法叫 **`Create1stAngleViews2`**（不是 `CreateFirstAngleViews2`），
另有 `Create3rdAngleViews2`。两者都会自动摆位，无法精确控制 GB 布局和比例，
所以技能主路径改为逐视图创建。视图名必须从模型读取：

```python
# 先打开零件，读本机视图名（中文版是 *前视/*上视/*左视/*右视/*等轴测）
names = list(part.GetModelViewNames())
front_name = next(n for n in names if "前视" in n or "Front" in n)
view = drawing.CreateDrawViewFromModelView3(partPath, front_name, x, y, 0)
```

不要硬编码 `*Front`：中文版 SW2023 只认 `*前视`。技能脚本用
`sw_three_view.resolve_model_view_names()` 做中英文解析。
第一角/第三角的区别靠**视图摆放位置**实现（俯视图在下/在上、左视图在右/右视图在右），
没有“一键第一角”API。

### 自定义视图

```python
view = drawing.CreateDrawViewFromModelView3(
    ModelName,     # str: 零件/装配体路径
    ViewName,      # str: 视图方向（见下表）
    X, Y, Z        # float: 放置位置（米）
)
```

视图方向名称（英文为 API 通用名；中文版 SW2023 实际返回本地化名）：
| 英文 | 中文 SW2023 |
|---|---|
| `*Front` | `*前视` |
| `*Back` | `*后视` |
| `*Top` | `*上视` |
| `*Bottom` | `*下视` |
| `*Left` | `*左视` |
| `*Right` | `*右视` |
| `*Isometric` | `*等轴测` |
| `*Trimetric` | `*三等轴测` |
| `*Dimetric` | `*二等轴测` |

以 `GetModelViewNames()` 的返回值为准；传英文名在中文版会返回 `None`。

### 设置视图比例

```python
import pythoncom
from win32com.client import VARIANT

# IView.ScaleRatio 是 COM 数组；pywin32 下必须用 VARIANT 包一层
view.ScaleRatio = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [1.0, 2.0])  # 1:2
view.ScaleRatio = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [2.0, 1.0])  # 2:1
```

`IView.Position` 同理，也必须传 VARIANT(VT_ARRAY|VT_R8)。

### 图纸比例与标题栏（SW2023 实测，2026-10-25）

```python
sheet = drawing.GetCurrentSheet()
ok = drawing.SetupSheet6(
    sheet.GetName(), paper_code,
    12,              # TemplateIn：传入 .slddrt 时必须是 swDwgTemplateCustom=12
    2.0, 1.0,        # Scale1, Scale2
    True,            # FirstAngle
    r"...\a3 - gb.slddrt",
    0.0, 0.0, "", False, 0.0, 0.0, 0.0, 0.0, 0, 0)
props = list(sheet.GetProperties2())
# [paper_size, template_in, scale1, scale2, first_angle, width, height, same_custom_prop]
actual_size = props[5:7]     # 米；A3 = [0.42, 0.297]
actual_scale = props[2:4]    # 2:1 = [2.0, 1.0]
```

两条硬规则：

1. **`TemplateIn` 必须传 12**，不能传图幅码（A3=8）。传 8 时 `SetupSheet6`
   仍返回 `True`，图幅也正确，但导出的 PDF 会**丢掉图框线、标题栏和尺寸线**
   （实测空白图导出 0 条矢量路径）。这是“标题栏消失”的真正原因。
2. **创建视图会把图面比例重置为 1:1**，标题栏“比例”格跟随图面比例。
   因此必须在**所有视图（含轴测图）创建完成后**再调用一次 `SetupSheet6`，
   并把这次 `GetProperties2` 回读作为 `sheet_setup` 的最终证据。

## 尺寸标注

> 排哪里、先标哪个、人为什么这样标：见 `dimension-layout.md`。本节只讲 API 与已实测的显示行为。

### 自动标注（模型项目）

```python
drawing.InsertModelAnnotations3(
    Option,              # int: 0=整个模型（插入范围）
    Types,               # int: 32768=标记为工程图的模型尺寸
    AllViews,            # bool: 是否插入到所有视图
    DuplicateDims,       # bool: 是否允许重复尺寸
    HiddenFeatureDims,   # bool: 是否含隐藏特征尺寸
    UsePlacementInSketch # bool: 是否沿用草图里的放置位置
)
```

> 签名以本机 `sldworks.tlb` 为准（SW2023）。旧文档里写成
> `(InsertType, AnnotationType, DuplicateDims, AutoArrange, UseDoc, UseView)`
> 是错的：第 3 个参数是 `AllViews`，第 4 个才是 `DuplicateDims`。
> 2026-10-25 用齿轮图实测：`AllViews=True, DuplicateDims=False` 仍会在
> 前/左视图各插一份同一模型尺寸；`DuplicateDims=False` 只约束同一视图内。
> 跨视图重复必须按 `IDimension.FullName` 去重后删除（见下节）。
>
> SW2024/2026 的动态 pywin32 代理通常把 `InsertModelAnnotations3` 暴露在工程图
> `IModelDoc2` 上，而不是 `IModelDocExtension`。技能脚本会先尝试文档对象，
> 再兼容旧的 Extension 代理。`32` 是几何公差，`32768` 才是标记为工程图
> 的模型尺寸；返回 `False` 或
> 复核不到尺寸实体时不得把尺寸证据标记为已验证。
>
> 该 API 只导入模型中已经存在的 `DisplayDimension`。对没有草图尺寸的矩形
> 或只有拉伸参数的零件，先在草图编辑态调用 `sw_part.auto_dimension_sketch()`
> 或由明确的参数化建模步骤创建模型尺寸；不得期待工程图 API 凭空生成尺寸。
>
> 能力清单将这一路径单独记录为 `drawing_dimension_insertion=verified`（SW2024/2026）。
> SW2026 SP01.1 已连续三次回读 3 个真实视图和 6 个真实尺寸实体。
> 完整工程图交付仍属于 `drawings_and_bom=pilot`，因为尺寸布局、孔槽定位链、
> 图框、标题栏和 BOM 需要人工目视复核。

### 跨视图去重与尺寸摆放（SW2023 实测）

**去重**：同一个模型尺寸在前视、左视各插一份，`FullName` 相同，删一份不影响模型。

```python
for view in sheet.GetViews():
    for dd in view.GetDisplayDimensions():
        dim = dd.GetDimension()
        key = dim.FullName          # 例：D1@草图2@part.Part
        if key in seen:
            dd.GetAnnotation().Select2(False, 0)
            drawing.EditDelete()    # 删的是工程图显示尺寸，不是模型尺寸
        else:
            seen.add(key)
```

实测 10 个显示尺寸 → 4 个唯一尺寸；删除后模型和其余视图不受影响。
`DuplicateDims=False` 不能替代这一步。

**摆放**：用建模时规划的视图框（`layout["views"][i]["box"]`）定位，不要用
`IView.GetOutline()`——它把视图边框算进去，左边缘比真实几何多约 6 mm，
按它偏移 24 mm 会把尺寸推到 PDF 检查器 25 mm 的“悬浮”阈值之外。

```python
annotation.SetPosition(x, y, 0.0)                  # 米
pos = annotation.GetPosition()                     # 必须回读校验
```

同一视图有多个尺寸时：视图中心在纸面左半 → 放左侧，否则放右侧；
两列间距 12 mm、第一列距视图 10 mm（第二列 22 mm，仍在 25 mm 悬浮阈值内）。
**并排两列要错开半个行距（约 4.5 mm）**：否则水平引出线会沿同一条中心线重叠
（实测 φ20/φ36 共线）；列距只有 8 mm 时旋转数字仍会跨列压字
（001 连杆实测 30/25、10/15，PDF 检查报 `TEXT_OVERLAP`）。

> `IDisplayDimension.GetText(0)` 对导入的模型尺寸返回空串，PDF 里却能正常显示数值；
> 不要用它判断“尺寸没有文字”，也不要拿它当尺寸值证据。

### SW2026 尺寸文字边界证据

本机 `SolidWorks.Interop.sldworks.dll` 反射确认：

- `IAnnotation.GetPosition()` 返回注解锚点。
- `IAnnotation.GetTextFormat(index)` / `GetTextFormatCount()` 返回文字格式。
- `ITextFormat.CharHeight`、`WidthFactor`、`CharSpacingFactor` 可读取字体尺度。
- `IDisplayDimension.GetText(swDimensionTextParts_e)` 可读取用户文字片段。
- `IAnnotation` 没有尺寸文字原生 bounding-box API；不要调用或宣称存在 `GetBox()`。

`scripts/sw_drawing.py::estimate_dimension_text_box()` 因此只生成保守估算边界：

1. 以 `IAnnotation.GetPosition()` 为中心。
2. 按字符数、`CharHeight`、`WidthFactor` 和 `CharSpacingFactor` 估算未旋转文字宽高。
3. 由于 API 未给出尺寸文字角度，使用该矩形对角线构造任意旋转均可覆盖的方形包络。
4. padding 取 `max(1 mm, 0.4 * CharHeight)`；字段缺失时使用保守默认值并降低置信度。
5. `GetText(0)` 在 SW2026 可能不返回格式化后的主尺寸数值；缺失时按 8 个等宽字符保守占位。

报告必须保留以下字段，禁止把估算值冒充原生证据：

```json
{
  "box_source": "estimated",
  "box_confidence": "low | medium | unavailable",
  "box_evidence": {
    "native_bounding_box_available": false,
    "method": "annotation_position_text_format_arbitrary_rotation_envelope",
    "padding_m": 0.001,
    "orientation_assumption": "unknown_angle_conservative_square_envelope"
  }
}
```

即使全部估算边界未发现碰撞，`review_drawing_layout()` 仍返回
`review_required / DRAWING_LAYOUT_ESTIMATED_EVIDENCE_REQUIRES_VISUAL_REVIEW`。
估算边界发生相交时返回 `DRAWING_LAYOUT_ESTIMATED_COLLISION_RISK`，finding 必须为
`evidence_source=estimated`、`confirmed_collision=false`；只有原生边界证据才可使用
`DRAWING_LAYOUT_COLLISION_DETECTED` 表示确认碰撞。
非空 BMP/PDF 只能证明预览产物可用，不能自动证明尺寸没有重叠；最终必须目视复核。

更强的非 COM 方案是先用 SolidWorks 官方导出 PDF，再调用
`sw_review.inspect_pdf_text_layout()` 读取 PDF 中真实矢量文字 span 的边界。该方法能
发现可提取文字之间的实际重叠，比字符宽度估算更可靠，也不需要 OCR；但它仍不能
证明文字与尺寸线、几何线或被轮廓化字体之间无碰撞。标题栏中“第 张 + 页码”等
设计性叠放也可能产生真实边界相交，因此结果只标记重叠风险，不直接判定视觉缺陷。
PyMuPDF 不可用时该检查返回 `DRAWING_PDF_TEXT_PARSER_MISSING`，退回 COM 锚点/字体估算。

因此工程图边界证据强度依次为：PDF 矢量文字边界 > COM 锚点/字体保守估算 > OCR，
最终交付仍保留一次 PDF/BMP 目视复核。

### 手动添加尺寸

```python
# 先选择两个实体
drawing.Extension.SelectByID2("Edge1@View1", "EDGE", 0, 0, 0, False, 0, None, 0)
drawing.Extension.SelectByID2("Edge2@View1", "EDGE", 0, 0, 0, True, 0, None, 0)
# 添加尺寸
drawing.AddDimension2(x, y, 0)  # 尺寸标注放置位置
```

## 注释与标注

```python
# 添加注释：InsertNote 只有 text 一个参数，坐标无效
note = drawing.InsertNote(text)
note.GetAnnotation.SetPosition(x, y, 0)          # 单位：米；这一步才决定位置
note.GetTextFormat.CharHeight = 0.0035           # 单位：米（3.5 mm）

# 添加表面粗糙度符号
drawing.InsertSurfaceFinishSymbol3(...)

# 添加焊接符号
drawing.InsertWeldSymbol(...)

# 添加基准符号
drawing.InsertDatumTag2(...)
```

SW2023 SP0.1 实测：

- `InsertNote("...")` 的返回对象默认落在**图纸原点附近**，不是鼠标位置；
  不调用 `SetPosition` 的注释会叠在标题栏上。封装：`sw_drawing.add_note()`。
- 本机 `GetAnnotation` / `GetTextFormat` 是**属性式成员**（不加括号），
  写成方法调用会报 `'str' object is not callable`；用 `get_com_member()` 自动兼容两种形态。
- 多行注释用 `\n` 分隔，`CharHeight` 是**米**；标题栏技术要求常用 0.0035（3.5 mm）。

## BOM 表

`InsertBomTable4` 是 **IView 上的 10 参数方法**（不是 IDrawingDoc 的 7 参数版本，
后者在 SW2023 上参数对不上、会报“无效的参数数目”）。模板路径在第 7 位：

```python
bom = view.InsertBomTable4(
    UseAnchorPoint,   # bool
    X, Y,             # float: 米
    AnchorType,       # int: swBOMConfigurationAnchorType_e 1=左上 2=右上 3=左下 4=右下
    BomType,          # int: swBomType_e 1=PartsOnly 2=TopLevelOnly 3=Indented
    Configuration,    # str: 配置名，空串=当前配置
    TableTemplate,    # str: BOM 模板路径(.sldbomtbt)；空串=默认模板
    Hidden,           # bool: 是否隐藏表格（true=隐藏）
    IndentedNumbering,# int: swNumberingType_e 0=None 1=Detailed 2=Flat
    DetailedCutList,  # bool: 仅 BomType=3 时有效
)
```

参数顺序与枚举值取自本机 `SolidWorks.Interop.sldworks` 帮助页
（`IView~InsertBomTable4`）与 `SwConst`：**`BomType` 不是 0/1/2/3 顺序递增**
（`PartsOnly=1`、`TopLevelOnly=2`、`Indented=3`），凭直觉写会拿到错误的表类型。
`InsertBomTable4` 只在 `IView` 上，`IDrawingDoc` 上没有这个方法。

封装：`sw_drawing.insert_bom_table(view, template_path, x, y, ...)`。

实测（SW2023 SP0.1，本机无自备 `.sldbomtbt` 模板）：

- `TableTemplate=""` 会用默认模板，表能插进去；行数据（序号、数量、材料、单重、总重）
  正确。
- **属性链接列可能不刷新**：001 减速器装配图实测，零件已写入「图样代号 / 图样名称」
  （含配置级，回读确认存在），GB 明细栏的「代号 / 名称」两列仍显示模板字面量
  「图样代号」「图样名称」。试过配置级/文档级属性、`CustomPropertyView` 指定、
  重存装配体后重建，均未解决。交付时二选一：
  1. 改用不含属性链接的列，自己填文字；
  2. 在交付说明里**逐列**写明哪些列是占位符（不要写“明细栏已完成”）。
- **球标（balloon）本技能未封装**。没有球标的 BOM 仍可交付，但必须在交付说明里
  写明“BOM 与视图未做球标关联”，不要写成已关联。

## 图纸操作

```python
# 获取当前图纸
sheet = drawing.GetCurrentSheet()

# 获取所有图纸名称
names = drawing.GetSheetNames()

# 激活指定图纸
drawing.ActivateSheet(sheetName)

# 添加新图纸
drawing.NewSheet4(
    Name,        # str: 图纸名称
    PaperSize,   # int: SW2023: A4=6, A3=8, A2=9, A1=10, A0=11, 自定义=12
    TemplateIn,  # int: 必须与 PaperSize 同码；传 12 且宽高为 0 时图幅不变
    Scale1,      # float: 比例分子
    Scale2,      # float: 比例分母
    FirstAngle,  # bool: 第一角投影法
    Template,    # str: 图纸格式路径
    W, H,        # float: 宽高
    PropertySheet, # str
    Zone_LeftMargin, Zone_RightMargin, Zone_TopMargin, Zone_BottomMargin,
    Zone_Col, Zone_Row  # int: 分区
)

# 设置图纸格式
sheet.SetTemplateName(formatPath)  # .slddrt 文件路径
```

## 导出 PDF

导出前必须先让视图“落定”，否则 PDF 会**随机缺视图**（SW2023 SP0.1 实测：
新插入的视图不落定直接导出，PDF 里的视图数会少于报告里的视图数）。固定顺序：

```python
from sw_drawing import export_sheet_to_pdf, settle_drawing_views

settle_drawing_views(drawing, pause=2.0, zoom=True)
# 内部顺序：EditRebuild3（本机是属性式成员）→ sleep → ViewZoomtofit2 → sleep
export_sheet_to_pdf(drawing, path)
settle_drawing_views(drawing, pause=1.0)   # 导出后再落定一次
export_sheet_to_pdf(drawing, path)         # 同名覆盖再导一次；第二次才稳定
assert os.path.getsize(path) > 0
```

规则：

- **重建 / 睡眠 / 缩放 / 保存** 四步缺一不可；跳过 sleep 直接 `SaveAs` 时
  新插入的视图常常不渲染。
- 导出后**再跑一遍同样的序列并覆盖导出**，是消除“缺视图”最省事的办法。
- PDF 落盘与否看文件大小，不看 `SaveAs` 返回值（可能返回 `False` 但文件已写入）。
- 导出完成后用 `sw_review.inspect_pdf_text_layout()` 读数：视图数与尺寸锚点
  对不上就重导一次，仍缺则逐视图检查 `IView` 是否为 `None`。

```python
sw = model.GetSldWorksObject()
pdf_data = sw.GetExportFileData(1)  # swExportPDFData
sheet_names = drawing.GetSheetNames()
pdf_data.SetSheets(0, sheet_names)  # 0=指定图纸

errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
model.Extension.SaveAs("output.pdf", 0, 1, pdf_data, errors, warnings)
```
