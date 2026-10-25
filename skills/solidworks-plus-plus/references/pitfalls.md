# 高频坑与兼容写法

这些是实际跑 SolidWorks 2023 COM 时踩过的坑。写脚本前先扫一遍，能省掉大部分返工。

## 1. 单位与数值

- SolidWorks API 内部单位是**米**；图纸、用户输入是**毫米**。所有入口用 `mm()` 转换。
- 角度用 `deg()`；`revolve_boss`、`circular_pattern` 接收弧度。
- 读回尺寸时 `SystemValue` 是米，转毫米再比较。
- 包围盒 `GetPartBox(True)` 返回 `[xmin, ymin, zmin, xmax, ymax, zmax]`，单位米。

## 2. COM 调用

- **串行**：同一桌面会话只允许一个 SolidWorks 自动化脚本写文档。不要并发开两个进程。
- `connect_solidworks()` 返回 `(sw, active_model)`，不是单个对象；必须解包。
- `session.sw.RevisionNumber` 是属性，不是方法。
- 长参数方法（`FeatureExtrusion3`、`FeatureCut4`、`SetupSheet6`）不要凭记忆改参数顺序；以 `scripts/` 里的封装为准。`FeatureExtrusion3` 与 `FeatureCut4` 的第 3 个参数都叫 Dir，但 SW2023 中含义相反（见第 4 节）。
- by-ref 参数用 `VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)` 包装。
- `visible=False` 在本机会导致打开第二个文档时 `RPC 服务器不可用`。**本机固定用可见模式**（`SolidWorksSession()` 默认可见，命令行加 `--visible`）。
- 每个特征调用后检查返回值；`None` 表示失败，不要继续叠加。

## 3. 选择与命名

- 不要用屏幕坐标或 `SelectByID2("Edge1")` 选边选面；编号会随版本、语言、特征顺序变化。
- 能拿到 COM 对象时优先 `entity.Select4(True, None)` / `Select2()`。
- 基准面可用 `SelectByID2("Front Plane", "PLANE", ...)`；草图选择优先用 `sw_part._ensure_sketch_selected()` 的缓存引用，中文版下按名称选草图可能失败。
- 需要稳定选边时，遍历 `body.GetEdges()`，按几何条件（圆边、半径、方向、位置）筛选，再选择对象。
- 圆角/倒角的难点是选边，不是 API 参数；选不准就跳过，保留直边并在交付说明中标注。

## 4. 坐标系与草图平面

SW2023 实测（不是教科书方向）：

| 平面 | 草图坐标映射 | 拉伸 `direction=True` 轴向 | 拉伸 `direction=False` 轴向 |
|---|---|---|---|
| Front Plane（前视） | (X=u, Y=v) | −Z | +Z |
| Top Plane（上视） | (X=u, Z=−v) | −Y | +Y |
| Right Plane（右视） | (Z=−u, Y=v) | −X | +X |

**切除与拉伸的 `direction` 语义相反**（SW2023 实测，2026-10-24）：`extrude_cut()` 的 `True` 沿 +法向、`False` 沿 −法向。底层 `FeatureExtrusion3` 与 `FeatureCut4` 的第 3 个参数都叫 Dir，但含义相反，照抄拉伸的 `direction` 去切除方向必反。

- **材料在哪一侧，切除就朝哪一侧**：主体用 `direction=True` 拉伸时材料在负轴，用 `False` 时在正轴；切除方向按材料侧选——`extrude_cut` 的 `direction` 语义与拉伸相反（见上表），材料在 +轴侧用 `True`、在 −轴侧用 `False`，不能只看基准面。
- **贯穿切除也不是方向无关**：从实体端面贯穿时，方向反了会朝空侧切并返回 `None`；`extrude_cut()` 的 `auto_flip` 会反向重试。
- 有通孔/沉孔时，把加工面放在基准面上（如 Top，Y=0）；不要用中面拉伸后再从基准面切，否则只切到一半。
- 需要从第二个面加工时，用 `insert_offset_plane()` 建偏置面；它先选中基面再调 `InsertRefPlane`，避免建面失败。**失败时抛异常、成功时一定返回特征，不会返回 `None`**——不要写 `if plane is None` 的无效分支。偏置面贴在材料外端时，朝 +法向切就是朝空处切，要用 `direction=False`——方向语义本身没变，不是“整体反转”（实测，2026-10-24：Front 偏置面 Z=+10、材料 Z=0..10，`direction=True` 返回 `None`，`False` 生成特征）。先做一个试验孔，切空时让 `auto_flip` 兜底。
- 不对称特征优先画在 Front Plane；必须画在 Top Plane 时，先用中心对称布局，放置后回读孔位核对。
- **不要直接把负数传给 `InsertRefPlane(8, …)`**：SW2023 静默忽略负号，面落在基面上（实测拖拉机左轮埋进车身，包围盒 Z 少 300 mm、实体数 3≠5）。用 `insert_offset_plane()`，它对负值自动走 Flip（`8|256`）；翻转面正法向仍是基面正法向。
- **已有几何附近画草图要关推理吸附**：`sketch(..., exact=True)`。不开时矩形会悄悄吸到旁边的边/残留草图上，尺寸被改且无报错，只有体积门禁能抓到。
- **`exact=True` 也挡不住矩形角点吸到草图轴**（SW2023 实测，2026-10-25）：`CreateCornerRectangle` 的角点离草图原点轴线 <≈0.5 mm 时被吸到轴上（托钩 v=0.5 → 0；底座十字槽角点 x=±0.35 → 0，草图退化，切除返回 `None`）。小矩形/贴轴矩形改用四条 `sketch_line`。另：Right Plane 上先画过圆弧的零件，之后的 `CreateCornerRectangle` 可能直接返回 `None`——先画矩形、最后画圆弧。
- **一个零件的特征对齐另一个零件时，先写出两原点的偏移再换算**：零件门禁（体积/包围盒/实体数）只证明“按我写的数建出来了”，抓不到“数是在别的零件坐标系里算的”。实测托钩挡边按背板坐标画，零件体积误差 0.000%，装配干涉 150 mm³。见 `assembly.md`「干涉检查」。
- **密集折线（≈100+ 段）即使空草图也要 `exact=True`**（2026-10-25 实测）：126 段瓶身剖面默认推理下相邻端点被吸附/打断，`GetSketchContours` 返回 28 条、`revolve_boss` 返回 `None`；`exact=True` 后 contours=1、旋转成功，体积与 Pappus 解析值差 2×10⁻⁷。信号：几何上只有一个闭环而 contours>1。
- `collect_geometry_measurements()["envelope_mm"]` 的键是**模型 XYZ**（`length`=X、`width`=Y、`height`=Z，见 `axis_order`），不是图纸长宽高；竖放回转件（轴=Y）的高度记在 `width`。
- **视觉审查 100 分 ≠ 几何正确**：埋进车身的轮子在预览里不明显，体积/实体数门禁才是硬证据。
- **包围盒 ≠ 孔径**（bounding box ≠ hole diameter）：包围盒只能证明外形；孔径/孔位/孔数必须用
  `hole_groups` / `compound_holes` 单独核对。“包围盒对上了”推不出“孔也对”。
- 拉伸/切除方向不确定时，只做一个特征，回读包围盒，再决定是否翻转。

## 5. 草图

- 草图必须闭合才能生成实体；自交、缺口、重复线都会让拉伸返回 `None`。
- `with sketch(model, plane)` 退出时自动结束草图；不要在 `with` 内调用 `extrude_*`。
- `auto_dimension_sketch()` 必须在草图编辑态调用，才会生成真实 DisplayDimension。
- `sketch_slot(..., radius)` 最后参数是**半径**，不是槽宽。
- 圆角矩形/槽口优先用草图轮廓实现，比特征圆角稳定。
- `CreateArc` 的 `direction` 实测（2026-10-25，弦+弧拉伸测面积）：`+1`=逆时针、`-1`=顺时针；给定圆心/起终点时决定小弧还是大弧（同一组参数：+1 围出 55.43 mm²、−1 围出 9447.9 mm²）。画反会自交或轮廓裂开。
- 用点列逐段画折线时，**首点是第一段起点，不要按上一段终点去重**：两点的单段串（口顶面、颈内壁）去重后变零段，轮廓裂成多条（实测 3 contours、regions=0）。

## 5.6 空壳函数与未生效参数（2026-10-24 核对源码）

- `sw_part.hole_wizard()` 是**空壳**（函数体只有 `pass`），调用会静默返回 `None`。
  不要用它建异形孔；改用 `sw_hole_features.create_through_hole /
  create_blind_hole / create_counterbore_hole / create_countersink_hole`。
- `revolve_boss()` 的 `axis_sketch_name` 参数当前实现**未使用**；旋转轴必须在调用前
  自行选中，否则会绕错轴或直接失败。
- `shell(model, thickness, faces_to_remove=None)`：传面列表会自动选面并返回
  「抽壳1」；不传面时用当前选择集，**不选任何面会抽成完全中空密封体**。
  本机 pywin32 动态派发找不到 `InsertFeatureShell`，封装已改用
  `IDispatch::Invoke`（GetIDsOfNames 取 dispid）——不要改回
  `model.InsertFeatureShell(...)`，会报“找不到成员”。
- `extrude_boss()` 只有盲深；不要传“成形到一面/完全贯穿/拔模/薄壁”参数。
- `linear_pattern()` 的 1D/2D 已修好（2026-10-24 实测）：`FeatureLinearPattern3`
  真实签名 10 参数，方向由辅助 3D 草图线表达；**数量是含源实例的总数**
  （`d1_count=3` 得到 3 个孔，不是源+3）。仍无 geometry pattern / 跳过实例 /
  对称 / 到参考。辅助 3D 草图被阵列引用，不要删。
- `circular_pattern()` 未实测，`DName` 传 `"None"` 不可靠；`mirror_feature()`
  无镜像实体。
- `rib()` 的第 1 参数是 `Is2Sided`（两侧加厚），不是拉伸方向；原实现少传一个
  参数，已补齐但本机简单 L 形支架仍返回 `None`——建筋改用闭合三角形草图拉伸。
- `fillet()` 的 `Options` 固定为 195，**切线延伸被硬编码为开启**，不能关闭；
  无完整圆角、无变半径。需要不传播的单边圆角时标“人工/新增封装”，
  不要臆造参数名。

## 6. 工程图

- `InsertModelAnnotations4/3` 只能导入模型里**已存在**的显示尺寸；不会凭空生成尺寸。
- 模型尺寸为 0 时，先回模型用 `auto_dimension_sketch()` 补标，再出图。
- 图纸尺寸异常少（整张只有 1–2 个）时，先按 `quick-snippets.md` 第 10 节遍历模型的
  DisplayDimension 清单：清单齐全但图纸少，**重跑一次出图**即可（2026-10-24 实测：
  同一块板首次导入 2 个，重跑 17 个）；清单本身就少，才是模型缺尺寸。
- 特征树遍历的 `FirstFeature`、`GetFirstDisplayDimension` 在本机是**属性式伪成员**，
  直接加括号会抛“找不到成员”（`-2147352573`）。必须用 `get_com_member()` 调用。
- `Feature.GetSpecificFeature2()` 同样是伪成员（2026-10-25 实测）：直接调用报“找不到成员”，
  读草图轮廓/线段必须 `get_com_member(feat, "GetSpecificFeature2")` 后再调
  `GetSketchContours/GetSketchRegions/GetSketchSegments`。`GetEntityName(seg)` 可能返回空串，
  线段选择用 `"Line1@" + 草图名`。
- 第一角：俯视图在主视图**下方**，左视图在主视图**右方**；第三角相反。国内图纸默认第一角。
- `SetupSheet6` 的图幅代码来自 `PAPER_SIZES`，不要手写枚举。
- **`SetupSheet6` 传 `.slddrt` 时 `TemplateIn` 必须为 12**（`swDwgTemplateCustom`），
  不能传图幅码（A3=8）。传 8 也返回 `True`、图幅也对，但导出 PDF 会丢图框线、
  标题栏和尺寸线（实测导出 0 条矢量路径）。不用 `.slddrt` 时才让两者同码。
- **`CreateDrawViewFromModelView3` 会把图面比例重置为 1:1**。标题栏“比例”格跟图面比例，
  所以视图（含轴测）全部建完后要再调一次 `SetupSheet6`，并用 `GetProperties2()`
  回读比例（第 3/4 项）与图幅（第 6/7 项，注意返回 8 项时尺寸仍在 `[5:7]`）。
  “重设比例会丢标题栏”是误判，真正原因是 `TemplateIn` 传错。
- `InsertModelAnnotations3(Option, Types, AllViews, DuplicateDims, HiddenFeatureDims,
  UsePlacementInSketch)`：第 3 个参数是 `AllViews`，不是 `DuplicateDims`。
  `DuplicateDims=False` 只防同一视图内重复，**跨视图重复仍会出现**；按
  `IDimension.FullName` 去重，用 `IAnnotation.Select2(False,0)` + `EditDelete` 删除
  多余的显示尺寸（不动模型）。实测齿轮图 10 → 4。
- `IView.GetOutline()` 含视图边框，左边缘比真实几何多约 6 mm。摆放尺寸用建模时
  的规划视图框，不要用它算偏移，否则容易顶到 PDF 检查器 25 mm 的悬浮阈值。
- 同一视图两列尺寸若同高，水平引出线会沿同一条中心线重叠（机器检查发现不了）；
  两列要错开半行距（约 4.5 mm）。
- `IDisplayDimension.GetText(0)` 对导入尺寸返回空串，PDF 里却有数值；不能据此判断
  尺寸无文字，也不能拿它当尺寸值证据。
- 出图后必须看 PDF/PNG 预览，不能只看 `view_count`。
- 标题栏字段若未链接自定义属性，COM 不会自动填写；需要手工补或改图纸格式。

## 7. 装配与运动

- `add_component()` 在中文版可能走 `AddComponent5`、静默打开零件、切回装配体的回退路径；不要自己写简化版。
- 先解析组件对象，再做 Mate；不要用屏幕坐标点选。
- 旋转件用同心 Mate 且 `lock_rotation=False`，不要用三个基准面锁死。
- Motion Study 的 `CreateMotionStudy` / `Activate` / `Calculate` 在 pywin32 下可能表现为属性；用 `sw_motion.motion_member()` 兼容。
- 只看到时间轴或 `Calculate=True` 不算通过；要检查马达数量、结果存在、`results_out_of_date=False`。

## 8. 外观与导入

- 材质数组必须用 `SAFEARRAY(double)` 编组；不要把 Python `list` 直接传给 COM。
- 设置颜色后回读 RGB 验证，不能只看 setter 返回值。
- OBJ/STL 导入用 `sw_import_mesh_reference.py` 的 `LoadFile4(path, "r", create_empty_dispatch_variant(), errors)`；不要用 `OpenDoc6()`，不要把 `None` 传给 `LoadFile4()`。
- 网格导入件不是参数化实体；需要可编辑结构时基于参考重新建模。

## 9. 文件与交付

- 新产物用新文件名或新版本目录，不覆盖上一轮 CAD、图纸、BOM、审查报告。
- 保存后检查文件真实存在且大小 > 0；导出后再检查目标格式文件。
- `.SLDDRW` 是原生可编辑交付物；PDF 只是预览/交付副本。
- 所有预览图必须目视检查；“非空白”不等于“正确”。
- **“检查没跑”不是“检查通过”**：报告里没执行的检查记 `not_run`，不许默认 pass；
  标 pass 的项必须有证据路径或回读数值。
- **PDF 与报告不一致时以 PDF 为准**：报告说 4 视图而 PDF 只有 3 个框，先查结构采集
  和布局，再决定信谁；不许只挑对自己有利的数字。
- **尺寸文字没有尺寸线**（`DIM_NO_LEADER`）是图纸缺陷，不是“标注成功”：
  `dimension_count > 0` 只说明有尺寸对象，不说明画对了。交付前跑
  `check_drawing_pdf.py`。
