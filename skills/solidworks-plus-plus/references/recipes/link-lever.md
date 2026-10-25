# 配方：连杆 / 摆臂 / 耳板支座

## 识别

- 一个主圆（凸台/轮毂）+ 一个端圆（环）+ 中间直杆，整体像“哑铃”或“连杆”。
- 主圆处通常有中心孔；端环有销孔；杆的宽度由两端圆的外公切线决定。
- 还可能带底板、开口槽、加强筋。

题目原型：64 题库 `001.SLDPRT`（本机已按图重建，包围盒与答案完全一致）。
完整案例见 `references/case-library.md` 案例 1。

## 参数表

| 参数 | 含义 | 001 示例 |
|---|---|---|
| `D_boss, d_boss` | 主圆外径、中心孔 | φ25 / φ15 |
| `D_ring, d_ring` | 端环外径、销孔 | φ12 / φ8 |
| `L` | 两圆中心距 | 37 |
| `theta` | 中心线相对 +X 的角度 | 32° |
| `t_arm` | 杆/端环厚度 | 4 |
| `H_boss` | 主圆凸台高度 | 10 |
| `base` | 底板 `W×H×T` + 开口槽 | 30×25×5，槽 13×10 |
| `origin` | 主圆中心 | `(0,0)` |

## 固定步骤

1. **底板**（若有）：Front Plane 画矩形，向 `+Z` 拉伸 `T`；开口槽用 `extrude_cut(..., 0.0)`。
2. **主圆凸台**：同一平面画 `D_boss/2` 圆，向 `+Z` 拉伸 `H_boss`。
3. **杆**：计算两圆外公切线四个切点，连成梯形，向 `+Z` 拉伸 `t_arm`。
4. **端环**：画 `D_ring/2` 圆，向 `+Z` 拉伸 `t_arm`。
5. **孔**：主圆孔、端环孔，`create_through_hole()` 贯穿。
6. **圆角/倒角**：最后；不稳定就跳过。
7. **标注**：每个草图 `auto_dimension_sketch()`，否则出图没有 φ25/φ12/37。

> 关键顺序：先做主圆和端环，再做杆；杆的梯形两端落在圆内，合并后自然成外公切线轮廓。
> 不要用“宽度 8 的矩形”代替——杆在图纸上是**变宽**的，矩形会在主圆处出现台阶。

## 杆身取法判断（先判断，再选公式）

杆的形状由两端圆的关系决定，**不是永远用外公切线梯形**：

| 两端圆关系 | 判据 | 杆身取法 |
|---|---|---|
| 相离 | `L > R1 + R2` | 外公切线梯形（下方公式；`beta = asin((R1−R2)/L)`） |
| 相交/相切 | `R1 + R2 ≥ L > |R1−R2|` | 两圆轮廓重叠；杆为矩形/覆盖块，或按图纸画圆弧过渡杆身 |
| 内含 | `L < |R1−R2|` | 一圆包住另一圆——不是连杆形状，回去重读图或问用户 |

图纸上杆身是**弧线过渡**而非直线切边时（弧形连杆），不用切线公式：画一条与两圆
相切的圆弧或按图纸轮廓点连线，形状由图纸定。切点公式只负责“直杆”这一种。

## 外公切线计算（通用公式，R1/R2/L/theta 替换参数即可）

```python
import math
R1, R2, L, theta = 12.5, 6.0, 37.0, math.radians(32.0)
beta = math.asin((R1 - R2) / L)          # 切线相对中心线的偏角
# 法向 n 由中心线方向旋转 (90° - beta)
n = (math.sin(beta) * math.cos(theta) - math.cos(beta) * math.sin(theta),
     math.sin(beta) * math.sin(theta) + math.cos(beta) * math.cos(theta))
ring = (L * math.cos(theta), L * math.sin(theta))
p1a = (R1 * n[0], R1 * n[1])
p2a = (ring[0] + R2 * n[0], ring[1] + R2 * n[1])
p1b = (-R1 * n[0], -R1 * n[1])
p2b = (ring[0] - R2 * n[0], ring[1] - R2 * n[1])
# 梯形顶点顺序：p1a → p2a → p2b → p1b
```

## 代码骨架（001 参数，已验证）

```python
import sys, math
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import mm
from sw_part import (sketch, sketch_circle, sketch_line, sketch_corner_rectangle,
                     auto_dimension_sketch, extrude_boss, extrude_cut)
from sw_hole_features import create_through_hole
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements

# --- 参数（mm / deg）---
PLATE_W, PLATE_H, PLATE_T = 30.0, 25.0, 5.0
NOTCH_H, NOTCH_D = 13.0, 10.0
D_BOSS, H_BOSS, D_BOSS_HOLE = 25.0, 10.0, 15.0
D_RING, T_ARM, D_RING_HOLE = 12.0, 4.0, 8.0
L, THETA = 37.0, 32.0

R1, R2 = D_BOSS / 2, D_RING / 2
theta = math.radians(THETA)
ring = (L * math.cos(theta), L * math.sin(theta))
beta = math.asin((R1 - R2) / L)
n = (math.sin(beta) * math.cos(theta) - math.cos(beta) * math.sin(theta),
     math.sin(beta) * math.sin(theta) + math.cos(beta) * math.cos(theta))
p1a = (R1 * n[0], R1 * n[1])
p2a = (ring[0] + R2 * n[0], ring[1] + R2 * n[1])
p1b = (-R1 * n[0], -R1 * n[1])
p2b = (ring[0] - R2 * n[0], ring[1] - R2 * n[1])

session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
try:
    # 1) 底板：原点在主圆中心，板在 -X 侧，向 +Z 拉伸 5
    with sketch(part, "Front Plane") as sk:
        sketch_corner_rectangle(part, mm(-PLATE_W), mm(-PLATE_H / 2),
                                mm(0), mm(PLATE_H / 2))
        auto_dimension_sketch(part)
    extrude_boss(part, sk, mm(PLATE_T), direction=False)

    # 2) 左侧开口槽 13×10，贯穿
    with sketch(part, "Front Plane") as sk:
        sketch_corner_rectangle(part, mm(-PLATE_W), mm(-NOTCH_H / 2),
                                mm(-(PLATE_W - NOTCH_D)), mm(NOTCH_H / 2))
        auto_dimension_sketch(part)
    extrude_cut(part, sk, 0.0)

    # 3) 主圆凸台 φ25×10
    with sketch(part, "Front Plane") as sk:
        sketch_circle(part, 0, 0, mm(R1))
        auto_dimension_sketch(part)
    extrude_boss(part, sk, mm(H_BOSS), direction=False)

    # 4) 杆：外公切线梯形，厚 4
    with sketch(part, "Front Plane") as sk:
        for a, b in ((p1a, p2a), (p2a, p2b), (p2b, p1b), (p1b, p1a)):
            sketch_line(part, mm(a[0]), mm(a[1]), mm(b[0]), mm(b[1]))
        auto_dimension_sketch(part)
    extrude_boss(part, sk, mm(T_ARM), direction=False)

    # 5) 端环 φ12×4
    with sketch(part, "Front Plane") as sk:
        sketch_circle(part, mm(ring[0]), mm(ring[1]), mm(R2))
        auto_dimension_sketch(part)
    extrude_boss(part, sk, mm(T_ARM), direction=False)

    # 6) 两个通孔（贯穿，默认方向即可）
    create_through_hole(part, (0, 0), mm(D_BOSS_HOLE),
                        plane_name="Front Plane", name="主圆孔")
    create_through_hole(part, (mm(ring[0]), mm(ring[1])), mm(D_RING_HOLE),
                        plane_name="Front Plane", name="端环孔")

    part.ForceRebuild3(False)
    m = collect_geometry_measurements(part)
    print("envelope_mm:", m["envelope_mm"], "holes:", m["hole_count"])
    session.save(part, r"<workdir>\link_lever.SLDPRT")
finally:
    session.close(part)
```

## 包围盒公式（不打开 SW 也能先算）

```text
Xmax = L*cos(theta) + R_ring
Ymax = L*sin(theta) + R_ring
Xmin = -PLATE_W
Ymin = -PLATE_H/2
Zmax = max(H_BOSS, PLATE_T, T_ARM)
```

001 代入：`37cos32°+6 = 37.3778`，`37sin32°+6 = 25.6070`，
`Xmin=-30`，`Ymin=-12.5`，`Zmax=10`
→ 包围盒 `67.3778 × 38.1070 × 10.0`，与答案文件一致。

## 视图角色提醒

001 的“主视图”在源图里是侧剖面（5/10/4 高度），平面轮廓是俯视图。
本配方把**平面轮廓**画在 Front Plane，所以生成的三视图里
Front 视图是平面轮廓、Top 视图是侧剖面，角色与源图互换。

- 只要几何正确，这是允许的；交付时说明视图角色即可。
- 若必须让生成图的主视图与源图一致，应按 `drawing-to-part.md`
  把**侧剖面**画在 Front Plane，再用 Top Plane 做平面切除（特征更多）。
- 不要为了“视图名字”重做已经正确的几何。

## 验证清单

| 项 | 通过标准 |
|---|---|
| 包围盒 | 与上面的公式一致，误差 ≤ 0.1 mm |
| 杆 | 两侧边是外公切线，不是平行矩形 |
| 重合 | 主圆、杆、端环合并为 1 个实体 |
| 孔 | φ15/φ8 位置正确，贯穿 |
| 图纸 | 尺寸含 φ25/φ15/φ12/φ8/37/32° |

## 常见错误

- 切点公式用**内公切线** → 杆穿过两圆内部，形状反。
- 杆先做、圆后做 → 圆与杆出现薄壁相交，合并失败。
- 底板向 `-Z`、凸台向 `+Z` → 凸台悬空或高度差反。
- 端环厚度做成 10（跟凸台一样）→ 侧视图 4 的尺寸错。
