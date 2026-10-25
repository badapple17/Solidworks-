"""
SolidWorks 连接工具
提供连接到 SolidWorks 实例的各种方法
"""
import atexit
import glob
import os
import tempfile
import time
from pathlib import Path

try:
    from .sw_preflight import ensure_solidworks_installed, import_com_dependencies
except ImportError:
    from sw_preflight import ensure_solidworks_installed, import_com_dependencies

pythoncom, win32com_client, VARIANT = import_com_dependencies()


DOC_TYPE_MAP = {
    "part": 1,
    "prt": 1,
    "sldprt": 1,
    "assembly": 2,
    "asm": 2,
    "sldasm": 2,
    "drawing": 3,
    "drw": 3,
    "slddrw": 3,
}

DOC_TYPE_LABELS = {
    "part": "零件",
    "assembly": "装配体",
    "drawing": "工程图",
}

DEFAULT_TEMPLATE_PREFS = {
    "part": 8,       # swUserPreferenceStringValue_e.swDefaultTemplatePart
    "assembly": 9,   # swUserPreferenceStringValue_e.swDefaultTemplateAssembly
    "drawing": 10,   # swUserPreferenceStringValue_e.swDefaultTemplateDrawing
}

SW_ALWAYS_USE_DEFAULT_TEMPLATES = 111


class SolidWorksConnectionError(RuntimeError):
    """带阶段和错误码的 SolidWorks 连接错误。"""

    def __init__(self, code, stage, message):
        self.code = code
        self.stage = stage
        super().__init__(f"[{code}] {stage}: {message}")


class _LaunchGuard:
    """跨进程启动互斥；Windows 使用命名 Mutex，其它平台使用独占锁文件。"""

    def __init__(self, name="CADStudio.SolidWorks.Launch"):
        self.name = name
        self.handle = None
        self.path = Path(tempfile.gettempdir()) / "cad-studio-solidworks-launch.lock"
        self._owns_file = False

    def __enter__(self):
        if os.name == "nt":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            self.handle = kernel32.CreateMutexW(None, False, self.name)
            if not self.handle:
                raise SolidWorksConnectionError("SW_MUTEX", "locking", "无法创建 SolidWorks 启动互斥锁")
            wait_result = kernel32.WaitForSingleObject(self.handle, 15000)
            if wait_result not in (0, 0x80):
                kernel32.CloseHandle(self.handle)
                self.handle = None
                raise SolidWorksConnectionError("SW_MUTEX_TIMEOUT", "locking", "等待其它启动任务超时")
            return self

        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            self._owns_file = True
        except FileExistsError as exc:
            try:
                stale_pid = int(self.path.read_text(encoding="ascii").strip())
                os.kill(stale_pid, 0)
            except (ProcessLookupError, ValueError):
                self.path.unlink(missing_ok=True)
                return self.__enter__()
            raise SolidWorksConnectionError("SW_MUTEX_BUSY", "locking", "已有 SolidWorks 启动任务") from exc
        return self

    def __exit__(self, *_):
        if os.name == "nt" and self.handle:
            import ctypes

            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
        elif self._owns_file:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._owns_file = False


def get_com_member(obj, attr_name, *args):
    """
    兼容 pywin32 中“同一成员在不同环境下可能是属性也可能是方法”的情况。

    参数:
        obj: COM 对象
        attr_name: 成员名称
        *args: 当成员可调用时传入的参数

    返回:
        成员值或调用结果
    """
    member = getattr(obj, attr_name)
    if args:
        return member(*args)
    try:
        return member() if callable(member) else member
    except Exception as exc:
        message = str(exc)
        if "-2147352573" in message or "找不到成员" in message or "Member not found" in message:
            return member
        raise


def safe_get_com_member(obj, attr_name, *args):
    """
    读取 COM 成员，兼容 pywin32 中伪可调用属性。

    保留该别名便于其它模块表达“安全读取”的意图；核心逻辑统一在 get_com_member。
    """
    return get_com_member(obj, attr_name, *args)


def create_empty_dispatch_variant():
    """创建可传给 COM 接口的空 Dispatch 参数。"""
    return VARIANT(pythoncom.VT_DISPATCH, None)


def normalize_doc_type(doc_type):
    """
    规范化文档类型名称。

    参数:
        doc_type: "part"、"assembly"、"drawing" 或常见缩写/扩展名

    返回:
        (name, enum_value) 元组
    """
    key = str(doc_type).strip().lower().lstrip(".")
    enum_value = DOC_TYPE_MAP.get(key)
    if enum_value is None:
        raise ValueError(f"未知文档类型: {doc_type}")

    name_map = {1: "part", 2: "assembly", 3: "drawing"}
    return name_map[enum_value], enum_value


def _expand_path(file_path):
    """展开用户目录和环境变量，并返回绝对路径。"""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(file_path)))


def _ensure_parent_dir(file_path):
    """确保输出文件的父目录存在。"""
    parent = os.path.dirname(_expand_path(file_path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _prog_id_for_version(version):
    """返回 SolidWorks 年份对应的 ProgID。"""
    if version is None:
        return "SldWorks.Application"
    try:
        year = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"SolidWorks 版本必须是年份，例如 2024: {version}") from exc
    if year < 2010 or year > 2035:
        raise ValueError(f"不支持的 SolidWorks 版本年份: {year}")
    return f"SldWorks.Application.{(year - 2000) + 8}"


def _read_active_document(sw):
    """读取活动文档，兼容 COM 属性/方法差异。"""
    try:
        return get_com_member(sw, "ActiveDoc")
    except Exception:
        return None


def _wait_until_ready(sw, timeout_seconds):
    """等待 COM 服务器可读，避免固定 sleep 导致 UI 假死。"""
    deadline = time.monotonic() + max(0.1, float(timeout_seconds))
    last_error = None
    while time.monotonic() < deadline:
        try:
            get_com_member(sw, "RevisionNumber")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise SolidWorksConnectionError(
        "SW_START_TIMEOUT", "ready", f"SolidWorks 启动超时（{timeout_seconds:.1f}s）: {last_error or 'COM 未就绪'}"
    )


def close_all_documents(sw, save=False):
    """
    关闭 SolidWorks 里所有已打开的文档，返回是否执行过关闭。

    为什么必须关：装配体 `CloseDoc` 之后，被引用的零件文档仍留在内存里，
    它们继续占着磁盘文件锁。用户双击交付的 .SLDPRT/.SLDASM 会打不开、报只读
    或被拒，只能重启电脑。脚本收尾一定要走到这里。

    参数:
        save: False（默认）= 丢弃未保存修改，不会弹保存对话框卡住自动化。
    """
    try:
        sw.CloseAllDocuments(bool(save))
        return True
    except Exception:
        pass
    closed_any = False
    try:
        # SW2023 实测：没有文档时 GetDocuments 是属性且返回 None，加括号会抛
        # "'NoneType' object is not callable"；用 get_com_member 兼容两种形态。
        documents = safe_get_com_member(sw, "GetDocuments") or []
    except Exception:
        documents = []
    for document in documents:
        try:
            title = safe_get_com_member(document, "GetTitle")
            if title:
                sw.CloseDoc(title)
                closed_any = True
        except Exception:
            continue
    return closed_any


def close_owned_solidworks(sw, started_by_cad_studio, close_documents=True):
    """
    只退出由当前 CAD Studio 会话启动的 SolidWorks 实例。

    先关文档（不保存）再 ExitApp：否则未关的文档会让 ExitApp 弹保存对话框，
    隐藏实例里没人点确认，进程就一直挂着占文件锁。
    """
    if not started_by_cad_studio:
        return False
    if close_documents:
        close_all_documents(sw, save=False)
    for member_name in ("ExitApp", "Quit"):
        try:
            member = getattr(sw, member_name)
            member() if callable(member) else None
            return True
        except Exception:
            continue
    return False


_OPENED_DOCUMENTS = []   # [(sw, model, title)] 本进程打开/新建的文档
_OWNED_INSTANCES = []    # [sw] 本进程启动的 SolidWorks 实例
_RELEASE_HOOKED = False


def register_owned_instance(sw):
    """登记本进程启动的实例，并挂一次 atexit 释放钩子（进程退出自动清场）。"""
    global _RELEASE_HOOKED
    if not any(item is sw for item in _OWNED_INSTANCES):
        _OWNED_INSTANCES.append(sw)
    if not _RELEASE_HOOKED:
        atexit.register(release_solidworks)
        _RELEASE_HOOKED = True


def _remember_document(sw, model):
    """记录本进程打开/新建的文档，释放时只关自己开的文档。"""
    try:
        title = safe_get_com_member(model, "GetTitle")
    except Exception:
        return model
    if title and all(existing[2] != title for existing in _OPENED_DOCUMENTS):
        _OPENED_DOCUMENTS.append((sw, model, title))
    return model


def release_solidworks(sw=None, quit_owned=True, close_documents=True, save=False):
    """
    释放 SolidWorks：关闭本进程打开的文档，退出本进程启动的实例。

    为什么必须做：只 `CloseDoc(装配体)` 时，被引用的零件文档仍留在内存里，
    继续占着磁盘文件锁；自动化实例又常常不在 ROT 里，用户双击交付的
    .SLDPRT/.SLDASM 会打不开或只能只读，往往要重启电脑才好。
    进程退出还有隐藏实例挂着，任务管理器里能看到 SLDWORKS.exe。

    `connect_solidworks()` 启动实例时会自动登记并挂 atexit 钩子，所以正常
    脚本无需显式调用；它主要给 `SolidWorksSession.finish()`、测试和
    异常中断后的手工清场用。

    参数:
        sw: 只释放该实例；None 表示释放本进程登记的全部实例。
        quit_owned: 是否退出本进程启动的实例。
        close_documents: 是否关闭本进程打开/新建的文档。
        save: 关闭前是否保存未保存的修改；默认 False，不会弹保存对话框。

    返回:
        dict: documents_closed、instances_quit、owned。
    """
    closed = 0
    if close_documents:
        for entry in list(_OPENED_DOCUMENTS):
            owner, model, title = entry
            if sw is not None and owner is not sw:
                continue
            if save:
                try:
                    save_document(model)
                except Exception:
                    pass
            try:
                owner.CloseDoc(title)
                closed += 1
            except Exception:
                pass
            try:
                _OPENED_DOCUMENTS.remove(entry)
            except ValueError:
                pass

    # 只有本进程**登记过**的实例才允许退出。用户自己双击启动的 SolidWorks
    # 不在登记表里，脚本绝不能把它关掉（否则会丢用户未保存的工作）。
    owned_targets = [
        instance for instance in _OWNED_INSTANCES
        if sw is None or instance is sw
    ] if quit_owned else []

    quit_count = 0
    keep_alive = os.environ.get("SW_KEEP_ALIVE") == "1"
    for instance in owned_targets:
        try:
            # 依赖零件会随装配体一起关掉：只 CloseDoc(装配体) 不够。
            close_all_documents(instance, save=save)
        except Exception:
            pass
        if not keep_alive:
            try:
                if close_owned_solidworks(instance, True, close_documents=False):
                    quit_count += 1
            except Exception:
                pass
        try:
            _OWNED_INSTANCES.remove(instance)
        except ValueError:
            pass
    if sw is None:
        _OPENED_DOCUMENTS.clear()
    return {
        "documents_closed": closed,
        "instances_quit": quit_count,
        "owned": bool(owned_targets),
    }


def connect_solidworks(version=None, wait_seconds=5, visible=True, return_metadata=False):
    """
    连接到 SolidWorks 实例。

    参数:
        version: SolidWorks 版本年份（如 2024），None 则自动检测
        wait_seconds: 启动新实例后等待秒数
        visible: 启动新实例后是否显示窗口

    返回:
        (sw, model) 元组，model 可能为 None（无打开的文档时）
    """
    ensure_solidworks_installed()
    prog_id = _prog_id_for_version(version)
    sw = None
    launched_here = False

    # 启动和附着共享同一把互斥锁，避免多个 worker 同时拉起实例。
    with _LaunchGuard():
        try:
            sw = win32com_client.GetActiveObject(prog_id)
            print(f"已连接到运行中的 SolidWorks 实例（ProgID: {prog_id}）")
        except Exception as attach_error:
            try:
                sw = win32com_client.Dispatch(prog_id)
                launched_here = True
                try:
                    sw.Visible = visible
                except Exception:
                    pass
                print(f"启动了新的 SolidWorks 实例（ProgID: {prog_id}）")
                _wait_until_ready(sw, wait_seconds)
            except SolidWorksConnectionError:
                close_owned_solidworks(sw, launched_here)
                raise
            except Exception as launch_error:
                close_owned_solidworks(sw, launched_here)
                raise SolidWorksConnectionError(
                    "SW_LAUNCH_FAILED", "launch", f"无法启动 {prog_id}: {launch_error}; attach={attach_error}"
                ) from launch_error

    if sw is None:
        raise SolidWorksConnectionError("SW_NO_INSTANCE", "connect", "未获得 SolidWorks COM 实例")

    model = _read_active_document(sw)
    if model:
        doc_types = {1: "零件", 2: "装配体", 3: "工程图"}
        doc_type = get_com_member(model, "GetType")
        title = get_com_member(model, "GetTitle")
        print(f"当前文档: {title} (类型: {doc_types.get(doc_type, '未知')})")
    else:
        print("当前没有打开的文档")

    if launched_here:
        register_owned_instance(sw)

    metadata = {
        "prog_id": prog_id,
        "requested_version": int(version) if version is not None else None,
        "started_by_cad_studio": launched_here,
    }
    return (sw, model, metadata) if return_metadata else (sw, model)


def get_sw_version(sw):
    """获取 SolidWorks 版本信息。"""
    rev = get_com_member(sw, "RevisionNumber")
    major = int(rev.split(".")[0])
    year = major - 8 + 2000
    return {"revision": rev, "year": year, "major": major}


def find_template(sw, doc_type="part"):
    """
    自动查找 SolidWorks 文档模板。

    参数:
        sw: SolidWorks 应用对象
        doc_type: "part" | "assembly" | "drawing"

    返回:
        模板文件路径字符串
    """
    doc_type, _ = normalize_doc_type(doc_type)

    type_map = {
        "part": (sw.GetUserPreferenceStringValue(DEFAULT_TEMPLATE_PREFS["part"]), "*.prtdot"),
        "assembly": (sw.GetUserPreferenceStringValue(DEFAULT_TEMPLATE_PREFS["assembly"]), "*.asmdot"),
        "drawing": (sw.GetUserPreferenceStringValue(DEFAULT_TEMPLATE_PREFS["drawing"]), "*.drwdot"),
    }

    default_path, pattern = type_map.get(doc_type, type_map["part"])
    if default_path:
        for candidate_root in str(default_path).split(";"):
            candidate_root = _expand_path(candidate_root.strip().strip('"'))
            if not candidate_root:
                continue

            if os.path.isfile(candidate_root):
                return candidate_root

            if os.path.isdir(candidate_root):
                matches = glob.glob(os.path.join(candidate_root, pattern))
                if matches:
                    return matches[0]

    search_dirs = [
        r"C:\ProgramData\SolidWorks\SOLIDWORKS *\templates",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\chinese-simplified",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\lang\english",
    ]
    for search_dir in search_dirs:
        matches = glob.glob(os.path.join(os.path.expandvars(search_dir), pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(f"无法找到 {doc_type} 模板文件，请手动指定路径")


def ensure_default_templates(sw):
    """
    @brief 配置默认模板并关闭新建文件模板选择提示。
    @param sw SolidWorks 应用对象。
    @return 字典，包含已确认的默认模板路径。
    """
    templates = {}
    for doc_type, preference in DEFAULT_TEMPLATE_PREFS.items():
        template_path = find_template(sw, doc_type)
        templates[doc_type] = template_path
        current_path = str(sw.GetUserPreferenceStringValue(preference) or "")
        if _expand_path(current_path) != _expand_path(template_path):
            sw.SetUserPreferenceStringValue(preference, template_path)
    try:
        sw.SetUserPreferenceToggle(SW_ALWAYS_USE_DEFAULT_TEMPLATES, True)
    except Exception as exc:
        print(f"提示: 无法设置始终使用默认模板: {exc}")
    return templates


def new_document(sw, doc_type="part", template_path=None):
    """
    创建新文档。

    参数:
        sw: SolidWorks 应用对象
        doc_type: "part" | "assembly" | "drawing"
        template_path: 模板路径，None 则自动查找

    返回:
        新建的 IModelDoc2 对象
    """
    doc_type, _ = normalize_doc_type(doc_type)
    if not template_path:
        template_path = find_template(sw, doc_type)
    else:
        template_path = _expand_path(template_path)

    model = sw.NewDocument(template_path, 0, 0, 0)
    if model is None:
        for _ in range(20):
            model = sw.ActiveDoc
            if model is not None:
                break
            time.sleep(0.25)

    if model is None:
        raise RuntimeError(f"创建{DOC_TYPE_LABELS.get(doc_type, doc_type)}文档失败，SolidWorks 未返回活动文档")

    print(f"已创建新{DOC_TYPE_LABELS.get(doc_type, doc_type)}文档")
    return _remember_document(sw, model)


def open_document(sw, file_path, read_only=False, silent=False, raise_on_error=False):
    """
    打开已有文档。

    参数:
        sw: SolidWorks 应用对象
        file_path: 文件完整路径
        read_only: 是否以只读模式打开
        silent: 是否静默打开
        raise_on_error: 打开失败时是否抛出异常

    返回:
        IModelDoc2 对象
    """
    file_path = _expand_path(file_path)
    if not os.path.exists(file_path):
        message = f"文件不存在: {file_path}"
        if raise_on_error:
            raise FileNotFoundError(message)
        print(message)
        return None

    # 装配体会把组件文档加载到当前会话；再次 OpenDoc6 可能返回
    # swFileWithSameTitleAlreadyOpen。复用同一路径对象也能保留文档所有权。
    try:
        existing_model = sw.GetOpenDocumentByName(file_path)
    except Exception:
        existing_model = None
    if existing_model is not None:
        print(f"已复用打开文档: {file_path}")
        return existing_model

    ext = os.path.splitext(file_path)[1].lower()
    foreign_exts = {".step", ".stp", ".igs", ".iges"}
    type_map = {".sldprt": 1, ".sldasm": 2, ".slddrw": 3}

    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    options = 2 if read_only else 0  # swOpenDocOptions_ReadOnly = 2
    if silent:
        options |= 1  # swOpenDocOptions_Silent = 1

    if ext in foreign_exts:
        if read_only:
            print("提示: LoadFile4 导入外来 CAD 文件时不支持 read_only，已忽略该参数")
        if silent:
            print("提示: LoadFile4 导入外来 CAD 文件时不支持 OpenDoc6 silent 选项，已忽略该参数")
        ensure_default_templates(sw)
        import_data = sw.GetImportFileData(file_path)
        if import_data is None:
            message = f"获取导入数据失败: {file_path}"
            if raise_on_error:
                raise RuntimeError(message)
            print(message)
            return None
        # 非 DXF/DWG、非 Pro/E 外来文件应传 "r"，表示导入为新的 SolidWorks 文档；
        # 空字符串会在部分 SW2024 环境中弹出模板选择对话框并阻塞自动化。
        model = sw.LoadFile4(file_path, "r", import_data, errors)
        warnings.value = 0
    else:
        doc_type = type_map.get(ext, 1)
        try:
            model = sw.OpenDoc6(file_path, doc_type, options, "", errors, warnings)
        except TypeError:
            # SW2024 的 makepy 强类型代理可能对 [out] long 再做 int(VARIANT)，
            # 动态代理会把显式 by-ref VARIANT 正确传给原生 OpenDoc6。
            ole_object = getattr(sw, "_oleobj_", None)
            if ole_object is None:
                raise
            dynamic_sw = win32com_client.dynamic.DumbDispatch(ole_object, "SldWorks.Application")
            model = dynamic_sw.OpenDoc6(file_path, doc_type, options, "", errors, warnings)
        if isinstance(model, (tuple, list)):
            values = list(model)
            model = values[0] if values else None
            if len(values) > 1 and values[1] is not None:
                errors.value = int(values[1])
            if len(values) > 2 and values[2] is not None:
                warnings.value = int(values[2])
    if model:
        print(f"已打开: {file_path}")
    else:
        message = f"打开失败, 错误码: {errors.value}, 警告码: {warnings.value}"
        if raise_on_error:
            raise RuntimeError(message)
        print(message)
    return _remember_document(sw, model) if model else model


def save_document(model, file_path=None):
    """
    保存文档。

    参数:
        model: IModelDoc2 对象
        file_path: 另存为路径，None 则保存到当前位置

    返回:
        bool 成功/失败
    """
    errors = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warnings = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)

    if file_path:
        file_path = _expand_path(file_path)
        _ensure_parent_dir(file_path)
        success = model.Extension.SaveAs(
            file_path, 0, 1, create_empty_dispatch_variant(), errors, warnings
        )
    else:
        success = model.Save3(1, errors, warnings)

    if success:
        print(f"保存成功: {file_path or get_com_member(model, 'GetPathName')}")
    else:
        print(f"保存失败, 错误码: {errors.value}, 警告码: {warnings.value}")
    return bool(success)


def mm(value):
    """毫米转米（SolidWorks API 单位）。"""
    return value / 1000.0


def deg(value):
    """角度转弧度。"""
    import math
    return value * math.pi / 180.0
