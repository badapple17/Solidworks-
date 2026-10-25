"""@brief 任务卡 / 提问记录 / 交付说明的机器检查器（SolidWorks++ 流程门禁）。

SKILL.md 里“提问要带依据、带后果、带推荐”“模式要讲透再问”“假设必须列出”这类规则，
原来只能靠模型自觉。本脚本把它们变成可检查的结构：模型在建模前写 task_card.json，
交付前再跑一次，失败就不许宣布完成。

不连接 SolidWorks，只读 JSON，任何机器都能跑：

    py -3.12 <skill>/scripts/check_task_card.py <workdir>/task_card.json
    py -3.12 <skill>/scripts/check_task_card.py <workdir>/task_card.json --stage delivery

返回码：0 = pass，1 = warn（仅 --strict 时），2 = fail，3 = 文件不可读。
字段定义见 references/task-card-schema.md。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MODES = {"A", "B", "A_then_B"}
STAGES = ("plan", "model", "assembly", "drawing", "export", "delivery")
SOURCES = {
    "explicit", "derived", "standard", "user_confirmed",
    "user_delegated", "assumed", "estimated",
}
# 只有这些来源可以未经提问直接使用；其余关键尺寸来源必须能追溯到一条已回答的提问。
SOURCES_WITHOUT_QUESTION = {"explicit", "derived", "standard"}
SOURCES_NEED_ANSWER = {"user_confirmed", "user_delegated"}
MAX_QUESTIONS_PER_ROUND = 4
MIN_OPTIONS, MAX_OPTIONS = 2, 4
# 空泛占位：出现即视为没写依据/后果。
VAGUE = re.compile(r"^(无|没有|不确定|待定|n/?a|tbd|todo|\?+|…+|\.\.\.|略)$", re.IGNORECASE)
MIN_TEXT = 6  # “我的理解”“为什么关键”“后果”最少字符数（中文按字计）


def _text_ok(value: Any, minimum: int = MIN_TEXT) -> bool:
    text = str(value or "").strip()
    return len(text) >= minimum and not VAGUE.match(text)


class Report:
    def __init__(self) -> None:
        self.findings: list[dict[str, str]] = []

    def add(self, severity: str, code: str, where: str, message: str) -> None:
        self.findings.append({"severity": severity, "code": code, "where": where, "message": message})

    def fail(self, code: str, where: str, message: str) -> None:
        self.add("fail", code, where, message)

    def warn(self, code: str, where: str, message: str) -> None:
        self.add("warn", code, where, message)

    @property
    def status(self) -> str:
        severities = {item["severity"] for item in self.findings}
        if "fail" in severities:
            return "fail"
        return "warn" if "warn" in severities else "pass"


def _questions(card: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(q.get("id")): q for q in card.get("questions", []) if isinstance(q, dict)}


def _answered(question: dict[str, Any] | None) -> bool:
    return bool(question) and question.get("answer_kind") in {"chosen", "delegated", "cannot_determine"}


def check_object_and_mode(card: dict[str, Any], rep: Report) -> None:
    """G0：对象、模式、交付物。"""
    obj = card.get("object") or {}
    if not _text_ok(obj.get("what"), 2):
        rep.fail("G0_OBJECT_MISSING", "object.what", "没写清做的是什么；对象不清必须先问（modes-and-questions.md §1 第 0 步）。")
    if not isinstance(obj.get("part_count"), int) or obj.get("part_count", 0) < 1:
        rep.fail("G0_PART_COUNT_MISSING", "object.part_count", "零件数量未确定；单件/多件/装配会改变拓扑，必须先确认。")
    mode = card.get("mode")
    if mode not in MODES:
        rep.fail("G0_MODE_INVALID", "mode", f"模式必须是 {sorted(MODES)} 之一，当前 {mode!r}。")
        return
    source = card.get("mode_source")
    if source not in {"user_explicit", "inferred_from_input", "asked"}:
        rep.fail("G0_MODE_SOURCE_INVALID", "mode_source", "mode_source 必须是 user_explicit / inferred_from_input / asked。")
    if not _text_ok(card.get("mode_evidence"), 4):
        rep.fail("G0_MODE_EVIDENCE_MISSING", "mode_evidence", "模式判定要引用用户原话或输入证据（例：“尺寸随意”→A）。")
    if source == "asked":
        question = _questions(card).get(str(card.get("mode_question_id")))
        if question is None:
            rep.fail("G0_MODE_QUESTION_MISSING", "mode_question_id", "模式是问出来的，但找不到对应提问记录。")
            return
        labels = " ".join(str(o.get("label", "")) for o in question.get("options", []))
        if not ("A" in labels and "B" in labels):
            rep.fail("G0_MODE_OPTIONS_INCOMPLETE", f"questions[{question.get('id')}]", "模式提问必须同时给出 A 示意 和 B 精确 两个选项。")
        b_option = next((o for o in question.get("options", []) if str(o.get("label", "")).strip().upper().startswith("B")), None)
        if b_option and "问" not in str(b_option.get("consequence", "")):
            rep.fail(
                "G0_MODE_B_COST_HIDDEN", f"questions[{question.get('id')}].options[B]",
                "B 选项的后果必须写明“缺失的关键尺寸会逐项停下来问你”，不许把提问量藏起来（§1.1）。",
            )
        a_option = next((o for o in question.get("options", []) if str(o.get("label", "")).strip().upper().startswith("A")), None)
        if a_option and not re.search(r"不问|不抠|定性|assumed", str(a_option.get("consequence", ""))):
            rep.fail(
                "G0_MODE_A_SCOPE_HIDDEN", f"questions[{question.get('id')}].options[A]",
                "A 选项的后果必须写明“不问具体数值、尺寸标 assumed、只供定性”。",
            )
    if not card.get("deliverables"):
        rep.fail("G0_DELIVERABLES_MISSING", "deliverables", "交付物清单为空。")


def check_question_quality(card: dict[str, Any], rep: Report) -> None:
    """§2.3 六段式 + §2.6 质量自检，逐条机器化。"""
    rounds: dict[str, int] = {}
    seen_topics: dict[str, str] = {}
    for index, q in enumerate(card.get("questions", [])):
        where = f"questions[{q.get('id', index)}]"
        if not _text_ok(q.get("question"), 4):
            rep.fail("Q_TEXT_MISSING", where, "问题本身为空或过短；要点名具体对象/尺寸/部位。")
        if not _text_ok(q.get("my_understanding")):
            rep.fail("Q_UNDERSTANDING_MISSING", where, "“我的理解”为空或空泛；要写当前猜测和依据。")
        if not str(q.get("evidence") or "").strip():
            rep.fail("Q_EVIDENCE_MISSING", where, "缺 evidence：哪张图/哪个部位/量出的值/用户哪句话。拿不出证据说明问题是背出来的（§2.6 背答案预防）。")
        if not _text_ok(q.get("why_critical")):
            rep.fail("Q_WHY_MISSING", where, "“为什么关键”为空；要写不确认会走错哪条路线、返工哪些步骤。")
        options = [o for o in q.get("options", []) if isinstance(o, dict)]
        if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
            rep.fail("Q_OPTION_COUNT", where, f"选项数必须 {MIN_OPTIONS}–{MAX_OPTIONS} 个，当前 {len(options)} 个。")
        labels = [str(o.get("label", "")).strip() for o in options]
        if len(set(labels)) != len(labels):
            rep.fail("Q_OPTION_DUPLICATE", where, "选项标签重复，选项必须互斥。")
        for option in options:
            if not _text_ok(option.get("consequence"), 4):
                rep.fail("Q_OPTION_CONSEQUENCE_MISSING", f"{where}.options[{option.get('label')}]", "每个选项都要写清后果。")
        recommended = str(q.get("recommended") or "").strip()
        if recommended not in labels:
            rep.fail("Q_RECOMMENDATION_INVALID", where, "推荐项必须是选项之一。")
        if not _text_ok(q.get("recommended_reason"), 4):
            rep.fail("Q_RECOMMENDATION_REASON_MISSING", where, "推荐要写理由和选错时的返工范围。")
        if not _text_ok(q.get("default_if_no_answer"), 4):
            rep.fail("Q_DEFAULT_MISSING", where, "要写用户不答时的默认动作（通常是重申风险后再问一次）。")
        if q.get("source_of_question") in {"recipe_default", "case_default"}:
            rep.fail("Q_FROM_RECIPE", where, "问题来源是配方/案例默认值，不是这次输入的观察；改成基于实际输入提问。")
        gate = q.get("gate")
        if gate not in {"G0", "G1", "G2"}:
            rep.fail("Q_GATE_INVALID", where, "gate 必须是 G0/G1/G2，用来证明提问发生在哪道门禁。")
        if q.get("major_branch") and q.get("batched_with"):
            rep.fail("Q_MAJOR_BRANCH_BATCHED", where, "重大分支必须当场单独问，不许和其他问题合并延迟（§2.5 G2）。")
        rounds[str(q.get("round", 1))] = rounds.get(str(q.get("round", 1)), 0) + 1
        topic = str(q.get("topic") or "").strip()
        if topic:
            if topic in seen_topics and _answered(_questions(card).get(seen_topics[topic])):
                rep.fail("Q_REPEATED", where, f"主题 {topic!r} 已在 {seen_topics[topic]} 回答过，不许重复问。")
            seen_topics.setdefault(topic, str(q.get("id")))
        if q.get("answer_kind") == "delegated" and q.get("follow_up_on_same_topic"):
            rep.fail("Q_ASK_AFTER_DELEGATED", where, "用户已答“你定”，不许继续追问同一项。")
    for round_id, count in rounds.items():
        if count > MAX_QUESTIONS_PER_ROUND:
            rep.fail("Q_ROUND_TOO_LARGE", f"round {round_id}", f"一轮最多 {MAX_QUESTIONS_PER_ROUND} 问，当前 {count} 问；拆成多轮。")


def check_parameters(card: dict[str, Any], rep: Report) -> None:
    """参数来源：关键项缺来源或来源无法追溯到提问 = 猜。"""
    questions = _questions(card)
    mode = card.get("mode")
    for index, item in enumerate(card.get("parameters", [])):
        name = str(item.get("name") or f"#{index}")
        where = f"parameters[{name}]"
        source = item.get("source")
        if source not in SOURCES:
            rep.fail("P_SOURCE_INVALID", where, f"来源必须是 {sorted(SOURCES)} 之一，当前 {source!r}。")
            continue
        if "value" not in item:
            rep.fail("P_VALUE_MISSING", where, "参数没有值。")
        critical = bool(item.get("critical"))
        if source == "derived" and not str(item.get("formula") or "").strip():
            rep.fail("P_DERIVED_NO_FORMULA", where, "derived 必须写推导公式。")
        if source == "standard" and not str(item.get("standard_ref") or "").strip():
            rep.fail("P_STANDARD_NO_REF", where, "standard 必须写标准号或系列（如 GB/T 5782 M6、6204）。")
        if source in SOURCES_NEED_ANSWER:
            question = questions.get(str(item.get("question_id")))
            if not _answered(question):
                rep.fail("P_ANSWER_UNTRACEABLE", where, f"{source} 必须指向一条已回答的提问（question_id）。")
        if source == "assumed" and critical:
            question = questions.get(str(item.get("question_id")))
            if not question or question.get("answer_kind") not in {"cannot_determine", "delegated"}:
                rep.fail(
                    "P_CRITICAL_GUESSED", where,
                    "关键尺寸标 assumed，但没有用户确认“确定不了/你定”的提问记录——这就是猜一个值先建着。",
                )
        if source == "estimated":
            if mode == "B" and critical:
                rep.fail("P_ESTIMATED_IN_B", where, "B 模式的关键尺寸不能只靠图片估读；要问用户或标明转为示意。")
            if not str(item.get("estimate_basis") or "").strip():
                rep.fail("P_ESTIMATE_NO_BASIS", where, "estimated 要写估读依据（参照物、像素比例、标尺）。")
        if mode == "A" and critical and source in SOURCES_NEED_ANSWER and not item.get("question_id"):
            rep.warn("P_A_MODE_NUMBER", where, "A 模式不问具体数值；确认这条提问是在问结构而不是数值。")


def check_gates(card: dict[str, Any], stage: str, rep: Report) -> None:
    """G1：进入新阶段前 OpenQuestions 必须清空或已授权。"""
    open_items = [q for q in card.get("open_questions", []) if isinstance(q, dict) or isinstance(q, str)]
    blocking = []
    for item in open_items:
        if isinstance(item, str):
            blocking.append(item)
        elif not item.get("authorized_to_proceed") and item.get("blocks_stage", stage) in STAGES[: STAGES.index(stage) + 1]:
            blocking.append(str(item.get("topic") or item))
    if blocking:
        rep.fail("G1_OPEN_QUESTIONS", "open_questions", f"进入 {stage} 阶段前仍有未决问题：{blocking}。先问清或拿到用户授权。")
    recorded = {str(g.get("stage")) for g in card.get("stage_gates", []) if isinstance(g, dict)}
    for previous in STAGES[1: STAGES.index(stage) + 1]:
        if previous in card.get("stages_entered", []) and previous not in recorded:
            rep.fail("G1_GATE_NOT_RECORDED", f"stage_gates[{previous}]", f"进入 {previous} 阶段时没有记录 G1 重扫。")


def check_delivery(card: dict[str, Any], rep: Report) -> None:
    """CHECKPOINT 3：交付说明必须列出假设、未测项、实际跑过的检查。"""
    handoff = card.get("handoff") or {}
    params = card.get("parameters", [])
    listed = {str(name) for name in handoff.get("assumptions_listed", [])}
    for item in params:
        if item.get("source") in {"assumed", "estimated", "user_delegated"} and str(item.get("name")) not in listed:
            rep.fail(
                "H_ASSUMPTION_HIDDEN", f"parameters[{item.get('name')}]",
                f"{item.get('source')} 参数没有出现在交付说明的 assumptions_listed 里；隐瞒来源是黑名单项。",
            )
    checks = [c for c in handoff.get("checks_run", []) if isinstance(c, dict)]
    if not checks:
        rep.fail("H_NO_CHECKS", "handoff.checks_run", "交付说明没有列出实际跑过的检查（命令/阈值/结果）。")
    for check in checks:
        where = f"handoff.checks_run[{check.get('name')}]"
        if check.get("result") not in {"pass", "fail", "not_run"}:
            rep.fail("H_CHECK_RESULT_INVALID", where, "检查结果必须是 pass / fail / not_run。")
        if check.get("result") == "pass" and not str(check.get("evidence") or "").strip():
            rep.fail("H_PASS_WITHOUT_EVIDENCE", where, "标 pass 的检查必须给出证据路径或回读数值；没算出来不是通过。")
        if check.get("result") == "fail" and not check.get("disclosed"):
            rep.fail("H_FAIL_UNDISCLOSED", where, "失败的检查必须在交付说明里如实写出。")
    if "untested" not in handoff:
        rep.fail("H_UNTESTED_MISSING", "handoff.untested", "要明确列出未验证的要求（可以是空列表，但字段必须存在）。")
    if card.get("deliverables") and not handoff.get("files"):
        rep.fail("H_FILES_MISSING", "handoff.files", "交付说明缺文件路径清单。")
    if "drawing" in [str(d).lower() for d in card.get("deliverables", [])] or "slddrw" in [str(d).lower() for d in card.get("deliverables", [])]:
        if not handoff.get("drawing_check_report"):
            rep.fail(
                "H_DRAWING_NOT_CHECKED", "handoff.drawing_check_report",
                "交付工程图时必须附 check_drawing_pdf.py 的报告路径（文字悬空/重叠/越界检查）。",
            )


def check_card(card: dict[str, Any], stage: str) -> dict[str, Any]:
    rep = Report()
    check_object_and_mode(card, rep)
    check_question_quality(card, rep)
    check_parameters(card, rep)
    check_gates(card, stage, rep)
    if stage == "delivery":
        check_delivery(card, rep)
    return {
        "status": rep.status,
        "stage": stage,
        "fail_count": sum(1 for f in rep.findings if f["severity"] == "fail"),
        "warn_count": sum(1 for f in rep.findings if f["severity"] == "warn"),
        "findings": rep.findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 SolidWorks++ 任务卡/提问记录/交付说明")
    parser.add_argument("card", help="task_card.json 路径")
    parser.add_argument("--stage", choices=STAGES, default="model", help="即将进入的阶段；交付前用 delivery")
    parser.add_argument("--strict", action="store_true", help="warn 也返回非零")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    args = parser.parse_args(argv)
    try:
        card = json.loads(Path(args.card).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[error] 无法读取任务卡: {exc}", file=sys.stderr)
        return 3
    result = check_card(card, args.stage)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{result['status']}] stage={args.stage} fail={result['fail_count']} warn={result['warn_count']}")
        for item in result["findings"]:
            print(f"  {item['severity']:4} {item['code']:30} {item['where']}: {item['message']}")
    if result["status"] == "fail":
        return 2
    if result["status"] == "warn" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
