# 常用操作代码速查（可直接复制）

所有长度单位：毫米输入，`mm()` 转米。所有角度：`deg()` 转弧度。
运行解释器：`py -3.12`（默认 `python` 是 3.9，没有依赖）。

```python
import sys
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import mm, deg
```

## 1. 连接 / 新建 / 保存 / 导出

```python
from sw_session import SolidWorksSession

session = SolidWorksSession()          # 默认可见
part = session.new_part()              # 新建零件
session.save(part, r"<workdir>\part.SLDPRT")
session.export(part, r"<workdir>\part.step")
session.export(part, r"<workdir>\part.stl")
```

## 2. 草图（自动进入/退出）

```python
from sw_part import (sketch, sketch_rectangle, sketch_corner_rectangle,
                     sketch_circle, sketch_slot, sketch_line, sketch_arc)

with sketch(part, "Front Plane") as sk:
    sketch_rectangle(part, 0, 0, mm(100), mm(60))     # 中心矩形
    # sketch_corner_rectangle(part, mm(-50), mm(-30), mm(50), mm(30))
    # sketch_circle(part, 0, 0, mm(15))
    # sketch_slot(part, mm(-30), 0, mm(30), 0, mm(4))   # 最后一个是半径：槽宽 8

# 直线 + 圆弧闭合轮廓（例：1/4 圆盘截面）
with sketch(part, "Front Plane", exact=True) as sk:
    sketch_arc(part, 0, 0, mm(10), 0, 0, mm(10), direction=1)  # 圆心(0,0)，起(10,0)，终(0,10)
    sketch_line(part, 0, mm(10), 0, 0)
    sketch_line(part, 0, 0, mm(10), 0)                        # 终点必须与弧起点重合
```

**圆弧方向（SW2023 实测，2026-10-25）**：`sketch_arc` 的 `direction=1` 是逆时针、
`-1` 是顺时针。给定圆心和起终点时，方向决定走**小弧还是大弧**——同一圆心/端点实测：
`+1` 围出 55.43 mm² 小扇形、`-1` 围出 9447.9 mm² 大扇形。方向画反会让轮廓自交或
裂成多条 contour，`revolve_boss` 直接返回 `None`。

**折线串首点不要“去重”**：用点列逐段画线时，`[(p0),(p1),…]` 的相邻两点就是线段；
`p0` 与上一特征终点重合是正常的，它是本串第一段的起点。按上一段终点把 `p0` 删掉，
会让只有两个点的串（口顶面、颈内壁这类单段）变成零段，轮廓裂开。

草图平面：`"Front Plane"`（XY）、`"Top Plane"`（XZ）、`"Right Plane"`（YZ）。
中文版互认已封装；不要自己传“前视基准面”。

> **每个坐标都要 `mm()`**，包括非零的起始坐标。`0` 可以裸写（0 米 = 0 毫米），
> 但 `10` 这种必须写成 `mm(10)`。混用会静默画错：真机案例里
> `sketch_corner_rectangle(part, 0, 10, mm(40), mm(20))` 的第二个参数被当成
> 10 米，矩形跨到板外 10 m，切除后只剩一半宽度——不报错。
> 建完必须用包围盒对参数表核对（`collect_geometry_measurements()["envelope_mm"]`），
> 这是唯一能兜住单位混用的门禁。

## 3. 拉伸（凸台/切除/中面）

```python
from sw_part import extrude_boss, extrude_cut, extrude_midplane

extrude_boss(part, sk, mm(20))                  # direction=True（默认）→ 负法向
extrude_boss(part, sk, mm(20), direction=False) # → 正法向（推荐，多个凸台共享底面）
extrude_midplane(part, sk, mm(20))              # 两侧对称（总深度 20）
extrude_cut(part, sk, mm(10))                   # 定深切除，默认正法向（与凸台相反）
extrude_cut(part, sk, 0.0)                      # 完全贯穿

# 特征命名（可选，name=None 时保留 SW 默认名）：
# 凸台、切除都支持 name=，方便特征树对照和图面检查
extrude_boss(part, sk, mm(12), direction=False, name="01_BASE")
extrude_cut(part, sk, 0.0, name="02_NOTCH")
```

**特征命名约定**（建议，不强制）：`01_BASE`、`02_NOTCH`、`03_BORE_D36` 这种
“序号_用途_关键尺寸”的格式；孔封装自带 `name=` 且会派生 `_通孔` / `_沉孔` 子特征名。

**方向硬规则（SW2023 实测）**：

- 凸台与切除的 `direction` 语义**相反**（SW2023 实测）：`extrude_boss` 的
  `True`→负法向、`False`→正法向；`extrude_cut` 的 `True`→正法向、`False`→负法向。
  基准面正法向：Front=+Z、Top=+Y、Right=+X。
- 多个凸台共享同一底面时，统一用 `direction=False` 向正轴拉伸。
- **贯穿切除不是方向无关**：从实体端面切入时，方向反了会朝空侧切并返回 `None`；
  `extrude_cut()` 的 `auto_flip=True` 会反向重试，但出现重试日志说明给的
  `direction` 朝了空侧（材料在另一侧），应修正调用方向，不要依赖兜底。
- 定深切除按材料所在侧选 `direction`：材料在正法向侧用 `True`、负法向侧用
  `False`。偏置面贴在材料外端时朝 +法向就是朝空处切（实测 Front Plane 偏置到
  Z=+12 后，`direction=True` 切空、`False` 才切进材料）——不是方向约定反转。
- `extrude_cut()` 盲切返回 `None` 时默认 `auto_flip=True` 自动反向重试，并打印
  `[sw_part] 切除 direction=... 未生成特征，自动翻转方向重试`。看到这行说明
  传的 `direction` 朝了空侧，应修正调用方向；仍失败则停下检查草图，不要连续叠特征。
- `FeatureCut4` 的方向参数是第 3 个 `Dir`，与 `FeatureExtrusion3` 的 `Dir` 在
  SW2023 中含义相反；不要自己传前两个参数。

## 4. 旋转

```python
from sw_part import revolve_boss

with sketch(part, "Front Plane") as sk:
    # 画半个剖面 + 一条中心线（用 sketch_line 画在旋转轴上）
    ...
revolve_boss(part, sk, deg(360))
```

## 5. 圆角 / 倒角（最后做，必须先选边）

`fillet()` / `chamfer()` **不会自动选边**；没有选择就调用会失败或生成空特征。

```python
from sw_part import fillet, chamfer

def select_edges(part, predicate):
    """按几何条件选边，返回选中的数量。"""
    part.ClearSelection2(True)
    count = 0
    for body in part.GetBodies2(0, False) or []:
        for edge in body.GetEdges() or []:
            try:
                if predicate(edge) and edge.Select4(True, None):
                    count += 1
            except Exception:
                continue
    return count

def is_circle_edge(edge):
    curve = edge.GetCurve()
    return bool(curve) and bool(curve.IsCircle())

# 例：给所有圆孔口倒角 C0.5（先选边，再调用）
n = select_edges(part, is_circle_edge)
if n:
    chamfer(part, mm(0.5))
part.ClearSelection2(True)
```

- 圆角/倒角放在所有切除之后；失败时保留直边模型，并在交付说明里写“圆角未应用”。
- 不确定选哪些边时，**不要做**；A 模式直接跳过，B 模式把它列为待人工处理项。
- 优先用草图轮廓（圆角矩形、槽口）代替特征圆角，稳定性更高。

## 6. 阵列 / 镜像

```python
from sw_part import linear_pattern, mirror_feature

linear_pattern(part, "Hole1", 1, 0, 0, mm(20), 4)       # X 向 4 个（含源），间距 20
linear_pattern(part, "Hole1", 1, 0, 0, mm(20), 3,
               0, 1, 0, mm(15), 2)                       # 3×2 网格，共 6 个
mirror_feature(part, "Boss1", "Right Plane")
# circular_pattern 未实测，默认不要用（见下方说明）
```

- `linear_pattern` 会自动建一个辅助 3D 草图表达方向，**不要删**；阵列数量
  是含源实例的总数。
- `circular_pattern` 未实测，**默认不要用**；均布孔优先在草图里画圆阵列，或逐个切除。
  轴没把握时标“需人工”；基准轴未封装，优先用圆柱面/圆边线。

## 7. 抽壳

```python
from sw_part import shell
shell(part, mm(2), [face])  # 移除 face（IFace2 对象），返回「抽壳1」
shell(part, mm(2))          # 不传面 = 完全中空密封体
```

- 面必须是 `IFace2` 对象，不能传名称；传错会抛 `ValueError`。
- 抽壳后孔要重做/后做：孔排在抽壳之后。

取面示例（按几何条件筛，不要用面名）：

```python
from sw_connect import get_com_member

body = part.GetBodies2(0, False)[0]
def face_box(face):
    return list(get_com_member(face, "GetBox"))  # [xmin,ymin,zmin,xmax,ymax,zmax]，米
top = next(f for f in body.GetFaces()
           if abs(face_box(f)[2] - mm(20)) < 1e-6
           and abs(face_box(f)[5] - mm(20)) < 1e-6)  # zmin=zmax=20 的顶面
shell(part, mm(2), [top])
```

## 8. 孔（推荐：圆草图切除；复杂孔用封装）

```python
from sw_hole_features import (
    create_blind_hole, create_through_hole,
    create_counterbore_hole, create_countersink_hole,
    create_semicircular_slot, create_hole_pattern,
)

# 注意：center 是草图平面内的二维坐标（米）
# 孔草图会自动生成直径/位置尺寸，出图时可用
create_through_hole(part, (mm(0), mm(0)), mm(8), plane_name="Top Plane", name="通孔_D8")
# 盲孔/沉孔/定深槽按材料所在侧传 direction：材料在正法向侧用 True、
# 负法向侧用 False（与凸台相反）；方向错时底层 extrude_cut 会自动反向重试
# （auto_flip=True）。通孔方向反了也可能返回 None，不要假设方向无关。
create_blind_hole(part, (mm(20), mm(10)), mm(6), mm(12),
                  plane_name="Front Plane", name="盲孔_D6", direction=True)
create_counterbore_hole(part, (mm(30), 0), mm(6.6), mm(11), mm(6),
                        plane_name="Top Plane", name="沉孔_M6", direction=True)
# 参数顺序：center, hole_diameter(小), counterbore_diameter(大), counterbore_depth
# 只有一个 direction，同时驱动通孔段和沉孔段，两段都从 plane_name 起算深度。
create_countersink_hole(part, (mm(-30), 0), mm(6.6), mm(12), 90,
                        plane_name="Top Plane", name="沉头_M6")
create_semicircular_slot(part, (mm(-20), 0), (mm(20), 0), mm(8),
                         plane_name="Top Plane", name="槽_8", direction=True)
```

孔位阵列：

```python
positions = [(mm(x), mm(y)) for x, y in [(-30, -20), (30, -20), (30, 20), (-30, 20)]]
create_hole_pattern(part, positions, create_through_hole,
                    diameter=mm(6.6), plane_name="Top Plane", name="安装孔_M6")
```

## 9. 草图自动标注（出图必需）

```python
from sw_part import auto_dimension_sketch

with sketch(part, "Front Plane") as sk:
    segments = sketch_rectangle(part, 0, 0, mm(120), mm(80))
    auto_dimension_sketch(part, sketch_segments=segments)
```

## 10. 读取 / 修改已有零件的命名尺寸

```python
from sw_connect import get_com_member
from sw_document_data import update_dimension_mm

def list_dimensions(model):
    """遍历特征树，返回 [(FullName, 当前值 mm), ...]。"""
    result = []
    # 本机 SW2023 上 FirstFeature / GetFirstDisplayDimension 是属性式伪成员，
    # 直接加括号会抛“找不到成员”。统一用 get_com_member 兼容两种形态。
    feature = get_com_member(model, "FirstFeature")
    while feature:
        dim = get_com_member(feature, "GetFirstDisplayDimension")
        while dim:
            dimension = get_com_member(dim, "GetDimension")
            result.append((get_com_member(dimension, "FullName"),
                           float(get_com_member(dimension, "SystemValue")) * 1000.0))
            dim = get_com_member(feature, "GetNextDisplayDimension", dim)
        feature = get_com_member(feature, "GetNextFeature")
    return result

for name, value_mm in list_dimensions(part):
    print(name, round(value_mm, 3))

update_dimension_mm(part, "D1@Sketch1", 150.0)   # value_mm 用毫米
part.ForceRebuild3(False)
```

实测（2026-10-24）：对同一块板，`list_dimensions` 应返回
`120/80`（外形）、`20/40`（缺口）、`9.0`（孔）、`12`（拉伸深度）、
`22/6`（沉孔）等全部模型尺寸。若工程图只导入极少数尺寸，先跑这个清单
确认**模型里确实有尺寸**，再重跑一次出图（首次导入偶发只拿到 2 个，
重跑得到 17 个）；不要看到尺寸少就直接判定“模型无尺寸”。

`dimension_name` 必须来自上面的清单，不要猜 `D1@Sketch1`。

## 11. 读取模型信息（建模后必做）

```python
from sw_review import collect_geometry_measurements, collect_model_summary, run_review

summary = collect_model_summary(part)          # 特征树
measurements = collect_geometry_measurements(part)
print(measurements["envelope_mm"], measurements["holes"])

report, report_path = run_review(
    part, r"<workdir>\review", basename="part",
    expected_outputs=[r"<workdir>\part.SLDPRT"])
print(report["evaluation"])
```

`run_review` 会导出 `isometric/front/top/right` BMP 和 JSON 报告。必须打开图片看。

`envelope_mm` 的键是**模型 XYZ**（`length`=X、`width`=Y、`height`=Z，另见
`axis_order`），不是图纸的“长宽高”。竖放的回转件（轴=Y）高度落在 `width`，
两个直径分列 `length`/`height`——按图纸习惯读 `width` 会误判高度。

**回转体体积独立验算（Pappus 定理）**：闭合材料剖面（外轮廓 + 内腔，含壁厚）的
有向面积 A 与形心半径 x̄ 满足 `V = 2π·x̄·A`。把直线/圆弧细分离散成点列后：

```python
import math

def pappus_ml(pts):          # pts=[(半径mm, 高度mm), ...]，按轮廓顺序，自动闭合
    s = sx = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        cross = x1 * y2 - x2 * y1
        s += cross
        sx += (x1 + x2) * cross
    area = 0.5 * s
    centroid_x = sx / (6.0 * area)
    return 2.0 * math.pi * centroid_x * abs(area) / 1000.0
```

与 `measurements["volume_mm3"] / 1000` 比，差 >0.1% 即停。圆弧用 300~500 点细分，
离散误差 <1e-6；实测两段圆弧水瓶差 2×10⁻⁷。

## 12. 特征树导出（分析已有模型 / 题库）

```bash
py -3.12 "<skill>\scripts\sw_feature_dump.py" \
  --part "<workdir>\part.SLDPRT" --output "<workdir>\part_features.json"
```

## 13. 模型 → 三视图

```bash
py -3.12 "<skill>\scripts\sw_three_view.py" \
  --part "<workdir>\part.SLDPRT" --out-dir "<workdir>\drawing" --paper A3 --projection first --dims
```

出图后先看 `_drawing_report.json`：

- `sheet_setup.sheet_size_verified` 必须为 `true`，A3 的 `actual_size_m` 必须是
  `[0.42, 0.297]`。SW2023 的纸型码：A4=6、A3=8、A2=9、A1=10、A0=11；
  `SetupSheet6`/`NewSheet4` 第 3 个参数 `TemplateIn` 必须同码，否则图幅不变。
- `structure.dimension_count` 为 0 时，回模型给草图/孔补
  `auto_dimension_sketch()`；直接 `CreateLine/CreateCircle` 不会生成尺寸。
- `preview.not_blank` 必须为 `true`，并打开 PNG 目视检查布局。

详见 `references/part-to-drawing.md`。

## 14. 装配体 + 配合（简版）

```python
from sw_assembly import add_component, add_mate5_checked, add_concentric_mate_by_cylinders

session = SolidWorksSession()
asm = session.new_assembly()
component = add_component(asm, r"<workdir>\part1.SLDPRT")
# 先解析组件对象，再按实体/面做配合；不要用屏幕坐标
```

完整用法见 `references/assembly.md`。

## 15. 平面坐标方向（SW2023 实测，务必遵守）

凸台 `extrude_boss`：

| 草图平面 | 草图 (u, v) 映射到模型 | `direction=True`（默认） | `direction=False` |
|---|---|---|---|
| Front Plane | (X=u, Y=v, Z=0) | 向 **−Z**，材料 Z ≤ 0 | 向 **+Z**，材料 Z ≥ 0 |
| Top Plane | (X=u, Y=0, Z=−v) | 向 **−Y**，材料 Y ≤ 0 | 向 **+Y**，材料 Y ≥ 0 |
| Right Plane | (X=0, Z=−u, Y=v) | 向 **−X**，材料 X ≤ 0 | 向 **+X**，材料 X ≥ 0 |

切除 `extrude_cut` 与凸台语义相反（2026-10-24 SW2023 SP0.1 实测矩阵，auto_flip=False）：

| 草图平面 | `direction=True`（默认） | `direction=False` |
|---|---|---|
| Front Plane | 向 **+Z**，切材料 Z ≥ 0 | 向 **−Z**，切材料 Z ≤ 0 |
| Top Plane | 向 **+Y**，切材料 Y ≥ 0 | 向 **−Y**，切材料 Y ≤ 0 |
| Right Plane | 向 **+X**，切材料 X ≥ 0 | 向 **−X**，切材料 X ≤ 0 |

实测记录（凸台，direction=True 默认；2026-10-24，SW2023 SP0.1）：

- Top Plane 画圆 (10, 20)，拉伸 5 mm → 包围盒 `[8,-5,-22, 12,0,-18]`。
- Front Plane 画圆 (10, 20)，拉伸 5 mm → 包围盒 `[8,18,-5, 12,22,0]`。
- Right Plane 画圆 (10, 20)，拉伸 5 mm → 包围盒 `[-5,18,-12, 0,22,-8]`。

由此得到三条稳定规则：

1. **拉伸只选一种方向约定**。推荐凸台共享底面时统一
   `extrude_boss(..., direction=False)`，材料在正轴一侧。拉伸的 `direction`
   可以全零件统一；**切除的 `direction` 永远以材料所在侧为准，不要机械照搬拉伸值**
   ——两个封装 True/False 语义相反，照抄必反。
2. **在哪个基准面上建立主体，就在同一个基准面上做孔/槽/切除**。
   切除方向必须与材料所在侧一致：材料在正轴侧用 `True`，在负轴侧用 `False`
   （与凸台相反，2026-10-24 实测矩阵）。**通孔也不是方向无关**：从实体端面贯穿时，
   方向反了会朝空侧切并返回 `None`；`extrude_cut()` 的 `auto_flip=True` 会反向重试。
3. 需要从另一个面加工时（例如主体在 Top 上、还要在 Front 面开孔），
   必须建**偏置基准面**。偏置面贴在材料外端时，朝 +法向切就是朝空处切，
   要用 `direction=False`（SW2023 实测：Front Plane 偏置 +12 mm 后，
   `direction=True` 切空、`False` 才切进材料）——不是方向约定反转。
   `extrude_cut()` 默认 `auto_flip=True` 会兜底，但仍要先做一个试验孔，
   回读孔深/包围盒后再批量。

```python
from sw_part import insert_offset_plane

# 偏置基准面：先选中基准面再 InsertRefPlane，否则返回 None（SW2023 实测）
plane = insert_offset_plane(part, "Front Plane", mm(offset), "Plane_Machining")
with sketch(part, "Plane_Machining") as sk:
    sketch_circle(part, 0, 0, mm(3))
# 偏置面贴在材料外端：+法向指向空侧，用 direction=False 朝 −法向切进材料
# （材料在偏置面的 +法向侧时才用 True）；切空时 auto_flip 会自动反向并打印提示
feat = extrude_cut(part, sk, mm(depth), direction=False)
if feat is None:
    raise RuntimeError("偏置面盲切失败：检查偏置量是否落在材料上")
```

`insert_offset_plane` 的正负号决定偏置方向；Front Plane 的 `+offset` 向 +Z。
第一次用新偏置面时，先做一个试验特征并回读包围盒，不要批量开孔。

**负偏置与左右对称件（SW2023 SP0.1 实测，2026-10-24）**：
直接 `InsertRefPlane(8, -d)` 负号被静默忽略，面落在基面上，不报错——
拖拉机 v1 的左侧两轮因此建在 Z=0、整个埋进车身，只有体积/实体数门禁抓到。
`insert_offset_plane` 已改为负值走 `8 | 256`（Flip）+ `abs(d)`；翻转面的
面内 X/Y 不变、正法向仍是 +Z。所以左右对称件这样写：

```python
for side, sign in (("R", 1), ("L", -1)):
    insert_offset_plane(part, "Front Plane", mm(sign * 320), f"Plane_Wheel{side}")
# 两侧都“从内侧面向外”拉：右侧 +Z → direction=False；左侧 −Z → direction=True
extrude_boss(part, sk, mm(260), direction=(sign < 0))
```

**草图吸附**：在已有实体或失败残留草图附近画图，用 `sketch(part, plane, exact=True)`
（`SketchManager.AddToDB=True`）。实测不开时 50×180 矩形被吸附成 60×160、无报错。

第一次放置不对称特征后，立刻回读孔位核对：

```python
from sw_review import collect_geometry_measurements
holes = collect_geometry_measurements(part)["holes"]
print([(h["diameter_mm"], h["position_mm"]) for h in holes])
```

包围盒 `GetPartBox(True)` 的三个方向必须与预期（长、高、深）对应；不对就回退，不要继续叠加特征。

## 16. 常见返回值检查

```python
feature = extrude_boss(part, sk, mm(20))
if feature is None:
    raise RuntimeError("拉伸失败：检查草图是否闭合/方向")
```

每个特征、保存、导出都必须检查 `None`/`False`；不要只看“没报错”。
