"""
SolidWorks 钣金工具：基体法兰与平板型式审计。

SW2023 SP0.1 实测结论（见 references/sheet-metal.md）：
    - ``InsertSheetMetalBaseFlange`` 可用，16 个参数，草图必须先被选中；
    - 基体法兰会**自动生成** ``FlatPattern`` 特征，不需要 ``CreateDefinition(38)``；
    - ``InsertSheetMetalEdgeFlange2`` 在本机返回 ``None``，侧壁应改用开放轮廓
      的基体法兰一次成形，本模块不封装边线法兰。
"""
try:
    from .sw_preflight import import_com_dependencies
    from .sw_connect import safe_get_com_member
except ImportError:
    from sw_preflight import import_com_dependencies
    from sw_connect import safe_get_com_member

pythoncom, win32com, VARIANT = import_com_dependencies()


def _select_sketch(model, sketch_name):
    """选中草图；返回 SelectByID2 的布尔结果。"""
    try:
        from .sw_part import _select_by_id
    except ImportError:
        from sw_part import _select_by_id

    model.ClearSelection2(True)
    return bool(_select_by_id(model.Extension, sketch_name, "SKETCH"))


def insert_base_flange(model, sketch_name, thickness, radius,
                       extrude_distance=0.0, thicken_dir=True, flip_dir=False):
    """
    由已完成的草图插入基体法兰（钣金主特征）。

    参数:
        model: 零件文档（IModelDoc2）。
        sketch_name: 草图名称，必须已完成（end_sketch 之后）。
        thickness: 板厚（米；用 ``mm(0.5)``）。
        radius: 全局折弯半径（米）。
        extrude_distance: 方向 1 拉伸长度（米）。闭合轮廓传 0（平板）；
            开放轮廓传板长，侧壁随截面一起成形。
        thicken_dir: 加厚方向。
        flip_dir: 是否翻转拉伸方向。

    返回:
        IFeature；失败返回 None（先查草图是否选中、轮廓是否自交）。

    实测（SW2023 SP0.1，2026-10-25）：
        闭合矩形 100×50 + ``thickness=0.5, radius=0.5, extrude_distance=0``
        → 包围盒 [-50,-25,-0.5,50,25,0] mm、体积 2500.0 mm³、1 个实体，
        特征树自动出现 SheetMetal / SMBaseFlange / FlatPattern。
        开放轮廓 ``extrude_distance=120 mm`` → 底板 + 侧壁一次成形。
    """
    if not sketch_name:
        raise ValueError("sketch_name 不能为空：基体法兰必须先选中草图")
    if float(thickness) <= 0 or float(radius) < 0:
        raise ValueError("thickness 必须 > 0，radius 不能为负")
    if not _select_sketch(model, sketch_name):
        return None

    empty_dispatch = VARIANT(pythoncom.VT_DISPATCH, None)
    return model.FeatureManager.InsertSheetMetalBaseFlange(
        float(thickness),       # Thickness
        bool(thicken_dir),      # ThickenDir
        float(radius),          # Radius
        float(extrude_distance),# ExtrudeDist1
        0.0,                    # ExtrudeDist2
        bool(flip_dir),         # FlipExtruDir
        0, 0, 0,                # EndCondition1 / EndCondition2 / DirToUse
        empty_dispatch,         # PCBA：空 CustomBendAllowance
        True,                   # UseDefaultRelief
        0, 0.0, 0.0, 0.0,       # ReliefType / Width / Depth / Ratio
        False,                  # UseReliefRatio
    )


def collect_feature_types(model):
    """
    返回特征树里的 (名称, 类型名) 列表，按特征树顺序。

    类型名用 ``GetTypeName2()``，钣金相关：``SheetMetal``、``SMBaseFlange``、
    ``FlatPattern``、``EdgeFlange``。
    """
    features = []
    feature = safe_get_com_member(model, "FirstFeature")
    while feature:
        features.append((
            str(safe_get_com_member(feature, "Name")),
            str(safe_get_com_member(feature, "GetTypeName2")),
        ))
        feature = safe_get_com_member(feature, "GetNextFeature")
    return features


def audit_sheet_metal(model):
    """
    审计钣金特征是否齐全。

    返回:
        dict：``feature_types``、``has_sheet_metal``、``has_base_flange``、
        ``has_flat_pattern``、``flat_pattern_name``、``ok``。

    ``ok`` 为 False 时最常见的两种原因：
        1. 用普通拉伸代替了基体法兰（没有 FlatPattern）；
        2. 基体法兰调用失败（没有 SMBaseFlange）。
    """
    features = collect_feature_types(model)
    types = [type_name for _name, type_name in features]
    flat_names = [name for name, type_name in features if type_name == "FlatPattern"]
    result = {
        "feature_types": types,
        "has_sheet_metal": "SheetMetal" in types,
        "has_base_flange": "SMBaseFlange" in types,
        "has_flat_pattern": bool(flat_names),
        "flat_pattern_name": flat_names[0] if flat_names else None,
    }
    result["ok"] = (
        result["has_sheet_metal"]
        and result["has_base_flange"]
        and result["has_flat_pattern"]
    )
    return result


def assert_sheet_metal(model):
    """
    交付前门禁：钣金特征必须齐全，否则抛 RuntimeError。

    返回:
        ``audit_sheet_metal(model)`` 的结果。
    """
    audit = audit_sheet_metal(model)
    if not audit["ok"]:
        missing = [
            label for key, label in (
                ("has_sheet_metal", "SheetMetal"),
                ("has_base_flange", "SMBaseFlange"),
                ("has_flat_pattern", "FlatPattern"),
            ) if not audit[key]
        ]
        raise RuntimeError(
            "钣金特征缺失: " + ", ".join(missing)
            + "。检查是否用普通拉伸代替了基体法兰，或基体法兰调用返回 None。"
        )
    return audit
