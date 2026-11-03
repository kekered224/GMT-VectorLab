# -*- mode: python ; coding: utf-8 -*-
# 安装器 spec —— 内嵌 GMT-VectorLab.exe(便携版), 运行时解压到
# %LOCALAPPDATA%\Programs\GMT-VectorLab, 并在开始菜单/桌面创建快捷方式 + 卸载脚本。
#
# 构建前: 先把便携版 GMT-VectorLab.exe (由根目录 GMT-VectorLab.spec 产出) 复制到本目录。
#   pyinstaller packaging/GMT-VectorLab-Setup.spec
import os

HERE = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(HERE)  # 仓库根目录 (含 icon.ico / version_info.txt)

a = Analysis(
    [os.path.join(HERE, 'installer.py')],
    pathex=[HERE],
    binaries=[],
    datas=[
        (os.path.join(HERE, 'GMT-VectorLab.exe'), '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'PyQt5', 'PySide6', 'scipy', 'pandas',
        'sqlalchemy', 'botocore', 'boto3', 'openpyxl', 'pytest', 'IPython',
        'notebook', 'jinja2', 'webview', 'fitz',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='GMT-VectorLab-Setup',
    debug=False, console=False,
    icon=os.path.join(ROOT, 'icon.ico'),
    version=os.path.join(ROOT, 'version_info.txt'),
)
