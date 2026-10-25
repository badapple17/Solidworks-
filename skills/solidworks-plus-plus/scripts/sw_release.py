"""
释放 SolidWorks：关闭残留文档，必要时退出实例。

为什么需要它：脚本只 `CloseDoc(装配体)` 时，被引用的零件文档仍留在内存里，
继续占着磁盘文件锁。用户双击交付的 .SLDPRT/.SLDASM 会打不开或只能只读，
往往要重启电脑。正常的脚本收尾应该调用 `SolidWorksSession.finish()`；
本脚本是异常中断后的**手工恢复**手段。

本脚本**不会启动** SolidWorks；没有运行中的实例时只报告。

用法（在 <skill>/scripts 目录下）::

    py -3.12 sw_release.py                 # 只报告：进程、文档清单
    py -3.12 sw_release.py --close-docs    # 关闭所有文档（不保存）
    py -3.12 sw_release.py --quit          # 关闭所有文档并退出 SolidWorks

`--quit` 会丢弃未保存的修改，只在确认实例里没有用户手工工作时使用。
"""
import argparse
import subprocess
import sys
import time

try:
    from .sw_connect import close_all_documents, get_com_member, import_com_dependencies
except ImportError:
    from sw_connect import close_all_documents, get_com_member, import_com_dependencies

pythoncom, win32com_client, VARIANT = import_com_dependencies()

PROG_ID = "SldWorks.Application"


def running_processes():
    """返回当前 SLDWORKS.exe 进程列表 [(pid, mem), ...]。"""
    try:
        output = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except Exception:
        return []
    processes = []
    for line in output.splitlines():
        fields = [field.strip('"') for field in line.strip().split('","')]
        if len(fields) >= 2 and fields[0].lower() == "sldworks.exe":
            try:
                processes.append((int(fields[1]), fields[4] if len(fields) > 4 else ""))
            except ValueError:
                continue
    return processes


def connect_running():
    """
    附着到已运行的实例；不启动新实例。

    先走 ROT（用户正常启动的实例会在 3 秒内注册）。自动化启动的实例常常
    **不在 ROT 里**（`GetActiveObject` 报 MK_E_UNAVAILABLE），但进程还在——
    这时用 `Dispatch`，它会复用已有进程而不是再开一个。只有进程列表为空时
    才不尝试，避免凭空拉起一个 SolidWorks。
    """
    try:
        return win32com_client.GetActiveObject(PROG_ID)
    except Exception:
        pass
    if not running_processes():
        return None
    try:
        return win32com_client.Dispatch(PROG_ID)
    except Exception:
        return None


def open_documents(sw):
    """返回 [(title, path), ...]。"""
    documents = []
    try:
        items = sw.GetDocuments() or []
    except Exception:
        items = []
    for document in items:
        try:
            documents.append((
                str(get_com_member(document, "GetTitle") or "?"),
                str(get_com_member(document, "GetPathName") or ""),
            ))
        except Exception:
            documents.append(("<无法读取>", ""))
    return documents


def main(argv=None):
    parser = argparse.ArgumentParser(description="关闭残留文档/退出 SolidWorks，释放交付文件锁")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--close-docs", action="store_true", help="关闭所有文档（不保存），保留应用")
    group.add_argument("--quit", action="store_true", help="关闭所有文档并退出 SolidWorks")
    args = parser.parse_args(argv)

    processes = running_processes()
    print(f"SLDWORKS.exe 进程数: {len(processes)}")
    for pid, mem in processes:
        print(f"  PID {pid}  内存 {mem}")

    sw = connect_running()
    if sw is None:
        print("没有可附着的 SolidWorks 实例（COM 未注册或进程已退出）。")
        return 0

    documents = open_documents(sw)
    print(f"已打开文档数: {len(documents)}")
    for title, path in documents:
        print(f"  {title}  {path}")

    if not (args.close_docs or args.quit):
        print("未做改动。加 --close-docs 或 --quit 执行清理。")
        return 0

    if args.quit:
        print("警告: --quit 会丢弃未保存修改。")
    close_all_documents(sw, save=False)
    print("文档已全部关闭（未保存修改已丢弃）。")

    if args.quit:
        quit_ok = False
        for member_name in ("ExitApp", "Quit"):
            try:
                member = getattr(sw, member_name)
                member() if callable(member) else None
                quit_ok = True
                break
            except Exception:
                continue
        deadline = time.time() + 20
        while time.time() < deadline and running_processes():
            time.sleep(1)
        remaining = running_processes()
        print(f"退出请求: {'已发出' if quit_ok else '失败'}")
        print(f"剩余 SLDWORKS.exe: {len(remaining)}")
        if remaining:
            print("实例仍在退出中或拒绝退出；稍后重跑本脚本确认。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
