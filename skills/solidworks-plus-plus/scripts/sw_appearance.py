"""
SolidWorks 外观与材质工具。

SolidWorks 的外观 API 在不同版本和对象类型上差异较多，本模块优先提供
容错封装：同一颜色会依次尝试文档、特征、组件层级的常见接口。
"""
import re

try:
    from .sw_preflight import import_com_dependencies
    from .sw_connect import safe_get_com_member
except ImportError:
    from sw_preflight import import_com_dependencies
    from sw_connect import safe_get_com_member


pythoncom, _win32com, VARIANT = import_com_dependencies()

SW_THIS_CONFIGURATION = 1
SW_SPECIFY_CONFIGURATION = 3


PRESET_COLORS = {
    "iron_red": "#8A0E0E",
    "armor_gold": "#D99A22",
    "dark_gunmetal": "#1F2328",
    "arc_blue": "#2AA8FF",
    "black": "#050505",
    "white": "#F2F2F2",
    "silver": "#BFC4C8",
    "aqua_blue": "#4FA6A8",
    "glass_tint": "#10232E",
    "signal_red": "#E31B35",
    "light_cyan": "#9DEBFF",
    "tire_black": "#111315",
    "graphite": "#33383D",
}


def rgb01(color):
    """
    将颜色转换为 0..1 RGB。

    支持:
        - 预设名，如 "iron_red"
        - 十六进制，如 "#8A0E0E"
        - 0..255 RGB 元组
        - 0..1 RGB 元组
    """
    if isinstance(color, str):
        value = PRESET_COLORS.get(color, color).strip()
        match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value)
        if not match:
            raise ValueError(f"未知颜色: {color}")
        hex_value = match.group(1)
        return tuple(int(hex_value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    if len(color) != 3:
        raise ValueError("RGB 颜色必须包含 3 个值")
    if max(color) > 1:
        return tuple(float(v) / 255.0 for v in color)
    return tuple(float(v) for v in color)


def material_values(color, ambient=0.35, diffuse=0.75, specular=0.45,
                    shininess=0.35, transparency=0.0, emission=0.0):
    """
    生成 SolidWorks 材质属性数组。

    数组顺序为:
        red, green, blue, ambient, diffuse, specular, shininess, transparency, emission
    """
    red, green, blue = rgb01(color)
    return [red, green, blue, ambient, diffuse, specular, shininess, transparency, emission]


def material_variant(values):
    """把九位材质数组封装为 COM SAFEARRAY(double)，防止 RGB 通道错位。"""
    if len(values) != 9:
        raise ValueError("SolidWorks 材质数组必须包含 9 个值")
    return VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in values])


def _configuration_args(configuration):
    """生成 SetMaterialPropertyValues2 的配置选项和名称参数。"""
    if not configuration:
        return SW_THIS_CONFIGURATION, None
    names = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_BSTR, [str(configuration)])
    return SW_SPECIFY_CONFIGURATION, names


def _try_set(target, attr_name, values, *args):
    """尝试设置属性或调用方法；void 方法无异常即视为成功。"""
    try:
        member = getattr(target, attr_name)
        if callable(member):
            result = member(values, *args)
        else:
            setattr(target, attr_name, values)
            result = True
        return bool(result) if result is not None else True
    except Exception:
        return False


def get_material_property_values(target):
    """读取文档、特征或组件的九位材质数组，读取失败返回 None。"""
    readers = [
        lambda: target.MaterialPropertyValues,
        lambda: target.GetMaterialPropertyValues(),
    ]
    for reader in readers:
        try:
            values = reader()
            if values is not None and len(values) >= 9:
                return tuple(float(value) for value in values[:9])
        except Exception:
            pass
    return None


def verify_appearance(target, color, tolerance=0.01):
    """回读并验证目标前三位 RGB，返回结构化结果。"""
    expected = rgb01(color)
    actual_values = get_material_property_values(target)
    actual = actual_values[:3] if actual_values else None
    max_error = max(abs(a - e) for a, e in zip(actual, expected)) if actual else None
    return {
        "ok": actual is not None and max_error <= float(tolerance),
        "expected_rgb": expected,
        "actual_rgb": actual,
        "max_error": max_error,
    }


def set_document_appearance(model, color, configuration=""):
    """
    设置文档级外观颜色。

    返回:
        bool 是否至少一个接口调用成功。
    """
    packed = material_variant(material_values(color))
    option, names = _configuration_args(configuration)
    if configuration:
        extension = getattr(model, "Extension", None)
        wrote = bool(extension) and _try_set(
            extension, "SetMaterialPropertyValues", packed, option, names
        )
    else:
        wrote = _try_set(model, "MaterialPropertyValues", packed)
    return wrote and verify_appearance(model, color)["ok"]


def set_feature_appearance(feature, color, configuration=""):
    """
    设置特征级外观颜色。

    返回:
        bool 是否至少一个接口调用成功。
    """
    packed = material_variant(material_values(color))
    option, names = _configuration_args(configuration)
    wrote = _try_set(feature, "SetMaterialPropertyValues2", packed, option, names)
    if not wrote and not configuration:
        wrote = _try_set(feature, "SetMaterialPropertyValues", packed)
    return wrote and verify_appearance(feature, color)["ok"]


def set_component_appearance(component, color, configuration="", transparency=None):
    """
    设置装配体组件外观颜色，可同时设置透明度。

    参数:
        component: IComponent2
        color: 颜色（预设名 / #RRGGBB / RGB 元组）
        configuration: 留空=当前配置；否则指定配置名
        transparency: None=沿用数组默认值（不透明）；0.0=不透明，1.0=全透明。
            SW2023 实测：0.82 左右是“玻璃壳体”观感，超过 0.9 基本只剩轮廓线。

    返回:
        bool 颜色回读一致且（若给了透明度）透明度回读一致。

    实测（SW2023 SP0.1）：
        ``component.SetMaterialPropertyValues2(mat, 2, VARIANT(VT_ARRAY|VT_BSTR, []))``
        写入成功，``component.MaterialPropertyValues`` 回读 9 位数组一致；
        ``swAllConfiguration=2`` + 空 BSTR 数组可用，不需要逐配置写。
        封装的默认写法 ``(mat, 1, None)``（swThisConfiguration + 空名称）同样通过，
        见 ``tests/solidworks_appearance_regression.py`` 的透明度用例。
    """
    values = material_values(color, transparency=0.0 if transparency is None else transparency)
    packed = material_variant(values)
    option, names = _configuration_args(configuration)
    wrote = _try_set(component, "SetMaterialPropertyValues2", packed, option, names)
    if not wrote and not configuration:
        wrote = _try_set(component, "MaterialPropertyValues", packed)
    if not wrote or not verify_appearance(component, color)["ok"]:
        return False
    if transparency is None:
        return True
    return verify_transparency(component, transparency)["ok"]


def get_component_transparency(component):
    """
    读取组件透明度（9 位材质数组第 8 位，0=不透明）。

    返回:
        float 或 None（读取失败）。
    """
    values = get_material_property_values(component)
    return None if values is None else values[7]


def set_component_transparency(component, transparency, color=None, configuration=""):
    """
    只改透明度，保留现有 RGB（color 为 None 且读不到现有颜色时抛异常）。

    参数:
        transparency: 0.0=不透明，1.0=全透明。
        color: 可选；给了就用该颜色重写整组材质值。

    返回:
        bool 透明度回读一致。
    """
    level = float(transparency)
    if not 0.0 <= level <= 1.0:
        raise ValueError("transparency 必须在 0..1 之间")
    current = get_material_property_values(component)
    if color is None:
        if current is None:
            raise RuntimeError("读不到组件现有颜色，请显式传 color")
        values = list(current)
    else:
        values = material_values(color)
    values[7] = level
    packed = material_variant(values)
    option, names = _configuration_args(configuration)
    wrote = _try_set(component, "SetMaterialPropertyValues2", packed, option, names)
    return bool(wrote) and verify_transparency(component, level)["ok"]


def verify_transparency(component, expected, tolerance=0.02):
    """回读并验证组件透明度，返回结构化结果。"""
    actual = get_component_transparency(component)
    return {
        "ok": actual is not None and abs(actual - float(expected)) <= float(tolerance),
        "expected": float(expected),
        "actual": actual,
    }


def apply_component_palette(assignments, strict=True):
    """
    批量设置组件颜色（可选透明度）并逐项回读。

    参数:
        assignments: ``[(component, color), ...]`` 或 ``[(component, color, transparency), ...]``
        strict: True 时任何组件失败立即抛出 RuntimeError

    返回:
        list[dict]，包含 index、color、transparency、ok、expected_rgb、actual_rgb、max_error
    """
    reports = []
    for index, item in enumerate(assignments):
        if len(item) not in (2, 3):
            raise ValueError("每次分配必须是 (component, color) 或 (component, color, transparency)")
        component, color = item[0], item[1]
        transparency = item[2] if len(item) == 3 else None
        wrote = set_component_appearance(component, color, transparency=transparency)
        report = verify_appearance(component, color)
        report.update({"index": index, "color": color, "transparency": transparency})
        if transparency is not None:
            report["transparency_check"] = verify_transparency(component, transparency)
            report["ok"] = bool(wrote and report["ok"] and report["transparency_check"]["ok"])
        else:
            report["ok"] = bool(wrote and report["ok"])
        reports.append(report)
        if strict and not report["ok"]:
            raise RuntimeError(
                f"组件 {index} 外观验证失败: 预期 {report['expected_rgb']}，"
                f"实际 {report['actual_rgb']}"
            )
    return reports


def component_part_name(component):
    """
    组件名去掉实例后缀：``11_body-3`` → ``11_body``。

    装配里同一零件的多个实例是 ``<零件名>-<序号>``；按零件名配色时必须先剥掉后缀。
    """
    name = str(safe_get_com_member(component, "Name2") or "")
    head, sep, tail = name.rpartition("-")
    return head if sep and tail.isdigit() else name


def _style_pass(asm_model, style_map, tolerance):
    """对整台装配跑一遍配色 + 回读。返回 (details, failed, unmatched)。"""
    details, failed, unmatched = [], [], []
    for component in (safe_get_com_member(asm_model, "GetComponents", False) or []):
        part = component_part_name(component)
        key = part if part in style_map else None
        if key is None:
            candidates = [k for k in style_map if k and k in part]
            key = max(candidates, key=len) if candidates else None
        if key is None:
            unmatched.append(part)
            details.append({"component": part, "ok": False, "reason": "no style rule"})
            continue

        style = style_map[key]
        color, transparency = style if isinstance(style, (tuple, list)) else (style, None)
        wrote = set_component_appearance(component, color, transparency=transparency)
        rgb_check = verify_appearance(component, color, tolerance=tolerance)
        alpha_check = (
            verify_transparency(component, transparency, tolerance=tolerance)
            if transparency is not None else {"ok": True}
        )
        ok = bool(wrote and rgb_check["ok"] and alpha_check["ok"])
        details.append({
            "component": part, "rule": key, "color": color,
            "transparency": transparency, "ok": ok,
            "rgb": rgb_check["actual_rgb"],
            "readback_transparency": alpha_check.get("actual"),
        })
        if not ok:
            failed.append(part)
    return details, failed, unmatched


def apply_component_style_map(asm_model, style_map, strict=True, tolerance=0.02,
                              retry_after_rebuild=True):
    """
    按零件名批量设置组件颜色/透明度，并逐个回读验证。

    SW2023 实测（2026-10-25，减速器透明涂色）：装配刚打开、还在解析组件时，
    最先上色的几个零件会**静默保留零件本来的颜色**——setter 不报错，
    回读却是 ``[1,1,1]``。只有回读能抓到。抓到后 ``ForceRebuild3(False)``
    再整台重跑一遍就能写进去，所以默认 ``retry_after_rebuild=True``。

    参数:
        asm_model: IAssemblyDoc
        style_map: ``{零件名: 颜色}`` 或 ``{零件名: (颜色, 透明度)}``。
            零件名先按 ``component_part_name()`` 去掉 ``-N`` 实例后缀；
            精确匹配优先，否则取最长的、作为子串出现的键（兼容“下盖”这类片段）。
        strict: True 时只要有组件匹配不到或回读失败就抛 RuntimeError。
        tolerance: RGB/透明度回读容差（0..1）。
        retry_after_rebuild: 回读失败时重建后整台重跑一遍。

    返回:
        dict: ok、applied、unmatched、failed、details、retried。
    """
    details, failed, unmatched = _style_pass(asm_model, style_map, tolerance)
    retried = False
    if failed and retry_after_rebuild:
        try:
            asm_model.ForceRebuild3(False)
        except Exception:
            pass
        details, failed, unmatched = _style_pass(asm_model, style_map, tolerance)
        retried = True

    report = {
        "ok": not failed and not unmatched,
        "applied": len(details) - len(unmatched) - len(failed),
        "unmatched": unmatched,
        "failed": failed,
        "details": details,
        "retried": retried,
    }
    if strict and not report["ok"]:
        raise RuntimeError(
            f"组件配色未全部通过: unmatched={unmatched}, failed={failed}")
    return report


def apply_named_appearance(target, name):
    """
    给任意常见对象应用预设外观。

    该函数会按文档、组件、特征的顺序尝试。
    """
    return (
        set_document_appearance(target, name)
        or set_component_appearance(target, name)
        or set_feature_appearance(target, name)
    )
