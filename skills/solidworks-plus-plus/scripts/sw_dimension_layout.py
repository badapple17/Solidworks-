"""GB 风格尺寸排布：按尺寸类型、朝向和测量位置分配版面。

旧实现（sw_drawing.arrange_dimension_positions）把视图里的所有尺寸按插入顺序
塞进左侧/右侧两列。齿轮实测的后果：
- φ20 与 φ36 两条直径尺寸落在同一列同一行，引出线沿一条水平线横穿齿顶圆；
- 竖直尺寸不看被测点在哪，尺寸界线从视图另一侧横穿整个视图；
- 同侧尺寸不分层，文字和尺寸线互相压。

本模块按人类标注的三条规则重排（依据 references/dimension-layout.md）：

1. **就近放置**：竖直尺寸按被测点 x 放左/右，水平尺寸按被测点 y 放上/下，
   尺寸界线只走最短的一小段，不横穿视图。
2. **小内大外、按层排布**：同一侧按跨度升序找层，跨度区间重叠才外移一层；
   层距 8 mm，首层距轮廓 8 mm（GB：平行尺寸线 5–8 mm，最小 ≥7 mm）。
3. **直径放射布置**：直径/半径尺寸从圆心沿 45°/135°/… 引出，文字落在
   “圆外且视图轮廓外”，多个直径自动换角度，不再共线。

坐标一律用毫米做规划，落到 COM 前再换算成米；IAnnotation.GetPosition 在
SW2023 动态代理下是属性（tuple），不是方法，读取时必须按属性处理。
"""
from __future__ import annotations

import math

try:
    from .sw_connect import get_com_member  # noqa: F401  (保持与 sw_drawing 相同的依赖面)
except ImportError:
    from sw_connect import get_com_member  # noqa: F401

# swDimensionType_e（SolidWorks.Interop.swconst.dll 反射确认，SW2023）
TYPE_UNKNOWN = 0
TYPE_ORDINATE = 1
TYPE_LINEAR = 2
TYPE_ANGULAR = 3
TYPE_ARC_LENGTH = 4
TYPE_RADIAL = 5
TYPE_DIAMETER = 6
TYPE_HOR_ORDINATE = 7
TYPE_VERT_ORDINATE = 8
TYPE_Z_AXIS = 9
TYPE_CHAMFER = 10
TYPE_HOR_LINEAR = 11
TYPE_VERT_LINEAR = 12
TYPE_SCALAR = 13
TYPE_RADIAL_LINEAR = 14
TYPE_DIAMETRIC_LINEAR = 15

_LINEAR_TYPES = {TYPE_LINEAR, TYPE_HOR_LINEAR, TYPE_VERT_LINEAR,
                 TYPE_HOR_ORDINATE, TYPE_VERT_ORDINATE, TYPE_SCALAR}
_CIRCULAR_TYPES = {TYPE_DIAMETER, TYPE_RADIAL}

# 直径/半径文字的候选引出角（度）。先 45° 象限，再 30°/60°，最后轴向。
_LEADER_ANGLES = (45.0, 135.0, 225.0, 315.0, 30.0, 150.0, 210.0, 330.0,
                  60.0, 120.0, 240.0, 300.0, 0.0, 90.0, 180.0, 270.0)

_TEXT_HEIGHT_MM = 3.5
_CHAR_WIDTH_MM = 2.4          # 3.5 号 GB 长仿宋数字宽约 2.4 mm
_MAX_LEVELS = 3               # 8 + 2×8 = 24 mm，仍在 PDF 检查器 25 mm 悬浮阈值内
_MIN_TEXT_GAP_MM = 2.0
_MIN_LEADER_MM = 10.0         # 文字离圆心/轮廓的最小引出长度


# --------------------------------------------------------------------------
# COM 读取：SW2023 的 pywin32 动态代理会把 propget 暴露成属性，
# 这里显式区分“读属性”和“调方法”，避免 getattr(...)() 把 tuple 当函数调。
# --------------------------------------------------------------------------

def _attr(obj, name, default=None):
    if obj is None:
        return default
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _call(obj, name, *args, default=None):
    """调方法；若该成员实际是 dispatch 属性且无参数，直接返回属性值。"""
    if obj is None:
        return default
    member = _attr(obj, name, None)
    if member is None:
        return default
    if not args and hasattr(member, "_oleobj_"):
        # SW2023 动态代理把 propget 暴露成 CDispatch；再调用会触发默认成员。
        return member
    try:
        return member(*args)
    except Exception:
        return default


def _value(obj, name, default=None):
    """读一个可能是属性、也可能是无参方法的成员。

    判据是 `_oleobj_`：CDispatch 属性带它，绑定方法不带。
    SW2023 的 GetAnnotation/GetDimension/GetPosition/ReferencePoints/
    ModelToViewTransform 全部属于前者，按方法调用会拿到 None 或错对象。
    """
    member = _attr(obj, name, None)
    if member is None:
        return default
    if hasattr(member, "_oleobj_"):
        return member
    if callable(member):
        try:
            return member()
        except Exception:
            return default
    return member


def _nums(value):
    """把 MathPoint/MathVector/COM 数组统一成浮点列表。"""
    if value is None:
        return []
    data = getattr(value, "ArrayData", None)
    if data is not None:
        value = data
    try:
        return [float(item) for item in value]
    except Exception:
        return []


def _position(annotation):
    """IAnnotation 的文字位置；SW2023 返回属性 tuple，其他版本可能是方法。"""
    value = _attr(annotation, "GetPosition")
    if value is None:
        return []
    if callable(value) and not isinstance(value, (tuple, list)):
        value = _call(annotation, "GetPosition")
    return _nums(value)


def _box(value):
    """Outline/GetBox → {left,bottom,right,top}（米）。"""
    values = _nums(value)
    if len(values) >= 6:
        x1, y1, x2, y2 = values[0], values[1], values[3], values[4]
    elif len(values) >= 4:
        x1, y1, x2, y2 = values[:4]
    else:
        return None
    return {"left": min(x1, x2), "bottom": min(y1, y2),
            "right": max(x1, x2), "top": max(y1, y2)}


def _box_mm(box):
    return {key: box[key] * 1000.0 for key in ("left", "bottom", "right", "top")}


def _display_text(type2, value_mm):
    """模型尺寸的 GetText 常为空，按类型和数值合成显示文本，用于估算字宽。"""
    if value_mm is None:
        return ""
    if type2 == TYPE_DIAMETER:
        return f"φ{value_mm:g}"
    if type2 == TYPE_RADIAL:
        return f"R{value_mm:g}"
    if type2 == TYPE_ANGULAR:
        return f"{value_mm:g}°"
    return f"{value_mm:g}"


def _text_width_mm(text):
    """估算尺寸数字占位宽度。

    GetText 对模型尺寸常为空，这里只能按字符数合成；SolidWorks 显示小数时
    会补尾零（模型值 4.5 常显示成 4.50），所以带小数点的文本多算一个字宽。
    """
    width = max(6.0, len(text) * _CHAR_WIDTH_MM)
    if "." in text:
        width += _CHAR_WIDTH_MM
    return width


def _rect(x, y, half_w, half_h):
    return (x - half_w, y - half_h, x + half_w, y + half_h)


def _overlap(a, b, gap=0.0):
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0]
                or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _inside(rect, box):
    """rect 与 box 是否相交（box 为 left/bottom/right/top，毫米）。"""
    return _overlap(rect, (box["left"], box["bottom"], box["right"], box["top"]))


def _exit_distance(center, angle_deg, box):
    """从 center 沿 angle 射出，到视图框边界的距离（毫米）。"""
    dx, dy = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    candidates = []
    if abs(dx) > 1e-9:
        for edge in (box["left"], box["right"]):
            t = (edge - center[0]) / dx
            if t > 0:
                candidates.append(t)
    if abs(dy) > 1e-9:
        for edge in (box["bottom"], box["top"]):
            t = (edge - center[1]) / dy
            if t > 0:
                candidates.append(t)
    return min(candidates) if candidates else 0.0


# --------------------------------------------------------------------------
# 单尺寸元数据
# --------------------------------------------------------------------------

class DimInfo:
    """一个 DisplayDimension 的排版输入。"""

    __slots__ = ("dd", "annotation", "type2", "value_mm", "text", "text_pos",
                 "refs", "kind", "p1", "p2", "span", "anchor", "horizontal",
                 "center", "radius", "current_ok")

    def __init__(self, dd, annotation, type2, value_mm, text, text_pos, refs):
        self.dd = dd
        self.annotation = annotation
        self.type2 = type2
        self.value_mm = value_mm
        self.text = text
        self.text_pos = text_pos
        self.refs = refs
        self.kind = "other"
        self.p1 = self.p2 = None
        self.span = 0.0
        self.anchor = (0.0, 0.0)
        self.horizontal = True
        self.center = None
        self.radius = 0.0
        self.current_ok = False

    def classify(self, view_scale):
        if self.type2 in _LINEAR_TYPES and len(self.refs) >= 2:
            best = None
            for i in range(len(self.refs)):
                for j in range(i + 1, len(self.refs)):
                    p1, p2 = self.refs[i], self.refs[j]
                    distance = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    if best is None or distance > best[0]:
                        best = (distance, p1, p2)
            if best and best[0] > 1e-6:
                self.kind = "linear"
                self.span, self.p1, self.p2 = best
                self.anchor = ((self.p1[0] + self.p2[0]) / 2.0,
                               (self.p1[1] + self.p2[1]) / 2.0)
                self.horizontal = abs(self.p2[0] - self.p1[0]) >= abs(self.p2[1] - self.p1[1])
                return
        if self.type2 in _CIRCULAR_TYPES:
            center = self._shared_point()
            if center is not None:
                self.kind = "circular"
                self.center = center
                measured = max((math.hypot(p[0] - center[0], p[1] - center[1])
                                for p in self.refs), default=0.0)
                if self.value_mm:
                    nominal = (self.value_mm / 2.0 if self.type2 == TYPE_DIAMETER
                               else self.value_mm) * view_scale
                else:
                    nominal = 0.0
                self.radius = measured if measured > 1e-6 else nominal
                return
        # 角度、倒角、弧长、坐标尺寸：按“从视图中心往外推”处理
        self.kind = "other"
        if self.refs:
            self.center = self.refs[0]
        elif len(self.text_pos) >= 2:
            self.center = (self.text_pos[0], self.text_pos[1])

    def _shared_point(self):
        """直径尺寸的三个参考点通常都落在圆心；返回这个公共点。"""
        if not self.refs:
            return None
        x0, y0 = self.refs[0][0], self.refs[0][1]
        for point in self.refs[1:]:
            if math.hypot(point[0] - x0, point[1] - y0) > 1e-3:
                return None
        return (x0, y0)


def _build_dim(dd, transform, view_scale):
    annotation = _value(dd, "GetAnnotation")
    dimension = _value(dd, "GetDimension")
    try:
        type2 = int(_value(dd, "Type2", TYPE_UNKNOWN))
    except (TypeError, ValueError):
        type2 = TYPE_UNKNOWN
    value_m = _call(dimension, "GetSystemValue2", "")
    try:
        value_mm = float(value_m) * 1000.0 if value_m is not None else None
    except (TypeError, ValueError):
        value_mm = None
    text = ""
    raw_text = _call(dd, "GetText", 0)
    if raw_text:
        text = str(raw_text)
    if not text:
        text = _display_text(type2, value_mm)

    text_pos = _position(annotation)
    if len(text_pos) < 2:
        text_pos = []
    else:
        text_pos = [text_pos[0] * 1000.0, text_pos[1] * 1000.0]

    refs = []
    points = _value(dimension, "ReferencePoints", None)
    for point in points or []:
        moved = point
        if transform is not None:
            try:
                moved = point.MultiplyTransform(transform)
            except Exception:
                moved = point
        values = _nums(moved)
        if len(values) >= 2:
            refs.append([values[0] * 1000.0, values[1] * 1000.0])

    info = DimInfo(dd, annotation, type2, value_mm, text, text_pos, refs)
    info.classify(view_scale)
    return info


# --------------------------------------------------------------------------
# 版面规划
# --------------------------------------------------------------------------

class Sheet:
    def __init__(self, width_mm, height_mm, margin_mm, title_block_mm):
        self.width = width_mm
        self.height = height_mm
        self.margin = margin_mm
        tb_w, tb_h = title_block_mm
        self.title_block = (width_mm - tb_w, 0.0, width_mm, tb_h)

    def limits(self, half_w, half_h):
        return (self.margin + half_w, self.margin + half_h,
                self.width - self.margin - half_w, self.height - self.margin - half_h)

    def fits(self, rect):
        if rect[0] < self.margin or rect[1] < self.margin:
            return False
        if rect[2] > self.width - self.margin or rect[3] > self.height - self.margin:
            return False
        return not _overlap(rect, self.title_block, gap=2.0)


def _preferred_side(info, box):
    center_x = (box["left"] + box["right"]) / 2.0
    center_y = (box["bottom"] + box["top"]) / 2.0
    if info.horizontal:
        return "top" if info.anchor[1] >= center_y else "bottom"
    return "right" if info.anchor[0] >= center_x else "left"


def _side_offset(side, box, level, offset_mm, pitch_mm):
    distance = offset_mm + level * pitch_mm
    if side == "top":
        return None, box["top"] + distance
    if side == "bottom":
        return None, box["bottom"] - distance
    if side == "left":
        return box["left"] - distance, None
    return box["right"] + distance, None


def _band_free(intervals, span_center, span_extent, text_center, text_extent):
    """同一层上既不能有重叠的尺寸线，也不能有重叠的数字。

    尺寸线重叠比数字重叠更隐蔽：两个尺寸同一层时，线完全共线，
    一条线会被另一条的箭头切断，读图时无法判断各自量的是哪一段。
    """
    for other_span, other_span_extent, other_text, other_text_extent in intervals:
        if abs(span_center - other_span) < (span_extent + other_span_extent) / 2.0 + 2.0:
            return False
        if abs(text_center - other_text) < (text_extent + other_text_extent) / 2.0 + _MIN_TEXT_GAP_MM:
            return False
    return True


def _clear_of_levels(center, half_len, levels, direction):
    """把数字沿尺寸线方向挪到不与任何尺寸界线相交的位置。

    小尺寸的数字如果只挪出自己那两条界线，仍会压在别的尺寸界线上
    （薄板叠尺寸实测：0.5 的数字正好被板底边界线穿过）。这里逐个跳过
    挡路的界线，直到数字两端都落在空档里。
    """
    for _ in range(8):
        lo, hi = center - half_len - 1.0, center + half_len + 1.0
        blockers = [level for level in levels if lo <= level <= hi]
        if not blockers:
            return center
        edge = max(blockers) if direction > 0 else min(blockers)
        center = edge + direction * (half_len + 3.0)
    return center


def _place_linear(info, box, sheet, bands, other_boxes, occupied, axis_levels,
                  offset_mm, pitch_mm):
    """在指定侧找一个不与已有尺寸线重叠的层，返回 (side, level, x, y)。

    GB 两条硬规则在这里落地：
    - 小尺寸在内、大尺寸在外：调用方按 span 升序送入，小尺寸先占内层。
    - 小尺寸数字放不进两条尺寸界线之间时，沿尺寸线方向把数字移到界线外
      （SolidWorks 的 SetPosition 只移动数字，箭头仍留在界线上）。
    """
    preferred = _preferred_side(info, box)
    text_len = _text_width_mm(info.text)
    if info.horizontal:
        half_w = text_len / 2.0
        half_h = _TEXT_HEIGHT_MM / 2.0 + 1.0
        along = info.anchor[0]
        axis_center = (box["left"] + box["right"]) / 2.0
    else:
        half_w = _TEXT_HEIGHT_MM / 2.0 + 1.0
        half_h = text_len / 2.0
        along = info.anchor[1]
        axis_center = (box["bottom"] + box["top"]) / 2.0
    span_extent = info.span + 4.0
    text_extent = text_len + 4.0

    # 数字长度超过尺寸线长度时，数字必然压住两条尺寸界线；沿尺寸线移到外侧，
    # 并继续跳过挡路的其他尺寸界线。
    if info.span + 2.0 < text_len:
        preferred_direction = 1.0 if along >= axis_center else -1.0
        free_centers = []
        for direction in (preferred_direction, -preferred_direction):
            start = along + direction * (info.span / 2.0 + text_len / 2.0 + 2.0)
            center = _clear_of_levels(start, text_len / 2.0, axis_levels, direction)
            if center not in free_centers:
                free_centers.append(center)
        free_centers.append(along)  # 实在无位可挪时保底，仍压线但不丢尺寸
    else:
        free_centers = [along]

    opposite = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
    candidates = [preferred, opposite[preferred]]
    last_reason = None
    fallback = None
    for side in candidates:
        intervals = bands.setdefault(side, [])
        for level in range(_MAX_LEVELS):
            while len(intervals) <= level:
                intervals.append([])
            fixed_x, fixed_y = _side_offset(side, box, level, offset_mm, pitch_mm)
            for free in free_centers:
                x = fixed_x if fixed_x is not None else free
                y = fixed_y if fixed_y is not None else free
                rect = _rect(x, y, half_w, half_h)
                if not _band_free(intervals[level], along, span_extent, free, text_extent):
                    last_reason = last_reason or "BAND_CROWDED"
                    continue
                if not sheet.fits(rect):
                    last_reason = "OUT_OF_SHEET"
                    continue
                if any(_inside(rect, other) for other in other_boxes):
                    last_reason = "HITS_OTHER_VIEW"
                    continue
                if any(_overlap(rect, other, gap=2.0) for other in occupied):
                    last_reason = "HITS_OTHER_DIM"
                    continue
                intervals[level].append((along, span_extent, free, text_extent))
                return side, level, x, y, rect, None
            # 该层已满：记住最外层（level 最大）的可行位置，两个方向都试。
            for free in free_centers:
                x = fixed_x if fixed_x is not None else free
                y = fixed_y if fixed_y is not None else free
                rect = _rect(x, y, half_w, half_h)
                if (sheet.fits(rect)
                        and not any(_inside(rect, other) for other in other_boxes)
                        and not any(_overlap(rect, other, gap=2.0) for other in occupied)):
                    fallback = (side, level, x, y, rect, free)
                    break
    if fallback is not None:
        side, level, x, y, rect, free = fallback
        intervals = bands.setdefault(side, [])
        while len(intervals) <= level:
            intervals.append([])
        intervals[level].append((along, span_extent, free, text_extent))
        return side, level, x, y, rect, "BAND_CROWDED"
    return None


def _place_circular(info, view_box, sheet, other_boxes, occupied, offset_mm):
    """直径/半径：沿候选角把文字放到圆周外。

    距离取“该视图内切圆”与自身半径的较大值再加 10 mm。齿轮这类回转体，
    视图框的四个角是空的，文字落在角上既在零件外，也不会被推到纸边；
    若按视图框边界算距离，φ36 会被推到图幅外（实测 45° 位置超出上边距）。
    """
    center = info.center or (info.text_pos[0] if len(info.text_pos) >= 2 else 0.0,
                             info.text_pos[1] if len(info.text_pos) >= 2 else 0.0)
    incircle = min(view_box["right"] - view_box["left"],
                   view_box["top"] - view_box["bottom"]) / 2.0
    radius = max(info.radius, incircle, 0.0)
    text_w = _text_width_mm(info.text)
    half_w, half_h = text_w / 2.0, _TEXT_HEIGHT_MM / 2.0 + 1.0
    fallback = None
    for angle in _LEADER_ANGLES:
        distance = radius + _MIN_LEADER_MM
        x = center[0] + math.cos(math.radians(angle)) * distance
        y = center[1] + math.sin(math.radians(angle)) * distance
        rect = _rect(x, y, half_w, half_h)
        if fallback is None:
            fallback = (angle, distance, x, y, rect)
        if not sheet.fits(rect):
            continue
        if any(_inside(rect, other) for other in other_boxes):
            continue
        if any(_overlap(rect, other, gap=3.0) for other in occupied):
            continue
        return angle, distance, x, y, rect, None
    return (*fallback, "RADIAL_CROWDED")


def _place_other(info, view_box, sheet, other_boxes, occupied, offset_mm):
    """角度/倒角/弧长/坐标尺寸：从视图中心往外推到轮廓外。"""
    center = ((view_box["left"] + view_box["right"]) / 2.0,
              (view_box["bottom"] + view_box["top"]) / 2.0)
    if len(info.text_pos) >= 2:
        dx = info.text_pos[0] - center[0]
        dy = info.text_pos[1] - center[1]
    else:
        dx = dy = 0.0
    angle = math.degrees(math.atan2(dy, dx)) if (abs(dx) + abs(dy)) > 1e-6 else 45.0
    text_w = _text_width_mm(info.text)
    half_w, half_h = text_w / 2.0, _TEXT_HEIGHT_MM / 2.0 + 1.0
    for candidate in (angle, angle + 90.0, angle - 90.0, 45.0, 135.0, 225.0, 315.0):
        distance = _exit_distance(center, candidate, view_box) + offset_mm
        x = center[0] + math.cos(math.radians(candidate)) * distance
        y = center[1] + math.sin(math.radians(candidate)) * distance
        rect = _rect(x, y, half_w, half_h)
        if not sheet.fits(rect):
            continue
        if any(_inside(rect, other) for other in other_boxes):
            continue
        if any(_overlap(rect, other, gap=3.0) for other in occupied):
            continue
        return candidate, distance, x, y, rect, None
    return None


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------

def arrange_dimension_positions(drawing_model, *, view_boxes=None, sheet_size=None,
                                offset_mm=8.0, pitch_mm=8.0, margin_mm=10.0,
                                title_block_mm=(180.0, 56.0), **legacy) -> dict:
    """按 GB 习惯重排视图尺寸，返回逐尺寸证据。

    view_boxes: 与视图同序的规划边界框（米），优先使用；缺省用 IView.GetOutline。
    sheet_size: (width_m, height_m)；缺省从图纸属性读取。
    legacy: 兼容旧参数 offset_m（米）。
    """
    if "offset_m" in legacy:
        offset_mm = float(legacy["offset_m"]) * 1000.0
    if "margin_m" in legacy:
        margin_mm = float(legacy["margin_m"]) * 1000.0
    if "column_gap_m" in legacy:
        pitch_mm = float(legacy["column_gap_m"]) * 1000.0

    try:
        from .sw_drawing import _collect_drawing_views, _view_display_dimensions
    except ImportError:
        from sw_drawing import _collect_drawing_views, _view_display_dimensions

    views = _collect_drawing_views(drawing_model)
    if not views:
        return {"status": "blocked", "error_code": "DRAWING_VIEWS_UNAVAILABLE",
                "method": "GB type-aware layout", "views": []}

    width_m, height_m = _sheet_dimensions(drawing_model, views, sheet_size)
    if not width_m or not height_m:
        return {"status": "blocked", "error_code": "DRAWING_SHEET_SIZE_UNAVAILABLE",
                "method": "GB type-aware layout", "views": []}
    sheet = Sheet(width_m * 1000.0, height_m * 1000.0, margin_mm, title_block_mm)

    planned = list(view_boxes or [])
    frames = []
    for index, view in enumerate(views):
        view_type = _value(view, "Type", None)
        if view_type == 1:  # 图纸视图本身，不是模型视图
            continue
        box = _match_planned_box(view, planned, index)
        if box is None:
            box = _box(_call(view, "GetOutline"))
        if box is None:
            continue
        frames.append({
            "view": view,
            "name": str(_value(view, "Name", "") or ""),
            "box": _box_mm(box),
            "transform": _value(view, "ModelToViewTransform", None),
            "scale": _view_scale(view),
        })
    if not frames:
        return {"status": "blocked", "error_code": "DRAWING_VIEW_OUTLINE_UNAVAILABLE",
                "method": "GB type-aware layout", "views": []}

    occupied = []
    results = []
    placed_total = verified_total = 0
    for frame in frames:
        box = frame["box"]
        dimensions = [_build_dim(dd, frame["transform"], frame["scale"])
                      for dd in _view_display_dimensions(frame["view"])]
        # 先放放射尺寸（会检查 occupied），再按 span 升序放线性尺寸：
        # 小尺寸先占内层 → 小内大外，不靠“碰巧先处理谁”。
        kind_order = {"circular": 0, "other": 1, "linear": 2}
        dimensions.sort(key=lambda item: (kind_order.get(item.kind, 1), item.span))
        axis_ys = sorted({round(point[1], 3) for item in dimensions for point in item.refs})
        axis_xs = sorted({round(point[0], 3) for item in dimensions for point in item.refs})
        if not dimensions:
            results.append({"view": frame["name"], "dimension_count": 0,
                            "status": "skipped", "placed": []})
            continue
        other_boxes = [item["box"] for item in frames if item is not frame]
        bands = {}
        records = []
        for info in dimensions:
            plan = None
            if info.kind == "linear":
                plan = _place_linear(info, box, sheet, bands, other_boxes, occupied,
                                     axis_xs if info.horizontal else axis_ys,
                                     offset_mm, pitch_mm)
                mode = "band"
            elif info.kind == "circular":
                plan = _place_circular(info, box, sheet, other_boxes, occupied, offset_mm)
                mode = "radial"
            else:
                plan = _place_other(info, box, sheet, other_boxes, occupied, offset_mm)
                mode = "outward"

            if plan is None:
                # 保留 SolidWorks 原位置，但仍要如实记录“没排成”
                x = info.text_pos[0] if len(info.text_pos) >= 2 else box["left"]
                y = info.text_pos[1] if len(info.text_pos) >= 2 else box["top"]
                rect = _rect(x, y, 6.0, 4.0)
                side, level, angle = "keep", None, None
                issue = "NO_FEASIBLE_SLOT"
            elif mode == "band":
                side, level, x, y, rect, issue = plan
                angle = None
            elif mode == "radial":
                angle, _distance, x, y, rect, issue = plan
                side, level = "radial", None
            else:
                angle, _distance, x, y, rect, issue = plan
                side, level = "outward", None

            occupied.append(rect)
            verified, error, readback = _apply(drawing_model, info, x, y)
            placed_total += 1
            verified_total += int(verified)
            records.append({
                "text": info.text,
                "dim_type": info.type2,
                "kind": info.kind,
                "side": side,
                "level": level,
                "angle_deg": None if angle is None else round(float(angle), 1),
                "span_mm": round(info.span, 2),
                "anchor_mm": [round(info.anchor[0], 2), round(info.anchor[1], 2)],
                "ref_points": len(info.refs),
                "x_m": round(x / 1000.0, 6),
                "y_m": round(y / 1000.0, 6),
                "readback_m": readback,
                "verified": verified,
                "issue": issue,
                "error": error,
            })
        results.append({
            "view": frame["name"],
            "dimension_count": len(dimensions),
            "box_mm": [round(box[key], 2) for key in ("left", "bottom", "right", "top")],
            "levels": {side: len(intervals) for side, intervals in sorted(bands.items())},
            "status": "pass" if all(item["verified"] for item in records) else "warn",
            "placed": records,
        })

    _call(drawing_model, "ForceRebuild3", False)
    _call(drawing_model, "GraphicsRedraw2")
    status = "skipped" if not placed_total else ("pass" if verified_total == placed_total else "warn")
    return {
        "status": status,
        "method": "GB type-aware layout (band + radial)",
        "offset_mm": offset_mm,
        "pitch_mm": pitch_mm,
        "margin_mm": margin_mm,
        "placed_count": placed_total,
        "verified_count": verified_total,
        "views": results,
        "error_code": None if status in {"pass", "skipped"} else "DRAWING_DIMENSION_PLACEMENT_FAILED",
    }


def _apply(drawing_model, info, x_mm, y_mm):
    if info.annotation is None:
        return False, "annotation unavailable", None
    ok = _call(info.annotation, "SetPosition", x_mm / 1000.0, y_mm / 1000.0, 0.0,
               default=False)
    position = _position(info.annotation)
    if not position and ok is False:
        return False, "SetPosition failed", None
    if len(position) < 2:
        return False, "position unreadable", None
    readback = [round(position[0] * 1000.0, 3), round(position[1] * 1000.0, 3)]
    verified = (abs(position[0] - x_mm / 1000.0) <= 0.05
                and abs(position[1] - y_mm / 1000.0) <= 0.05)
    return verified, None if verified else "position mismatch", readback


def _view_scale(view):
    values = _nums(_value(view, "ScaleRatio", None))
    if len(values) >= 2 and values[1]:
        return values[0] / values[1]
    return 1.0


def _sheet_dimensions(drawing_model, views, sheet_size):
    if sheet_size:
        try:
            return float(sheet_size[0]), float(sheet_size[1])
        except (TypeError, ValueError, IndexError):
            pass
    sheet = _value(drawing_model, "GetCurrentSheet", None)
    if sheet is not None and not callable(sheet):
        properties = _nums(_call(sheet, "GetProperties2"))
        if len(properties) >= 7:
            return float(properties[5]), float(properties[6])
    for view in views:
        sheet = _value(view, "Sheet", None)
        if sheet is None:
            continue
        properties = _nums(_call(sheet, "GetProperties2"))
        if len(properties) >= 7:
            return float(properties[5]), float(properties[6])
    return None, None


def _match_planned_box(view, planned, index):
    """按视图中心匹配规划框；顺序不可靠时比索引更安全。"""
    if not planned:
        return None
    position = _nums(_value(view, "Position", None))
    if len(position) >= 2 and all(isinstance(item, dict) for item in planned):
        best = None
        for item in planned:
            try:
                box = item.get("box") if isinstance(item, dict) and "box" in item else item
                x1, y1, x2, y2 = (float(box[key]) for key in
                                  ("left", "bottom", "right", "top"))
            except (KeyError, TypeError, ValueError):
                continue
            distance = math.hypot((x1 + x2) / 2.0 - position[0],
                                  (y1 + y2) / 2.0 - position[1])
            if best is None or distance < best[0]:
                best = (distance, box)
        if best is not None and best[0] < 0.03:
            return best[1]
    if index < len(planned):
        item = planned[index]
        return item.get("box") if isinstance(item, dict) and "box" in item else item
    return None
