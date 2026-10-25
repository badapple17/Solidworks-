# 配方：法兰 / 端盖 / 圆盘 / 轮坯

## 识别

- 主视图是回转体，通常有外径、内径、厚度、轮毂、螺栓孔圆（PCD）。
- 俯视图/侧视图有一圈均布孔，可能带沉孔。
- 特征树典型：`Revolution → HoleWzd/Cut → CirPattern → Chamfer/Fillet`。

## 参数表

| 参数 | 含义 | 示例 |
|---|---|---|
| `OD, ID` | 法兰外径、中心孔 | φ120 / φ40 |
| `T` | 法兰厚度 | 12 |
| `hub_od, hub_h` | 轮毂外径、凸出高度 | φ60 / 20 |
| `PCD` | 螺栓孔中心圆直径 | 90 |
| `bolt_d, bolt_n` | 螺栓孔径、数量 | φ9 / 6 |
| `cb` | 沉孔大径/深度（可选） | φ15 / 6 |

## 固定步骤

1. **半剖轮廓**：Front Plane 画中心线（X 轴），画“法兰 + 轮毂”外形。
2. **旋转凸台** 360°。
3. **中心孔**：从右端面（Right Plane）沿 X 贯穿。
4. **螺栓孔**：按 PCD 算极坐标，从右端面贯穿；数量多时一次建全部孔位。
5. **沉孔**（若有）：按图纸选**实际有材料的端面**建偏置面，大径朝外；PCD 大于轮毂外径时从**轮毂一侧的法兰端面 x=T** 下刀，不能从轮毂端面 x=T+HUB_H 下刀（该处 r=PCD/2 是空的）。
6. **倒角/圆角**：轮毂根部圆角、外缘倒角最后做。

> 回转轴固定为 **X 轴**；法兰的两个端面是 YZ 平面。
> 因此所有轴向孔都从 **Right Plane** 进入，而不是 Front Plane。

## 代码骨架

```python
import math, sys
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import mm, create_empty_dispatch_variant
from sw_part import sketch, auto_dimension_sketch
from sw_hole_features import create_through_hole, create_hole_pattern
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements

OD, ID = 120.0, 40.0
T, HUB_OD, HUB_H = 12.0, 60.0, 20.0
PCD, BOLT_D, BOLT_N = 90.0, 9.0, 6

session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
try:
    # 1) 半剖轮廓：法兰 x=0..T，轮毂 x=T..T+HUB_H
    with sketch(part, "Front Plane") as sk:
        part.SketchManager.CreateCenterLine(mm(-5), 0, 0, mm(T + HUB_H + 5), 0, 0)
        points = [
            (0, 0), (0, OD / 2), (T, OD / 2),
            (T, HUB_OD / 2), (T + HUB_H, HUB_OD / 2),
            (T + HUB_H, 0), (0, 0),
        ]
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            part.SketchManager.CreateLine(mm(x1), mm(y1), 0, mm(x2), mm(y2), 0)
        auto_dimension_sketch(part)

    part.ClearSelection2(True)
    part.Extension.SelectByID2(sk, "SKETCH", 0, 0, 0, False, 0,
                               create_empty_dispatch_variant(), 0)
    feature = part.FeatureManager.FeatureRevolve2(
        True, True, False, False, False, False,
        0, 0, 2 * math.pi, 0,
        False, False, 0, 0, 0, 0, 0,
        True, True, True,
    )
    if feature is None:
        raise RuntimeError("法兰旋转主体失败")

    # 2) 中心孔：从右端面沿 X 贯穿
    create_through_hole(part, (0, 0), mm(ID),
                        plane_name="Right Plane", name="中心孔")

    # 3) 螺栓孔：Right 草图 (u,v) -> (X=0, Z=-u, Y=v)
    r = PCD / 2.0
    positions = []
    for i in range(BOLT_N):
        angle = 2 * math.pi * i / BOLT_N
        y = r * math.cos(angle)
        z = r * math.sin(angle)
        positions.append((mm(-z), mm(y)))
    create_hole_pattern(part, positions, create_through_hole,
                        diameter=mm(BOLT_D), plane_name="Right Plane",
                        name=f"螺栓孔_D{BOLT_D:g}")

    part.ForceRebuild3(False)
    m = collect_geometry_measurements(part)
    print("envelope_mm:", m["envelope_mm"], "holes:", m["hole_count"])
    session.save(part, r"<workdir>\flange.SLDPRT")
finally:
    session.close(part)
```

## 沉孔（可选）

先判断沉孔加工面，**不能一律从轮毂端面下刀**。端面由图纸定，再检查该面上
`r = PCD/2` 处有没有材料：

| 图纸沉孔画在 | 偏置面 | 注意 |
|---|---|---|
| 轮毂一侧的法兰端面（大径朝轮毂侧） | `x = T` | 本配方默认；`PCD > HUB_OD` 时也只有这个面在 `r=PCD/2` 处有材料 |
| 轮毂端面 | `x = T + HUB_H` | **仅当 `PCD <= HUB_OD` 才可能**；`PCD > HUB_OD` 时草图悬空、切除返回 None |
| 另一端面（无轮毂侧） | `x = 0` | 用 `x=0` 的偏置面 |

```python
cbore_x = T if PCD > HUB_OD else T + HUB_H
```

```python
from sw_hole_features import create_counterbore_hole
from sw_part import insert_offset_plane

plane = insert_offset_plane(part, "Right Plane", mm(cbore_x), "Plane_CboreFace")
for u, v in positions:
    create_counterbore_hole(part, (u, v), mm(BOLT_D), mm(15), mm(6),
                            plane_name="Plane_CboreFace", name="螺栓沉孔",
                            direction=False, through=False)
```

- `through=False`：第 4 步已经打穿螺栓孔，这里只切沉孔；对已有同径通孔再切一次会返回 None。
- `direction=False`：偏置面 `x=T` 在 `r=PCD/2` 处贴着法兰材料外端，+法向朝 +X（轮毂一侧）；朝 +法向切就是朝空处切，所以 `False` 朝 −X 切进法兰（实测 φ15 落在 `x=6..12`）。`extrude_cut()` 的 `auto_flip=True` 会兜底，出现提示时应修正实参。
- 首批只做一个沉孔，确认大径朝外、孔底有材料后再批量。

### 实测（2026-10-24，SW2023 SP0.1）

参数：`OD=120, ID=40, T=12, HUB_OD=60, HUB_H=20, PCD=90, 6×φ9, 沉孔 φ15×6`。

结果：实体 1 个，包围盒 `32×120×120`；`collect_geometry_measurements()` 返回
13 个圆柱面 = 6×φ9（贯穿孔）+ 1×φ40（中心孔）+ 6×φ15（沉孔）；
`compound_holes` 6 组，每组 `diameters_mm=[9, 15]`，φ15 段位于 `x=6..12`。
右视图可见 6 个同心圆（φ15 外圈、φ9 内孔），确认大径朝法兰端面。

**读数说明**：`hole_count` 数的是 B-Rep 圆柱面，不是“孔的数量”。
中心孔 1 + 螺栓通孔 6 + 沉孔 6 = 13；写验收标准时按这个口径，
不要因为 13 ≠ 7 就判定多打了孔。用 `compound_holes` 检查同轴两段。

## 验证清单

| 项 | 通过标准 |
|---|---|
| 包围盒 | 长度 = `T+HUB_H`；宽 = 高 = `OD`；误差 ≤ 0.1 mm |
| 孔数 | `1 + BOLT_N`（中心孔 + 螺栓孔）；有沉孔时圆柱面数 = `1 + 2×BOLT_N` |
| PCD | 每个螺栓孔到轴线距离 = `PCD/2`，角度均布 |
| 中心孔 | 直径 `ID`，贯穿 |
| 沉孔 | `compound_holes` 有 `BOLT_N` 组，`diameters_mm` 含 `BOLT_D` 和 `CB_D` |
| 图纸 | 出图含 OD/ID/T/PCD/孔数 |

## 常见错误

- 在 Front Plane 上打轴向孔 → 孔沿 Z 方向，和轴线垂直。
- 螺栓孔按 `(x,y)` 直角坐标摆 → 不是圆周均布。
- 轮廓包含中心孔（从 `y=ID/2` 开始）又再做一次中心孔 → 重复切除。
- 轮毂方向搞反 → 总长对但凸出端在图纸背面。
