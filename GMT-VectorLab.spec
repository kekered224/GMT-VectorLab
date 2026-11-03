# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec —— GMT VectorLab 桌面程序 (单文件 exe, 精简版)
import os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files, collect_submodules

HERE = os.path.abspath(SPECPATH)

# 只收集 webview 需要的原生 DLL(WebView2 等)与子模块, 不做 collect_all 以免拖入无关重包
wv_bins = collect_dynamic_libs('webview')
wv_data = collect_data_files('webview')
wv_hidden = collect_submodules('webview')

a = Analysis(
    [os.path.join(HERE, 'app.py')],
    pathex=[HERE],
    binaries=wv_bins,
    datas=[
        (os.path.join(HERE, 'ui.html'), '.'),
        (os.path.join(HERE, 'fieldkit.js'), '.'),
        (os.path.join(HERE, 'canvaskit.js'), '.'),
    ] + wv_data,
    hiddenimports=[
        'core', 'gmt_editor', 'svgify', 'reapply',
        'webview.platforms.winforms', 'webview.platforms.edgechromium',
        'clr', 'pythonnet',
    ] + wv_hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'PyQt5', 'PySide6', 'scipy',
        'pandas', 'sqlalchemy', 'botocore', 'boto3', 'openpyxl',
        'pytest', 'py', 'IPython', 'notebook', 's3transfer', 'jinja2',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='GMT-VectorLab',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, upx_exclude=[],
    runtime_tmpdir=None, console=False,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
    icon=os.path.join(HERE, 'icon.ico'),
    version=os.path.join(HERE, 'version_info.txt'),
)
