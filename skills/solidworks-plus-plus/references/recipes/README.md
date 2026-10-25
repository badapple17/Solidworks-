# 零件族固定配方（训练产物）

配方是**低自由度**的执行卡：识别零件族 → 填参数表 → 按固定顺序调已验证函数。
不要从零设计建模顺序；先匹配下面的零件族。

## 先判断，再套配方（防“背答案”）

配方是**起点不是答案**。套用前必须过一遍判断，任何一条不满足就停下来调整或问用户：

1. **结构对不对得上**：零件是否真是这个族（带端环的杆 → link-lever；有键槽的轴 → stepped-shaft 旋转+偏置面切槽）。多个族特征混在一起时（轴+法兰=带轮毂法兰），按主特征选配方，次要特征按 `feature-strategy.md` 补。
2. **尺寸链齐不齐**：配方里每个 key_dims 都有来源了吗？缺关键尺寸 → 先问（`modes-and-questions.md` 2.1），不许填一个“看起来合理”的值。
3. **主视图角色对不对**：图纸主视图是侧剖面（L 形、台阶轴、盘类剖面）→ 侧剖面画在 Front Plane，并在交付说明写清视图角色；不是所有零件都照默认方向摆。
4. **终止条件选型**：通孔/盲孔/沉孔、拉伸到面/贯穿，判断后选；不匹配的配方步骤要替换而不是硬套。
5. **顺序理由**：配方给的顺序为什么是这个顺序（先加后减、孔在抽壳后、圆角最后）——能说出理由才执行；说不出理由就先读 `feature-strategy.md` 对应节。

判断结果写进任务卡的 FeatureGroups，再动手。判断与配方冲突时以判断为准，并在交付说明记录“配方 X 步骤 Y 替换为 Z，原因…”。判断方法详见 `references/expert-thinking.md`。

| 配方 | 适用零件 | 首特征 | 已验证程度 |
|---|---|---|---|
| `plate-with-holes.md` | 平板、盖板、安装板、带缺口/孔板 | 拉伸 | 实测（2026-10-24） |
| `link-lever.md` | 连杆、摆臂、支座耳板、带端环的杆 | 拉伸 | 实测，包围盒与答案一致 |
| `stepped-shaft.md` | 阶梯轴、销轴、套筒、轮毂轴 | 旋转 | API 已验证，按本机模板复核 |
| `flange-disk.md` | 法兰、端盖、圆盘、轮坯 | 旋转 | API 已验证，按本机模板复核 |
| `bracket-rib.md` | L 形支架、角座、带筋板 | 拉伸（侧剖面） | 部分实测；筋用闭合三角形草图拉伸（`rib()` 返回 None） |

**族匹配失败或跨族时（板+轴颈、支架+法兰），不许硬套最近的一个族。**
退回通用决策链（`expert-thinking.md` R15 简版）：
① 剖面有回转中心线/同心圆组且主体绕轴 → 旋转起步（R1）；
② 否则找信息量最大的平视图 → 该面为草图、向薄方向拉伸（R2）；
③ 特征粒度对齐图纸标注粒度（R3）；
④ 主序列 `drawing-to-part.md` 七步，遇父子依赖按 R6–R10 调整；
⑤ 重复 ≥2 用阵列/镜像（R13）。
主特征选配方、次要特征按 `feature-strategy.md` 补。

## 通用执行规则

1. 先读 `references/dataset-patterns.md` 第 3 节确认零件族，不要凭文件名猜。
2. 参数表里每个值必须标来源：`explicit/derived/assumed/estimated`。
3. 模式 B 下，`assumed/estimated` 的值先问用户；模式 A 可直接取整。
4. 每个特征后检查返回值；`None` 立即停，不要继续叠加。
5. 建模完成后必须回读包围盒、实体数、孔；与参数表逐项比对。
6. 需要出图时，草图/孔必须带尺寸（`auto_dimension_sketch()`），否则图纸没有尺寸。

## 坐标系约定（本机 SW2023 实测）

| 草图平面 | 草图 (u,v) → 模型 | 拉伸方向 | 切除方向 |
|---|---|---|---|
| Front Plane | X=u, Y=v, Z=0 | `direction=True` → −Z；`False` → +Z | `direction=True` → +Z；`False` → −Z |
| Top Plane | X=u, Y=0, Z=−v | `direction=True` → −Y；`False` → +Y | `direction=True` → +Y；`False` → −Y |
| Right Plane | X=0, Z=−u, Y=v | `direction=True` → −X；`False` → +X | `direction=True` → +X；`False` → −X |

> 拉伸与切除的 `direction` 语义相反（2026-10-24 实测）：底层 `FeatureExtrusion3`
> 与 `FeatureCut4` 的第 3 个参数都叫 Dir，但 SW2023 中含义相反。
> 照抄拉伸的 `direction` 去切除，方向必反。

> 本机所有零件的“共同底面”优先放在草图平面上，向 **+轴** 拉伸：
> Front 用 `direction=False`，Top/Right 同理用 `False`。
> 这样多个凸台共享同一底面，和大多数工程图的主视图一致。

## 出图提醒

- 三视图脚本只导入模型里**已有的显示尺寸**；直接画线不会产生尺寸。
- 每个草图闭合前调用一次 `auto_dimension_sketch(part)`。
- 孔用 `create_through_hole()` 时，脚本会自动给孔草图加尺寸。
