# SolidWorks API 查证流程

当任务需要使用 `scripts/` 尚未封装的 SolidWorks API 时，先查证再实现。不要凭记忆补长参数、枚举值或返回值。

## 优先资料源

1. SolidWorks 官方 API Help：按 `<InterfaceName> <MethodName>`、`<MethodName> Method (SOLIDWORKS API Help)` 或枚举名（如 `swSaveAsOptions_e`）检索
2. 本地 SDK / API Help：
   - 常见入口：SolidWorks 安装目录下的 `api`、`api\help`、`api\redist`
   - 常见类型库：`SolidWorks.Interop.sldworks.dll`、`SolidWorks.Interop.swconst.dll`
3. 本技能封装与经验：
   - 优先搜索 `scripts/*.py`
   - 再查 `references/*.md`
   - 最后才写新的最小验证脚本

## 离线查证：本机 CHM + SwConst（不联网，最可靠）

联网检索经常拿到错版本或旧参数表。本机已装 SolidWorks 时，**先解包本地 CHM**：

```bash
# 1) 找到 CHM（路径含空格/中文，先复制到 ASCII 目录，hh.exe 对中文路径不稳）
ls "C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/help/sldworksapi.chm"
cp "C:/Program Files/SOLIDWORKS Corp/SOLIDWORKS/api/help/sldworksapi.chm" /c/swapi_tmp/
# 2) 解包成 17000+ 个 htm，每个成员一个文件
hh.exe -decompile C:/swapi_tmp/out C:/swapi_tmp/sldworksapi.chm
```

文件名规则：`SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.<接口>~<成员>.html`，
可直接按成员名搜：

```bash
ls /c/swapi_tmp/out | grep "IView~InsertBomTable4"
```

抽正文（必须设 `PYTHONIOENCODING=utf-8`，否则 Windows GBK 控制台报
`UnicodeEncodeError: '\ufeff'`；读文件用 `utf-8-sig`）：

```python
import re, html, pathlib
p = pathlib.Path(r"C:\swapi_tmp\out\SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IView~InsertBomTable4.html")
t = p.read_text(encoding="utf-8-sig", errors="ignore")
t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
t = re.sub(r"<[^>]+>", " ", t)
print(re.sub(r"[ \t\xa0]+", " ", html.unescape(t))[:4000])
```

**枚举数值直接读 `comtypes.gen.SwConst` 的属性**（不必猜、不必反射 DLL）：

```bash
py -3.12 -c "import comtypes.gen.SwConst as C; print(C.swBomType_PartsOnly, C.swBomType_TopLevelOnly, C.swBomType_Indented)"
# 1 2 3 —— 注意不是按顶层/零件顺序，凭直觉写必然弄错
py -3.12 -c "import comtypes.gen.SwConst as C; [print(n, getattr(C,n)) for n in sorted(dir(C)) if n.startswith('swComponentSuppressionState')]"
```

规则：

- **枚举名的数值只认 `SwConst`（类型库生成）或 `swconst.dll` 反射**，不认博客、不认记忆。
- **参数顺序只认 CHM 的 `Insert... Method` 页**（含 VB/C#/C++ 三份签名）。
- 同一成员有多个编号版本（`InsertBomTable` / `InsertBomTable2` / `...4`）时，
  取 CHM 里参数表与本机类型库一致的那个；旧版博客多数过时。

## 必查 API 类型

- `IModelDocExtension.SaveAs*`、`OpenDoc*`、`CloseDoc`、导出相关 API
- `SelectByID2`、选择标记、选择类型字符串与选择追加逻辑
- `FeatureManager.FeatureExtrusion*`、`FeatureCut*`、扫描、放样、圆角、倒角等长参数方法
- `IAssemblyDoc.AddComponent*`、`AddMate*`、组件变换、轻化/压缩状态
- 运动装配体必查：`IAssemblyDoc.AddMate5`、`IComponent2.GetModelDoc2`、`IComponent2.GetCorresponding`、`IComponent2.SetSuppression2`、`ISurface.IsCylinder`、`ISurface.CylinderParams`、`IComponent2.SetTransformAndSolve2`
- Motion Study 必查：`IModelDocExtension.GetMotionStudyManager`、`IMotionStudyManager.CreateMotionStudy`、`IMotionStudy.CreateDefinition`、`IMotionStudy.CreateFeature`、`ISimulationMotorFeatureData.ConstantSpeedMotor`、`ISimulationMotorFeatureData.LoadReferences`
- 外观/材质：`MaterialPropertyValues`、`IMaterialVisualPropertiesData`、组件级外观、显示状态
- 工程图：视图创建、BOM、尺寸标注、打印/导出 PDF
- 需要 `VARIANT`、by-ref、枚举或 bitmask 的接口

## 查证记录模板

在任务脚本或提交说明中保留最小记录，方便后续沉淀：

```text
API:
资料源:
版本:
签名:
关键参数:
枚举/常量:
返回值:
失败症状:
验证脚本:
是否沉淀到 scripts/references:
```

## 运动装配 API 查证速记

- `AddMate5`：确认 15 参数签名，最后一个 `ErrorStatus` 是 by-ref 整型；Gear Mate 使用 `GearRatioNumerator` / `GearRatioDenominator`；同心 Mate 运动时 `LockRotation=False`。
- `GetModelDoc2`：官方说明中组件可能因压缩、轻化或未加载而无法返回模型；自动化前先解析组件。
- `GetCorresponding`：把零件文档中的对象映射到装配体上下文；同一零件有多个实例时，必须由目标组件实例调用。
- `IsCylinder` / `CylinderParams`：识别轴、孔和齿轮圆柱面；`CylinderParams[6]` 是半径，单位米。
- `SetTransformAndSolve2`：适合驱动组件位置并让装配求解器更新；稳定性差时优先复用组件现有 `Transform2` 并修改 `ArrayData`。
- `swmotionstudy.tlb`：Motion Study 强类型接口在独立类型库中；pywin32 下需要 `pythoncom.LoadTypeLib(...)` + `win32com.client.gencache.EnsureModule(...)`。
- `swFmAEMRotationalMotor`：实测于 SW 2024 `swFeatureNameID_e` 验证值为 `78`，用于 `CreateDefinition(78)` 创建旋转马达 FeatureData。
- `ISimulationMotorFeatureData.ConstantSpeedMotor(60.0)`：参数单位为 RPM，不是 rad/s。
- `swAddMateError_e`：`swAddMateError_NoError=1`；不要把 `AddMate5` 的 by-ref `ErrorStatus=1` 当失败。

枚举交叉验证命令：

```powershell
Add-Type -Path '<SolidWorks 安装目录>\SolidWorks.Interop.swconst.dll'  # 默认 C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\；装在其他盘按实际目录
[int][SolidWorks.Interop.swconst.swMateType_e]::swMateGEAR
[int][SolidWorks.Interop.swconst.swMateType_e]::swMateHINGE
[int][SolidWorks.Interop.swconst.swFeatureNameID_e]::swFmAEMRotationalMotor
[int][SolidWorks.Interop.swconst.swAddMateError_e]::swAddMateError_NoError
[enum]::GetValues([SolidWorks.Interop.swconst.swComponentSuppressionState_e])
```

## 最小验证脚本要求

1. 单独连接 SolidWorks，打印 `sw.RevisionNumber()` 和当前文档类型。
2. 只验证一个新 API，不把它直接混入大任务。
3. 对每个 COM 调用检查 `None` / `False` / 错误码 / 警告码。
4. 生成可打开的 `.SLDPRT` / `.SLDASM` / `.SLDDRW` 或导出文件。
5. 运行 `sw_review.py` 或人工截图复核模型/工程图/装配体是否真的正确。

## 沉淀规则

- 同一 API 第二次用到，优先封装进 `scripts/`。
- 出现兼容问题、错误码、中文版名称差异、选择标记坑位时，补充到对应 `references/*.md`。
- 封装函数应隐藏 COM 长参数细节，暴露稳定、可读、带单位约定的 Python API。
- 文档示例必须是已运行过的写法，不放未经验证的猜测代码。
