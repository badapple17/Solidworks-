# 配方：L 形支架 / 角座 / 带筋板

## 识别

- 侧视图是 L 形或 U 形；俯视图是矩形；通常有底板安装孔和立板连接孔。
- 可能有三角筋、圆角、减重孔。
- 特征树典型：`Extrusion → ICE/Cut → Rib → MirrorPattern → HoleWzd → Fillet`。

## 轮廓判断（先判断，再选轮廓）

下方点表只覆盖**直角 L**。侧剖面是别的形状时按表取轮廓，不要硬套直角 L：

| 侧剖面形状 | 草图取法 |
|---|---|
| 直角 L（底板+立板） | 下方固定点表 |
| U 形（底板+两立板） | 同平面画 U 形闭合轮廓（左右对称走镜像更省：画半边 L → MirrorPattern，见 expert-thinking.md R10） |
| 斜立板（立板与底板非 90°） | 立板边用斜线：从底板端画到 `(−T', H)`，`T'` 由角度和高度算；坐标映射同下方 |
| 底板 + 双侧立板（T 形侧剖） | 画 T 形闭合轮廓，孔分两侧打 |
| 带圆弧过渡的支架 | 内角画圆弧轮廓（在草图里），不做特征圆角 |

判断依据：侧剖面定形时（宽度方向无信息），侧剖面画 Right Plane 向宽度拉伸；
俯视（平面图）信息更多时反过来（expert-thinking.md R2）。拿不准剖面形状 →
先问用户，不许按“看起来像直角 L”建。

## 参数表

| 参数 | 含义 | 示例 |
|---|---|---|
| `B, H, W` | 底板长、立板高、宽度 | 80 / 60 / 50 |
| `T` | 底板厚 = 立板厚 | 10 |
| `base_holes` | 底板孔 `(x, z, d)` | 4×φ9 |
| `wall_holes` | 立板孔 `(z, y, d)` | 2×φ11 |
| `rib` | `(thickness, height)` 可选 | 8 / 30 |

## 固定步骤

1. **侧剖面**：在 Right Plane 画 L 形闭合轮廓（底板 + 立板）。
2. **拉伸宽度**：沿 −X 拉伸 `W`，得到整个支架。
3. **底板孔**：从 Top Plane 沿 Y 贯穿。
4. **立板孔**：从 Right Plane 沿 X 贯穿。
5. **筋**（可选）：闭合三角形草图 + 拉伸，不要用 `rib()`（本机返回 None）。
6. **圆角/倒角**：最后。

## 坐标映射（Right Plane 侧剖面）

Right Plane 草图 `(u,v) → (X=0, Z=−u, Y=v)`，所以：

- 底板沿 **Z** 方向：`u = −Z`，从 `u=0` 到 `u=−B`。
- 立板沿 **Y** 方向：`v = Y`，从 `v=0` 到 `v=H`。
- 拉伸沿 **−X**：材料在 `X∈[−W, 0]`。

L 形轮廓点（逆时针）：

```text
(0,0) → (−B,0) → (−B,T) → (−T,T) → (−T,H) → (0,H) → 回到 (0,0)
```

## 代码骨架

```python
import sys
sys.path.insert(0, r"<skill>\scripts")
from sw_connect import mm
from sw_part import sketch, sketch_line, auto_dimension_sketch, extrude_boss
from sw_hole_features import create_through_hole
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements

B, H, W, T = 80.0, 60.0, 50.0, 10.0
BASE_HOLES = [(-20, 15, 9), (-20, 65, 9), (-30, 15, 9), (-30, 65, 9)]  # (x, z, d)
WALL_HOLES = [(T / 2, 40, 11), (T / 2, 20, 11)]                         # (z, y, d)

session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
try:
    # 1) Right Plane 画 L 形侧剖面
    with sketch(part, "Right Plane") as sk:
        pts = [(0, 0), (-B, 0), (-B, T), (-T, T), (-T, H), (0, H), (0, 0)]
        for (u1, v1), (u2, v2) in zip(pts, pts[1:]):
            sketch_line(part, mm(u1), mm(v1), mm(u2), mm(v2))
        auto_dimension_sketch(part)
    # 2) 沿 −X 拉伸宽度 W
    extrude_boss(part, sk, mm(W), direction=True)

    # 3) 底板孔：Top Plane 二维 (u,v) = (X, -Z)
    for i, (x, z, d) in enumerate(BASE_HOLES, 1):
        create_through_hole(part, (mm(x), mm(-z)), mm(d),
                            plane_name="Top Plane", name=f"底板孔{i}")

    # 4) 立板孔：Right Plane 二维 (u,v) = (-Z, Y)
    for i, (z, y, d) in enumerate(WALL_HOLES, 1):
        create_through_hole(part, (mm(-z), mm(y)), mm(d),
                            plane_name="Right Plane", name=f"立板孔{i}")

    part.ForceRebuild3(False)
    m = collect_geometry_measurements(part)
    print("envelope_mm:", m["envelope_mm"], "holes:", m["hole_count"])
    session.save(part, r"<workdir>\bracket.SLDPRT")
finally:
    session.close(part)
```

## 筋（可选）

`sw_part.rib()` 在实测**仍返回 None**（参数已修正为 10 参，第 1 参是 `Is2Sided`），
不要依赖它。建筋改用**闭合三角形草图拉伸**：

```python
# 筋 = 底板顶面、立板内侧面、斜边围成的闭合三角形，沿 −X 拉伸 8 mm（筋厚）
with sketch(part, "Right Plane") as sk:
    sketch_line(part, mm(-40), mm(T), mm(-T), mm(40))
    sketch_line(part, mm(-T), mm(40), mm(-T), mm(T))
    sketch_line(part, mm(-T), mm(T), mm(-40), mm(T))
from sw_part import extrude_boss
rib_feature = extrude_boss(part, sk, mm(8), direction=True, name="Rib1")
```

拉伸方向以回读包围盒为准；一次只加一条筋，确认体积增加后再阵列/镜像。

**筋与镜像的顺序判断**：对称件（双侧筋）→ 筋建在镜像**之前**，镜像一次得到双侧筋
（expert-thinking.md R10；题库证据 `Extrusion → Boss → Cut → Cut → Rib → Mirror`）。
单侧筋 → 无镜像，直接建。筋是否随镜像，取决于图纸筋在对称面两侧是否成对出现——
看不清就问用户。

## 验证清单

| 项 | 通过标准 |
|---|---|
| 包围盒 | 长 = `W`，高 = `H`，宽 = `B`；误差 ≤ 0.1 mm |
| 实体 | 1 个实体；底板与立板无薄壁相交 |
| 孔 | 底板孔沿 Y、立板孔沿 X；数量/孔径正确 |
| 图纸 | 出图含 B/H/W/T、孔距、孔径 |

## 常见错误

- 侧剖面画在 Front Plane → 拉伸方向变成 Z，孔系全部错位。
- L 形轮廓方向画反 → 立板在底板下方，包围盒对但形状反。
- 底板孔从 Right Plane 打 → 孔沿 X，打到立板上。
- 筋没合并 → 出现 2 个实体，出图多一条轮廓。
