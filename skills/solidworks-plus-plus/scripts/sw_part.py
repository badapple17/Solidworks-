"""
SolidWorks 零件建模工具
提供草图绘制和特征创建的常用函数
"""
from dataclasses import dataclass
from contextlib import contextmanager

try:
    from .sw_connect import get_com_member
    from .sw_preflight import import_com_dependencies
except ImportError:
    from sw_connect import get_com_member
    from sw_preflight import import_com_dependencies

pythoncom, _win32com, VARIANT = import_com_dependencies()

PLANE_NAME_ALIASES = {
    "Front Plane": ["Front Plane", "前视基准面"],
    "Top Plane": ["Top Plane", "上视基准面"],
    "Right Plane": ["Right Plane", "右视基准面"],
    "前视基准面": ["前视基准面", "Front Plane"],
    "上视基准面": ["上视基准面", "Top Plane"],
    "右视基准面": ["右视基准面", "Right Plane"],
}

SKETCH_NAME_PREFIX_ALIASES = {
    "Sketch": "草图",
    "草图": "Sketch",
}


@dataclass
class SketchSelectionRef:
    """
    记录草图对象引用，避免后续只能靠 SelectByID2("SKETCH") 按名称反查。

    SolidWorks 2024 中文版中，按名称选择 SKETCH 可能持续返回 False。创建草图时
    保存对象引用，后续特征创建可直接 Select2 草图、草图特征或轮廓。
    """

    name: str
    sketch: object = None
    feature: object = None
    contours: tuple = ()
    regions: tuple = ()
    segments: tuple = ()
    source: str = ""

    def __str__(self):
        """保持与旧代码中普通草图名称字符串相近的表现。"""
        return self.name


_SKETCH_SELECTION_CACHE = {}


# ============================================================
# 草图操作
# ============================================================

def _empty_callout():
    """创建兼容 SelectByID2 的空 Callout 参数。"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def _select_by_id(extension, entity_name, entity_type, append=False, mark=0):
    """
    统一封装 SelectByID2，避免 None 在部分 SolidWorks 版本中触发类型不匹配。

    参数:
        extension: ModelDocExtension 对象
        entity_name: 实体名称
        entity_type: 实体类型字符串
        append: 是否追加选择
        mark: 选择标记

    返回:
        bool
    """
    return extension.SelectByID2(
        entity_name, entity_type, 0, 0, 0, append, mark, _empty_callout(), 0
    )


def _get_plane_name_candidates(plane_name):
    """
    获取基准面的候选名称列表

    参数:
        plane_name: 用户提供的基准面名称

    返回:
        list[str]
    """
    return PLANE_NAME_ALIASES.get(plane_name, [plane_name])


def _get_sketch_name_candidates(sketch_name):
    """
    获取草图名称候选列表，自动兼容中英文前缀。

    参数:
        sketch_name: 草图名称

    返回:
        list[str]
    """
    sketch_name = str(sketch_name)
    candidates = [sketch_name]
    for prefix, alias in SKETCH_NAME_PREFIX_ALIASES.items():
        if sketch_name.startswith(prefix):
            alias_name = alias + sketch_name[len(prefix):]
            if alias_name not in candidates:
                candidates.append(alias_name)
    return candidates


def _as_tuple(value):
    """把 COM 返回的单对象、SAFEARRAY 或 None 统一成 tuple。"""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return tuple(item for item in value if item is not None)
    if isinstance(value, list):
        return tuple(item for item in value if item is not None)
    return (value,)


def _safe_com_member(obj, attr_name, *args, default=None):
    """读取 COM 成员，失败时返回默认值，避免排障路径再次抛 COM 异常。"""
    if obj is None:
        return default
    try:
        value = get_com_member(obj, attr_name, *args)
        return default if value is None else value
    except Exception:
        return default


def _model_cache_key(model):
    """生成仅用于当前 Python 进程的模型缓存键。"""
    ole_object = getattr(model, "_oleobj_", None)
    if ole_object is not None:
        return id(ole_object)
    return id(model)


def _cache_name_variants(sketch_name):
    """生成草图缓存名称，兼容中英文默认草图名前缀。"""
    variants = []
    for candidate in _get_sketch_name_candidates(sketch_name):
        if candidate not in variants:
            variants.append(candidate)
    return variants


def _cache_sketch_ref(model, sketch_ref):
    """缓存草图对象引用，后续可跳过 SelectByID2("SKETCH")。"""
    if not sketch_ref or not sketch_ref.name:
        return sketch_ref
    model_cache = _SKETCH_SELECTION_CACHE.setdefault(_model_cache_key(model), {})
    for candidate in _cache_name_variants(sketch_ref.name):
        model_cache[candidate] = sketch_ref
    return sketch_ref


def _find_cached_sketch_ref(model, sketch_name):
    """从当前进程缓存中查找草图对象引用。"""
    if isinstance(sketch_name, SketchSelectionRef):
        return sketch_name

    model_cache = _SKETCH_SELECTION_CACHE.get(_model_cache_key(model), {})
    for candidate in _cache_name_variants(sketch_name):
        cached = model_cache.get(candidate)
        if cached:
            return cached
    return None


def _capture_sketch_ref(model, sketch_obj=None, fallback="Sketch1", source=""):
    """从活动草图或给定草图对象中提取可复用的选择引用。"""
    if sketch_obj is None:
        sketch_obj = _safe_com_member(model.SketchManager, "ActiveSketch")
    if sketch_obj is None:
        return None

    sketch_name = _safe_com_member(sketch_obj, "Name", default=fallback) or fallback
    sketch_ref = SketchSelectionRef(
        name=sketch_name,
        sketch=sketch_obj,
        feature=_safe_com_member(sketch_obj, "GetFeature"),
        contours=_as_tuple(_safe_com_member(sketch_obj, "GetSketchContours")),
        regions=_as_tuple(_safe_com_member(sketch_obj, "GetSketchRegions")),
        segments=_as_tuple(_safe_com_member(sketch_obj, "GetSketchSegments")),
        source=source,
    )
    return _cache_sketch_ref(model, sketch_ref)


def _refresh_sketch_ref(sketch_ref):
    """退出草图后再次刷新 Feature/Contour 引用。"""
    if not sketch_ref or sketch_ref.sketch is None:
        return sketch_ref
    feature = _safe_com_member(sketch_ref.sketch, "GetFeature")
    contours = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchContours"))
    regions = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchRegions"))
    segments = _as_tuple(_safe_com_member(sketch_ref.sketch, "GetSketchSegments"))
    if feature is not None:
        sketch_ref.feature = feature
    if contours:
        sketch_ref.contours = contours
    if regions:
        sketch_ref.regions = regions
    if segments:
        sketch_ref.segments = segments
    return sketch_ref


def _select_first_candidate(extension, candidate_names, entity_type, append=False, mark=0):
    """
    按候选名称列表依次尝试选择实体。

    参数:
        extension: ModelDocExtension 对象
        candidate_names: 候选名称列表
        entity_type: 实体类型字符串
        append: 是否追加选择
        mark: 选择标记

    返回:
        str | None
    """
    for candidate_name in candidate_names:
        if _select_by_id(extension, candidate_name, entity_type, append=append, mark=mark):
            return candidate_name
    return None


def _get_selection_count(model):
    """
    获取当前选择集中的对象数量。

    参数:
        model: IModelDoc2 对象

    返回:
        int
    """
    selection_manager = model.SelectionManager
    count_member = getattr(selection_manager, "GetSelectedObjectCount2")
    return count_member(-1) if callable(count_member) else int(count_member)


def _select_com_object(obj, append=False, mark=0):
    """使用对象自身 Select2/Select4 选择，优先避开 SelectByID2 名称解析。"""
    if obj is None:
        return False
    for method_name in ("Select2", "Select4"):
        method = getattr(obj, method_name, None)
        if not method:
            continue
        try:
            if method_name == "Select2":
                if bool(method(append, mark)):
                    return True
            elif bool(method(append, _empty_callout())):
                return True
        except Exception:
            continue
    return False


def _select_any_object(objects, append=False, mark=0):
    """从一组 COM 对象里尽量选择全部对象，至少选中一个即视为成功。"""
    selected_count = 0
    for obj in _as_tuple(objects):
        if _select_com_object(obj, append=(append or selected_count > 0), mark=mark):
            selected_count += 1
    return selected_count > 0


def _select_sketch_ref(model, sketch_ref, mark=0):
    """
    按稳定优先级选择草图引用。

    轮廓/区域更接近 FeatureExtrusion3 需要的预选对象；不可用时再回退草图
    Feature 或 Sketch 对象。
    """
    if not sketch_ref:
        return False
    model.ClearSelection2(True)
    _refresh_sketch_ref(sketch_ref)
    for objects in (
        sketch_ref.feature,
        sketch_ref.sketch,
        sketch_ref.contours,
        sketch_ref.regions,
        sketch_ref.segments,
    ):
        if _select_any_object(objects, append=False, mark=mark):
            return True
        model.ClearSelection2(True)
    return False


def _select_sketch_feature_by_name(model, sketch_name, mark=0):
    """通过 FeatureByName 找到草图特征后对象级选择。"""
    for candidate in _get_sketch_name_candidates(sketch_name):
        feature = _safe_com_member(model, "FeatureByName", candidate)
        if feature and _select_com_object(feature, append=False, mark=mark):
            return candidate
    return None


def _ensure_sketch_selected(model, sketch_name):
    """
    确保拉伸/切除前已有可用的草图选择。

    参数:
        model: IModelDoc2 对象
        sketch_name: 草图名称

    返回:
        str
    """
    if str(sketch_name) == "__current_selection__" and _get_selection_count(model) > 0:
        return "__current_selection__"

    active_ref = _capture_sketch_ref(model, fallback=str(sketch_name), source="active")
    if active_ref and _select_sketch_ref(model, active_ref):
        return active_ref.name

    cached_ref = _find_cached_sketch_ref(model, sketch_name)
    if cached_ref and _select_sketch_ref(model, cached_ref):
        return cached_ref.name

    selected_feature = _select_sketch_feature_by_name(model, sketch_name)
    if selected_feature:
        return selected_feature

    selected_sketch = _select_first_candidate(
        model.Extension, _get_sketch_name_candidates(sketch_name), "SKETCH"
    )
    if not selected_sketch:
        model.ClearSelection2(True)
        raise ValueError(
            f"无法选择草图: {sketch_name}。已尝试活动草图对象、缓存草图对象、"
            "FeatureByName 和 SelectByID2('SKETCH')。"
        )
    return selected_sketch


def start_sketch(model, plane_name="Front Plane"):
    """
    在指定基准面上开始草图

    参数:
        model: IModelDoc2
        plane_name: 基准面名称
            英文: "Front Plane", "Top Plane", "Right Plane"
            中文: "前视基准面", "上视基准面", "右视基准面"
    """
    model.ClearSelection2(True)

    selected_plane = _select_first_candidate(
        model.Extension, _get_plane_name_candidates(plane_name), "PLANE"
    )
    if selected_plane:
        model.SketchManager.InsertSketch(True)
        return selected_plane

    raise ValueError(f"无法选择基准面: {plane_name}")


def insert_offset_plane(model, base_plane_name="Front Plane", offset_m=0.0,
                        name="Plane_Offset"):
    """@brief 从标准基准面创建平行偏置面，返回 IRefPlane 特征。

    SW2023 实测：`InsertRefPlane` 依赖当前选择集。必须先选中基准面，
    否则创建失败（沉孔/键槽常在这里失败）。偏置量单位是米，
    正负号决定偏置方向；第一次使用后回读草图位置或包围盒确认。

    负偏置（SW2023 SP0.1 实测）：`InsertRefPlane(8, -d)` 的负号被**静默忽略**，
    面落在基面上（偏置 0），不报错。本函数对负值改用
    `8 | 256`（Distance + OptionFlip）传 `abs(d)`；实测 Front −100 mm
    → 面在 Z=−100，面内 X/Y 坐标不变，正法向仍是 +Z。

    失败时**抛异常**（`ValueError` 选不中基面 / `RuntimeError` 建面失败），
    不会返回 None；成功时一定返回特征对象。调用方不需要写 `if plane is None`。
    """
    model.ClearSelection2(True)
    selected = _select_first_candidate(
        model.Extension, _get_plane_name_candidates(base_plane_name), "PLANE"
    )
    if not selected:
        model.ClearSelection2(True)
        raise ValueError(f"无法选择基准面: {base_plane_name}")
    constraint = 8 | 256 if offset_m < 0 else 8  # Distance (+ OptionFlip)
    plane = model.FeatureManager.InsertRefPlane(
        constraint, abs(float(offset_m)), 0, 0, 0, 0
    )
    model.ClearSelection2(True)
    if plane is None:
        raise RuntimeError(
            f"创建偏置面失败: {base_plane_name} offset={offset_m} m"
        )
    try:
        plane.Name = name
    except Exception:
        pass  # 改名失败不能丢掉已建成的偏置面
    return plane


def end_sketch(model):
    """
    退出当前草图，并返回可复用的草图选择引用。

    返回值兼容旧调用：调用者可以忽略它；需要稳定选择时可传给
    `extrude_boss()` / `extrude_cut()` 等特征函数。
    """
    sketch_ref = _capture_sketch_ref(model, source="end_sketch")
    model.SketchManager.InsertSketch(True)
    return _cache_sketch_ref(model, _refresh_sketch_ref(sketch_ref))


@contextmanager
def sketch(model, plane_name="Front Plane", exact=False):
    """
    草图上下文管理器。

    exact=True：草图期间设 `SketchManager.AddToDB = True`，关闭推理吸附。
    已有实体或失败残留草图附近画图时必须开：实测 50×180 矩形被吸附成
    60×160、中心偏移 5 mm，无任何报错，只能靠体积门禁发现。

    示例:
        with sketch(model, "Front Plane") as sketch_name:
            sketch_circle(model, 0, 0, mm(25))
        extrude_boss(model, sketch_name, mm(50))
    """
    start_sketch(model, plane_name)
    sketch_ref = None
    if exact:
        model.SketchManager.AddToDB = True
    try:
        sketch_ref = _capture_sketch_ref(model, source="context")
        yield sketch_ref.name if sketch_ref else current_sketch_name(model)
    finally:
        if exact:
            model.SketchManager.AddToDB = False
        finished_ref = end_sketch(model)
        if sketch_ref and finished_ref:
            sketch_ref.feature = finished_ref.feature
            sketch_ref.contours = finished_ref.contours
            sketch_ref.regions = finished_ref.regions
            sketch_ref.segments = finished_ref.segments
            _cache_sketch_ref(model, sketch_ref)


def current_sketch_name(model, fallback="Sketch1"):
    """
    获取当前草图名称。

    参数:
        model: IModelDoc2
        fallback: 无法读取当前草图时返回的默认名称
    """
    active_sketch = model.SketchManager.ActiveSketch
    if active_sketch:
        return active_sketch.Name
    return fallback


def sketch_line(model, x1, y1, x2, y2):
    """画直线（单位: 米）"""
    return model.SketchManager.CreateLine(x1, y1, 0, x2, y2, 0)


def sketch_rectangle(model, cx, cy, w, h):
    """以中心点画矩形（单位: 米）"""
    return model.SketchManager.CreateCenterRectangle(
        cx, cy, 0, cx + w / 2, cy + h / 2, 0
    )


def sketch_corner_rectangle(model, x1, y1, x2, y2):
    """以对角线画矩形（单位: 米）"""
    return model.SketchManager.CreateCornerRectangle(x1, y1, 0, x2, y2, 0)


def sketch_circle(model, cx, cy, radius):
    """画圆（单位: 米）"""
    return model.SketchManager.CreateCircleByRadius(cx, cy, 0, radius)


def sketch_arc(model, cx, cy, x1, y1, x2, y2, direction=1):
    """
    画圆弧

    参数:
        cx, cy: 圆心坐标（米）
        x1, y1: 起点坐标
        x2, y2: 终点坐标
        direction: 1=逆时针, -1=顺时针
    """
    return model.SketchManager.CreateArc(cx, cy, 0, x1, y1, 0, x2, y2, 0, direction)


def sketch_polygon(model, cx, cy, radius, sides=6):
    """画正多边形（内切圆方式）"""
    return model.SketchManager.CreatePolygon(cx, cy, 0, cx + radius, cy, 0, sides, True)


def sketch_slot(model, x1, y1, x2, y2, radius):
    """画槽口"""
    return model.SketchManager.CreateSketchSlot(
        0,  # swSketchSlotCreationType_e: 0=Straight
        radius, radius,  # 宽度
        x1, y1, 0,
        x2, y2, 0,
        0, 0, 0,
        1, False
    )


def sketch_spline(model, points):
    """
    画样条曲线

    参数:
        points: [(x1,y1), (x2,y2), ...] 控制点列表（单位: 米）
    """
    import array
    point_array = array.array('d')
    for x, y in points:
        point_array.extend([x, y, 0.0])
    return model.SketchManager.CreateSpline2(point_array, False)


def auto_dimension_sketch(model, sketch=None, sketch_segments=None):
    """@brief 按官方 AutoDimension2 流程为当前草图创建真实模型尺寸。

    SolidWorks 的工程图 ``InsertModelAnnotations`` 只能导入模型中已有的
    显示尺寸，不能凭空为拉伸深度或矩形轮廓生成尺寸。该函数在草图编辑态
    选择水平/垂直基准线，再调用 ``ISketch.AutoDimension2``，因此生成的尺寸
    会成为模型的真实 DisplayDimension，可被工程图导入并复核。

    返回值包含 ``status_code``（官方约定 0 表示成功）、选择数量和是否创建
    尺寸的可审计信息。函数不会把失败伪装成成功。
    """
    active = sketch or _safe_com_member(model.SketchManager, "ActiveSketch")
    if active is None:
        return {"status": "blocked", "status_code": None, "error_code": "SKETCH_NOT_ACTIVE", "selected": 0}

    def segments():
        supplied = _as_tuple(sketch_segments)
        if supplied:
            return supplied
        for name in ("GetSketchSegments", "IGetSketchSegments"):
            value = _safe_com_member(active, name)
            result = _as_tuple(value)
            if result:
                return result
        return ()

    horizontal = None
    vertical = None
    for segment in segments():
        try:
            start = get_com_member(segment, "GetStartPoint2")
            end = get_com_member(segment, "GetEndPoint2")
            dx = abs(float(get_com_member(start, "X")) - float(get_com_member(end, "X")))
            dy = abs(float(get_com_member(start, "Y")) - float(get_com_member(end, "Y")))
        except Exception:
            continue
        if dx > dy and horizontal is None:
            horizontal = segment
        elif dy > dx and vertical is None:
            vertical = segment

    model.ClearSelection2(True)
    selected = 0
    # SW2024 swAutodimMark_e：2=水平基准，4=垂直基准。
    # 官方示例要求垂直线作为水平基准、水平线作为垂直基准。
    for segment, mark in ((vertical, 2), (horizontal, 4)):
        if segment is None:
            continue
        try:
            if bool(segment.Select3(selected > 0, mark, _empty_callout())):
                selected += 1
        except Exception:
            try:
                if bool(segment.Select4(selected > 0, _empty_callout())):
                    selected += 1
            except Exception:
                pass

    status_code = None
    try:
        # swAutodimEntitiesAll=1, Baseline=1, Below=-1, Left=-1。
        status_code = int(get_com_member(active, "AutoDimension2", 1, 1, -1, 1, -1))
    except Exception as exc:
        model.ClearSelection2(True)
        return {
            "status": "failed",
            "status_code": None,
            "error_code": "SKETCH_AUTODIMENSION_CALL_FAILED",
            "error": str(exc),
            "selected": selected,
        }
    try:
        model.GraphicsRedraw2()
    except Exception:
        pass
    model.ClearSelection2(True)
    return {
        "status": "pass" if status_code == 0 else "blocked",
        "status_code": status_code,
        "error_code": None if status_code == 0 else "SKETCH_AUTODIMENSION_REJECTED",
        "selected": selected,
    }


def add_dimension(model, x, y):
    """在指定位置添加尺寸标注"""
    return model.AddDimension2(x, y, 0)


def add_sketch_relation(model, relation_type):
    """
    添加草图几何关系

    常用 relation_type:
        "sgFIXED", "sgHORIZONTAL", "sgVERTICAL", "sgCOLINEAR",
        "sgPARALLEL", "sgPERPENDICULAR", "sgTANGENT", "sgCONCENTRIC",
        "sgEQUAL", "sgSYMMETRIC", "sgMIDPOINT", "sgCOINCIDENT"
    """
    return model.SketchAddConstraints(relation_type)


# ============================================================
# 特征操作
# ============================================================

def extrude_boss(model, sketch_name, depth, direction=True, merge=True, name=None):
    """
    凸台拉伸

    参数:
        model: IModelDoc2
        sketch_name: 草图名称（如 "Sketch1"）
        depth: 拉伸深度（米）
        direction: True=沿基准面负法向（SW2023 默认），False=正法向
        merge: True=合并结果
        name: 可选特征名（如 "01_BASE"）；None 时保留 SolidWorks 默认名
    """
    _ensure_sketch_selected(model, sketch_name)
    feature = model.FeatureManager.FeatureExtrusion3(
        True,         # Sd: 单向拉伸
        False,        # Flip
        direction,    # Dir: 拉伸方向
        0,            # T1: Blind
        0,            # T2: Blind
        depth,        # D1
        0.0,          # D2
        False,        # Dchk1
        False,        # Dchk2
        False,        # Ddir1
        False,        # Ddir2
        0.0,          # Dang1
        0.0,          # Dang2
        False,        # OffsetReverse1
        False,        # OffsetReverse2
        False,        # TranslateSurface1
        False,        # TranslateSurface2
        merge,        # Merge
        False,        # UseFeatScope
        True,         # UseAutoSelect
        0,            # T0: 从草图平面开始
        0.0,          # StartOffset
        False         # FlipStartOffset
    )
    if feature is not None and name:
        try:
            feature.Name = name
        except Exception:
            pass  # 改名失败不能丢掉已建成的特征
    return feature


def _feature_cut_once(model, depth, end_condition, direction, flip):
    """@brief 单次调用 FeatureCut4；方向参数固定放在第 3 位 Dir。"""
    return model.FeatureManager.FeatureCut4(
        True, flip, direction,
        end_condition, 0,
        depth, 0,
        False, False, False, False,
        0.0, 0.0,
        False, False, False, False, False,
        True, True, True, True,
        False, 0, 0, False, False
    )


def extrude_cut(model, sketch_name, depth, direction=True, flip=False, auto_flip=True,
                name=None):
    """
    切除拉伸

    参数:
        model: IModelDoc2
        sketch_name: 草图名称
        depth: 切除深度（米），0 表示完全贯穿
        direction: True=沿基准面正法向，False=负法向。
                   **与 extrude_boss 相反！** FeatureCut4 的 Dir 与
                   FeatureExtrusion3 的 Dir 在 SW2023 里含义相反：
                   同一块 +Z 材料的平板，凸台 direction=False，切除 direction=True。
        flip: True=翻转切除方向
        auto_flip: 切除失败时自动反向重试（默认 True）
        name: 可选特征名（如 "03_NOTCH"）；None 时保留 SolidWorks 默认名

    方向说明（2026-10-24 SW2023 SP0.1 六组实测，auto_flip=False）:
        - 基准面 +法向：Front=+Z、Top=+Y、Right=+X。
        - `extrude_cut(direction=True)` 沿 +法向切，`False` 沿 −法向切。
        - Front 基准面 +Z 材料：True 成功、False 返回 None；
          −Z 材料：False 成功、True 返回 None。
        - 偏置面贴在材料外端（如 Front 偏置到 Z=+T）时用 direction=False，
          因为朝 +法向就是朝空处切；这不是“方向整体反转”。
        - 方向错时切除落在空处，SolidWorks 返回 None；此时 auto_flip
          自动换另一方向重试，并在成功时打印提示。贯穿切除同样适用。
        - 打印了“自动翻转方向重试”说明调用方给的 direction 是错的，
          应修正调用，不要依赖兜底。
    """
    _ensure_sketch_selected(model, sketch_name)
    if depth == 0:
        # 完全贯穿用 ThroughAll（1）。SW2023 实测 ThroughAllBoth（2）在
        # FeatureCut4 这个参数组合下不生成特征，不要改成 2。
        end_condition = 1  # swEndCondThroughAll
        depth = 0.01  # 占位值
    else:
        end_condition = 0  # swEndCondBlind

    feature = _feature_cut_once(model, depth, end_condition, direction, flip)
    if feature is None and auto_flip:
        # 盲切切空、或贯穿草图位于实体端面且方向朝空侧时，SolidWorks 返回 None。
        # 换另一方向重试；贯穿方向翻转不会改变结果。
        print(
            f"[sw_part] 切除 direction={direction} 未生成特征，"
            f"自动翻转方向重试: {sketch_name}"
        )
        _ensure_sketch_selected(model, sketch_name)
        feature = _feature_cut_once(model, depth, end_condition, not direction, flip)
    if feature is not None and name:
        try:
            feature.Name = name
        except Exception:
            pass  # 改名失败不能丢掉已建成的特征
    return feature


def extrude_midplane(model, sketch_name, total_depth):
    """
    中面拉伸（两侧对称拉伸）

    参数:
        total_depth: 总深度（米），每侧为 total_depth/2
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureExtrusion3(
        True,         # Sd: 单向定义，终止条件控制为中面
        False,        # Flip
        True,         # Dir
        6,            # T1: swEndCondMidPlane
        0,            # T2
        total_depth,  # D1
        0.0,          # D2
        False,        # Dchk1
        False,        # Dchk2
        False,        # Ddir1
        False,        # Ddir2
        0.0,          # Dang1
        0.0,          # Dang2
        False,        # OffsetReverse1
        False,        # OffsetReverse2
        False,        # TranslateSurface1
        False,        # TranslateSurface2
        True,         # Merge
        False,        # UseFeatScope
        True,         # UseAutoSelect
        0,            # T0
        0.0,          # StartOffset
        False         # FlipStartOffset
    )


def revolve_boss(model, sketch_name, angle_rad, axis_sketch_name=None):
    """
    旋转凸台

    参数:
        sketch_name: 轮廓草图名称
        angle_rad: 旋转角度（弧度），2*pi 表示 360 度
        axis_sketch_name: 旋转轴草图名称（None 则需预先选择轴线）
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.FeatureRevolve2(
        True, True, False,
        False, False, False,
        0, 0,
        angle_rad, 0,
        False, False,
        0.0, 0.0,
        0, 0, 0, True, True, True
    )


def fillet(model, radius, edges=None):
    """
    倒圆角

    参数:
        model: IModelDoc2
        radius: 圆角半径（米）
        edges: 预先选择的边线列表，None 则使用当前选择
    """
    return model.FeatureManager.FeatureFillet(
        195, radius, 0, 0, None, None, None
    )


def chamfer(model, distance, angle_deg=45):
    """
    倒角

    参数:
        distance: 倒角距离（米）
        angle_deg: 倒角角度（度）
    """
    import math
    angle_rad = angle_deg * math.pi / 180.0
    return model.FeatureManager.InsertFeatureChamfer(
        4, 1, distance, angle_rad, 0, 0, 0, 0
    )


def linear_pattern(model, feature_name, d1_x, d1_y, d1_z, d1_spacing, d1_count,
                    d2_x=0, d2_y=0, d2_z=0, d2_spacing=0, d2_count=1):
    """
    线性阵列（1D/2D）

    参数:
        feature_name: 要阵列的特征名称
        d1_*: 方向1 的方向向量（无量纲）、间距（米）和数量
        d2_*: 方向2（可选）；d2_count<=1 时忽略方向2

    实现说明（2026-10-24 SW2023 实测）:
        FeatureLinearPattern3 的真实签名是
        (Num1, Spacing1, Num2, Spacing2, FlipDir1, FlipDir2,
         DName1, DName2, GeometryPattern, VaryInstance)，没有 xyz 字符串参数。
        方向必须用「方向参照实体」表达：本函数自动建一个 3D 草图，
        沿 d1/d2 各画一条辅助线，按 mark 1/2 选中后把线名传给 DName1/DName2。
        辅助 3D 草图会被阵列引用，**不要删除**。
        数量是含源实例的总数：d1_count=3 得到 3 个实例（不是源+3）。
    """
    import math

    vector1 = (float(d1_x), float(d1_y), float(d1_z))
    if max(abs(value) for value in vector1) < 1e-12:
        raise ValueError("linear_pattern: 方向1 不能是零向量")
    if int(d1_count) < 1:
        raise ValueError("linear_pattern: d1_count 必须 >= 1")

    vector2 = (float(d2_x), float(d2_y), float(d2_z))
    use_second = int(d2_count) > 1 and max(abs(value) for value in vector2) > 1e-12

    def endpoint(vector):
        length = math.sqrt(sum(value * value for value in vector))
        scale = 0.05 / length  # 50 mm 辅助线，只表达方向
        return tuple(value * scale for value in vector)

    model.SketchManager.Insert3DSketch(True)
    line1 = model.SketchManager.CreateLine(0, 0, 0, *endpoint(vector1))
    name1 = get_com_member(line1, "GetName") or ""
    line2 = None
    name2 = ""
    if use_second:
        line2 = model.SketchManager.CreateLine(0, 0, 0, *endpoint(vector2))
        name2 = get_com_member(line2, "GetName") or ""
    model.SketchManager.Insert3DSketch(True)

    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    line1.Select2(True, 1)
    if line2 is not None:
        line2.Select2(True, 2)

    feature = model.FeatureManager.FeatureLinearPattern3(
        int(d1_count), float(d1_spacing),
        int(d2_count) if use_second else 1,
        float(d2_spacing) if use_second else 0.0,
        False, False,
        name1, name2,
        False, False
    )
    model.ClearSelection2(True)
    return feature


def circular_pattern(model, feature_name, axis_name, angle_rad, count, equal_spacing=True):
    """
    圆形阵列

    参数:
        feature_name: 要阵列的特征名称
        axis_name: 旋转轴名称
        angle_rad: 总角度（弧度）
        count: 实例数量
        equal_spacing: True=等间距
    """
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, axis_name, "AXIS", append=True, mark=1)
    return model.FeatureManager.FeatureCircularPattern4(
        count, angle_rad, False, "None", False, equal_spacing, False
    )


def shell(model, thickness, faces_to_remove=None):
    """
    抽壳

    参数:
        thickness: 壁厚（米）
        faces_to_remove: 要移除的面对象列表；None 时使用当前选择集

    实现说明（2026-10-24 SW2023 实测）:
        `IModelDoc2.InsertFeatureShell` 在本机 pywin32 动态派发下报
        「找不到成员」，但它的 dispid 仍可由 GetIDsOfNames 取得，用
        IDispatch::Invoke 直接调用可正常生成「抽壳1」。因此本函数绕开
        动态派发，改为 raw Invoke，并用调用前后的特征列表差异找回特征对象。
        不要改回 `model.InsertFeatureShell(...)`。
    """
    if float(thickness) <= 0:
        raise ValueError("shell: 壁厚必须大于 0")

    if faces_to_remove:
        model.ClearSelection2(True)
        for index, face in enumerate(faces_to_remove):
            if not face.Select2(index > 0, 1):
                model.ClearSelection2(True)
                raise ValueError(
                    "shell: 无法选择要移除的面；请传 IFace2 对象而不是名称"
                )

    def feature_names():
        features = get_com_member(
            model.FeatureManager, "GetFeatures", False
        ) or []
        return {getattr(feature, "Name", None) for feature in features}

    before = feature_names()
    dispid = model._oleobj_.GetIDsOfNames("InsertFeatureShell")
    model._oleobj_.Invoke(
        dispid, 0, pythoncom.DISPATCH_METHOD, True, float(thickness), False
    )
    model.ClearSelection2(True)

    features = get_com_member(
        model.FeatureManager, "GetFeatures", False
    ) or []
    for feature in features:
        name = getattr(feature, "Name", None)
        if name and name not in before:
            return feature
    return None


def mirror_feature(model, feature_name, mirror_plane_name):
    """
    镜像特征

    参数:
        feature_name: 要镜像的特征名称
        mirror_plane_name: 镜像基准面名称
    """
    _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
    _select_by_id(model.Extension, mirror_plane_name, "PLANE", append=True, mark=1)
    return model.FeatureManager.InsertMirrorFeature2(False, False, False, False, 0)


def hole_wizard(model, hole_type, standard, fastener_type, size, depth, x, y, z):
    """
    异型孔向导（简化版）
    注意：完整的异型孔向导参数复杂，建议参考 API 文档调整
    """
    # 异型孔向导需要通过 FeatureManager.HoleWizard5 调用
    # 具体参数取决于孔类型，此处提供框架
    pass


def rib(model, sketch_name, thickness, two_sided=True):
    """
    筋特征

    参数:
        sketch_name: 筋轮廓草图名称
        thickness: 筋厚度（米）
        two_sided: True=厚度在草图两侧各一半（InsertRib 的 Is2Sided）；
                   False=厚度在草图一侧

    实现说明（2026-10-24 SW2023 实测）:
        InsertRib 的第 1 个参数是 Is2Sided，不是拉伸方向；旧实现只传了 9 个
        参数（该 API 要 10 个），已补齐最后的 IsDraftedFromWall=False。
        本机在简单 L 形支架上实测仍返回 None（几何未生成）；弱模型优先用
        「闭合三角形草图 + 拉伸」建筋，不要依赖本函数。需要拔模角或平行拉伸
        时同样走草图拉伸路线。
    """
    _ensure_sketch_selected(model, sketch_name)
    return model.FeatureManager.InsertRib(
        two_sided, False, thickness, 0, False, False, False, 0, False, False
    )
