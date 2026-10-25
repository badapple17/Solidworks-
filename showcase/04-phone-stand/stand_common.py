# -*- coding: utf-8 -*-
"""手机支架逆向建模公共工具：单位换算、几何校验、外观着色。"""

import math
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


SKILL = _find_skill_dir() / "scripts"
if str(SKILL) not in sys.path:
    sys.path.insert(0, str(SKILL))

from sw_connect import mm, deg, safe_get_com_member  # noqa: E402
from sw_review import collect_geometry_measurements  # noqa: E402
from sw_appearance import (  # noqa: E402
    set_feature_appearance, set_document_appearance,
)

OUT = Path(__file__).parent / "deliverables"
OUT.mkdir(exist_ok=True)

# 统一配色（RGB 0-255）
C_BODY = (58, 58, 63)        # 深灰主体
C_METAL = (120, 122, 128)    # 转盘 / 销轴
C_RUBBER = (150, 150, 148)   # 脚垫 / 硅胶垫
C_SCREW = (170, 170, 175)    # 螺钉


def annulus_sector(cx, cy, r_out, r_in, a0_deg, a1_deg):
    """返回闭合环扇形的点序列（外弧 -> 内弧），用于逐段画线。"""
    a0, a1 = math.radians(a0_deg), math.radians(a1_deg)
    pts = []
    return {
        "outer": ((cx + r_out * math.cos(a0), cy + r_out * math.sin(a0)),
                  (cx + r_out * math.cos(a1), cy + r_out * math.sin(a1))),
        "inner": ((cx + r_in * math.cos(a1), cy + r_in * math.sin(a1)),
                  (cx + r_in * math.cos(a0), cy + r_in * math.sin(a0))),
        "a0": a0, "a1": a1, "cx": cx, "cy": cy, "r_out": r_out, "r_in": r_in,
        "pts": pts,
    }


def draw_annulus_sector(part, spec):
    """在活动草图里画一个闭合环扇形。圆弧用 sketch_arc，半径边用 sketch_line。"""
    from sw_part import sketch_arc, sketch_line
    cx, cy = spec["cx"], spec["cy"]
    o0, o1 = spec["outer"]
    i1, i0 = spec["inner"]
    sketch_arc(part, cx, cy, o0[0], o0[1], o1[0], o1[1], direction=1)
    sketch_line(part, o1[0], o1[1], i1[0], i1[1])
    sketch_arc(part, cx, cy, i1[0], i1[1], i0[0], i0[1], direction=-1)
    sketch_line(part, i0[0], i0[1], o0[0], o0[1])


def measure(part):
    return collect_geometry_measurements(part)


def body_count(part):
    return len(safe_get_com_member(part, "GetBodies2", 0, False) or [])


def check(part, label, exp_bbox, exp_volume=None, exp_bodies=1, tol_bbox=0.05, tol_vol=0.002):
    """校验包围盒 / 体积 / 实体数，返回 dict 并在控制台打印。"""
    m = measure(part)
    env = m.get("envelope_mm") or {}
    actual = (env.get("length"), env.get("width"), env.get("height"))
    vol = m.get("volume_mm3")
    bodies = body_count(part)

    bbox_ok = all(
        a is not None and abs(a - e) <= max(0.05, abs(e) * tol_bbox)
        for a, e in zip(actual, exp_bbox)
    )
    vol_err = None
    vol_ok = True
    if exp_volume:
        vol_err = abs(vol - exp_volume) / exp_volume
        vol_ok = vol_err <= tol_vol
    bodies_ok = bodies == exp_bodies

    print(f"\n=== {label} ===")
    print(f"  bbox  实测 {tuple(round(v, 3) if v else v for v in actual)}  期望 {exp_bbox}  "
          f"{'OK' if bbox_ok else 'FAIL'}")
    print(f"  volume 实测 {round(vol, 2) if vol else vol} mm3  期望 "
          f"{round(exp_volume, 2) if exp_volume else '-'}  err="
          f"{f'{vol_err*100:.3f}%' if vol_err is not None else '-'}  "
          f"{'OK' if vol_ok else 'FAIL'}")
    print(f"  bodies 实测 {bodies}  期望 {exp_bodies}  {'OK' if bodies_ok else 'FAIL'}")
    if not (bbox_ok and vol_ok and bodies_ok):
        issues = []
        if not bbox_ok:
            issues.append("bbox")
        if not vol_ok:
            issues.append("volume")
        if not bodies_ok:
            issues.append("bodies")
        raise RuntimeError(f"{label} 校验失败: {', '.join(issues)}")
    return {"bbox": actual, "volume": vol, "bodies": bodies, "measurements": m}


def color(feature, rgb, label=""):
    ok = set_feature_appearance(feature, rgb)
    print(f"  外观 {label or getattr(feature, 'Name', '?')} -> {rgb} {'OK' if ok else 'FAIL'}")
    return ok


def color_part(part, rgb, label=""):
    """整件着色：文档级接口，带回读验证（特征级回读在本机 SW2023 上不可靠）。"""
    ok = set_document_appearance(part, rgb)
    print(f"  外观 {label or '?'} -> {rgb} {'OK' if ok else 'FAIL'}")
    return ok
