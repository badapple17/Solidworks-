# 配方：平板 / 盖板 / 安装板

## 识别

- 主视图和俯视图的外形是矩形或矩形组合；厚度方向尺寸单一（`T`）。
- 图上有缺口、方槽、圆孔、沉孔、长圆槽，通常都在板面上。
- 特征树典型：`Extrusion → Cut/ICE×N → HoleWzd → Fillet/Chamfer`。

## 姿势判断（先判断，再套步骤）

“板平放、Front Plane 画轮廓、孔沿 Z 向钻”是**默认姿势，不是唯一姿势**。
动手前先判三点，任一不符就调整步骤而不是硬套：

1. **草图面 = 图纸信息量最大的视图**：孔位/缺口/凸台全在俯视图 → Front Plane；
   全在主视图 → Top/Right 方向摆。哪个视图信息最多，就把哪个画成第一张草图
   （expert-thinking.md R2）。
2. **沉孔/沉头孔端面由图纸定**：大孔画在哪一侧的视图/剖面上，就朝哪侧加工。
   下面第 4 节的表同时覆盖顶面 `Z=T` 与底面 `Z=0` 两种情况，按图纸选行，不要
   默认“顶面”。
3. **原点跟随图纸基准**：图纸尺寸从对称面起标 → 原点放对称面；从左下角起标 →
   原点放左下角（expert-thinking.md §1.6）。

判断结果写进任务卡 FeatureGroups 再执行；判断与固定步骤冲突时以判断为准。

## 参数表

| 参数 | 含义 | 来源 |
|---|---|---|
| `L, W, T` | 板长、板宽、板厚 | 图纸总尺寸 |
| `origin` | 原点位置（左下角/中心） | 自定；全模型统一 |
| `notches` | 缺口：`(x, y, w, h)` 或轮廓点 | 图纸 |
| `holes` | `(x, y, d)`，必要时 `type=cb/cs` | 图纸 |
| `fillets` | 外角/内角半径 | 图纸或 `assumed` |

## 固定步骤

1. **定原点**：建议板面左下角为 `(0,0)`，厚度向 `+Z`。
2. **底板**：Front Plane 画矩形，`extrude_boss(direction=False)`。
3. **缺口/方槽**：同一平面画闭合轮廓，`extrude_cut(..., 0.0)` 贯穿。
   - **开口缺口（含图纸上说的“U 形缺口”）一律用矩形轮廓建模**：矩形一条边压在或越过板轮廓线上，切开后板边自然形成开口；不需要画 U 形的半圆弧。图上确实带圆弧的 U 形口，也先按矩形开口做出总尺寸，圆弧留到以后用圆角补，不要为此猜未文档化的 API。
   - **开口规则**：矩形的开口边必须落在板轮廓上或伸出板外（如 `x=0` 边从 `x=-1` 画到 `x=w`）；矩形完全落在板内只会切出一个封闭方槽，外边缘仍在。
4. **孔**：同一平面 `create_through_hole()`；沉孔/沉头孔用对应封装。
5. **长圆槽**：`create_semicircular_slot()`。
6. **圆角/倒角**：最后做；不稳定就跳过并记录。
7. **出图前**：每个草图调用 `auto_dimension_sketch()`。

> 板向 `+Z` 拉伸时，底面在 `Z=0`、顶面在 `Z=T`。
> 通孔从 Front Plane 贯穿时用默认 `direction=True`（材料在 +Z 侧，沿 +法向切进材料）；
> **沉孔必须从顶面加工**，见第 4 节。

## 代码骨架（可直接改参数）

```python
import sys
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import mm
from sw_part import (sketch, sketch_corner_rectangle, auto_dimension_sketch,
                     extrude_boss, extrude_cut)
from sw_hole_features import create_through_hole, create_counterbore_hole
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements

L, W, T = 120.0, 80.0, 10.0          # mm
HOLES = [(20, 20, 8), (100, 20, 8), (20, 60, 8), (100, 60, 8)]
NOTCH = (0, 30, 15, 20)               # x, y, w, h（从左边缘开口的缺口）

session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
try:
    # 1) 底板：左下角为原点，向 +Z 拉伸
    with sketch(part, "Front Plane") as sk:
        sketch_corner_rectangle(part, 0, 0, mm(L), mm(W))
        auto_dimension_sketch(part)
    extrude_boss(part, sk, mm(T), direction=False, name="01_BASE")

    # 2) 左侧开口缺口（贯穿）。开口边压在 x=0 板轮廓上；
    #    若担心浮点误差可画到 x=-1，伸到板外不影响切除结果。
    x, y, w, h = NOTCH
    with sketch(part, "Front Plane") as sk:
        sketch_corner_rectangle(part, mm(x), mm(y), mm(x + w), mm(y + h))
        auto_dimension_sketch(part)
    extrude_cut(part, sk, 0.0, name="02_NOTCH")

    # 3) 通孔
    for i, (hx, hy, hd) in enumerate(HOLES, 1):
        create_through_hole(part, (mm(hx), mm(hy)), mm(hd),
                            plane_name="Front Plane", name=f"安装孔{i}_D{hd:g}",
                            direction=True)

    part.ForceRebuild3(False)
    m = collect_geometry_measurements(part)
    print("envelope_mm:", m["envelope_mm"], "holes:", m["hole_count"])
    assert abs(m["envelope_mm"]["length"] - L) < 0.1
    assert abs(m["envelope_mm"]["width"] - W) < 0.1
    assert abs(m["envelope_mm"]["height"] - T) < 0.1
    assert m["hole_count"] == len(HOLES)   # 无沉孔时：圆柱面数 == 通孔数
    session.save(part, r"<workdir>\plate.SLDPRT")
finally:
    session.close(part)
```

> `hole_count` 数的是 B-Rep 圆柱面，不是“孔的数量”。有沉孔/沉头时，
> 一个孔会有 2 段圆柱面，`hole_count` 大于孔数；此时用 `compound_holes`
> 检查同轴两段，不要用 `hole_count == 孔数` 做断言。
>
> **混合孔数示例**（黄金用例 `d2p_b_plate_holes`，2026-10-24 实测）：
> 4 个 D9 通孔（4 段圆柱面）+ 1 个 D22×6 沉孔压在 D10 通孔上（大孔 1 段 + 小孔 1 段，
> 共 2 段）= `hole_count == 6`。期望值按“通孔数 + 2×沉孔数”手算，再与实际比对。
>
> `compound_holes` 中这一组同轴两段的直径是 `[22.0, 10.0]`（大孔在前），
> 可用来断言“沉孔大径 22、通孔 10”而不用读实体面。

## 4. 沉孔 / 沉头孔（顶面加工）

板向 `+Z` 拉伸时，材料在 Front Plane 的正法向一侧。沉孔是**定深切除**，
方向必须让大孔落在要求的面上：

| 大孔所在面 | 草图平面 | `direction` |
|---|---|---|
| 顶面 `Z=T` | 偏置面 `Z=T` | `False`（2026-10-24 实测；`True` 会切空，auto_flip 兜底） |
| 底面 `Z=0` | Front Plane | `True`（向 +Z 切进材料） |

顶面沉孔先建偏置面，再在偏置面上做孔（二维坐标与原 Front Plane 一致）：

```python
from sw_part import insert_offset_plane

plane = insert_offset_plane(part, "Front Plane", mm(T), "Plane_Top")
create_counterbore_hole(
    part,
    (mm(20), mm(20)),      # center：孔心二维坐标（单位与草图一致，用 mm()）
    mm(6.6),               # hole_diameter：通孔直径（小孔）
    mm(11),                # counterbore_diameter：沉孔大径
    mm(6),                 # counterbore_depth：沉孔深度（从草图平面量起）
    plane_name="Plane_Top",
    name="沉孔_M6",
    direction=False)       # 一个 direction 同时驱动大孔段和小孔段
```

> **参数顺序固定为** `(model, center, hole_diameter, counterbore_diameter,
> counterbore_depth, plane_name=, name=, direction=)`：小径在前、大径在后、深度最后。
> 不要按“大径、小径”的直觉顺序传，否则会建出大头朝下的孔。
>
> **`direction` 只有一个，同时作用于沉孔段和通孔段**（2026-10-24 实机确认）：
> 两段都从草图平面沿同一法向切出，深度从草图平面起算。
> 所以只要草图平面选对（大孔所在面），一个方向参数就够，不存在“大孔一段方向、小孔另一段方向”的写法。

偏置面 `Z=T` 贴在材料外端，+法向与基面同向：朝 +法向切就是朝空处切
（2026-10-24 实测矩阵：材料 `Z=0..10`、偏置面 `Z=+10` 时 `True` 返回 `None`、
`False` 生成特征）。`extrude_cut()` 盲切返回 `None` 时会自动反向重试，并打印
`[sw_part] 切除 direction=... 未生成特征，自动翻转方向重试`。看到该提示说明
实参 `direction` 给反了，应修正调用，并把后续同类孔的方向统一。若孔位镜像，检查 `InsertRefPlane` 的偏移符号，先做一个孔回读
`position_mm` 和包围盒，再批量。**不要**在 Front Plane 上用默认方向做顶面
沉孔：默认 `direction=True` 朝 +Z 切，大孔会落在底面。

## 5. 验证清单

| 项 | 通过标准 |
|---|---|
| 包围盒 | 长/宽/厚与 `L,W,T` 差 ≤ 0.1 mm |
| 缺口 | 缺口尺寸和开口方向与图一致；不是封闭方槽 |
| 孔 | 数量、孔径、孔位全对；沉孔大径朝顶面 |
| 图纸 | 三维出图后尺寸数 > 0，且含 `L/W/T/孔径` |

## 6. 常见错误

- 用中心矩形却把原点当左下角 → 整体偏移半个板。
- 缺口画成封闭矩形切除 → 变成内部方槽，外边缘还在。
- 沉孔从错误的面切入 → 大孔在底面，图纸方向反。
- 忘记 `auto_dimension_sketch()` → 出图没有长宽尺寸。
