"""Probe how IComponent2 transforms actually take effect (SW2023 late binding).

Answers three questions with one variable at a time:
  1. does ArrayData translation use metres or millimetres?
  2. is `Transform2 = xf` enough, or is SetTransformAndSolve2 required?
  3. does a rotation matrix survive?
"""
from __future__ import annotations

import sys

from common import PARTS, bbox_mm

from sw_assembly import add_component
from sw_session import SolidWorksSession


def pose(comp):
    d = [float(v) for v in comp.Transform2.ArrayData]
    return [round(v, 6) for v in d]


def set_array(comp, data, solve):
    xf = comp.Transform2
    xf.ArrayData = data
    if solve:
        try:
            return bool(comp.SetTransformAndSolve2(xf))
        except Exception as exc:
            return f"err {exc}"
    comp.Transform2 = xf
    return "assigned"


def data_tx(tx, ty, tz, R=None):
    R = R or ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    out = []
    for row in R:
        out.extend(float(v) for v in row)
    out.extend([float(tx), float(ty), float(tz), 1.0, 0.0, 0.0, 0.0])
    return out


def main() -> int:
    session = SolidWorksSession(visible=True)
    sw = session.sw
    try:
        sw.CloseAllDocuments(True)
        asm = session.new_assembly()
        comp = add_component(asm, str(PARTS / "04_steel_ball.SLDPRT"), 0, 0, 0, sw=sw)
        asm.ForceRebuild3(False)
        print("start bbox:", bbox_mm(asm))
        print("start pose:", pose(comp))

        print("\n-- A: metres, SetTransformAndSolve2 --")
        print("ret:", set_array(comp, data_tx(0.010, 0.020, 0.030), True))
        asm.ForceRebuild3(False)
        print("pose:", pose(comp))
        print("bbox:", bbox_mm(asm))

        print("\n-- B: millimetres, SetTransformAndSolve2 --")
        print("ret:", set_array(comp, data_tx(10.0, 20.0, 30.0), True))
        asm.ForceRebuild3(False)
        print("pose:", pose(comp))
        print("bbox:", bbox_mm(asm))

        print("\n-- C: 90 deg about X, metres --")
        Rx = ((1, 0, 0), (0, 0, -1), (0, 1, 0))
        print("ret:", set_array(comp, data_tx(0.5, 0.0, 0.0, Rx), True))
        asm.ForceRebuild3(False)
        print("pose:", pose(comp))
        print("bbox:", bbox_mm(asm))

        print("\n-- D: assign Transform2 only (no solve) --")
        xf = comp.Transform2
        xf.ArrayData = data_tx(0.0, 0.0, 0.0)
        comp.Transform2 = xf
        asm.ForceRebuild3(False)
        print("pose:", pose(comp))
        print("bbox:", bbox_mm(asm))
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
