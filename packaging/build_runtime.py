#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""组装 GMT VectorLab 的内置运行时（仅用标准库）。

从官方发布包下载并解出：

    runtime/
      gmt/      <- GMT 6.7.0 win64 官方包（含 Ghostscript / GDAL / PROJ / FFmpeg）
      bash/     <- MinGit（提供 usr/bin/sh.exe，供 GMT 现代模式脚本执行）

再压成 packaging/runtime.zip（zip 内直接是 gmt/ 与 bash/，不含外层 runtime/），
供 packaging/GMT-VectorLab-Setup.spec 内嵌，或与 GMT-VectorLab.exe 同目录做便携版。

用法：
    python packaging/build_runtime.py                 # 下载 + 组装 + 打 zip
    python packaging/build_runtime.py --no-zip        # 只组装 runtime/
    python packaging/build_runtime.py --gmt-zip X.zip --mingit-zip Y.zip   # 用本地包
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import urllib.request
import zipfile

GMT_VERSION = "6.7.0"
GMT_URL = (
    "https://github.com/GenericMappingTools/gmt/releases/download/"
    f"{GMT_VERSION}/gmt-{GMT_VERSION}-win64.zip"
)
GMT_SIZE = 176530546  # 官方包字节数，仅用于下载完整性提示

MINGIT_VERSION = "2.56.0.4"
MINGIT_TAG = "v2.56.0.windows.4"  # 注意：tag 带 .windows，资产名不带
MINGIT_URL = (
    "https://github.com/git-for-windows/git/releases/download/"
    f"{MINGIT_TAG}/MinGit-{MINGIT_VERSION}-64-bit.zip"
)
MINGIT_SIZE = 39846926

AGPL_URL = "https://www.gnu.org/licenses/agpl-3.0.txt"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def log(msg):
    print(msg, flush=True)


def human(n):
    if n < 1048576:
        return "%.0f KB" % (n / 1024.0)
    return "%.1f MB" % (n / 1048576.0)


def download(url, dest, force=False):
    """下载到 dest；已存在则跳过，force=True 时重新下载。"""
    if force and os.path.isfile(dest):
        os.remove(dest)
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        log("  已存在，跳过下载：%s (%s)" % (dest, human(os.path.getsize(dest))))
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    log("  下载 %s" % url)
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            last = -1
            while True:
                buf = r.read(1 << 20)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if total:
                    pct = int(done * 100 / total)
                    if pct >= last + 5:
                        last = pct
                        log("    %3d%%  %s / %s" % (pct, human(done), human(total)))
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise SystemExit(
            "下载失败：%s\n  %s\n  可手动下载后通过 --gmt-zip / --mingit-zip 指定本地文件。" % (url, e)
        )
    os.replace(tmp, dest)
    log("  完成：%s (%s, %.0fs)" % (dest, human(os.path.getsize(dest)), time.time() - t0))
    return dest


def check_size(path, expected, what):
    got = os.path.getsize(path)
    if got != expected:
        log("  [提示] %s 大小与记录值不同（%d != %d），若来自官方 Release 可忽略。" % (what, got, expected))


def extract_zip(zip_path, target):
    """解压到 target（zip 根目录内容直接铺在 target 下）。"""
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.makedirs(target, exist_ok=True)
    log("  解压 %s -> %s" % (os.path.basename(zip_path), target))
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise SystemExit("压缩包损坏：%s 内条目 %s 校验失败" % (zip_path, bad))
        names = z.namelist()
        for i, name in enumerate(names, 1):
            z.extract(name, target)
            if i % 2000 == 0:
                log("    %d/%d ..." % (i, len(names)))


def prepare_bash(bash_dir):
    """MinGit 只有 sh.exe，GMT 的 gmt begin/end 会调用 bash。"""
    usr_bin = os.path.join(bash_dir, "usr", "bin")
    sh = os.path.join(usr_bin, "sh.exe")
    bash = os.path.join(usr_bin, "bash.exe")
    if not os.path.isfile(sh):
        raise SystemExit("MinGit 结构不符合预期，缺少 usr/bin/sh.exe")
    if not os.path.isfile(bash):
        shutil.copy2(sh, bash)
        log("  已由 sh.exe 生成 bash.exe")


def prepare_licenses(gmt_dir, force=False):
    agpl_src = os.path.join(gmt_dir, "share", "doc", "copying", "COPYING.AGPLv3")
    if os.path.isfile(agpl_src) and not force:
        log("  AGPLv3 已随 GMT 官方包提供：%s" % agpl_src)
        return
    dest_dir = os.path.join(gmt_dir, "share", "doc", "copying")
    os.makedirs(dest_dir, exist_ok=True)
    download(AGPL_URL, os.path.join(dest_dir, "COPYING.AGPLv3"), force=force)


def copy_notices(runtime_dir):
    src = os.path.join(ROOT, "THIRD_PARTY_NOTICES.md")
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(runtime_dir, "THIRD_PARTY_NOTICES.md"))
        log("  已复制 THIRD_PARTY_NOTICES.md")


def verify(runtime_dir):
    checks = [
        (os.path.join(runtime_dir, "gmt", "bin", "gmt.exe"), "GMT 主程序"),
        (os.path.join(runtime_dir, "gmt", "bin", "gswin64c.exe"), "Ghostscript"),
        (os.path.join(runtime_dir, "gmt", "share", "coast", "binned_border_i.nc"),
         "GSHHG 海岸线数据"),
        (os.path.join(runtime_dir, "bash", "usr", "bin", "bash.exe"), "bash"),
    ]
    missing = [name for path, name in checks if not os.path.isfile(path)]
    if missing:
        raise SystemExit("运行时组装不完整，缺少：" + "、".join(missing))
    total = 0
    for dp, _dns, fns in os.walk(runtime_dir):
        for fn in fns:
            total += os.path.getsize(os.path.join(dp, fn))
    log("  校验通过：GMT + Ghostscript + GSHHG + bash，共 %s" % human(total))


def make_zip(runtime_dir, zip_path):
    """zip 内条目为 gmt/... 与 bash/...（安装器直接解到 <安装目录>\\runtime）。"""
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    if os.path.isfile(zip_path):
        os.remove(zip_path)
    log("  压缩 -> %s" % zip_path)
    t0 = time.time()
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as z:
        for dp, dns, fns in os.walk(runtime_dir):
            dns.sort()
            for fn in sorted(fns):
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, runtime_dir).replace(os.sep, "/")
                z.write(p, rel)
                n += 1
                if n % 2000 == 0:
                    log("    %d 个文件 ..." % n)
    log("  完成：%d 个文件，%s（%.0fs）" % (n, human(os.path.getsize(zip_path)), time.time() - t0))


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装内置运行时并生成 packaging/runtime.zip")
    ap.add_argument("--runtime", default=os.path.join(ROOT, "runtime"),
                    help="运行时输出目录（默认：仓库根/runtime）")
    ap.add_argument("--cache", default=os.path.join(ROOT, "build", "_runtime_cache"),
                    help="官方包下载缓存目录（默认：仓库根/build/_runtime_cache）")
    ap.add_argument("--zip", dest="zip_path", default=os.path.join(HERE, "runtime.zip"),
                    help="生成的运行时压缩包（默认：packaging/runtime.zip）")
    ap.add_argument("--gmt-zip", help="本地 GMT 官方 win64 zip（跳过下载）")
    ap.add_argument("--mingit-zip", help="本地 MinGit zip（跳过下载）")
    ap.add_argument("--force", action="store_true", help="忽略缓存，重新下载/解压")
    ap.add_argument("--no-zip", action="store_true", help="只组装 runtime/，不生成 zip")
    args = ap.parse_args(argv)

    if os.name != "nt":
        log("[提示] 该脚本用于组装 Windows 运行时，当前系统不是 Windows，产物仅作查看。")

    runtime_dir = os.path.abspath(args.runtime)
    cache_dir = os.path.abspath(args.cache)

    log("== 1/4 准备官方包 ==")
    gmt_zip = os.path.abspath(args.gmt_zip) if args.gmt_zip else download(
        GMT_URL, os.path.join(cache_dir, "gmt-%s-win64.zip" % GMT_VERSION), force=args.force)
    mingit_zip = os.path.abspath(args.mingit_zip) if args.mingit_zip else download(
        MINGIT_URL, os.path.join(cache_dir, "MinGit-%s-64-bit.zip" % MINGIT_VERSION),
        force=args.force)
    for path, what in ((gmt_zip, "GMT 包"), (mingit_zip, "MinGit 包")):
        if not os.path.isfile(path):
            raise SystemExit("%s 不存在：%s" % (what, path))
    check_size(gmt_zip, GMT_SIZE, "GMT 包")
    check_size(mingit_zip, MINGIT_SIZE, "MinGit 包")

    log("== 2/4 解出 runtime ==")
    os.makedirs(runtime_dir, exist_ok=True)
    extract_zip(gmt_zip, os.path.join(runtime_dir, "gmt"))
    extract_zip(mingit_zip, os.path.join(runtime_dir, "bash"))

    log("== 3/4 收尾 ==")
    prepare_bash(os.path.join(runtime_dir, "bash"))
    prepare_licenses(os.path.join(runtime_dir, "gmt"), force=args.force)
    copy_notices(runtime_dir)
    verify(runtime_dir)

    log("== 4/4 打包 ==")
    if args.no_zip:
        log("  已指定 --no-zip，跳过。")
    else:
        make_zip(runtime_dir, os.path.abspath(args.zip_path))

    log("完成。运行时目录：%s" % runtime_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
