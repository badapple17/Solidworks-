# 外观与材质参考

## 核心规则

SolidWorks 的九位材质数组必须以 `SAFEARRAY(double)` 传给 COM。不要直接把 Python
`list` 赋给 `MaterialPropertyValues`；在 pywin32 动态分派下，普通列表可能被错误编组，
表现为 RGB 落入第 2、5、8 位，最终模型几乎只显示绿色。

稳定封装位于 `scripts/sw_appearance.py`：

- `material_variant()`：把九位数组封装为 `VT_ARRAY | VT_R8`。
- `set_document_appearance()`：写入并回读文档级 RGB。
- `set_feature_appearance()`：写入并回读特征级 RGB。
- `set_component_appearance()`：写入并回读装配组件级 RGB；可传 `transparency=`
  同时设透明度。
- `set_component_transparency()` / `get_component_transparency()`：只改/只读透明度。
- `apply_component_palette()`：批量上色，支持 `(组件, 颜色)` 或
  `(组件, 颜色, 透明度)` 三元组。
- `component_part_name()`：组件名去掉 `-N` 实例后缀，用于按零件名配色。
- `apply_component_style_map()`：按 `{零件名: 颜色/透明度}` 给整台装配上色，
  逐件回读，返回 unmatched/failed 清单（透明涂色版的首选入口）。
- `verify_appearance()` / `verify_transparency()`：比较预期值与 COM 回读值。

## 推荐用法

```python
from sw_appearance import (
    apply_component_palette,
    set_document_appearance,
    set_feature_appearance,
    verify_appearance,
)

set_document_appearance(model, "iron_red")
set_feature_appearance(feature, "armor_gold")
assert verify_appearance(model, "iron_red")["ok"]

reports = apply_component_palette([
    (body_component, "aqua_blue"),
    (glass_component, "glass_tint"),
    (rear_light_component, "signal_red"),
    (rim_component, "silver"),
])
assert all(item["ok"] for item in reports)
```

## 预设颜色

| 名称 | 说明 |
|---|---|
| `iron_red` | 深红装甲 |
| `armor_gold` | 金色装甲 |
| `dark_gunmetal` | 深色金属/关节 |
| `arc_blue` | 蓝色发光件 |
| `silver` | 银色金属 |
| `black` | 黑色 |
| `white` | 白色 |
| `aqua_blue` | 青蓝车身色 |
| `glass_tint` | 深色玻璃 |
| `signal_red` | 尾灯/警示红 |
| `light_cyan` | 浅蓝发光件 |
| `tire_black` | 轮胎黑 |
| `graphite` | 石墨灰 |

## 已验证 API 签名

本机 SolidWorks 2024 SP3.1 的 `SolidWorks.Interop.sldworks.dll` 反射结果：

```text
IModelDoc2.MaterialPropertyValues = Object
IModelDocExtension.SetMaterialPropertyValues(Object, Int32, Object) -> void
IFeature.SetMaterialPropertyValues(Object) -> bool
IFeature.SetMaterialPropertyValues2(Object, Int32, Object) -> void
IComponent2.SetMaterialPropertyValues2(Object, Int32, Object) -> void
IComponent2.GetMaterialPropertyValues2(Int32, Object) -> Object
```

配置选项：`swThisConfiguration=1`、`swAllConfiguration=2`、
`swSpecifyConfiguration=3`。返回 `void` 的 setter 只要没有 COM 异常即表示调用完成，
不能写成 `bool(method(...))` 判断成败；最终必须以 `verify_appearance()` 回读为准。

SW2023 SP0.1 实机复测（2026-10-25）：组件级颜色与透明度均通过
`SetMaterialPropertyValues2(mat, 2, [])` 写入成功，`MaterialPropertyValues`
回读 9 位一致；`2 + 空 BSTR 数组`可用，不必逐配置写。
`IComponent2.GetMaterialPropertyValues2` 在 pywin32 下不可用，改用属性
`MaterialPropertyValues`。

同一实测还确认：封装的默认写法 `SetMaterialPropertyValues2(mat, 1, None)`
（`swThisConfiguration` + 空名称）同样能写入并回读一致；两种配置参数都可用，
`tests/solidworks_appearance_regression.py` 已把透明度三元组、只改透明度、
`set_component_appearance(transparency=)` 三条路径纳入回归。

## 组件透明度：让装配后的内部关系可见（SW2023 实测）

用途：壳体（上盖/下盖/箱体）叠在外部，装配后看不见内部传动件。把**壳体**设成
半透明、内部零件保持实色，一张等轴测图就能同时表达装配关系与外观。

```python
from sw_appearance import apply_component_palette

reports = apply_component_palette([
    (lower_cover, "silver",  0.82),   # 壳体：玻璃感
    (upper_cover, "white",   0.82),
    (sleeve,      "arc_blue", 0.35),  # 半透明，能看到里面的轴和垫块
    (gear,        "signal_red", 0.0), # 实色
    (ring,        "armor_gold", 0.10),
], strict=True)
```

已验证的写入方式：

```python
values = [r, g, b, 0.30, 0.70, 0.60, 0.40, transparency, 0.0]
component.SetMaterialPropertyValues2(
    material_variant(values),
    2,                                            # swAllConfiguration
    VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, []),
)
back = component.MaterialPropertyValues            # 属性，不能加括号
```

规则：

- 透明度是 9 位数组的**第 8 位**（索引 7），不是独立 API。0=不透明，1=全透明。
- 壳体取 **0.75~0.85**；再高就只剩轮廓线。内部零件保持 0~0.1。
- **不要所有零件都设半透明**：透明件越多，边线越乱，反而看不清。
- 半透明件在“带边线着色”下会画出**全部**内部边线。边缘特别密的零件（内齿圈、
  多孔法兰）建议保持实色；否则整张图会变成线团。
- 写入后必须回读 `MaterialPropertyValues[7]`；setter 不抛异常不代表生效。
- 透明不等于隐藏：透明件仍参与配合、质量和干涉计算（见 `assembly.md`）。

## 多色装配工作流

1. 在源零件文档级设置基础颜色并保存。
2. 添加组件后按需设置组件级覆盖色。
3. 每次写入后回读前三位 RGB；不匹配立即停止。
4. 保存前调用 `assembly.ClearSelection2(True)`。
5. 预览前再次清除选择并重绘，避免绿色选择高亮覆盖真实外观。
6. 至少检查一张彩色等轴测图和一张能看到灯组/轮毂的正投影视图。

## 透明涂色版：复制 → 解析 → 按件配色 → 回读（2026-10-25 两次大装配实测）

交付“透明涂色装配”时，**原件绝不上色**。标准顺序：

```python
import shutil
from sw_appearance import apply_component_style_map
from sw_assembly import resolve_all_components
from sw_connect import open_document, save_document

shutil.copy2(src_asm, dst_asm)                 # 1. 先复制，原文件不动
asm = open_document(sw, str(dst_asm), raise_on_error=True)
resolve_all_components(asm)                    # 2. 压缩件先全部解析
asm.ForceRebuild3(False)

STYLE = {
    "11_body":            ("#C8CDD2", 0.80),   # 壳体：玻璃感
    "07_cover":           ("#D98CA8", 0.75),
    "08_drive_gear_shaft": ("#2E5FA8", 0.0),   # 轴类同色
    "06_gear_shaft":      ("#2E5FA8", 0.0),
    "16_pulley":          ("#3FA34D", 0.0),
    "17_key_5x5x18":      ("#F2C200", 0.0),
    "19_nut_M12":         ("#4A4F55", 0.0),
    # ... 每个零件都要有一条，包括螺栓/垫圈/挡圈
}
report = apply_component_style_map(asm, STYLE, strict=True)
print(report["applied"], report["unmatched"], report["failed"])
save_document(asm, str(dst_asm))
```

`apply_component_style_map()` 内部做四件事：

1. `component_part_name()` 剥掉实例后缀（`11_body-3` → `11_body`）；
2. 先精确匹配零件名，再退回“最长的子串键”（兼容 `下盖` 这类片段）；
3. 逐件 `SetMaterialPropertyValues2` + 回读 RGB/透明度（容差 0.02）；
4. `strict=True` 时任何未匹配或回读失败都抛异常，并列出零件名。

配色规则：

- **壳体/上盖/下盖**：透明度 0.75~0.82；**内部件一律实色**（0~0.1）。
- **同一功能族用同一颜色**：两根轴同蓝、齿轮红、齿圈金；一眼能看出传动链。
- **标准件也要配色**：螺栓银、螺母深灰、键黄、垫圈浅灰。漏掉会留默认灰，
  和大面积灰色壳体混在一起，看起来像“没上色”。
- **密封圈/垫片**给 0.35~0.5 的半透明或醒目色，表示柔性件。
- 不要在透明壳体上再用“每个面一个颜色”；组件级一层就够，特征级颜色在装配里
  可能被组件覆盖。

验证与交付：

- 回读值写进 `evidence/*.json`：每件的 `rgb`、`readback_transparency`、`ok`。
- 保存后重新打开一次，确认配色仍在（组件外观存在装配文件里）。
- 至少导 3 张预览：等轴测、前视、俯视；透明件多时再看一张底视。
- 透明件仍参与干涉/质量计算，透明只是显示属性。
- **常见坑：装配以“全压缩”状态存盘**。此时 `GetComponents` 齐全，但包围盒为 0、
  截图空白、配色也可能不生效；先 `resolve_all_components()` 再上色和出图。
- **常见坑：先上色再另存为**。`SaveAs` 后新文件继承了颜色，但原文件也已被改；
  必须“先复制文件，再打开副本上色”。
- **常见坑：装配还在解析时上色，前几件静默丢色**（SW2023，2026-10-25 减速器实测）：
  刚打开副本、组件还在解析就写颜色，最先上色的几个零件会**保留零件本来的颜色**，
  setter 不抛异常，回读却是 `[1,1,1]`、透明度 0。只有逐件回读能发现。
  抓到后 `ForceRebuild3(False)` 再整台重跑一遍即可写入。
  `apply_component_style_map(..., retry_after_rebuild=True)`（默认开）已内置这个重试，
  返回的 `retried` 字段记录是否触发过；交付证据里要把 `retried` 一起写进 JSON。
- **顺序**：`shutil.copy2` → 打开副本 → `resolve_all_components()` → `ForceRebuild3` →
  上色 + 逐件回读 → 渲染预览 → 保存。原件自始至终不打开写模式。

## 稳定性建议

- 单零件多特征上色可能受 SolidWorks 版本、显示状态、特征合并影响。
- 对颜色要求高的模型，优先拆成多个零件，并对每个零件使用文档级外观。
- 复杂项目建议输出装配体，由组件层级表达颜色、材质和可替换模块。
- 不要把“setter 未抛异常”当作颜色正确；必须回读 RGB。
- 不要在仍有选中组件/面/边时截图；绿色选择色会干扰视觉判断。
- 生成后必须用 `sw_review.py` 导出预览图检查颜色和层次是否可见。
