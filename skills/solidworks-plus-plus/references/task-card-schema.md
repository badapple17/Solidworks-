# 任务卡 `task_card.json` 字段定义

`references/modes-and-questions.md` §4 的任务卡在这里落成机器可读的 JSON。
模型在开工前写 `<workdir>\task_card.json`，用 `scripts/check_task_card.py` 自检；
交付前用 `--stage delivery` 再查一次。**检查不通过 = 不许宣布完成。**

```bash
py -3.12 "<skill>\scripts\check_task_card.py" "<workdir>\task_card.json" --stage model
py -3.12 "<skill>\scripts\check_task_card.py" "<workdir>\task_card.json" --stage delivery --strict
```

- `--stage`：`plan/model/assembly/drawing/export/delivery`（默认 `model`）。
- `--strict`：warn 也返回非零，建议交付时加。
- `--json`：只输出 JSON，供其他脚本读取。
- 返回码：`0` = pass，`1` = warn（仅 `--strict`），`2` = fail，`3` = 文件读不了。

它检查的是**结构**（有没有把该说的话说清楚），不是话术质量：空泛占位
（“无”“待定”“TBD”“…”）一律按没写处理。

## 1. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `object` | object | 是 | `{what, part_count}`；`what` 写“做的是什么”，`part_count` ≥1 |
| `mode` | string | 是 | `A` / `B` / `A_then_B` |
| `mode_source` | string | 是 | `user_explicit` / `inferred_from_input` / `asked` |
| `mode_evidence` | string | 是 | 判定依据（用户原话或输入证据） |
| `mode_question_id` | string | `asked` 时必填 | 指向 `questions` 里那条模式提问 |
| `deliverables` | array | 是 | 如 `["sldprt","step","preview","report"]`；工程图加 `"slddrw"/"pdf"/"drawing"` |
| `questions` | array | 否 | 提问记录，见 §2 |
| `parameters` | array | 否 | 参数表，见 §3 |
| `open_questions` | array | 否 | 未决问题，见 §4 |
| `stages_entered` | array | 否 | 已进入的阶段，如 `["plan","model","drawing"]` |
| `stage_gates` | array | 否 | 每个进入的阶段一条 `{"stage":"drawing","scanned_at":"..."}` |
| `handoff` | object | 交付时必填 | 交付说明，见 §5 |

## 2. `questions[]`（固定六段式 + 机器字段）

```json
{
  "id": "Q1",
  "topic": "plate_thickness",
  "round": 1,
  "gate": "G1",
  "question": "这块安装板的板厚按 12 mm 还是按图上的 10 mm？",
  "my_understanding": "主视图标 12，剖视图标 10，我倾向前者但两处冲突。",
  "evidence": "主视图下方尺寸 12；A-A 剖面尺寸 10；两处都指向板厚。",
  "why_critical": "板厚决定四角通孔深度和沉孔能否做在 12 mm 内，选错要重做板和孔。",
  "options": [
    {"label": "A", "consequence": "按 12 mm 建，孔深与沉孔按 12 核算；剖视图的 10 视为标注错误。"},
    {"label": "B", "consequence": "按 10 mm 建，主视图 12 视为标注错误；沉孔深度改为 4。"}
  ],
  "recommended": "A",
  "recommended_reason": "主视图是主要尺寸来源；选错返工范围是整块板加全部孔。",
  "default_if_no_answer": "再问一次并说明两处标注冲突；未答复前不建模。",
  "source_of_question": "input_observation",
  "major_branch": true,
  "batched_with": null,
  "answer_kind": "chosen",
  "answer": "A",
  "follow_up_on_same_topic": false
}
```

| 字段 | 规则 |
|---|---|
| `id` | 唯一，参数用 `question_id` 引用 |
| `topic` | 同一主题回答过后不许再问 |
| `round` | 每轮最多 4 问；重要问题拆多轮，不要一次抛十几个 |
| `gate` | `G0`（开工）/ `G1`（阶段）/ `G2`（过程中） |
| `question` | 点名具体对象/尺寸/部位，不能是“还有问题吗” |
| `my_understanding` | 当前猜测 + 依据；空泛 = fail |
| `evidence` | 哪张图、哪个部位、量出的值、用户哪句话；**拿不出证据说明是背答案** |
| `why_critical` | 不确认会走错哪条路线、返工哪些步骤 |
| `options` | 2–4 个，标签唯一，每个都有 `consequence` |
| `recommended` | 必须是某个选项标签 |
| `recommended_reason` | 推荐理由 + 选错时的返工范围 |
| `default_if_no_answer` | 用户不答时的默认动作（通常是重申风险再问一次） |
| `source_of_question` | 不许是 `recipe_default` / `case_default`（配方默认值不是这次输入） |
| `major_branch` | 命中“重大分支”判据时为 true |
| `batched_with` | `major_branch=true` 时不许有值——重大分支必须当场单独问 |
| `answer_kind` | `chosen` / `delegated`（用户说“你定”）/ `cannot_determine`（用户确认“确定不了”）；没有此字段 = 未回答 |
| `follow_up_on_same_topic` | 已回答 `delegated` 后不许再追问同一项 |

`mode_source="asked"` 时，模式提问的选项里必须同时出现 A 和 B：
B 的 `consequence` 必须写明“缺失的关键尺寸会逐项问”，A 的 `consequence`
必须写明“不问具体数值 / 尺寸标 assumed / 只供定性”。

## 3. `parameters[]`（每个关键值的来源都要能追溯）

```json
{"name": "plate_thickness", "value": 12, "unit": "mm", "source": "user_confirmed",
 "critical": true, "question_id": "Q1"}
```

| `source` | 额外必填 | 说明 |
|---|---|---|
| `explicit` | — | 图纸/用户明确给出 |
| `derived` | `formula` | 尺寸链推导，公式写清 |
| `standard` | `standard_ref` | 如 `GB/T 5782 M6`、`6204` |
| `user_confirmed` | `question_id` 指向已回答问题 | 用户回答确认 |
| `user_delegated` | `question_id` 指向已回答问题 | 用户授权“你定” |
| `assumed` | 关键项需 `question_id` 指向 `cannot_determine`/`delegated` | 未经确认的假设 = 猜，关键项直接 fail |
| `estimated` | `estimate_basis`（参照物/像素比例/标尺） | B 模式关键项不许只靠估读 |

- `critical: true` 的参数是“选错要返工”的功能/接口/包络尺寸。
- 模式 A 只允许对**具体数值**做假设；对象、结构、拓扑仍然要问。

## 4. `open_questions[]` 与阶段门禁

```json
[{"topic": "铰链位置", "blocks_stage": "assembly", "authorized_to_proceed": false}]
```

- 进入某阶段前，`blocks_stage` 不晚于该阶段的未决项必须清空或 `authorized_to_proceed=true`。
- 每进入一个新阶段，在 `stages_entered` 记录阶段名，并在 `stage_gates` 加一条
  `{"stage": "...", "scanned_at": "..."}`，证明重扫过任务卡。缺记录 = G1 fail。

## 5. `handoff`（交付说明）

```json
{
  "assumptions_listed": ["fillet_radius"],
  "checks_run": [
    {"name": "bracket_geometry", "result": "pass", "evidence": "review/bracket_review_report.json",
     "command": "sw_review.py --file ...", "threshold": "envelope tolerance 0.1 mm"},
    {"name": "drawing_pdf", "result": "fail", "disclosed": true,
     "evidence": "drawing/bracket_pdf_check.json", "command": "check_drawing_pdf.py ..."}
  ],
  "untested": ["外观纹理未验证"],
  "files": ["<workdir>/bracket.SLDPRT", "<workdir>/drawing/bracket.SLDDRW"],
  "drawing_check_report": "<workdir>/drawing/bracket_pdf_check.json"
}
```

- `assumptions_listed` 必须包含**每一个** `assumed` / `estimated` / `user_delegated`
  参数名；漏一个 = 隐瞒来源。
- `checks_run` 每条必须有 `result`：`pass` / `fail` / `not_run`。
  - `pass` 必须带 `evidence`（报告路径或回读数值）——**没算出来不是通过**。
  - `fail` 必须 `disclosed: true`——失败可以存在，隐瞒不行。
  - 没跑的检查写 `not_run`，不许写成 pass。
- `untested` 字段必须存在（可以是空列表）：明确哪些要求没验证。
- `files` 是交付文件清单。
- `deliverables` 含 `slddrw` / `drawing` 时，必须给 `drawing_check_report`
  （`check_drawing_pdf.py` 的报告路径）。

## 6. 最小可过示例

```json
{
  "object": {"what": "带四角安装孔的矩形板", "part_count": 1},
  "mode": "B",
  "mode_source": "inferred_from_input",
  "mode_evidence": "用户给出带尺寸三视图并要求按图施工",
  "deliverables": ["sldprt", "preview", "report"],
  "questions": [],
  "parameters": [
    {"name": "plate_length", "value": 120, "unit": "mm", "source": "explicit", "critical": true},
    {"name": "plate_width", "value": 80, "unit": "mm", "source": "explicit", "critical": true},
    {"name": "plate_thickness", "value": 12, "unit": "mm", "source": "explicit", "critical": true}
  ],
  "open_questions": [],
  "stages_entered": ["plan"],
  "stage_gates": [],
  "handoff": {
    "assumptions_listed": [],
    "checks_run": [{"name": "envelope", "result": "pass", "evidence": "review/report.json"}],
    "untested": [],
    "files": ["<workdir>/plate.SLDPRT"]
  }
}
```

> 这个示例只演示结构；真实任务按实际参数、提问和检查填写，不许照抄数值。
