"""Add real sketch dimensions to the gear hub sketch (diameters) for drawing import."""

from __future__ import annotations

import os
import sys
from pathlib import Path

def _find_skill_dir() -> Path:
    override = (
        os.environ.get("SOLIDWORKS_PLUS_PLUS_SKILL_DIR")
        or os.environ.get("SOLIDWORKS_MODELING_SKILL_DIR")
    )
    here = Path(__file__).resolve()
    candidates = [
        Path(override).expanduser() if override else None,
        here.parents[2] / "skills" / "solidworks-plus-plus",  # 仓库布局 <repo>/showcase/<case>/
        here.parents[2] / "solidworks-plus-plus",  # 发布包布局 <release>/showcase/<case>/
        Path.home() / ".claude" / "skills" / "solidworks-plus-plus",
        Path.home() / ".codex" / "skills" / "solidworks-plus-plus",
        Path.home() / ".agents" / "skills" / "solidworks-plus-plus",
        # 旧名回退：升级前安装的目录仍可用
        here.parents[2] / "solidworks-modeling",
        Path.home() / ".claude" / "skills" / "solidworks-modeling",
        Path.home() / ".codex" / "skills" / "solidworks-modeling",
        Path.home() / ".agents" / "skills" / "solidworks-modeling",
    ]
    for candidate in candidates:
        if candidate and (candidate / "scripts" / "sw_session.py").is_file():
            return candidate.resolve()
    raise SystemExit(
        "找不到 solidworks-plus-plus 技能目录；"
        "请设置 SOLIDWORKS_PLUS_PLUS_SKILL_DIR（或旧名 "
        "SOLIDWORKS_MODELING_SKILL_DIR）指向技能根目录。"
    )


SKILL_DIR = _find_skill_dir()
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from sw_connect import get_com_member, safe_get_com_member  # noqa: E402
from sw_part import _empty_callout, auto_dimension_sketch  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


def feature_dims(feature) -> list[dict]:
    dims = []
    display = safe_get_com_member(feature, "GetFirstDisplayDimension")
    guard = 0
    while display and guard < 200:
        guard += 1
        record = {}
        dim = safe_get_com_member(display, "GetDimension")
        if dim is not None:
            record["full_name"] = safe_get_com_member(dim, "FullName")
            try:
                record["value_mm"] = round(float(get_com_member(dim, "SystemValue")) * 1000.0, 6)
            except Exception:
                pass
        text = safe_get_com_member(display, "GetText", 0)
        if text:
            record["text"] = str(text)
        if record:
            dims.append(record)
        display = (safe_get_com_member(display, "GetNext3")
                   or safe_get_com_member(display, "GetNext"))
    return dims


def main() -> int:
    part = Path(sys.argv[1])
    out = Path(sys.argv[2])
    session = SolidWorksSession(visible=True)
    model = session.open(str(part), read_only=False, silent=False)
    if model is None:
        raise SystemExit("open failed")

    sketches = []
    feature = safe_get_com_member(model, "FirstFeature")
    guard = 0
    while feature and guard < 2000:
        guard += 1
        type_name = (safe_get_com_member(feature, "GetTypeName2")
                     or safe_get_com_member(feature, "GetTypeName"))
        if type_name == "ProfileFeature":
            sketches.append(feature)
        feature = safe_get_com_member(feature, "GetNextFeature")

    print("sketches:", [(safe_get_com_member(s, "Name"), feature_dims(s)) for s in sketches])
    if len(sketches) < 2:
        raise SystemExit("expected two sketches")

    target = sketches[-1]  # hub annulus: outer D36 + bore D20
    name = safe_get_com_member(target, "Name")
    model.ClearSelection2(True)
    selected = bool(model.Extension.SelectByID2(
        name, "SKETCH", 0.0, 0.0, 0.0, False, 0, _empty_callout(), 0))
    print("selected:", name, selected)
    if not selected:
        raise SystemExit("could not select hub sketch")

    # SW2023 返回 None 也可能已进入草图，以 ActiveSketch 为准。
    model.EditSketch()
    active = safe_get_com_member(model.SketchManager, "ActiveSketch")
    active_name = safe_get_com_member(active, "Name") if active is not None else None
    print("active sketch:", active_name)
    if active_name != name:
        raise SystemExit(f"could not edit sketch (active={active_name})")

    result = auto_dimension_sketch(model)
    print("auto_dimension:", result)
    model.SketchManager.InsertSketch(True)
    model.ForceRebuild3(False)

    after = feature_dims(target)
    print("hub dims after:", after)
    if result.get("status") != "pass" or not after:
        raise SystemExit("auto dimension did not create usable dimensions")

    saved = session.save(model, str(out))
    print("saved:", saved, out.exists(), out.stat().st_size if out.exists() else 0)
    session.close(model=model)
    return 0 if saved and out.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
