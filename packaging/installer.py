# -*- coding: utf-8 -*-
"""GMT VectorLab 轻量安装器 (单文件 exe, 内嵌应用本体 + 内置 GMT 运行时)。

行为:
  - 默认安装到 %LOCALAPPDATA%\\Programs\\GMT-VectorLab (无需管理员/UAC)
  - 解压内置 runtime/ (GMT + Ghostscript + bash), 安装后无需另外装 GMT
  - 在开始菜单与桌面创建快捷方式, 并在开始菜单创建"卸载"快捷方式
  - 安装目录下写入 uninstall.bat 用于卸载
  - 支持 --dir=<路径> 自定义安装位置(静默安装, 便于测试/便携部署)
"""
import os
import sys
import shutil
import subprocess
import tempfile
import traceback
import ctypes
import zipfile


def bundle_exe():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "GMT-VectorLab.exe")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "GMT-VectorLab.exe")


def bundle_runtime():
    """内嵌的 runtime.zip (GMT + Ghostscript + bash)。"""
    base = sys._MEIPASS if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS") \
        else os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, "runtime.zip")
    return p if os.path.isfile(p) else None


def mb(title, text, style=0):
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, style)
    except Exception:
        print(text)


def default_install_dir():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "Programs", "GMT-VectorLab")
    if not d.isascii():
        # GMT 的 Windows 版打不开含中文的路径; 用户名是中文时改到公共目录 (无需管理员)
        pub = os.environ.get("PUBLIC") or r"C:\Users\Public"
        d = os.path.join(pub, "GMT-VectorLab")
    return d


def create_shortcut(lnk_path, target, working_dir, description):
    ps = (
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$s = $ws.CreateShortcut('%s')\n"
        "$s.TargetPath = '%s'\n"
        "$s.WorkingDirectory = '%s'\n"
        "$s.Description = '%s'\n"
        "$s.Save()\n"
    ) % (lnk_path, target, working_dir, description)
    fd, psp = tempfile.mkstemp(suffix=".ps1")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(ps)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", psp],
            capture_output=True,
            check=True,
        )
    finally:
        try:
            os.remove(psp)
        except OSError:
            pass


def write_uninstaller(inst_dir):
    bat = os.path.join(inst_dir, "uninstall.bat")
    content = (
        "@echo off\n"
        "setlocal\n"
        'del /f /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\GMT VectorLab.lnk" 2>nul\n'
        'del /f /q "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Uninstall GMT VectorLab.lnk" 2>nul\n'
        'del /f /q "%USERPROFILE%\\Desktop\\GMT VectorLab.lnk" 2>nul\n'
        'set "INST=%~dp0"\n'
        'set "INST=%INST:~0,-1%"\n'
        'echo rmdir /s /q "%INST%" ^& del /f /q "%%~f0" > "%TEMP%\\gvl_rm.bat"\n'
        'start "" /min cmd /c "%TEMP%\\gvl_rm.bat"\n'
        "exit /b\n"
    )
    with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)
    return bat


def install(inst_dir, src_exe, silent=False):
    try:
        os.makedirs(inst_dir, exist_ok=True)
        dst = os.path.join(inst_dir, "GMT-VectorLab.exe")
        shutil.copy2(src_exe, dst)

        # 内置运行时: 解压到 <安装目录>\runtime, 应用启动时自动优先使用
        rz = bundle_runtime()
        if not rz:
            raise RuntimeError("安装包损坏: 缺少内嵌的 runtime.zip (内置 GMT 运行时)。")
        rt_dir = os.path.join(inst_dir, "runtime")
        if os.path.isdir(rt_dir):
            shutil.rmtree(rt_dir)
        os.makedirs(rt_dir, exist_ok=True)
        with zipfile.ZipFile(rz) as z:
            z.extractall(rt_dir)

        write_uninstaller(inst_dir)

        appdata = os.environ.get("APPDATA", "")
        sm = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")
        os.makedirs(sm, exist_ok=True)
        create_shortcut(os.path.join(sm, "GMT VectorLab.lnk"), dst, inst_dir, "GMT VectorLab")

        desk = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
        if os.path.isdir(desk):
            create_shortcut(os.path.join(desk, "GMT VectorLab.lnk"), dst, inst_dir, "GMT VectorLab")

        create_shortcut(
            os.path.join(sm, "Uninstall GMT VectorLab.lnk"),
            os.path.join(inst_dir, "uninstall.bat"),
            inst_dir,
            "Uninstall GMT VectorLab",
        )

        if not silent:
            mb("GMT VectorLab", "安装完成!\n\n安装位置: %s\n\n已在开始菜单与桌面创建快捷方式。" % inst_dir, 0)
        return True, inst_dir
    except Exception as e:  # noqa: BLE001
        if not silent:
            mb("GMT VectorLab - 安装失败", "错误信息:\n%s" % e, 0x10)
        traceback.print_exc()
        return False, None


def main():
    src_exe = bundle_exe()
    if not os.path.isfile(src_exe):
        mb("GMT VectorLab", "找不到 GMT-VectorLab.exe (内嵌资源缺失)。", 0x10)
        sys.exit(1)

    custom = None
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a.startswith("--dir="):
            custom = a.split("=", 1)[1]
        elif a == "--dir" and i + 1 < len(args):
            custom = args[i + 1]

    if custom:
        install(os.path.abspath(custom), src_exe, silent=True)
        print("Installed to", custom)
        return

    inst = default_install_dir()
    # MB_YESNOCANCEL = 3 ; IDYES = 6
    res = mb(
        "GMT VectorLab 安装",
        "GMT VectorLab 将安装到:\n%s\n\n"
        "安装包内含 GMT 运行时（约 400 MB），解压需要一点时间，请耐心等待。\n\n"
        "点击“是”开始安装，“否”取消。" % inst,
        3,
    )
    if res == 6:
        ok, _ = install(inst, src_exe, silent=False)
        sys.exit(0 if ok else 1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
