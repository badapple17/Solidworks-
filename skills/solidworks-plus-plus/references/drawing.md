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

## 尺寸标注

### 自动标注（模型项目）

```python
drawing.InsertModelAnnotations3(
    InsertType,    # int: 0=整个模型
    AnnotationType, # int: 32768=标记为工程图的模型尺寸
    DuplicateDims, # bool
    AutoArrange,   # bool
    UseDoc,        # bool
    UseView        # bool
)
```

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
# 添加注释
note = drawing.InsertNote(text)

# 添加表面粗糙度符号
drawing.InsertSurfaceFinishSymbol3(...)

# 添加焊接符号
drawing.InsertWeldSymbol(...)

# 添加基准符号
drawing.InsertDatumTag2(...)
```

## BOM 表

```python
bom = drawing.InsertBomTable4(
    TemplateName,  # str: BOM 模板路径(.sldbomtbt)
    X, Y,          # float: 位置
    BomType,       # int: 1=顶层, 2=仅零件, 3=缩进
    Configuration, # str: 配置名
    TableAnchor,   # str: 锚点名
    Hidden         # bool: 是否包含隐藏组件
)
```

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

```python
sw = model.GetSldWorksObject()
pdf_data = sw.GetExportFileData(1)  # swExportPDFData
sheet_names = drawing.GetSheetNames()
pdf_data.SetSheets(0, sheet_names)  # 0=指定图纸

errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
model.Extension.SaveAs("output.pdf", 0, 1, pdf_data, errors, warnings)
```
