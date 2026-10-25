"""@brief 技能自身一致性检查：版本说法、description、用例计数、引用文件。

SKILL.md、capabilities.yaml、test-prompts.json 三处最容易各说各话：
“仅 2023 实测”与“已验证 2024/2026”矛盾、description 写成功能清单、
“6 个黄金用例”对不上实际数量、引用的参考文件已经改名。本脚本把这些
变成可检查项，不连接 SolidWorks：

    py -3.12 <skill>/scripts/check_skill_consistency.py
    py -3.12 <skill>/scripts/check_skill_consistency.py --json --strict

返回码：0 = pass，1 = warn（仅 --strict），2 = fail，3 = 文件不可读。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL_MD = SKILL_DIR / "SKILL.md"
CAPABILITIES = SKILL_DIR / "capabilities.yaml"
TEST_PROMPTS = SKILL_DIR / "test-prompts.json"

SKILL_NAME = "solidworks-plus-plus"
REQUIRED_TRIGGERS = ("SolidWorks", "建模", "出图", "SLDPRT")
NEGATIVE_MARKERS = ("不适用", "不用于", "不处理")
LOCAL_VERSION_QUALIFIERS = ("上游", "继承", "未复测", "pilot")
VALID_LEVELS = {"verified", "pilot", "reference_only", "not_implemented"}
PATH_PATTERN = re.compile(r"`((?:references|scripts|subskills)/[^`\s]+)`")
COUNT_PATTERN = re.compile(r"(\d+)\s*个可重复验收用例[（(]\s*(\d+)\s*个黄金")


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


def _read_text(path: Path, rep: Report, label: str) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        rep.fail("FILE_UNREADABLE", label, f"读不了 {path}: {exc}")
        return None


def _load_json(path: Path, rep: Report, label: str) -> dict[str, Any] | None:
    """capabilities.yaml 是 JSON-compatible YAML，可直接 json 解析。"""
    text = _read_text(path, rep, label)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except ValueError as exc:
        rep.fail("JSON_INVALID", label, f"{path.name} 不是合法 JSON-compatible YAML: {exc}")
        return None
    return payload if isinstance(payload, dict) else None


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[match.group(1)] = value
    return result


def check_frontmatter(text: str, rep: Report, max_description: int) -> None:
    meta = parse_frontmatter(text)
    if not meta:
        rep.fail("FM_MISSING", "SKILL.md", "缺 frontmatter（--- name/description ---）。")
        return
    name = meta.get("name", "")
    if name != SKILL_NAME:
        rep.fail("FM_NAME_MISMATCH", "SKILL.md:name", f"name 应为 {SKILL_NAME!r}，当前 {name!r}。")
    description = meta.get("description", "")
    if not description:
        rep.fail("FM_DESCRIPTION_MISSING", "SKILL.md:description", "description 为空。")
        return
    if len(description) > max_description:
        rep.fail(
            "FM_DESCRIPTION_TOO_LONG", "SKILL.md:description",
            f"description {len(description)} 字，超过上限 {max_description}；写成触发词 + 用途 + 不适用场景，不要功能清单。",
        )
    missing = [word for word in REQUIRED_TRIGGERS if word not in description]
    if missing:
        rep.fail(
            "FM_TRIGGERS_MISSING", "SKILL.md:description",
            f"description 缺触发词：{missing}；用户说“SolidWorks 建模、出图、SLDPRT”时必须能命中。",
        )
    if not any(marker in description for marker in NEGATIVE_MARKERS):
        rep.warn(
            "FM_NO_NEGATIVE_TRIGGER", "SKILL.md:description",
            "description 没写“不适用”场景；容易在非 SolidWorks CAD 请求上误触发。",
        )


def check_versions(text: str, caps: dict[str, Any], rep: Report) -> None:
    policy = caps.get("version_policy")
    if not isinstance(policy, dict):
        rep.fail("CAP_VERSION_POLICY_MISSING", "capabilities.yaml", "缺 version_policy；版本说法没有唯一口径。")
    verified = (caps.get("verified_versions") or {}).get("solidworks") or []
    upstream = (caps.get("upstream_verified_versions") or {}).get("solidworks") or []
    if "2023" not in verified:
        rep.fail("CAP_LOCAL_2023_MISSING", "capabilities.yaml:verified_versions",
                 "本机唯一实测版本 2023 不在 verified_versions 里。")
    overlap = set(verified) & set(upstream)
    if overlap:
        rep.fail(
            "CAP_VERSION_OVERLAP", "capabilities.yaml",
            f"{sorted(overlap)} 同时出现在 verified_versions 和 upstream_verified_versions；"
            "本仓库没复测的版本不能算本仓库实测。",
        )
    capability_ids: list[str] = []
    for index, item in enumerate(caps.get("capabilities") or []):
        if not isinstance(item, dict):
            rep.fail("CAP_ENTRY_INVALID", f"capabilities[{index}]", "能力条目不是对象。")
            continue
        cap_id = str(item.get("id") or "")
        if not cap_id:
            rep.fail("CAP_ID_MISSING", f"capabilities[{index}]", "能力条目没有 id。")
        capability_ids.append(cap_id)
        level = item.get("level")
        if level not in VALID_LEVELS:
            rep.fail("CAP_LEVEL_INVALID", f"capabilities[{cap_id or index}]",
                     f"level 必须是 {sorted(VALID_LEVELS)}，当前 {level!r}。")
        local = item.get("verified_versions")
        upstream_item = item.get("upstream_verified_versions")
        if isinstance(local, list):
            extra = [v for v in local if v not in verified]
            if extra:
                rep.fail(
                    "CAP_LOCAL_VERSION_UNLISTED", f"capabilities[{cap_id}]",
                    f"verified_versions {extra} 不在全局 verified_versions {verified} 里；“已实测”必须有本机证据。",
                )
        if isinstance(upstream_item, list):
            for version in upstream_item:
                text_version = str(version)
                # 原样字符串（如 "OCP 7.9.3.1.1"、"CalculiX 2.23"）属于后端库版本，
                # 不走 SolidWorks 年份口径；这里只核对四年份。
                if not re.fullmatch(r"\d{4}", text_version):
                    continue
                if version not in verified and version not in upstream:
                    rep.fail(
                        "CAP_UPSTREAM_VERSION_UNLISTED", f"capabilities[{cap_id}]",
                        f"upstream_verified_versions {version!r} 既不在本机实测也不在上游继承列表里。",
                    )
    if len(set(capability_ids)) != len(capability_ids):
        rep.fail("CAP_ID_DUPLICATE", "capabilities.yaml", "能力 id 重复。")

    if "2023" not in text or "实测" not in text:
        rep.fail("SKILL_VERSION_LINE_MISSING", "SKILL.md §0",
                 "SKILL.md 没写清 2023 是本机实测版本。")
    for line_no, line in enumerate(text.splitlines(), 1):
        if not re.search(r"\b(2024|2026)\b", line):
            continue
        if "实测" not in line:
            continue
        if any(word in line for word in LOCAL_VERSION_QUALIFIERS):
            continue
        rep.fail(
            "SKILL_VERSION_OVERCLAIM", f"SKILL.md:{line_no}",
            "同一行把 2024/2026 和“实测”写在一起，却没有标“上游/继承/未复测/pilot”；"
            "会被读成本仓库已实测这些版本。",
        )


def check_test_prompts(text: str, prompts: dict[str, Any], rep: Report) -> None:
    cases = prompts.get("cases")
    if not isinstance(cases, list) or not cases:
        rep.fail("TP_CASES_MISSING", "test-prompts.json", "没有 cases 数组。")
        return
    ids = [str(case.get("id") or "") for case in cases if isinstance(case, dict)]
    if "" in ids or len(set(ids)) != len(ids):
        rep.fail("TP_IDS_INVALID", "test-prompts.json", "用例 id 有空值或重复。")
    golden = [str(case.get("id")) for case in cases if isinstance(case, dict) and case.get("golden")]
    match = COUNT_PATTERN.search(text)
    if not match:
        rep.warn("TP_COUNT_NOT_DECLARED", "SKILL.md §8",
                 "SKILL.md 没写“N 个可重复验收用例（M 个黄金）”，无法核对计数。")
    else:
        declared_total, declared_golden = int(match.group(1)), int(match.group(2))
        if declared_total != len(cases):
            rep.fail("TP_TOTAL_MISMATCH", "SKILL.md §8",
                     f"SKILL.md 声明 {declared_total} 个用例，实际 {len(cases)} 个。")
        if declared_golden != len(golden):
            rep.fail("TP_GOLDEN_MISMATCH", "SKILL.md §8",
                     f"SKILL.md 声明 {declared_golden} 个黄金用例，实际标记 golden 的 {len(golden)} 个。")
    for case_id in golden:
        if case_id and case_id not in text:
            rep.warn("TP_GOLDEN_NOT_LISTED", "SKILL.md §5",
                     f"黄金用例 {case_id} 没有出现在 SKILL.md 的验收清单里。")
    env = prompts.get("environment") or {}
    if "2023" not in str(env.get("solidworks", "")):
        rep.warn("TP_ENV_VERSION", "test-prompts.json:environment",
                 "用例环境没写 SolidWorks 2023（本机实测基线）。")


def check_referenced_paths(text: str, rep: Report) -> None:
    seen: set[str] = set()
    for match in PATH_PATTERN.finditer(text):
        raw = match.group(1).split("#")[0].strip()
        if raw in seen:
            continue
        seen.add(raw)
        target = SKILL_DIR / raw
        if target.is_dir():
            continue
        if not target.is_file():
            rep.fail("REF_PATH_MISSING", "SKILL.md",
                     f"引用的路径不存在：{raw}（改名或删除后没同步文档）。")


def check_skill_dir(rep: Report, max_description: int = 500) -> dict[str, Any]:
    text = _read_text(SKILL_MD, rep, "SKILL.md")
    caps = _load_json(CAPABILITIES, rep, "capabilities.yaml")
    prompts = _load_json(TEST_PROMPTS, rep, "test-prompts.json")
    if text is not None:
        check_frontmatter(text, rep, max_description)
        check_referenced_paths(text, rep)
    if text is not None and caps is not None:
        check_versions(text, caps, rep)
    if text is not None and prompts is not None:
        check_test_prompts(text, prompts, rep)
    return {
        "status": rep.status,
        "skill_dir": str(SKILL_DIR),
        "fail_count": sum(1 for f in rep.findings if f["severity"] == "fail"),
        "warn_count": sum(1 for f in rep.findings if f["severity"] == "warn"),
        "findings": rep.findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查 SolidWorks++ 技能自身一致性")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    parser.add_argument("--strict", action="store_true", help="warn 也返回非零")
    parser.add_argument("--max-description", type=int, default=500, help="description 字数上限（默认 500）")
    args = parser.parse_args(argv)
    result = check_skill_dir(Report(), args.max_description)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"[{result['status']}] dir={result['skill_dir']} "
              f"fail={result['fail_count']} warn={result['warn_count']}")
        for item in result["findings"]:
            print(f"  {item['severity']:4} {item['code']:32} {item['where']}: {item['message']}")
    if result["status"] == "fail":
        return 2
    if result["status"] == "warn" and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
