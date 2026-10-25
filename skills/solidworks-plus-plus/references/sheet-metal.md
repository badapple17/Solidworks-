# 钣金：基体法兰、切除与展开（SW2023 SP0.1 实测）

能力等级见 `capabilities.yaml` 的 `sheet_metal`（pilot）。本文只写**本机验证过**的
调用；未验证的路线明确标注，不要照抄去猜参数。

## 能做什么、不能做什么

| 需求 | 本机结论 |
|---|---|
| 平板类钣金件（基体法兰） | ✅ `InsertSheetMetalBaseFlange` 可用 |
| 带侧壁/折弯的盖板 | ✅ **用开放轮廓 + 基体法兰一次成形**（考试 Q2 实测） |
| 平板型式（FlatPattern） | ✅ 基体法兰**自动生成**，不需要额外 API |
| 边线法兰 `InsertSheetMetalEdgeFlange2` | ❌ 实测返回 `None`，包围盒不变；不要依赖 |
| `CreateDefinition(38)` + `CreateFeature` | ❌ `CreateDefinition` 返回 `False`，`CreateFeature` 报“类型不匹配” |
| 展开图（工程图平板型式视图） | ⚠️ 未实测；需要时用 `IDrawingDoc.CreateFlatPatternViewFromModelView3` 自行验证 |

## 基体法兰：唯一可靠的主特征

```python
from sw_connect import mm
import sw_part as P
from sw_sheetmetal import audit_sheet_metal, insert_base_flange

# 1) 画轮廓：闭合=平板；开放=带折弯的截面（推荐做盖板）
P.start_sketch(model, "Front Plane")
model.SketchManager.AddToDB = True
for (x1, y1), (x2, y2) in zip(profile, profile[1:]):
    P.sketch_line(model, mm(x1), mm(y1), mm(x2), mm(y2))
model.SketchManager.AddToDB = False
sketch_name = P.current_sketch_name(model)
P.end_sketch(model)

# 2) 封装会先 ClearSelection2 + 选草图，再调 16 参数方法
base = insert_base_flange(model, sketch_name, mm(0.5), mm(0.5), mm(120.0))
if base is None:
    raise RuntimeError("基体法兰失败：先查草图是否被选中、轮廓是否自交")

assert audit_sheet_metal(model)["ok"]     # SheetMetal + SMBaseFlange + FlatPattern
```

封装的内部调用（需要自己扩参时照抄）：

```python
model.FeatureManager.InsertSheetMetalBaseFlange(
    thickness,    # Thickness        板厚（米）
    True,         # ThickenDir       加厚方向
    radius,       # Radius           全局折弯半径（米）
    extrude_dist, # ExtrudeDist1     开放轮廓=板长；闭合轮廓传 0
    0.0,          # ExtrudeDist2
    False,        # FlipExtruDir
    0, 0, 0,      # EndCondition1 / EndCondition2 / DirToUse
    nul,          # PCBA             CustomBendAllowance，传空 Variant
    True,         # UseDefaultRelief
    0, 0.0, 0.0, 0.0,  # ReliefType / Width / Depth / Ratio
    False,        # UseReliefRatio
)
```

签名与参数顺序来自本机 `IFeatureManager~InsertSheetMetalBaseFlange` 帮助页；
两种用法均已实测：

- **闭合轮廓**（100×50 矩形，`ExtrudeDist1=0`）→ 平板，包围盒
  `[-50, -25, -0.5, 50, 25, 0]` mm，板厚方向向下。
- **开放轮廓**（`(-28,7)…(26,18)` 的折线，`ExtrudeDist1=120`）→ 底板 + 侧壁一次成形，
  这是盖板类零件的正确做法。

## 平板型式是自动的

干净变量实测：只调 `InsertSheetMetalBaseFlange`（闭合轮廓），特征树随即出现
`钣金N (SheetMetal)` → `基体-法兰1 (SMBaseFlange)` → `平板型式N (FlatPattern)`。

所以：

- **不要**再调 `CreateDefinition(38)`：本机返回 `False`，接着 `CreateFeature` 会抛
  `类型不匹配`。`swFmFlatPattern=38` 这个枚举存在，但 `CreateDefinition` 的帮助页
  明确没把它列进支持的类型。
- 交付前审计特征树，确认三类特征都在：

```python
from sw_sheetmetal import assert_sheet_metal, audit_sheet_metal

print(audit_sheet_metal(model))   # has_sheet_metal / has_base_flange / has_flat_pattern
assert_sheet_metal(model)         # 缺任何一类抛 RuntimeError
```

## 切除要在法兰之后

切除用普通 `extrude_cut`，注意草图平面与材料所在侧：

```python
P.start_sketch(model, "Top Plane")      # Top: (u, v) → 世界 (X=u, Z=−v)
...
P.extrude_cut(model, sketch_name, 0, direction=True, name="02_PANEL_CUTS")
```

- 切完必须 `ForceRebuild3(False)` 再读包围盒/体积。
- 圆弧孔优先用**真圆弧**；多段折线近似可能切出零体积碎片实体、把实体数抬高
  （见 `pitfalls.md`）。若只能折线，切完核对实体数与总体积。

## 验收清单

1. 特征树含 `SheetMetal`、`SMBaseFlange`、`FlatPattern`。
2. 包围盒与板厚/板长/壁高一致（误差 ≤ 0.1 mm）。
3. 体积与手算一致：平板 ≈ 长×宽×厚；带壁按各段展开长度×宽度×厚累加，
   折弯区按中性层近似，差 > 2% 先查板厚与折弯半径。
4. 预览图目视：折弯圆角方向、切除是否穿透、壁是否在正确一侧。
5. 交付说明写明板厚、折弯半径、是否使用默认折弯系数（K 因子本技能未验证）。

## 失败分支

| 症状 | 一线修复 | 仍失败兜底 |
|---|---|---|
| 基体法兰返回 `None` | `ClearSelection2(True)` 后重新选草图再调 | 检查轮廓是否自交/重复线；改用最简单的矩形验证 |
| 壁在错误一侧 | 翻转 `ThickenDir` 或调整轮廓走向（开放轮廓的方向决定加厚侧） | 用闭合轮廓 + 单独切除重做 |
| 没有 `FlatPattern` | 确认主特征是 `SMBaseFlange` 而不是普通拉伸 | 删掉重建，不要在普通实体上找平板型式 |
| 边线法兰返回 `None` | 不要继续试参数 | 改用开放轮廓基体法兰一次成形侧壁 |
