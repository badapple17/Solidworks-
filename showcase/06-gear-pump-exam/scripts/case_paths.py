# -*- coding: utf-8 -*-
"""06 齿轮油泵实例的可移植路径与技能目录发现。

用法：每个建造脚本在 import 第三方模块之前先执行

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import case_paths

它会：
1. 找到 solidworks-plus-plus 技能脚本目录并加入 sys.path；
2. 定义本实例的输入/交付/预览/证据目录并确保存在。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CASE = Path(__file__).resolve().parents[1]
INPUTS = CASE / "inputs"
STD = INPUTS / "标准件"
OUT = CASE / "deliverables"
PARTS = OUT / "parts"
ASM = OUT / "assembly"
PREVIEWS = CASE / "previews"
EVIDENCE = CASE / "evidence"
WORK = CASE / "work"


def _find_skill_dir() -> Path:
    override = (
        os.environ.get("SOLIDWORKS_PLUS_PLUS_SKILL_DIR")
        or os.environ.get("SOLIDWORKS_MODELING_SKILL_DIR")
    )
    here = Path(__file__).resolve()
    candidates = [Path(override).expanduser() if override else None]
    # 仓库布局 <repo>/showcase/<case>/scripts/ 与发布包布局都从任意祖先目录找
    for parent in here.parents:
        for rel in (
            ("skills", "solidworks-plus-plus"),
            ("solidworks-plus-plus",),
            # 旧名回退：升级前安装的目录仍可用
            ("skills", "solidworks-modeling"),
            ("solidworks-modeling",),
        ):
            candidates.append(parent.joinpath(*rel))
    home = Path.home()
    for base in (".claude", ".codex", ".agents"):
        for name in ("solidworks-plus-plus", "solidworks-modeling"):
            candidates.append(home / base / "skills" / name)
    for candidate in candidates:
        if candidate and (candidate / "scripts" / "sw_session.py").is_file():
            return candidate.resolve()
    raise SystemExit(
        "找不到 solidworks-plus-plus 技能目录；"
        "请设置 SOLIDWORKS_PLUS_PLUS_SKILL_DIR（或旧名 "
        "SOLIDWORKS_MODELING_SKILL_DIR）指向技能根目录。"
    )


SKILL = _find_skill_dir() / "scripts"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

for _path in (INPUTS, PARTS, ASM, PREVIEWS, EVIDENCE, WORK):
    _path.mkdir(parents=True, exist_ok=True)
