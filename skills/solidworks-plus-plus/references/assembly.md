# 装配体与运动配合参考

## 相关 API

`IAssemblyDoc.AddMate5`、`IComponent2.GetModelDoc2`、`IComponent2.GetCorresponding`、`ISurface.IsCylinder` / `CylinderParams`；Gear Mate、Hinge Mate、Mate Controller。

## 添加组件

优先复用 `scripts/sw_assembly.py` 的 `add_component()`。中文版 + pywin32 下，
`AddComponent4()` 可能无异常但返回 `None`；当前封装会优先走 `AddComponent5()` 的
8 参数签名，失败后再回退 `AddComponent4()`。若两者都返回空，封装会自动把零件
静默打开到 SolidWorks 会话、重新激活装配体，再重试 `AddComponent5()`。

```python
from sw_assembly import add_component

component = add_component(asm_model, r"<workdir>\parts\base.SLDPRT", x=0, y=0, z=0)
```

底层稳定调用：

```python
component = asm_model.AddComponent5(
    CompPath, 0, "", False, ConfigName, X, Y, Z
)
```

`AddComponent4` / `AddComponent5` 失败时，先检查零件文件是否真实存在、装配体是否为活动文档、零件是否已保存到磁盘；必要时先打开零件再切回装配体。真实回归验证：

```powershell
py -3.12 tests\solidworks_add_component_regression.py --output-dir <workdir>\solidworks_add_component_regression
```

## 运动型装配工作流

1. 先生成并保存每个零件，尽量关闭不再编辑的零件文档，避免 SolidWorks 打开的文档过多。
2. 新建装配体，添加底座、轴承座、轴、齿轮、上盖等组件。
3. 对所有需要读特征或面的组件先调用 `resolve_component(component)`；轻化/压缩组件会让 `GetModelDoc2()` 返回 `None`。
4. 用 `IComponent2.GetCorresponding()` 将零件内部基准面、圆柱面或草图实体映射到装配体上下文，再用 `Select2()` 选择。
5. 固定件可以用三基准面重合或距离 Mate 锁死；旋转件不要用三基准面完全锁死。
6. 轴/孔用同心 Mate，`lock_rotation=False`，保留绕轴旋转自由度。
7. 齿轮联动用 Gear Mate；选择齿轮轴线、孔圆柱面、圆柱面或轴实体，按齿数传入比例。
8. 上盖铰链可用同心 Mate 加一个平面重合/距离 Mate 表达一条旋转自由度；若需要 Motion 分析，优先在 GUI 中用官方 Hinge Mate 或用更高阶 MateFeatureData API 生成。
   **销类零件例外**：销已和两侧孔同心时再加轴向重合会被拒（error_status=5），销只加同心（见「冗余配合」）。
9. 创建后遍历 MateGroup 子特征，确认真实 Mate 写入特征树；预览动画只说明脚本能驱动，不等同于可在软件里拖动。
10. 最后运行 `sw_review.py` 导出多视角预览图，并在 SolidWorks 中手动拖动一个自由件验证运动。

多姿态可动装配体（展开/收拢等）的已验证脚本顺序（2026-10-25，SW2023 SP0.1，8 零件折叠支架）：

1. 每个组件按**设计位姿**放置：`add_component` 的 x/y/z = 期望原点 + 零件局部包围盒中心。
2. 永久配合：同心一律 `align=SW_MATE_ALIGN_CLOSEST`；面对面贴合 `SW_MATE_ALIGN_ANTI`。
   **每加一个配合读一次 `get_component_pose()`**，旋转对角出现负值立刻停。
3. 摆姿态：每个转动件一个临时角度配合 → 读位姿/包围盒 → `delete_mates()` → `ForceRebuild3` 后再读一次。
4. `collect_mate_feature_summary()` 确认只剩永久配合；`assert save_document(...)`。
5. `get_interference_detection(asm)`：0 处才算过；干涉项给出两个组件名和体积，按体积反推是哪块几何。
6. 关装配体后逐个 `CloseDoc` 被引用的零件——否则下次重建零件时 SaveAs 报错码 1。

## 工程经验摘要

- Gear Mate 只强制两个组件绕所选轴按比例相对转动；Hinge Mate 的效果等价于同心配合加重合配合，并可限制角度。
- Mate 是零部件之间的几何约束；机械配合用于齿轮、齿条、螺旋、万向节等运动关系，不等同于接触仿真。
- `GetModelDoc2()` 对轻化/压缩组件会返回空，可通过解析或静默打开引用模型兜底。
- part context 与 assembly context 不能混用；能拿对象引用时优先用 `GetCorresponding()` + `Select2()`，少依赖坐标点击。
- 轻化组件导致 `GetModelDoc2()` 返回空是高频坑；做 Mate 前先解析组件，不要把 `None` 当作“零件没有特征”。

## AddMate5 参数

SolidWorks 2015+ 的 `AddMate5` 是 15 参数签名，Python COM 下 by-ref 错误码必须用 `VARIANT` 包装：

```python
errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
mate = asm_model.AddMate5(
    mate_type,          # swMateType_e
    align,              # swMateAlign_e，常用 0=Aligned
    flip,               # bool
    distance,           # 距离配合值，单位米
    distance_upper,     # 距离上限；无限制时等于 distance
    distance_lower,     # 距离下限；无限制时等于 distance
    gear_num,           # Gear Mate 分子
    gear_den,           # Gear Mate 分母
    angle,              # 角度，单位弧度
    angle_upper,        # 角度上限
    angle_lower,        # 角度下限
    for_positioning_only,
    lock_rotation,      # 同心配合是否锁定旋转
    width_mate_option,  # Width Mate 选项
    errors,
)
```

优先复用 `scripts/sw_assembly.py`：

```python
from sw_assembly import (
    add_concentric_mate_by_cylinders,
    add_gear_mate_by_cylinders,
    collect_mate_feature_summary,
)

add_concentric_mate_by_cylinders(
    asm,
    shaft_comp,
    bearing_comp,
    radius_a=(0.004, 0.006),
    radius_b=(0.004, 0.006),
    name="shaft_bearing_concentric",
    lock_rotation=False,
)

add_gear_mate_by_cylinders(
    asm,
    small_gear_comp,
    large_gear_comp,
    teeth_a=18,
    teeth_b=26,
    radius_a=(0.004, 0.008),
    radius_b=(0.004, 0.008),
    name="small_large_gear_ratio_18_26",
)

print(collect_mate_feature_summary(asm))
```

## 配合类型枚举

实测于 SW 2024 `SolidWorks.Interop.swconst.dll` 验证过的常用值：

| 值 | 名称 | 说明 |
|---:|---|---|
| 0 | `swMateCOINCIDENT` | 重合 |
| 1 | `swMateCONCENTRIC` | 同心 |
| 2 | `swMatePERPENDICULAR` | 垂直 |
| 3 | `swMatePARALLEL` | 平行 |
| 4 | `swMateTANGENT` | 相切 |
| 5 | `swMateDISTANCE` | 距离 |
| 6 | `swMateANGLE` | 角度 |
| 10 | `swMateGEAR` | 齿轮 |
| 11 | `swMateWIDTH` | 宽度 |
| 16 | `swMateLOCK` | 锁定 |
| 22 | `swMateHINGE` | 铰链 |

SW2023 SP0.1 同样验证了 0/1/3/5/6/10/22；`SW_MATE_ANGLE = 6` 已在 `sw_assembly.py` 导出。

## 对齐方式 swMateAlign_e（2026-10-25 SW2023 实测）

| 值 | 常量 | 同心（轴入孔） | 两平面贴合 |
|---:|---|---|---|
| 0 | `SW_MATE_ALIGN_ALIGNED` | **可能翻 180°** | 法向同向，会把件翻到背面 |
| 1 | `SW_MATE_ALIGN_ANTI` | **可能翻 180°** | **面对面贴合用它** |
| 2 | `SW_MATE_ALIGN_CLOSEST` | **保持原位：同心一律用它** | 定位用的平面重合**不要**用（实测把托钩甩到 ±59，另一侧） |

证据（干净位姿，每次只变一个 align）：

- 折叠支架：align=0 把转盘绕横轴翻 180°（z 7.4→15.8，对角 (−0.924, 0.924, −1)）；align=1 把销翻
  180°（对角 (−1, 0.382, −0.382)，x 偏 −18.5）；align=2 全部组件对角 (1,1,1)、平移不变。
- 回归件（方块+销）：align=0 保持、align=1 翻（z −3→37，对角 (−0.924, 0.924, −1)）、align=2 保持。

**0/1 翻不翻取决于两个圆柱面各自的轴向**（由建模方式决定，事先看不出来），两个案例里
哪一档翻转并不一致；只有 CLOSEST 两次都保持。`add_concentric_mate_by_cylinders` 默认已改为 CLOSEST。

识别翻转：翻转多半**不在当前配合报错**，而是让下一个配合失败（平面重合/角度配合 error_status=5）。
所以每加一个配合就读 `get_component_pose()`；旋转对角出现负值、或平移突然跳动，就是翻了。
验证枚举语义要在**干净位姿**下一次只测一个值；在已经被翻乱的装配体里换参数重试，
得到的结论会自相矛盾（本次曾因此写下“同心用 0”的错误注释，探针推翻后才改正）。

回归：`py -3.12 tests\solidworks_assembly_align_regression.py`（对齐 + 角度摆姿态 + 干涉检出）。

## 冗余配合：error_status=5

`AddMate5` 的 `error_status=5` = 配合被拒（与已有约束冲突或冗余）。实测触发：

1. 销已与两侧孔同心，再加“销头内侧面 ↔ 耳板外侧面”重合 → 5。销只留同心，轴向靠初始放置。
2. 零件已被上一个配合翻转后，再加平面重合/角度配合 → 5（根因是翻转，不是这个配合）。
3. 转角已被其他配合锁死再加角度：手机背面贴背板、底面贴右托钩胶垫后，右托钩转角已定，
   再给它加角度配合 → 5。只给仍然自由的那个件（左托钩）加。

遇到 5 先问：这个自由度是否已被别的配合占用？零件是否已经翻了？不要换 align 盲试。

## 摆姿态：临时角度配合 → 删除

SW2023 SP0.1 上 `SetTransformAndSolve2` / 改 `Transform2` 只能平移，**加不上旋转**
（`apply_component_transform_x` 只适合平移和演示帧）。已验证路线：

```python
from sw_assembly import SW_MATE_ANGLE, add_mate5_checked, delete_mates, select_entities_for_mate

select_entities_for_mate(asm, face_arm_back, face_turntable_top)
temp = add_mate5_checked(asm, SW_MATE_ANGLE, angle=math.radians(98.0), name="T_ARM")
# ... 其他转动件同理
delete_mates(asm, [temp, ...])
asm.ForceRebuild3(False)          # 重建后位姿保留，铰链恢复可拖动
```

**角度配合有镜像解**：它只约束夹角的绝对值，相对转角 ψ 与 −ψ（或 180°−ψ）给出同一夹角，
求解器取离当前位姿近的一个。目标正好落在两个解的中间时，结果不可控：

- 两参考面初始垂直（90°），目标相对转角 0 → 目标夹角 90°，ψ=0 与 ψ=180° 都满足。
  实测收拢位背板被折回压在臂上，干涉 11 处。
- 改用两个**平行**参考面、目标夹角 0° → 唯一解，背板与臂共线，干涉 0。

选参考面的规则：目标是“共线/平行”就用平行面 + 0°；目标是“倾斜 α”就用初始垂直的面 + 90°±α
（α 离 0 远，镜像解在另一侧）。摆完读包围盒核对：共线时总长应变长，折回时不变或变短。

## 放置坐标与选面

- `add_component(asm, path, x, y, z)` 的 x/y/z 是**组件包围盒中心**落点，不是零件原点。
  零件局部包围盒不对称时（U 座外伸、托钩只向一侧伸），放置值 = 期望原点 + 局部包围盒中心，
  否则整条链偏移。
- 选面用坐标，不用面名/索引：`find_planar_face(comp, "z", 0.0074, sign=+1)`、
  `find_face_by_normal(comp, (0, 0.866, 0.5))`（斜面）、
  `find_cylinder_face_at(comp, r_min, r_max, "z", 0.092)`（同径的上下两个孔）。
  坐标都是**零件局部坐标**、单位米；零件改尺寸后同步改选面坐标。
- 外法向只能读 `IFace2.Normal`；`PlaneParams` 的法向是平面的任意朝向（上下两面都可能是 +Z）。
- `CylinderParams` 的 root 是无限长轴线上的一点，可能在面外：只能比较与轴线**垂直**的坐标。
- `IAssemblyDoc` 没有 `GetMates`：列配合用 `collect_mate_feature_summary`。
- `IAssemblyDoc.GetBox(False, False)` 报“无效的参数数目”；装配体包围盒用各组件
  `Component2.GetBox(False, False)` 的并集。

组件压缩状态常用值：

| 值 | 名称 | 说明 |
|---:|---|---|
| 0 | `swComponentSuppressed` | 压缩 |
| 1 | `swComponentLightweight` | 轻化 |
| 2 | `swComponentFullyResolved` | 完全解析 |
| 3 | `swComponentResolved` | 解析 |
| 4 | `swComponentFullyLightweight` | 完全轻化 |

## 选择与装配体上下文

稳定顺序：

```python
from sw_assembly import (
    get_component_feature,
    get_assembly_entity,
    find_component_by_name,
    resolve_component,
    select_entities_for_mate,
)

component_a = find_component_by_name(asm, "shaft")
component_b = find_component_by_name(asm, "bearing")
resolve_component(component_a)
resolve_component(component_b)

feature_a = get_component_feature(component_a, ["前视基准面", "Front Plane"])
feature_b = get_component_feature(component_b, ["前视基准面", "Front Plane"])
entity_a = get_assembly_entity(component_a, feature_a)
entity_b = get_assembly_entity(component_b, feature_b)

select_entities_for_mate(asm, entity_a, entity_b, mark=1)
```

注意事项：

- 先解析组件，再选择实体；`SetSuppression2()` 可能清空选择集。
- 第一个实体用 `Select2(False, 1)`，第二个实体用 `Select2(True, 1)` 追加。
- 创建 Mate 前检查 `SelectionManager.GetSelectedObjectCount2(-1) == 2`。
- Gear Mate、普通 Mate 选择标记通常用 `1`；Width Mate 用 `16`，Cam-Follower 用 `8`。

## 圆柱面识别

轴、孔、齿轮轴线常通过最大圆柱面识别：

```python
from sw_assembly import find_largest_cylinder_face

face = find_largest_cylinder_face(
    gear_component,
    min_radius=0.004,
    max_radius=0.008,
)
```

底层逻辑：

```python
bodies = part.GetBodies2(0, False)
for body in bodies:
    for face in body.GetFaces():
        surface = face.GetSurface()
        if surface.IsCylinder:
            params = surface.CylinderParams
            radius = params[6]  # 单位米
```

## 可以在软件里操作吗

可以，但前提是装配体里有真实 Mate 且没有被过约束：

- 在 SolidWorks 打开 `.SLDASM`。
- 使用 `移动零部件` / `Move Component` 拖动轴、齿轮或上盖。
- 如果 Gear Mate 正确，拖动一个齿轮绕轴旋转时，另一个齿轮会按比例反向/同向联动。
- 如果拖不动，优先检查：零件是否固定、同心 Mate 是否勾了 Lock Rotation、是否额外用平面 Mate 把旋转件锁死、Mate 是否报错或过定义。

脚本生成的 GIF/预览视频只能证明“可以被驱动到多个位置”；真正可交互要靠 SolidWorks Mate 求解器和自由度。

## 干涉与运动边界

Gear Mate 不负责防止齿轮实体穿透；它只建立旋转比例关系。需要几何安全时：

- 用 `get_interference_detection(asm)` 或 GUI 中的干涉检查验证。
- 用 Limit Angle / Limit Distance 限制行程。
- 用 Mate Controller 保存几个关键位置并生成 Motion Study 动画。

```python
from sw_assembly import get_interference_detection

report = get_interference_detection(asm)
# {'status': 'pass'|'warn'|'blocked', 'interference_count': n,
#  'items': [{'components': ['06_plate-1', '07_hook-1'], 'volume_mm3': 62.69}, ...]}
```

底层（SW2023 SP0.1 实测）：入口是 `asm.InterferenceDetectionManager`；**先读
`GetInterferenceCount` / `GetInterferences` 再 `Done()`**，Done 会释放结果。
`asm.InterferenceDetection` 在本机不存在（AttributeError），旧版封装用它，因此永远返回
`blocked`——`blocked` 不是“没有干涉”。回归测试会故意放一个插进实体的销，要求检出 1 处、
体积 π·3²·10 = 282.74 mm³（实测 282.743）。

## 大型装配体建议

- 超过 20 个零件时，分批生成零件，保存后关闭文档，再统一装配。
- 添加组件前确认所有路径存在，失败组件要记录清单。
- 自动化脚本中关闭不必要的图形刷新；最终恢复、重建、导出预览。
- 文档太多或 COM 报内部错误时，先 `CloseAllDocuments(False)`；仍不稳定再重启 SolidWorks 主进程。

## 装配配合知识与判据（教材沉淀）

来源：《SOLIDWORKS 零件与装配体教程（2024版）》P293–359 提炼（训练区
`digests/parts_assembly_p241_300.md`、`p301_361.md`）。教材数值只作示例。

### 装配起步：第一件固定于原点

1. 第一个零部件放在原点：零部件原点与装配体原点重合、基准面对齐 → 完全定位，
   装配体不会整体漂移。教材称“产品空间/汽车空间”：先立框架，再装零件（P293–294）。
2. 后续零部件以**欠定义**加入（6 个自由度），用配合逐个限制。
3. 状态符号：`(固定)`；`(-)` 欠定义仍可动；无符号=完全定义；`(+)` 过定义；
   `?` 无解（P294）。
4. 配合在 Mates 文件夹中**按列表顺序求解**，顺序会影响结果；不要随意重排（P295）。
5. 验证约束程度：拖动零件。固定的或完全定义的拖不动；能转说明还剩旋转自由度（P304、P309）。
6. **单位**：距离/角度栏可直接输入其他单位（如 1/32 in = 0.79375 mm，P319）；
   装配体单位可与零件不同，在装配体内编辑零件尺寸时按装配体单位显示（P294–296）。
   API 的 `add_mate5_checked` 距离/角度恒按米/弧度传值，换算由调用方完成。

### 配合选型表

| 几何关系 | 配合 | 注意 |
|---|---|---|
| 两平面实际贴合 | 重合 | 最常用 |
| 两平面有设计间隙 | **平行**（不标值）或**距离**（标值） | **禁用重合**，否则无解/过定义（P308、P319） |
| 轴入孔 | 同轴心 + 一个平面重合/距离 | 配合列表应恰好 2 项；防转加锁定旋转或角度配合（P302–303、P310） |
| 零件关于槽/箱体对称居中 | **宽度配合**：2 个宽度面 + 2 个薄片面，约束选中心 | 高级配合；楔形槽=宽度+重合（P304–306、P323） |
| 用基准面居中两件 | 各自参考基准面做重合 | 简单可靠（P322） |
| 距离配合位置反了 | 反转配合对齐 / 反转尺寸 | 距离配合通常多解（P319） |
| 只要视图定位、不要约束 | 勾“只用于定位” | 不进入运动链（P320） |

**轴-孔标准配合对 = 同轴心 + 平面配合**；“栓和孔”智能配合就是这两个配合的
一次拖放（P316–317）。自动化里组合
`add_concentric_mate_by_cylinders` + `add_mate_coincident` 即可，不需要智能配合 UI。

**宽度配合的 API 现状**：`add_mate5_checked` 已暴露 `width_mate_option` 参数（底层
`AddMate5` 第 14 位），但**没有**“找两对平行面并正确标记选择”的辅助函数；
Width Mate 的选择标记用 `16`。没有把握时标为“需人工”，不要猜面。

### 隐藏、压缩、透明度的语义（不可混用）

| 操作 | 是否驻留内存 | 是否参与配合 | 是否参与质量/干涉 |
|---|---|---|---|
| 隐藏 | 是 | 是 | **是**（除非干涉检查勾“忽略隐藏”） |
| 压缩 | 否 | 否 | 否 |
| 透明度 75% | 是 | 是 | 是 |

“隐藏即排除”是错误直觉；质量属性或干涉结果与预期不符时先查隐藏件（P313–315、P331）。
压缩/解除压缩已封装：`suppress_component` / `unsuppress_component`；
**组件级隐藏（`Component2.Visible`）与透明度未封装**，需要时用 UI 或标“新增封装”。

### 子装配体：一个零部件，刚/柔可控

子装配体连同内部零部件与配合作为一个整体处理，可被配合、可整体移动；〖求解为〗
刚性/柔性决定内部零部件能否在父装配体中独立运动（P314–315）。`Component2.Solving`
未封装；插入子装配体仍用 `add_component`。

### 干涉检查：静态与动态是两件事

**静态干涉**（`get_interference_detection` 已封装）：

1. 选零部件 → 计算 → 结果成对列出并给干涉体积。
2. 选项：视重合为干涉、视子装配体为零部件、包括多体零件、忽略隐藏实体/零部件、
   生成扣件文件夹、匹配装饰螺纹线（P331）。**封装固定设置前两项为 False，
   `include_multibody` 控制“包括多体零件”**；其余 3 项无法通过 `get_interference_detection`
   控制，需要时直接操作 `InterferenceDetectionManager` COM 对象或标“需人工”。
   重合面（手机底面贴托钩胶垫）在“视重合为干涉=False”下不计入，实测确认。
3. 结果可忽略、忽略所有小于此值的干涉、孤立、按大小排序（P332）。
4. **修复三手段**：① 改零件尺寸重建（`update_dimension_mm`）；② 配合方向错 →
   反转尺寸；③ 结构干涉 → 加倒角/切除（`chamfer` / `extrude_cut`）（P332、P354）。
5. 修复后必须重跑检查；被“忽略”的项不会自动恢复。
6. **零件自校验发现不了坐标系错误**：零件的体积/包围盒/实体数门禁只证明“按我写的数建出来了”，
   不证明“数是在对的坐标系里算的”。实测：托钩原点在卷边轴心（背板局部 Y=4.5），却把背板坐标里的
   手机屏面 Y=−4.42 直接当成托钩坐标画挡边，零件体积误差 0.000%，装配后挡边切进手机 150.5 mm³。
   规则：一个零件的特征要对齐另一个零件时，先写出两个原点之间的偏移，再换算；
   装配完成**必须**跑干涉，按“组件对 + 体积”反推是哪块几何（体积 ≈ 长×宽×高 可直接对上尺寸）。
7. 位姿检查与干涉检查互补：位姿全对（对角 1,1,1、平移对）时仍可能有干涉（零件本身几何错）；
   干涉为 0 时姿态也可能错（折到了另一个解上但恰好不碰）。两项都要做。

**动态检查**（未封装）：运动过程中的碰撞用〖碰撞检查〗（碰撞时停止/高亮/声音），
最小间距用〖动态间隙〗；**静态干涉检查不覆盖运动过程**（P333–334）。
大装配性能：选“这些零部件之间”、勾“仅被拖动的零件”、勾“忽略复杂曲面”。

### 装配体上下文修改与文件引用

- 装配体中双击零件改尺寸 → 所有引用该零件文件的装配体/工程图同步更新；
  同一文件不是副本（P335–336）。改前确认该零件是否被多项目复用。
- **文件名必须唯一**；同名不同件按内部 ID 判定。打开冲突时：
  〖无此文档而打开〗=压缩同名实例；〖接受此文件〗=复用已打开件，可能引发重建/配合问题（P329）。
  自动化批量打开前先按路径做唯一性检查。
- 同一零件多配置可在装配体中各用一份：插入时选配置（`add_component(config_name=...)`），
  或事后改 `Component2.ReferencedConfiguration`（未封装）（P309–315）。
- **同一零件多配置互配时，优先用零件的中心轴（临时轴）做配合对象**：配置切换后
  所选面可能失效，中心轴不会（P326）。
- 退回控制棒可退回装配基准面/草图/装配体特征/阵列/关联零件特征，**单独零部件
  不能退回**；实例删除后不重新编号，最大实例号≠实例总数（P294–296）。

### 爆炸视图、BOM 与工程图（只列可执行判据）

- 爆炸视图**随配置保存**：先建专用配置（如 Exploded），再把每步爆炸存入该配置（P336）。
- 圆周爆炸用〖径向步骤〗；〖选择子装配体零件〗控制子装配体整体或散件爆炸；
  〖自动调整零部件间距〗沿单轴分布并按边界框中心/后部/前部排序；操纵杆右键可
  〖与零部件原点对齐〗/〖与装配体原点对齐〗（P339–342）。
- 爆炸前解除压缩用于定位的配合（如角度配合），否则零件位置被锁（P336）。
- 步骤可回滚/重排；操纵杆方向不对时重定位到边/轴/面（P340–341）。
- 爆炸直线：智能生成后大量重叠，必须清理；手动线的选择顺序决定连线顺序（P343–348）。
- BOM 顺序随设计树；`Description` 可由零件说明自动填；复制到工程图时勾〖链接〗，
  自动零件序号才会联动（P348–351）。
- **爆炸视图、爆炸直线、BOM〖链接〗勾选与自动零件序号联动、视图配置选择均未封装**；
  BOM 表插入本身已有 `insert_bom_table(config_name=...)`，不要整体标“人工”。
- 删除配合：`delete_mates(asm, [mate, ...])`（`Mate.Select2(False, 0)` + `EditDelete`，
  2026-10-25 实测删除后组件保持当前位姿）；读侧 `collect_mate_feature_summary`；
  添加侧 `add_mate5_checked` 及各配合封装。

### 选项与模板（P358–359）

自动化开始前的一次性配置，决定后面所有文档的默认行为：

1. **系统选项 vs 文档属性**：系统选项**不随文档保存、全局生效**（如尺寸输入增量）；
   文档属性**随文档保存**（单位、绘图标准、字体都在这里）。改“单位不对/字体不对”
   要去文档属性，改“每个新文档都要重新设”才去系统选项。
2. **模板文件**：默认模板建文件 → 改选项与文档属性 → 另存为 `*.prtdot`（零件）、
   `*.asmdot`（装配体）、`*.drwdot`（工程图），再在〖系统选项→默认模板〗指向它。
3. **模板能固定命名**：基准面重命名（如 XY/YZ/XZ）后随模板沿用；**零件/装配体
   基准面命名不一致，是脚本按 `"Front Plane"` 选面失败的高频根因**。交付他人
   使用的脚本必须同时兼容中英文名，或先读模板确认。
4. **GB 模板建议值**（教材示例）：绘图标准 GB、汉仪长仿宋体 3.5 mm、主精度 2 位小数、
   网格不显示、单位 MMGS。数值可按企业标准改，但 MMGS 与 GB 是国标交付的默认前提。
5. **API 边界**：系统选项可用 `UserPreference` API 设置但**未封装**；文档属性部分可读写；
   模板本身走**文件复制**（把 `*.prtdot/*.asmdot/*.drwdot` 拷到模板目录）而不是 COM 生成。
   要改默认模板路径时标“需人工”，不要臆造 API。

### 装配失败模式

| 现象 | 原因 | 一线修复 | 兜底 |
|---|---|---|---|
| 重合配合无解/过定义 | 两零件实际有间隙 | 改平行或距离配合 | 检查是否有隐藏件/配置尺寸不对 |
| 距离配合零件跑到反侧 | 多解 | 反转配合对齐/反转尺寸 | 删除重建并显式选面 |
| 零件拖不动 | 被固定 / 同心勾了锁定旋转 / 被三个基准面锁死 | 解固定、`lock_rotation=False`、删多余配合 | 只留同轴心+一个轴向定位 |
| 能转但不联动 | 配合链断开 | 补被删的配合（如同轴心+重合） | 检查子装配体是否为刚性 |
| 干涉结果与直觉不符 | 隐藏件仍参与 / 视重合为干涉 | 勾“忽略隐藏”、核对选项 | 用间隙验证复核 |
| 打开提示同名文档 | 文件名不唯一 | 保证唯一命名 | 选“无此文档打开”压缩实例 |
| 插入后尺寸不对 | 插错配置 | 零部件属性切配置 | 重新插入并指定 `config_name` |
| 加同心后零件翻 180°，下一个配合报 5 | align=0/1 按圆柱面轴向对齐 | 同心改 `SW_MATE_ALIGN_CLOSEST` | 干净位姿逐个探针 |
| 定位平面重合后零件跑到另一侧 | 用了 CLOSEST | 面对面贴合用 ANTI | 换参考面 |
| 加配合 error_status=5 | 冗余（自由度已被占）/ 零件已翻转 | 删掉冗余配合；先查位姿 | 见「冗余配合」 |
| 摆姿态后件折到错误一侧 | 角度配合镜像解（目标在两解中间） | 改平行参考面 + 0° | 摆完读包围盒核对 |
| 旋转写不进去 | SW2023 `SetTransformAndSolve2` 不应用旋转 | 临时角度配合 → 删除 | — |
| 零件门禁全过、装配有干涉 | 零件特征在错的坐标系里算 | 写出两原点偏移再换算 | 干涉体积反推几何 |
| 干涉检查 `blocked` | 用了不存在的 `InterferenceDetection` | 用 `InterferenceDetectionManager` | — |
| 重建零件后 SaveAs 错误码 1 | 装配体关了，引用零件还留在会话 | 关装配体后逐个 `CloseDoc` 零件 | `assert save_document(...)` |

### 给弱模型的执行边界

- 第一件固定在原点；其余一件一件加配合，每加一个检查状态符号。
- 贴合面用重合，有间隙用平行/距离；**不要用重合硬拉有间隙的面**。
- 轴入孔固定用“同轴心 + 平面重合”，需要转就 `lock_rotation=False`。
- 对称居中优先宽度配合；没有把握选面时标“需人工”，不要用两个距离配合凑。
- 静态干涉检查通过 ≠ 运动过程无碰撞；交付说明要写清做了哪一种检查（P333）。
- 同心 = CLOSEST，面对面贴合 = ANTI；每加一个配合读一次位姿，对角出现负值就停。
- 报 error 5 不要换 align 盲试：先查是不是冗余、是不是上一个配合已经把件翻了。
- 摆姿态只用“临时角度配合 → 删除”；目标为 0° 时选平行参考面。
- 装配完成必须跑 `get_interference_detection`，`blocked` 当作未检查，不当作通过。
