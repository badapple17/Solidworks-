# 06 · 立式 42 型齿轮油泵（考试题：19 件全套 + 三套装配）

> 模式 B（精确）· 装配图/零件图 + STEP 标准件 → 三维模型 → 装配
> 生成模型：DeepSeek V4 系列（低成本档位）
> 规模：19 个零件 + 3 套装配（每套 26 个组件）

## 1. 任务

输入是一份 7 页的 CAD 考试卷（`inputs/试卷.pdf`）：**立式 42 型齿轮油泵**，明细栏 19 项，齿轮副 `m=3, z=14`，两轴中心距 42 mm（装配高度 Z=104 / Z=62）。要求按零件图建全部零件，按装配示意图装成整泵，再出爆炸图与透明涂色图。

和 05 的区别：05 是“零件图 + 装配图但缺两件”，06 是**图纸齐全、标准件直接给 STEP**，所以整个建造过程几乎不需要回头问尺寸——这也是 6 个实例里“输入越全、结果越准”的最强对照。

## 2. 输入

| 文件 | 用途 |
|---|---|
| `inputs/试卷.pdf` | 装配示意图、19 项明细栏、各零件图与尺寸 |
| `inputs/标准件/6-齿轮轴.STEP` | 下齿轮轴（m=3 z=14，Ø48 × 62） |
| `inputs/标准件/8-传动齿轮轴.STEP` | 上传动齿轮轴（Ø48 × 155） |
| `inputs/标准件/GB／T1096-2003普通平键A型5x5×18.STEP` | 平键 5×5×18 |
| `inputs/标准件/GB／T119.1-2000圆柱销A型5×20.STEP` | 圆柱销 5×20 |
| `inputs/标准件/GB／T5782-2000六角头螺栓 M6×18.STEP` | 六角头螺栓 M6×18 |
| `inputs/标准件/GB／T93-1987标准型弹性垫圈(装配)12×6．21.STEP` | 弹性垫圈（装配态） |
| `inputs/标准件/GB／T93-1987标准型弹性垫圈(零件)12×6．21.STEP` | 弹性垫圈（零件态） |

两个齿轮轴直接用 STEP，不重建齿形；它们的齿是**真实渐开线**，后面装配对齿时按半齿距相位对齐即可。

## 3. 交付物

| 文件 | 说明 |
|---|---|
| `deliverables/parts/01_adjust_screw.SLDPRT` | 调节螺钉 M20×1.5，总长 34 |
| `deliverables/parts/02_spring.SLDPRT` | 调压弹簧 Ø14 × 19.7 |
| `deliverables/parts/03_locknut_M20.SLDPRT` | 锁紧螺母 M20×1.5，Ø29.58 × 7 |
| `deliverables/parts/04_steel_ball.SLDPRT` | 钢球 Ø10 |
| `deliverables/parts/05_pin_5x20.SLDPRT` | 圆柱销 5×20（STEP 导入） |
| `deliverables/parts/06_gear_shaft.SLDPRT` | 下齿轮轴 m=3 z=14（STEP 导入） |
| `deliverables/parts/07_cover.SLDPRT` | 泵盖 34 × 80 × 122，双圆弧轮廓 |
| `deliverables/parts/08_drive_gear_shaft.SLDPRT` | 上传动齿轮轴（STEP 导入） |
| `deliverables/parts/09_washer_12.SLDPRT` | 弹性垫圈 12（STEP 导入） |
| `deliverables/parts/10_gasket.SLDPRT` | 垫片 1 × 80 × 122 |
| `deliverables/parts/11_body.SLDPRT` | 泵体 113 × 94 × 144，含进出油口、底座、双轴孔 |
| `deliverables/parts/12_packing.SLDPRT` | 填料 Ø26 × 10（装配用两件） |
| `deliverables/parts/13_locknut_M36.SLDPRT` | 锁紧螺母 M36×1.5，Ø47.6 × 7 |
| `deliverables/parts/14_gland_nut.SLDPRT` | 压盖螺母 M36×1.5，Ø36.95 × 29 |
| `deliverables/parts/15_packing_gland.SLDPRT` | 填料压盖 Ø30 × 16 |
| `deliverables/parts/16_pulley.SLDPRT` | V 带轮 Ø105 × 23，5×Ø18 减重孔 |
| `deliverables/parts/17_key_5x5x18.SLDPRT` | 平键 5×5×18（STEP 导入） |
| `deliverables/parts/18_bolt_M6x18.SLDPRT` | 六角头螺栓 M6×18（STEP 导入） |
| `deliverables/parts/19_nut_M12.SLDPRT` | 螺母 M12 |
| `deliverables/assembly/CLYBZP.SLDASM` | 紧凑装配（26 组件） |
| `deliverables/assembly/CLYBZP_EXPLODED.SLDASM` | 爆炸图（复制件，原件不动） |
| `deliverables/assembly/CLYBZP_TRANSPARENT.SLDASM` | 透明涂色（复制件，原件不动） |
| `scripts/01_import_std.py` | 导入 7 个 STEP 标准件并回读尺寸/体积 |
| `scripts/03_parts_small.py` | 01/02/03/04/12/13/19 小件 |
| `scripts/04_cover_gasket.py` | 07 泵盖、10 垫片、14 压盖螺母、15 填料压盖 |
| `scripts/05_part_body.py` | 11 泵体 |
| `scripts/09_part_pulley.py` | 16 皮带轮 |
| `scripts/20_assemble.py` / `22_explode.py` / `25_transparent.py` | 装配、爆炸、透明涂色 |
| `scripts/26_verify.py` | 交付门禁：重开三套装配，回读组件数、包围盒、透明度 |
| `previews/*.png` | 紧凑 4 视图、爆炸 2 视图、涂色 2 视图、泵盖轴测 |
| `evidence/verify_report.json` | `26_verify.py` 的最终回读（`status: pass`） |
| `work/build_status.json` | 各建造脚本写入的过程记录 |

## 4. 零件参数

| 零件 | 关键尺寸（mm） |
|---|---|
| 01 调节螺钉 | 六角头 S30，总长 34，M20×1.5 螺纹段 |
| 02 弹簧 | 外径 Ø14，自由长 19.7，线径 1.6，有效圈 7 |
| 03 锁紧螺母 M20 | Ø29.58（对边 29.58 = 34.16×cos30） × 7 |
| 04 钢球 | Ø10 |
| 06 齿轮轴 | Ø48 × 62，m=3 z=14，轴伸 Ø16 |
| 07 泵盖 | 34 × 80 × 122；双圆弧（stadium）轮廓 R40，两轴孔距 42 |
| 08 传动齿轮轴 | Ø48 × 155，m=3 z=14，长端穿过填料函 |
| 10 垫片 | 1 × 80 × 122，与泵盖同轮廓 |
| 11 泵体 | 113 × 94 × 144；X −30…+32，Y ±47，Z 0…144；两轴孔 Z=104 / Z=62 |
| 12 填料 | Ø26 × 10，内孔 Ø16 |
| 13 锁紧螺母 M36 | Ø47.6 × 7 |
| 14 压盖螺母 | Ø36.95 × 29，M36×1.5 |
| 15 填料压盖 | Ø30 × 16 |
| 16 皮带轮 | Ø105 × 23；V 槽 30° 夹角、槽顶宽 10、槽底 Ø85；轮毂 Ø30；孔 Ø16H7 + 键槽 5×2.3；5×Ø18 减重孔 PCD Ø52 |
| 17 平键 | 5 × 5 × 18 |
| 18 螺栓 | M6 × 18 |
| 19 螺母 | M12 |

齿轮副：`m=3`、`z=14`，分度圆 R21、齿顶 R24，中心距 **42**（Z=104 − Z=62）——型号里的“42”就是中心距。

## 5. 装配

### 5.1 世界坐标系

```
X = 轴轴线（泵盖侧为负，输出侧为正）
Y = 油口轴线
Z = 竖直（底座底面 Z=0）
轴向布局：泵盖 −65…−31 | 垫片 −31…−30 | 泵体 −30…+32 | 填料函 32…67
上轴 Z=104（08 传动轴，穿出填料函 → 带轮/键/垫圈/螺母）
下轴 Z=62 （06 齿轮轴，两端在泵体轴承孔内）
```

### 5.2 26 个组件

| 组件 | 数量 | 定位 |
|---|---|---|
| 11 泵体 | 1 | 原点 |
| 10 垫片 | 1 | 贴泵盖面 |
| 07 泵盖 | 1 | X=−1 |
| 08 传动齿轮轴 | 1 | Z=104，绕轴转 180°（键槽朝 +Y） |
| 06 齿轮轴 | 1 | Z=62，相对 08 转**半个齿距**（`360/14/2 = 12.857°`）保证啮合 |
| 16 带轮 / 17 键 / 09 垫圈 / 19 螺母 | 1 各 | 上轴输出端 X=71/82/96.9/100.1 |
| 01/03/02/04 调压阀组 | 1 各 | 泵盖下轴孔 X=−93/−72/−59/−40 |
| 12 填料 | **2** | 上轴填料函 X=20、30 |
| 15 压盖 / 14 压盖螺母 / 13 锁紧螺母 | 1 各 | X=40/56/67 |
| 18 螺栓 M6×18 | **6** | 泵盖法兰四角 + 上下两端 |
| 05 圆柱销 | **2** | 对角定位 |

合计 18 + 6 + 2 = **26 个组件**。全部用 `IComponent2.Transform2.ArrayData` 显式定位，不用配合：零件都按同一个世界系建模，位置表就是装配定义。

### 5.3 变换矩阵的两个坑（已写成探针）

`21_probe_transform.py` 一次只改一个变量，确认了 SW2023 的真实语义：

1. **`ArrayData` 前 9 个元素是列主序**：按行主序写，90° 旋转会朝反方向转。`transform_data()` 因此显式转置。
2. **平移单位是米**：这里的位置表用毫米，写入前 `/1000`。
3. **必须用 `VT_ARRAY | VT_R8` 包装**：直接传 Python list 会被静默丢弃，位姿保持单位矩阵。

## 6. 上色

`25_transparent.py` 复制 `CLYBZP.SLDASM` 为 `CLYBZP_TRANSPARENT.SLDASM` 后逐组件上色：

| 零件 | 颜色 | 透明度 |
|---|---|---|
| 11 泵体 | `#C8CDD2` | 0.80 |
| 07 泵盖 | `#D98CA8` | 0.75 |
| 10 垫片 | `#4F86C6` | 0.45 |
| 06 / 08 齿轮轴 | `#2E5FA8` 蓝 | 0 |
| 16 带轮 | `#3FA34D` 绿 | 0 |
| 17 键 | `#F2C200` 黄 | 0 |
| 12 填料 | `#D84315` 橙红 | 0 |
| 13/14/15 填料函件 | 金黄系 | 0 |
| 其余标准件 | 银灰 | 0 |

回读 `11_body` 外观：`[0.784, 0.804, 0.824, 1.0, 1.0, 0.45, 0.35, 0.8, 0.0]`，透明度 0.8，齿轮副与填料函透过壳体清晰可见。

## 7. 验证证据

`scripts/26_verify.py` 重新打开三套交付装配，报告写入 `evidence/verify_report.json`：

| 门禁 | 结果 |
|---|---|
| CLYBZP | 26 组件，包围盒 `[-93, -52.5, 0, 110.1, 52.5, 156.5]`，`match=True` |
| CLYBZP_EXPLODED | 26 组件，包围盒 `[-458, -52.5, 0, 430.1, 52.5, 156.5]`，`match=True` |
| CLYBZP_TRANSPARENT | 26 组件，包围盒与紧凑件完全一致，`match=True` |
| 11_body 透明度 | 0.8，`translucent=True` |
| 总判定 | `ALL PASS: True` |

爆炸图的偏移只作用于副本：`22_explode.py` 打开复制件、沿拆卸方向平移组件后另存，紧凑件从未被修改。

## 8. 真实修正记录

1. **泵盖/泵体轮廓的 36–40 段折线**：最初用折线近似双圆弧（stadium）轮廓，壳体外表面出现约 80 条棱线，渲染成条纹。`23_probe_capsule_arc.py` 找到 `CreateArc(direction=1)` 的扫掠方向后，改成**两段真圆弧 + 两条公切线**的四实体闭合轮廓，外表面变成光滑圆柱面，包络完全一致。
2. **切除方向语义**：`extrude_cut` 的 `direction` 与 `extrude_boss` 相反（cut True→+法向，boss True→−法向），并且 SW2023 的返回值不保证方向正确。`07_probe_cutdir.py` 用“块 + 盲孔 + 面框”三步确认后写进 `build_lib`，另加 `auto_flip` 兜底：切完落在空气里就自动反向。
3. **草图平面轴向**：Right 平面 `u→−Z, v→+Y`，Top 平面 `u→+X, v→−Z`，Front 平面 `u→+X, v→+Y`；`08_probe_signs.py` 用偏离原点 (10,20) 的圆逐个平面验证，`build_lib` 的三个 `circle_on_*` 就是这张表。
4. **组件变换**：见 5.3，列主序 + 米 + SAFEARRAY 三点全部由 `21_probe_transform.py` 实测。
5. **齿对齿相位**：06 齿轮轴必须相对 08 转半个齿距，否则两轮齿顶对齿顶、装配后齿面重叠。

## 9. 已知偏差与限制

1. **装配是静态展示**：无配合、无运动算例；组件位置由变换矩阵固定。
2. **齿轮副按 STEP 原始齿形装配**：没有侧隙修形；两轴相位按半齿距对齐，属于“能装进去”的展示状态。
3. **没有工程图**：06 只交付三维零件与装配，未出零件图/装配图（05 覆盖了出图路线）。
4. **标准件外形来自 STEP**：规格与图纸一致，但没有按 GB 重新建模，也没有螺纹细节。
5. **没有材料与强度校核**：模型只保证几何。
6. **爆炸图偏移量是展示值**：沿各件拆卸方向给定，不代表装配工艺顺序。

## 10. 复现

```bash
cd showcase/06-gear-pump-exam

py -3.12 scripts/01_import_std.py     # 7 个 STEP -> SLDPRT
py -3.12 scripts/03_parts_small.py
py -3.12 scripts/04_cover_gasket.py
py -3.12 scripts/05_part_body.py
py -3.12 scripts/09_part_pulley.py

py -3.12 scripts/20_assemble.py       # CLYBZP.SLDASM
py -3.12 scripts/22_explode.py        # 复制 + 爆炸
py -3.12 scripts/25_transparent.py    # 复制 + 透明涂色

py -3.12 scripts/26_verify.py         # 门禁 -> evidence/verify_report.json
```

路径由 `scripts/case_paths.py` 自动推导：实例目录 `inputs/`、`deliverables/`、`previews/`、`evidence/`、`work/` 跟着仓库走；技能目录用 `SOLIDWORKS_PLUS_PLUS_SKILL_DIR` 覆盖，或从仓库祖先 / `~/.claude/skills` 自动发现。

探针脚本（`00`、`06`、`07`、`08`、`21`、`23`）只读或只建临时件，不写交付目录，用来复现上文的 API 语义结论。

## 11. 备注

- 泵体是整套里最重的件（113 × 94 × 144），建造时按“方块主体 → 双轴孔 → 油口 → 底座 → 圆角”的顺序做，先加后减。
- 预览为 PNG：`SaveBMP` 先写 BMP，PIL 压缩后删除 BMP。
- 脚本结束统一调用 `session.finish()`：关闭本文档并退出脚本启动的 SolidWorks 实例，避免依赖零件继续占用文件锁。
