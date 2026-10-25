# 配方：阶梯轴 / 销轴 / 套筒

## 识别

- 主视图有回转中心线（点划线），轮廓沿轴线分成若干段，每段标直径和长度。
- 可能有键槽、退刀槽、倒角、中心孔、径向孔。
- 特征树典型：`Revolution → ICE/Cut → Chamfer → Fillet`。

## 参数表

| 参数 | 含义 | 示例 |
|---|---|---|
| `segments` | `[(start, end, diameter), ...]` | `[(0,43,56),(43,113,65)]` |
| `total_length` | 总长 | `max(end)` |
| `chamfer` | 端部倒角 | `C1`（默认） |
| `keyway` | `(length, width, depth, x_start)` | 可选 |
| `holes` | 径向孔 `(x, angle, d)` | 可选 |

**轴向坐标 `x` 从轴左端面起算，向右为正；旋转轴取 X 轴。**

## 轮廓判断（先判断，再套步骤）

旋转一次成形是首选，但轮廓要按零件类型画，`segments` 表不是唯一输入形式：

| 零件类型 | 轮廓画法 |
|---|---|
| 实心阶梯轴 | 半剖轮廓闭合到轴线（下方骨架即此型） |
| 套筒/空心轴 | 轮廓留壁厚：外轮廓走 `y>0`，内轮廓走内径线闭合，不闭合到轴线 |
| 鼓形/两端大中间小 | 直径非单调也照写 `segments`（按 x 排）；此类尤其**不要**逐段拉伸——中段细、两端粗时逐段拉伸会互相遮挡 |
| 带凸缘/法兰段 | 凸缘是旋转轮廓的一部分（径向台阶），一次旋成，不另建特征（expert-thinking.md R12） |

**何时才逐段拉伸**：图纸剖面不是绕同一轴线的连续轮廓（如偏心段、叉形端）——
这时旋转不成立，按凸台/切除分段建，并接受特征数变多。判断依据是剖面能否绕轴
旋出整件，不是“直径是否递减”。

## 固定步骤

1. **半剖轮廓**：Front Plane 画中心线（X 轴），在 `y>0` 侧画“阶梯形”闭合轮廓。
2. **旋转凸台**：`FeatureRevolve2` 360°，一次生成所有轴段。
3. **端部倒角**：先选端面外圆边，再 `chamfer(C1)`。
4. **键槽**：在圆柱面切向偏置面上画长圆槽，盲切；不要从中心面切。
5. **径向孔**：从偏置面或 Right/Top 面切入，确保穿过轴线。
6. **圆角**：轴肩过渡圆角最后做；失败则保留直角并记录。

## 代码骨架（可直接改 segments）

```python
import math, sys
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import mm, deg, create_empty_dispatch_variant
from sw_part import sketch, auto_dimension_sketch
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements

SEGMENTS = [(0.0, 43.0, 56.0), (43.0, 113.0, 65.0)]   # start, end, diameter (mm)

session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
try:
    with sketch(part, "Front Plane") as sk:
        # 中心线（旋转轴）
        part.SketchManager.CreateCenterLine(mm(-5), 0, 0, mm(SEGMENTS[-1][1] + 5), 0, 0)
        # 半剖轮廓：从 (0,0) 沿台阶走一圈
        points = [(SEGMENTS[0][0], 0.0)]
        for start, end, dia in SEGMENTS:
            points.append((start, dia / 2.0))
            points.append((end, dia / 2.0))
        points.append((SEGMENTS[-1][1], 0.0))
        points.append((SEGMENTS[0][0], 0.0))
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            part.SketchManager.CreateLine(mm(x1), mm(y1), 0, mm(x2), mm(y2), 0)
        auto_dimension_sketch(part)

    # 选中草图后旋转 360°
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
        raise RuntimeError("旋转主体失败：检查轮廓是否闭合、是否跨过中心线")

    part.ForceRebuild3(False)
    m = collect_geometry_measurements(part)
    print("envelope_mm:", m["envelope_mm"], "cyl_faces:", len(m.get("cylindrical_faces", [])))
    session.save(part, r"<workdir>\stepped_shaft.SLDPRT")
finally:
    session.close(part)
```

## 键槽（可选，圆柱面切向加工）

```python
from sw_part import sketch_slot, extrude_cut, insert_offset_plane

key_len, key_w, key_depth, x_start = 30.0, 8.0, 4.0, 50.0
radius = 65.0 / 2.0
plane = insert_offset_plane(part, "Front Plane", mm(radius), "Plane_Keyway")
with sketch(part, "Plane_Keyway") as sk:
    # 偏置面与 Front Plane 平行，二维 u=x，v=y；槽中心必须在 v=0（圆柱顶线）
    sketch_slot(part, mm(x_start), 0, mm(x_start + key_len), 0, mm(key_w / 2))
    auto_dimension_sketch(part)
# 偏置面贴在材料外端（Z=+R，材料在 −法向一侧）：extrude_cut 的 direction=True
# 朝 +法向切，等于朝空处切（2026-10-24 实测矩阵，与 extrude_boss 语义相反）。
# 这里必须用 False，不要靠 auto_flip 兜底。
extrude_cut(part, sk, mm(key_depth), direction=False)
```

要点：

- 偏置面必须与圆柱**相切**，不能穿过轴线。
- 下刀方向：偏置面贴在材料外端，`extrude_cut` 用 `direction=False`
  （其 `True` 朝 +法向切，与 `extrude_boss` 语义相反；2026-10-24 实测矩阵）。
- 偏置面与 Front Plane 平行时，草图 `(u,v)=(X,Y)`，**不是** `(X,−Z)`；
  槽中心放 `v=0`，不要放到 `v=key_w/2`，否则键槽偏离圆柱顶线。
- 槽宽是 `2×半径`；`sketch_slot` 最后参数是半径，不是宽度。
- 切完回读槽底：槽底到轴线距离应等于 `半径 − 槽深`。

## 验证清单

| 项 | 通过标准 |
|---|---|
| 包围盒 | 长 = `total_length`；宽 = 高 = 最大直径；误差 ≤ 0.1 mm |
| 圆柱面 | 每个轴段一个圆柱面，直径与参数表一致 |
| 同轴 | 所有轴段轴线共线；端面圆跳动无异常 |
| 倒角 | 两端 C1，方向朝外 |
| 图纸 | 出图含各段直径、长度、总长、倒角 |

## 常见错误

- 轮廓跨过中心线（`y<0`）→ 旋转出双层实体或失败。
- 先逐段拉伸再合并 → 轴肩出现接缝，出图多一堆边线。
- 键槽从中心面切 → 把轴剖开，不是表面凹槽。
- 倒角选到轴肩内圆边 → 轴肩被削掉一圈。
