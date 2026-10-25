---
name: solidworks-plus-plus
description: "SolidWorks 建模与出图（非官方）：三视图/剖视图/照片 → 可编辑 SLDPRT 零件，SLDPRT/SLDASM → GB 第一角三视图与 PDF，含装配、孔特征、验证门禁。触发词：SolidWorks、SW 建模、建模、出图、三视图、工程图、零件、装配、SLDPRT、SLDASM、SLDDRW。不适用：非 SolidWorks 的 CAD（UG/Creo/Fusion/FreeCAD）、纯二维 DWG 编辑。"
---

# SolidWorks++ 建模与出图

> **SolidWorks++ 是建立在 SolidWorks API 之上的工程库与工作流层**：不是新的 CAD 内核，也不是 SolidWorks 的修改版；输出仍是原生 SLDPRT/SLDASM，任何 SolidWorks 都能打开。
> SolidWorks 是 Dassault Systèmes 的注册商标；本项目与其无隶属或背书关系。

本技能只有一个执行权威：**先判定模式与输入类型，再按固定路线调用脚本**。
不要临场发明 API、不要跳过验证、不要把“保存成功”当成“建模成功”。

## 0. 环境与路径约定（实测基线）

| 项 | 值 |
|---|---|
| SolidWorks | **2023 SP0.1 本机实测**；2024/2026 是继承上游的实测记录（本仓库未复测，按 pilot 处理：先跑 `sw_preflight.py` + 黄金用例再交付）；来源口径见 `capabilities.yaml` 的 `version_policy`。ProgID `SldWorks.Application` |
| Python | 3.9+，依赖 pywin32、comtypes、Pillow、PyMuPDF；开发机用 `py -3.12` 启动器，目标机按本机解释器调用 |
| 技能目录 | 本 SKILL.md 所在目录，下文记作 `<skill>`；用户工作目录记作 `<workdir>`。文档里的路径命令把这两个占位符替换成实际路径即可 |
| 图幅模板 | 脚本自动搜索 `ProgramData\SOLIDWORKS\SOLIDWORKS *\templates` 与 `Program Files` 语言目录；找不到时按报错手动指定 |

自检：

```bash
py -3.12 "<skill>\scripts\sw_preflight.py"
```

`capabilities.yaml` 是能力等级的唯一真源；`pilot` 能力必须做结果审查，`reference_only` / `not_implemented` 不得当作无人值守交付。

## 0.5 质量分层（弱模型保底，强模型加高）

同一个 skill 服务不同能力的模型，**不靠删知识来降门槛**：

| 层级 | 适用 | 必读 | 交付线 |
|---|---|---|---|
| **L1 保底** | 能力较弱/上下文受限 | 本文件 + 路线文档 + `quick-snippets.md` + 命中的配方 | 第 5 节门禁全部通过；几何、实体、孔、图纸不得错 |
| **L2 专业** | 中等及以上模型 | L1 + `part-modeling.md`、`feature-strategy.md`、`expert-thinking.md`、`drawing-standards.md`、`dimension-layout.md`、`standard-parts.md`、`pitfalls.md` | 加：特征顺序与选型、公差/配合、尺寸排版与尺寸链、表面粗糙度、标准件、GB 视图规范 |
| **L3 专家** | 强模型/复杂件 | 全部 references + `case-library.md` + 题库案例 | 加：复杂曲面、装配、运动、工艺性审查 |

规则：

- **L1 是地板，不是天花板。** 弱模型照 L1 做也必须能交付合格件；强模型在 L1 通过后继续 L2/L3，不得被 L1 的简化步骤限制。
- **门禁只拦错误交付，不拦更好的方案。** 强模型可以用配方之外的建模顺序，只要第 5 节证据齐全。
- **不得为了省 token 删除或跳过 L2/L3 的检查项**；上下文不够时先完成 L1，再在下一轮补 L2/L3。

## 1. 开工协议（每次任务先做）

1. 判定输入类型：`三视图/工程图`、`轴测图/照片`、`已有模型`、`文字需求`。
2. 确认对象：做什么、长什么样、几个零件、用在哪儿——不清楚就先问，不猜（见 `references/modes-and-questions.md` 第 1 节第 0 步）。
3. 判定模式（模式本身只问一次；**提问贯穿全程**，决策门禁见 `references/modes-and-questions.md` §2.5）：
   - **A 示意模式**：定性看形状，不抠尺寸——不问具体数值，只问对象/结构/拓扑。
   - **B 精确模式**：按图施工，尺寸可追溯，可交付——图纸/描述缺失的关键尺寸必须逐项提问（grill-me 多轮，贯穿全程）。
   - 用户没明说模式（需求模糊）→ 用 `references/modes-and-questions.md` §1.1 六段式模板把两种模式的提问范围、交付物、选错后果讲透再问，**不许一句带过**；选 B 时向用户说明“后续缺失的每个关键尺寸都会停下来问你”。
   - 判据表和提问模板见 `references/modes-and-questions.md`。
4. 关键信息不确定 → 先问再建：一次最多 4 问，可多轮；只有用户说“你定/随便”或确认“这项确实确定不了”后才按推荐值建模并标记来源。**不许猜一个值先建着。** 每条提问按 §2.6 自检：带依据、带选项后果、带推荐。
   - **提问强度与输入信息量成反比**（`references/modes-and-questions.md` §2.0）：照片反求、一句话需求、口头描述等信息薄的任务要多问几轮；简单件 + “随便做/看着像就行”是最容易瞎编的场景，至少问清**用途、关键接口、可自定尺寸、质量档位**四项，未答全不开工。简单件同样要做形体分析，不许“先画个大概再改”。
5. 生成任务卡（模式、交付物、包络、实体数、特征组、假设清单、未决问题），**落盘为 `<workdir>\task_card.json`**（字段见 `references/task-card-schema.md`）；建模前先跑 `py -3.12 "<skill>\scripts\check_task_card.py" "<workdir>\task_card.json" --stage model`，不通过就补卡，不许跳过。
6. 按路线执行；每个关键步骤后检查返回值。**每进入新阶段前（装配/出图/导出等）重扫任务卡未决问题（G1）；执行中发现重大分支——影响多个后续步骤或返工成本高——立即停下提问（G2），不许攒到交付。**
7. 交付前通过验证门禁，展示预览和假设清单；**再跑 `check_task_card.py --stage delivery`，假设清单、未测项、检查证据不齐不许宣布完成。**

🔴 **CHECKPOINT 1**：说明对象理解 + 模式与交付物；模式是问出来的（§1.1）要重申两种模式差异与后果（A 不问数值只问结构；B 缺失尺寸逐项提问）。
🔴 **CHECKPOINT 2**：存在任何未确定关键项（含模式 A 的对象/结构）时，先提问、展示任务卡，等用户回答或授权。
🔴 **阶段门禁（G1/G2）**：进入新阶段前重扫任务卡 `OpenQuestions`；执行中发现重大分支立即停下问，不许攒到交付。
🔴 **CHECKPOINT 3**：交付时展示包围盒、实体数、预览、尺寸证据和文件路径。

## 2. 路线选择

| 用户意图 | 路线 | 主文档 |
|---|---|---|
| 三视图 / 工程图 / 剖视图 + 直观图 → 三维模型 | **A：图 → 模型** | `references/drawing-to-part.md` |
| 已有 SLDPRT/SLDASM → 三视图 / 工程图 / PDF | **B：模型 → 图** | `references/part-to-drawing.md` |
| 照片 / 截图 → 示意模型 | A + 图片估读 | `references/image-to-part.md` |
| 只改尺寸、改特征、加孔 | 参数修改 / 局部重建 | `references/part-modeling.md`、`references/quick-snippets.md` |
| 定特征顺序、选拉伸终止条件、圆角/抽壳/阵列选型、修特征树 | 特征策略 | `references/feature-strategy.md` |
| 不背配方：读图分解、判断选型、自检习惯的专家思维 | 建模思维 | `references/expert-thinking.md` |
| 装配、配合、运动 | 装配子流程 | `references/assembly.md`、`references/motion-study.md` |
| 装配体上色、壳体透明化、隐藏零件让内部关系可见 | 外观子流程 | `references/appearance.md` |
| 螺纹孔、沉孔、沉头孔、槽 | 孔特征子流程 | `references/complex-hole-features.md` |
| 钣金件、基体法兰、折弯、平板型式/展开 | 钣金子流程 | `references/sheet-metal.md` |
| 螺栓、键、轴承、齿轮、弹簧等标准件 | 标准件路线 | `references/standard-parts.md` |
| 出图公差/粗糙度/技术要求 | GB 制图规范 | `references/drawing-standards.md` |
| 尺寸排版乱、尺寸链/基准、零件族标注习惯 | 尺寸标注策略 | `references/dimension-layout.md` |
| 自由曲面件、模具型腔、导入无特征史曲面 | 曲面路线（先判能否降级为实体） | `references/surfacing.md` |
| 管道 / 管筒 / 电气布线、Routing 规划与验收 | 布线路线（**本技能不自动布线**） | `references/piping.md` |
| 有限元选型、网格、边界条件、结果判据 | 验证方法（求解器无关） | `references/verification.md` |
| 多圆角/倒角 CNC 件 | 子技能 | `subskills/solidworks-fillet-chamfer-cnc/SKILL.md` |
| 螺纹孔规格与装饰螺纹 | 子技能 | `subskills/solidworks-threaded-holes/SKILL.md` |

**上下文受限时的最低必读三份**：本文件 + 对应路线文档 + `references/quick-snippets.md`。
这是 L1 保底包，不是能力上限；完成 L1 门禁后，按第 0.5 节继续读 L2/L3 文档，不要通读无关 references。

## 3. 路线 A：图 → 模型（固定顺序）

1. **清点输入**：给每张图编号并标注视图类型、尺寸清晰度。
2. **判定投影**：中国图纸默认第一角（俯视图在主视图下方，左视图在右方）。
3. **形体分析**：分线框 → 对投影 → 定体素 → 定组合 → 定基准。
4. **填三张表**：总体尺寸、特征尺寸、定位尺寸；每个值标来源
   （`explicit/derived/standard/user_confirmed/user_delegated/assumed/estimated`）。
   关键尺寸缺来源 → **先问，不编**（见 `references/modes-and-questions.md` 2.1）。
5. **建任务卡**：坐标系固定 X=长、Y=高、Z=深；把信息最多的视图
   画在 Front Plane（XY）。**若图纸主视图是侧剖面**（L 形支架、台阶轴、盘类剖面），
   就把侧剖面画在 Front Plane，平面轮廓放 Top/Right；出图后必须在交付说明里
   写清生成图的 Front/Top 分别是哪个视图，不能让用户按错的主视图加工。
6. **先匹配零件族配方**（`references/recipes/`），**套用前先过一遍“判断先行”**（配方 README：结构对不对得上、尺寸链齐不齐、主视图角色、终止条件选型、顺序理由），再按七步建模：
   基础体 → 主体 → 凸台/筋 → 孔槽 → 阵列/镜像 → 圆角/倒角 → 收尾。
   配方已给出固定顺序和代码骨架，不要临场重排；**但判断与配方冲突时以判断为准**，并在交付说明记录替换原因。配方未覆盖时，按
   `references/feature-strategy.md` 的选型、终止条件与顺序规则执行
   （尤其：先圆角后抽壳、孔排在抽壳后、装饰圆角最后）。
7. **逐项验证**：包围盒、实体数、孔证据、四视图预览。
8. **交付**：`.SLDPRT` + 参数表 + 预览 + 审查报告；模式 B 追加 `.STEP`。

硬规则：

- 所有长度输入用毫米，调用 `mm()`；API 内部单位是米。
- 草图必须闭合；每个特征调用后检查返回值是否为 `None`。
- 先加后减；圆角/倒角最后做。
- 特征命名写清用途和关键尺寸，如 `02_BORE_D36`；用封装的 `name=` 参数
  （`extrude_boss/extrude_cut/create_*_hole` 都支持），不要另写改名代码。
- 方向不确定时先做一个特征，回读 `GetPartBox(True)` 再继续。
- 不要用屏幕坐标选面/选边；用几何条件或特征名。

最小脚本骨架见 `references/drawing-to-part.md` 第 6 节；可复制 API 见 `references/quick-snippets.md`。

## 4. 路线 B：模型 → 三视图

一条命令：

```bash
py -3.12 "<skill>\scripts\sw_three_view.py" \
  --part "<workdir>\part.SLDPRT" --out-dir "<workdir>\drawing" \
  --paper A3 --projection first --dims --iso
```

输出：`.SLDDRW`、`.pdf`、`_drawing_preview.png`、`_drawing_report.json`。

必须检查：

1. `report["status"]` 为 `pass`，视图数 ≥ 3。
2. `report["sheet_setup"]["sheet_size_verified"]` 为 `true`，
   且 `actual_size_m` 与所选图幅一致（A3 = 0.420×0.297）。**不要只看 `configured: true`**。
3. `report["sheet_setup"]["sheet_scale_verified"]` 为 `true`，`actual_scale` 等于
   `layout.scale_ratio`；标题栏“比例”格同步（PDF 里应读到同一比值）。
4. `dimension_count > 0`；为 0 时回模型给草图/孔补尺寸（`auto_dimension_sketch`），
   不要说“已自动标注”。API 直接画线不会产生尺寸。
5. `dimension_dedupe.status == "pass"` 且 `after == unique_dimension_count`；
   `dimension_placement.status == "pass"`、`verified_count == placed_count`，
   且 `placed[]` 中没有 `issue == "NO_FEASIBLE_SLOT"`（`BAND_CROWDED`/`RADIAL_CROWDED` 目视后放行）。
   **pass 只代表写入回读成功，不代表好看**：同层共线、小尺寸在外、
   数字压线仍可能出现，必须再过 `references/dimension-layout.md` §7.2 目视清单。
6. 预览 PNG 非空白，且目视确认：第一角布局（俯视图在下、左视图在右）、
   长对正/高平齐/宽相等、尺寸不重叠、不压线、小内大外、不侵入标题栏。
7. 跑 PDF 机器检查（`report["pdf_check"]`，或单独执行
   `py -3.12 "<skill>\scripts\check_drawing_pdf.py" "<workdir>\drawing\part.pdf" --report "<workdir>\drawing\part_drawing_report.json"`）：
   `DIM_NO_LEADER`（尺寸文字没有引出线/尺寸线）、`DIM_FLOATING`（离视图太远）、
   `OUT_OF_FRAME`（越出图框）、`VIEW_OVERLAP`、`SHEET_SCALE_MISMATCH`、
   `VIEW_SCALE_MISMATCH`、`TITLE_SCALE_MISMATCH` 都是 fail——修图或如实披露，不许瞒；
   `pdf_check.status` 为 `skipped` 时按 not_run 处理，不算通过。
8. 保留 `.SLDDRW`，不要只交 PDF。

详细验收与失败分支见 `references/part-to-drawing.md`。

## 5. 验证门禁（所有任务）

| 门禁 | 通过标准 | 证据 |
|---|---|---|
| 文件 | `.SLDPRT` 存在且能重新打开 | 文件大小 > 0 |
| 几何 | 包围盒与总体尺寸一致 | B：≤ max(0.1 mm, 0.2%)；A：≤ 5% |
| 体积 | 与参数表手算体积差 ≤ 0.1% | `collect_geometry_measurements()["volume_mm3"]` |
| 实体 | 实体数等于任务卡 `BodyCount` | `GetBodies2(0, False)` |
| 特征 | 关键特征存在、无重建错误 | `ForceRebuild3(False)` + 特征树 |
| 孔 | 孔径/孔位与图纸一致 | `collect_geometry_measurements()` |
| 视觉 | 四视图预览方向、比例、特征正确 | `run_review()` 导出的 BMP |
| 装配运动 | 固定件 `IsFixed`；非固定件三向强推 10 mm 位移为 0；角度驱动时链上零件同步、垂直转轴分量 0；`probe_hinge_axis()` 转轴 = 设计轴、原点漂移 ≤ 0.01 mm | 运动探针 JSON（`a04_motion_check.py` 模式） |
| 装配上色 | 逐件回读 RGB/透明度一致；`retried` 记录是否触发二次上色；透明版是副本，原件 sha256 未变 | `apply_component_style_map()` 报告 + `assembly_check.json` |
| 图纸 | 视图数、尺寸数、布局、比例、PDF | `_drawing_report.json` + PDF 首屏 |
| 图纸 PDF | `pdf_check.status == "pass"`（悬空尺寸、无引出线、越界、视图重叠、比例不一致） | `pdf_check` 报告或独立检查输出 |
| 释放 | 脚本结束调用 `session.finish()`（或依赖 `connect_solidworks` 的 atexit 兜底）；交付后 `tasklist` 里没有脚本启动的 `SLDWORKS.exe`，另一个 SolidWorks 能直接打开交付文件 | `finish()` 返回值 + `sw_release.py` 报告 |
| 流程 | 任务卡过 `check_task_card.py`；交付时 handoff 证据齐全 | `task_card.json` + 检查输出 |

```python
report, path = run_review(part, r"<workdir>\review", basename="part",
                          expected_outputs=[r"<workdir>\part.SLDPRT"])
print(report["evaluation"]["status"], report["evaluation"]["issues"])
```

`evaluation.status` 不是 `pass` 时禁止宣布完成；先修复并重新生成。

改完技能后至少跑 `test-prompts.json` 里的 7 个黄金用例：
`d2p_b_link_001`（包围盒必须等于 67.37778×38.107013×10.0）、
`d2p_b_plate_holes`（包围盒 120×80×12，6 个圆柱面，体积 99794.337 mm³）、
`d2p_b_flange_cbore`（包围盒 32×120×120，6 个 φ9+φ15 复合孔，体积 143401.138 mm³）、
`m2d_a3_first_angle`（A3 回读 0.420×0.297、视图 ≥3、尺寸 >0）、
`d2p_b_missing_dims`（必须先问再建，可多轮）、
`d2p_a_ambiguous_object`（对象不清时必须先问清对象和拓扑）、
`sm_base_flange_flat`（100×50×0.5 钣金板，体积 2500.0 mm³，特征树含 FlatPattern）。

**体积是最便宜的全量自检**：孔漏切、缺口没开、凸台高度错，包围盒都看不出来，
体积会立刻露馅。建模脚本里按参数表手算期望体积并断言，差 > 0.1% 就停下来查。

## 6. 失败分支

| 触发条件 | 一线修复 | 仍失败兜底 |
|---|---|---|
| 连接失败 / RPC 不可用 | 确认 SolidWorks 已启动、无残留进程；用 `--visible` 重试一次 | 重启 SolidWorks 后再连一次；仍失败就停止并告知用户，不要连续重试 |
| 草图未闭合 / 拉伸返回 `None` | 检查轮廓自交、漏边；先用最简单矩形验证 | 重画闭合轮廓；导出草图截图目视检查；仍失败则停下问用户，不要继续叠加特征 |
| 切除方向反了 | 按材料所在侧翻转 `direction`，回读包围盒 | 在加工面建偏置面，只做一个试验孔；确认无误再批量 |
| 孔位整体偏移 | 检查 Top Plane 纵轴符号（`v = −Z`） | 改中心对称布局，或把孔系移到 Front Plane；回读 `position_mm` 逐项比对 |
| 视图创建返回 `None` | 用 `GetModelViewNames()` 读本机名（中文版 `*前视` 等），重试一次 | 逐视图单独创建并记录 `failures`；缺视图不得交付，停下来问用户 |
| 图纸空白 / 视图在纸外 | 查 `sheet_size_verified` 与 `actual_size_m`；SW2023 A3 码是 8，不是 6 | 用同码重设图幅并重排布局；仍空白就打开 `.SLDDRW` 人工检查模板 |
| 尺寸数为 0 | 回模型对每个草图调用 `auto_dimension_sketch()`，重新出图 | 检查特征树有无 DisplayDimension；仍为 0 就停下说明原因（如导入实体无草图尺寸），不得用“模型无尺寸”绕过门禁交付，也不得声称已自动标注 |
| 预览空白 | 检查 PDF 是否落盘（SaveAs 可能返回 False 但文件已写入） | 重新导出并渲染；仍空白就打开 `.SLDDRW` 截图，不要交付空白预览 |
| 装配体预览只剩背景 / `GetBox` 全 0 | 查组件是否全被压缩（`GetSuppression==0`），`resolve_all_components()` 后重建再截图 | 解析后包围盒仍为 0 就停下检查文件来源，不要反复改导出代码 |
| PDF 缺视图（视图数少于报告） | 走 `settle_drawing_views()`：重建→等待→缩放→保存→导出，并覆盖导出第二次 | 仍缺则逐视图检查 `IView` 是否为 `None`；缺视图不得交付 |
| 圆角失败 | 跳过圆角，保留直边，交付说明标注“外观圆角未应用” | 改用草图圆角/圆角矩形；不要为圆角重做主体超过一次 |

## 7. 黑名单（出现即返工）

- ❌ 不判定模式就直接建模。
- ❌ 需求模糊时模式判定一句带过，不说明两种模式的提问范围与后果。
- ❌ 把虚线当外轮廓，或把轴测图斜线当真实角度。
- ❌ 用屏幕坐标、`SelectByID2("Edge1")` 选边选面。
- ❌ 猜测未封装的 COM 方法签名和枚举值。
- ❌ 草图未闭合就拉伸，或特征返回 `None` 还继续叠加。
- ❌ 圆角在主体切除之前做。
- ❌ 只保存不审查，或只看“无报错”不看预览图。
- ❌ 用第三角布局交付国内加工图纸。
- ❌ 尺寸数为 0 却声称“已自动标注”。
- ❌ 覆盖上一轮交付文件；新产物用新文件名或新版本目录。
- ❌ 隐瞒 `assumed`/`estimated` 参数的来源。
- ❌ 关键信息不确定就瞎猜尺寸/结构开始建模（先问；仅用户确认“确定不了”或授权后才可编）。
- ❌ 推荐值未经用户确认就当作答案使用。
- ❌ 不判断实际结构就背配方生搬硬套特征顺序（配方是起点，判断后按 `feature-strategy.md` 调整）。
- ❌ 任务简单就少问或不问：信息越薄越容易把结构、数量、比例编出来，简单件 + 含糊质量要求必须多问（§2.0）。
- ❌ 用户说“随便”就直接开建：先摆选项和后果，拿到明确授权后再按推荐值建。
- ❌ 只在开工问一次，过程中发现新歧义不提问、攒到交付再补“假设”。
- ❌ 重大分支（影响多个后续步骤/返工成本高）自己拍板，不提问。
- ❌ 工程图 PDF 没过 `check_drawing_pdf.py` 就把“出图完成”写进交付说明。
- ❌ 任务卡/交付说明没过 `check_task_card.py --stage delivery` 就宣布完成。
- ❌ 检查没跑就在报告里写 pass（没算出来不是通过）。
- ❌ 照片复刻没有比例基准就直接估尺寸。
- ❌ 自己发明公差、材料或标题栏字段。
- ❌ 把 BOM 写成“已与视图关联/已加球标”，而实际只插了表；未做的事记 not_run。
- ❌ 交付“透明化”版本时覆盖原装配体文件；先复制再改，原文件保留。
- ❌ 把半透明当成隐藏来解释装配关系（透明件仍参与质量、配合与干涉计算）。
- ❌ 脚本结束只 `CloseDoc(装配体)` 不退实例：依赖零件仍占文件锁，用户打不开交付文件，只能重启电脑。
- ❌ 可动装配只跑干涉检查就说“可以拖动”；第一个件未固定、铰链缺轴向定位都会让拖动轨迹错。
- ❌ 用“配合数量增加了”代替自由度探针；漏掉的平动自由度只能靠强推位移发现。

## 8. 参考文件与子技能

| 文件 | 用途 |
|---|---|
| `references/modes-and-questions.md` | 模式判定、提问规则、决策门禁（G0/G1/G2）、任务卡、检查点 |
| `references/task-card-schema.md` | `task_card.json` 字段定义与示例（`check_task_card.py` 的检查依据） |
| `references/drawing-to-part.md` | 图 → 模型完整流程、尺寸表、验证 |
| `references/part-to-drawing.md` | 模型 → 三视图、验收、失败分支 |
| `references/quick-snippets.md` | 可复制代码：草图、拉伸、孔、阵列、审查、出图 |
| `references/pitfalls.md` | 单位、选择、坐标系、COM 兼容等高频坑 |
| `references/part-modeling.md` | 特征与草图细节 |
| `references/feature-strategy.md` | 设计意图、草图规划、特征顺序、终止条件、圆角/抽壳/拔模、阵列选型、修复与配置（含 API 缺口） |
| `references/expert-thinking.md` | 专家建模思维（知识库提炼）：读图分解、判断选型、自检习惯、该问用户的时刻 |
| `references/drawing-standards.md` | GB 视图/尺寸/公差/粗糙度/技术要求与出图自检 |
| `references/dimension-layout.md` | 尺寸排版：人类动作顺序、基准/尺寸链、GB 版面数值、零件族配方、算法映射与目视清单 |
| `references/standard-parts.md` | 螺栓/键/轴承/齿轮/弹簧/链轮/销的建模策略与速查表 |
| `references/surfacing.md` | 曲面适用边界、补洞/加厚/修复选型、失败处理（含“未封装”边界） |
| `references/complex-hole-features.md` | 盲孔/沉孔/沉头/槽与孔位验收 |
| `references/sheet-metal.md` | 钣金：基体法兰（开放/闭合轮廓）、平板型式（自动生成）、切除与验收、已验证/未验证边界 |
| `references/assembly.md`、`motion-study.md` | 装配、配合、运动算例 |
| `references/appearance.md` | 外观与材质：颜色预设、九位材质数组、**组件透明度**（装配内部关系可视化）、回读验证 |
| `references/export.md` | 文件导出（PDF/BMP/STEP/DXF 等）与产物复核 |
| `references/api-lookup.md` | 未封装 API 的离线查证：本地 CHM 解包、`SwConst` 枚举取值、最小验证脚本要求 |
| `references/api-reference.md`、`advanced.md` | API 速查（常用对象/方法）与高级功能目录 |
| `references/mesh-reference-import.md` | 高还原网格参考模型导入（OBJ/STL） |
| `references/complex-mechanical-routing.md` | 复杂机械模型的能力路由（先探测再执行） |
| `references/verification.md` | 有限元选型、边界条件、网格、后处理判据与失败分支（Simulation/Motion 知识） |
| `references/piping.md` | 管道与布线：线路组织、配件拓扑、折弯/直段、自动步路、验收、BOM（不含 Routing API） |
| `references/review.md` | 自审查报告字段与门禁 |
| `references/troubleshooting.md` | COM 报错与兼容问题 |
| `references/dataset-patterns.md` | 题库挖掘出的建模顺序与尺寸模式（训练产物） |
| `references/recipes/` | 按零件族拆分的固定建模配方（训练产物） |
| `references/case-library.md` | 已实测/题库模式案例：参数表、特征顺序、验证结果 |
| `test-prompts.json` | 18 个可重复验收用例（7 个黄金）：黄金包围盒、法兰沉孔、图幅、尺寸数、该问不该问、冲突尺寸、图纸字段、PDF 检查、排版分诊、装配透明上色、装配运动自由度、钣金平板型式 |
| `capabilities.yaml` | 能力等级唯一真源（含 SW2023 实测限制与 2024/2026 上游来源口径） |
| `golden-workflows.yaml` | 关键工作流的必需输入与产物 |
| `scripts/check_task_card.py` | 任务卡/提问/交付说明机器检查（模式、六段式、参数来源、门禁、handoff） |
| `scripts/check_drawing_pdf.py` | 工程图 PDF 机器检查（悬空尺寸、无引出线、越界、重叠、与报告不一致） |
| `scripts/check_skill_consistency.py` | 技能自身一致性（版本说法、description、用例计数、引用文件存在） |

子技能（按需读取，不要默认全读）：

- `subskills/solidworks-fillet-chamfer-cnc/SKILL.md`：多圆角/倒角 CNC 件。
- `subskills/solidworks-threaded-holes/SKILL.md`：螺纹孔、攻丝底孔、装饰螺纹。
- `subskills/solidworks-vibecad/SKILL.md`：自然语言 → 结构化设计计划。
- `subskills/autocad-automation/SKILL.md`：DWG/DXF 二维图纸（需 AutoCAD；未安装时仅走无头路线）。
