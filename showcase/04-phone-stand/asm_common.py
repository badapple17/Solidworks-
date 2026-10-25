# -*- coding: utf-8 -*-
"""装配用工具：项目侧薄封装，实际实现都在 skill 的 sw_assembly.py（本项目验证后回灌）。"""

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

from sw_assembly import (  # noqa: E402
    SW_MATE_ANGLE,
    SW_MATE_ALIGN_ALIGNED as SW_ALIGN_ALIGNED,
    SW_MATE_ALIGN_ANTI as SW_ALIGN_ANTI,
    SW_MATE_ALIGN_CLOSEST as SW_ALIGN_CLOSEST,
    add_mate5_checked, select_entities_for_mate, find_largest_cylinder_face,
    find_planar_face, find_face_by_normal, find_cylinder_face_at, get_component_pose,
)

# swMateAlign_e 实测（probe_align2.py，干净位姿）：同心用 CLOSEST(2) 才保持原位；
# ALIGNED(0) 把转盘绕横轴翻 180°，ANTI(1) 把销翻 180°。两平面面对面贴合用 ANTI(1)。


def mate(asm, mtype, e1, e2, align=0, angle=0.0, distance=0.0,
         lock_rotation=False, name=None):
    select_entities_for_mate(asm, e1, e2, mark=1)
    return add_mate5_checked(asm, mtype, align=align, angle=angle,
                             distance=distance, lock_rotation=lock_rotation,
                             name=name)


def comp_pose(component):
    """返回 (平移 mm, 旋转矩阵 3x3)。"""
    pos, rot = get_component_pose(component)
    return tuple(v * 1000 for v in pos), rot


def comp_bbox(component):
    """组件在装配坐标系里的包围盒（mm）：(xmin,ymin,zmin,xmax,ymax,zmax)。"""
    return tuple(v * 1000 for v in component.GetBox(False, False))


def cyl(component, r_min_mm, r_max_mm, at=None):
    """按半径范围取圆柱面；at=("z", 92.0) 时再按轴心在 z=92 附近过滤。"""
    if at is None:
        return find_largest_cylinder_face(component, r_min_mm / 1000.0, r_max_mm / 1000.0)
    axis, coord_mm = at
    return find_cylinder_face_at(component, r_min_mm / 1000.0, r_max_mm / 1000.0,
                                 axis, coord_mm / 1000.0)
