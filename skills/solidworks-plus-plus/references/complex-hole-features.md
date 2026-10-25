# 复杂孔槽自动化

## 支持范围

`scripts/sw_hole_features.py` 使用草图和切除特征创建以下结构：

- 定深盲孔。
- 完全贯穿孔。
- 通孔 + 圆柱沉孔的两级复合孔。
- 通孔 + 指定包含角的锥形沉头孔。
- 两端为半圆的直槽，支持贯穿或定深。
- 按显式坐标创建的孔阵列。

该模块不调用 `HoleWizard5`。Hole Wizard 的长参数和版本差异没有完成官方签名与真实版本验证前，禁止凭记忆拼接参数。

## 单位与基准

- 所有输入长度使用米，建议由 `sw_connect.mm()` 转换。
- `center`、`start`、`end` 是目标草图平面的局部二维坐标。
- 默认基准面是 `Front Plane`，中文版由 `sw_part.start_sketch()` 自动兼容。
- 创建参数证据同时输出米和毫米字段，但毫米字段只用于报告，不回传 COM。

## 示例

```python
from sw_connect import mm
from sw_hole_features import (
    create_blind_hole,
    create_counterbore_hole,
    create_countersink_hole,
    create_semicircular_slot,
)

blind = create_blind_hole(model, (mm(20), mm(20)), mm(8), mm(10), name="H1_盲孔")
counterbore = create_counterbore_hole(
    model,
    (mm(50), mm(20)),
    hole_diameter=mm(6),
    counterbore_diameter=mm(12),
    counterbore_depth=mm(4),
    name="H2_沉孔",
)
countersink = create_countersink_hole(
    model,
    (mm(80), mm(20)),
    hole_diameter=mm(5),
    countersink_diameter=mm(10),
    included_angle_deg=90,
    name="H3_沉头",
)
slot = create_semicircular_slot(
    model,
    (mm(30), mm(50)),
    (mm(60), mm(50)),
    width=mm(10),
    depth=0,
    name="S1_半圆端槽",
)
```

> **方向规则（SW2023 实测）**：标准基准面上 `direction=True`（默认）沿 +法向切除
> （Front=+Z、Top=+Y、Right=+X），适合主体向正轴拉伸的零件（本页示例即此情况）。
> 如果主体用 `extrude_boss(..., direction=True)` 向负轴拉伸，
> 盲孔、沉孔、定深槽要传 `direction=False`。
> 注意 `extrude_cut` 与 `extrude_boss` 的 `direction` 语义相反：向 +Z 拉伸的
> 平板，凸台要 `direction=False`、切除要 `direction=True`；照抄拉伸的
> direction 去切除，方向必反。**通孔也不是方向无关**：从实体端面
> 贯穿时，方向反了会朝空侧切、`FeatureCut4` 返回 `None`；`extrude_cut()` 会
> `auto_flip` 反向重试，但看到重试日志应记下该面的实际方向。
> 沉孔的大孔在哪个面，就用哪个面的草图平面，再按材料侧定 `direction`。
> **从材料外端的偏置面下刀要用 `direction=False`**：偏置面贴在材料外端时，
> 朝 +法向切就是朝空处切（2026-10-24 实测：Front 偏置面 Z=+10、材料 Z=0..10，
> `direction=True` 返回 `None`、`False` 生成特征），不是方向在偏置面上整体反转；
> `extrude_cut()` 盲切默认 `auto_flip=True`，切空时会自动反向重试并打印提示。

## 验收证据

创建函数返回的是参数证据，不是几何验收结论。交付前必须继续执行：

1. `sw_review.collect_geometry_measurements()` 读取 B-Rep 圆柱面。
2. `sw_review.validate_hole_positions()` 验证孔径和孔轴线位置。
3. 对盲孔深度、沉孔深度和沉头角度回读特征参数，或用剖视图人工复核。
4. 半圆槽端部圆柱面必须进入 `slot_arc_candidates`，不能被计入圆孔数量。
5. 复合孔应在 `compound_holes` 中出现同轴多直径孔段。

推荐每个孔至少记录：孔型、规格、数量、基准边定位、中心距、深度/贯穿状态、尺寸公差和证据来源。

### 已实测：先打穿，再单独做沉孔（2026-10-24）

法兰试件：`OD120 / ID40 / T12 / 轮毂 φ60×20 / PCD90 / 6×φ9 / 沉孔 φ15×6`。

```python
# 第 1 遍：从右端面把螺栓孔打穿
create_through_hole(part, center, mm(9), plane_name="Right Plane")

# 第 2 遍：在法兰端面 x=T 的偏置面上只切沉孔
insert_offset_plane(part, "Right Plane", mm(12), "Plane_CboreFace")
create_counterbore_hole(part, center, mm(9), mm(15), mm(6),
                        plane_name="Plane_CboreFace",
                        direction=False, through=False)
```

验收结果：

- 6 个沉孔全部创建，没有 `None`。
- `compound_holes` 6 组，每组 `[9, 15]` 两段，φ15 段在 `x=6..12`（法兰厚 12，沉孔深 6）。
- `hole_count=13`：6 个 φ9 + 1 个 φ40 + 6 个 φ15；这是圆柱面数，不是孔数。

**结论**：`through=False` 路径可用；沉孔必须从**实际有材料的端面**下刀，
本例 PCD 90 > 轮毂外径 60，所以从法兰端面 `x=12` 下刀，不能从轮毂端面 `x=32`。
`direction=False` 在 Right 偏置面上仍然需要，`auto_flip` 会兜底。

## 已知限制

- 锥形沉头使用通孔入口圆边的角度/距离倒角。入口边按圆心、半径和基准面位置筛选，不依赖临时边线名称；倒角后仍必须查看剖视图确认入口方向。
- B-Rep 单独不能可靠区分盲孔和通孔；必须与创建参数或特征定义回读交叉验证。
- 当前孔阵列按显式孔位逐个建特征，优先保证可审计性；大量规则阵列后续可增加 Linear/Circular Pattern 封装。
