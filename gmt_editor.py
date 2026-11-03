#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gmt_editor.py —— GMT VectorLab 命令行工具与渲染引擎

架构理念 (对应上一轮的结论):
  GMT 没有 matplotlib 那种"活的、可点选的对象场景图"。
  所以本原型不假装能"点中某根轴改属性"，而是把 GMT 脚本解析成
  结构化的中间表示 (IR = 命令/图层列表)，让用户在 *命令级* 编辑,
  所有改动写进独立的 overlay.json —— **源脚本 plot.sh 一字节都不改**，
  数据更新后重跑，overlay 自动套用。

子命令:
  parse   源脚本 -> IR, 打印图层树 + 导出 spec.json
  report  源脚本 + overlay -> 改动 diff (人可读)
  render  源脚本 + overlay -> 生成 rendered.sh (可选 --run 真渲染出图)
  verify  打印源脚本 sha256, 供"脚本未被改动"验证

设计约束: 只用标准库; GMT 选项按"值粘连在 flag 后"的 shell 惯例解析
         (如 -W0.5p,black / -JM12c / -BWSen+t"...")。
"""
import sys, os, re, json, shutil, hashlib, subprocess, argparse, tempfile

# ---------------------------------------------------------------------------
# 分词: 类 shell 切分, 尊重成对引号 (双/单), 并把引号原样保留在 token 里,
#       这样 re-emit 时能忠实还原。
# ---------------------------------------------------------------------------
def tokenize(line: str):
    toks, buf, quote, i = [], "", None, 0
    while i < len(line):
        c = line[i]
        if quote:
            buf += c
            if c == quote:
                quote = None
        elif c in ('"', "'"):
            quote = c
            buf += c
        elif c.isspace():
            if buf:
                toks.append(buf); buf = ""
        else:
            buf += c
        i += 1
    if buf:
        toks.append(buf)
    return toks

# 把一个 option token 拆成 (flag, value)。
#   -W0.5p,black      -> ("-W", "0.5p,black")
#   -BWSen+t"标题"     -> ("-B", 'WSen+t"标题"')
#   -N                -> ("-N", "")
#   stations.dat      -> (None, "stations.dat")   (positional / 数据)
def split_flag(tok: str):
    if len(tok) >= 2 and tok[0] == "-" and tok[1].isalpha():
        return ("-" + tok[1], tok[2:])
    return (None, tok)

# ---------------------------------------------------------------------------
# 解析器: GMT 现代模式脚本 -> IR
# ---------------------------------------------------------------------------
class DrawOp:
    def __init__(self, index, module, tokens, lineno, heredoc=None):
        self.index = index        # 全局序号 (overlay 用 index 定位)
        self.module = module      # coast / plot / text ...
        self.tokens = tokens      # 原始 token 列表 (含 gmt 与 module)
        self.lineno = lineno
        self.heredoc = heredoc or []   # << EOF 内联数据块 (原样行, 含结束行)
    def to_dict(self):
        opts = {}
        order = []
        for t in self.tokens[2:]:              # 跳过 'gmt' 和 module
            flag, val = split_flag(t)
            if flag is None:
                order.append(("@", t))          # 数据/位置参数
            else:
                k = flag
                # 同一 flag 多次出现 -> -B#0 -B#1
                if k in opts:
                    n = sum(1 for kk in order if kk[0].startswith(flag))
                    k = f"{flag}#{n}"
                opts[k] = val
                order.append((k, val))
        d = {"index": self.index, "module": self.module,
             "line": self.lineno, "options": opts,
             "raw": " ".join(self.tokens)}
        if self.heredoc:
            d["heredoc_lines"] = len(self.heredoc) - 1   # 不含 EOF 行
        return d

def _heredoc_delimiter(line):
    """从一行里认出 `<< EOF` / `<<EOF` / `<<'EOF'` 的定界符。"""
    m = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
    return m.group(2) if m else None

# 脚本里允许原样保留的 shell 行 (生成/清理中间数据文件, 如 echo ... > box.txt)。
# 只放数据准备与清理类命令, 不把任意 shell 塞进渲染流程。
_SHELL_KEEP = {"echo", "printf", "cat", "cp", "mv", "rm", "mkdir", "rmdir",
               "ln", "sed", "awk", "gawk", "head", "tail", "sort", "uniq",
               "cut", "tr", "grep", "touch", "test", "sleep", "export", "unset"}

def parse_script(path):
    src = open(path, "r", encoding="utf-8-sig").read()
    lines = src.splitlines()
    begin, end, ops, raw, idx = None, None, [], [], 0
    i = 0
    while i < len(lines):
        line = lines[i]
        lineno = i + 1
        toks = tokenize(line.strip())
        i += 1
        if not toks:
            continue
        if toks[0] == "gmt" and len(toks) > 1 and toks[1] == "begin":
            begin = {"tokens": toks, "line": lineno}; continue
        if toks[0] == "gmt" and len(toks) > 1 and toks[1] == "end":
            end = {"tokens": toks, "line": lineno}; continue
        if toks[0] == "gmt" and len(toks) > 1:
            # here-document: 数据行既不是 gmt 命令也不是注释, 逐行收进来,
            # 否则重渲染时整块数据丢失 -> bash 报 "here-document delimited by EOF"
            hd = []
            delim = _heredoc_delimiter(line)
            if delim:
                while i < len(lines):
                    hd.append(lines[i])
                    done = lines[i].strip() == delim
                    i += 1
                    if done:
                        break
            ops.append(DrawOp(idx, toks[1], toks, lineno, hd)); idx += 1
            continue
        # 非 gmt 行: 数据准备/清理命令要保留, 否则中间文件 (box.txt 等) 缺失
        if toks[0] in _SHELL_KEEP:
            raw.append({"line": lineno, "text": line.rstrip()})
    if begin is None or end is None:
        raise ValueError("未找到 gmt begin / gmt end (需现代模式脚本)")
    return {"path": path, "begin": begin, "end": end, "ops": ops,
            "raw": raw, "lines": lines}



# ---------------------------------------------------------------------------
# 覆盖引擎: 把 overlay.json 里的改动作用到某个 op 的 tokens 上
# overlay schema:
#   {"note": "...",
#    "ops":[
#      {"index":0, "set":{"-R":"...","-W":"1.25p,red","-B#1":'+WSen+t"新标题"'},
#                "unset":["-Na+d"] 或 ["-N"], "append":["-A100/100"]}
#    ]}
# ---------------------------------------------------------------------------
def apply_overlay(ir, overlay):
    changed = []
    rules = {r["index"]: r for r in overlay.get("ops", [])}
    new_ops = []
    for op in ir["ops"]:
        r = rules.get(op.index)
        if not r:
            new_ops.append(DrawOp(op.index, op.module, list(op.tokens), op.lineno, list(op.heredoc)))
            continue
        setd   = r.get("set", {})
        unset  = r.get("unset", [])
        append = r.get("append", [])
        unset_flags = {u.split("#")[0] for u in unset}
        out, seen = [], {}
        for pos, tok in enumerate(op.tokens):
            flag, val = split_flag(tok)
            if flag is None:
                out.append(tok); continue
            occ = seen.get(flag, 0); seen[flag] = occ + 1
            key_occ = f"{flag}#{occ}"
            # 命中 unset (按 flag 或按 occ key)
            if flag in unset_flags or key_occ in unset:
                changed.append((op.index, op.module, flag, val, "(removed)"))
                continue
            new_val = None
            if key_occ in setd:                 # 指定第几次出现, 如 -B#1
                new_val = setd[key_occ]
            elif flag in setd:                  # 裸 flag 键 -> 该 flag 每次出现都替换
                new_val = setd[flag]
            if new_val is not None:
                out.append(flag + new_val)
                changed.append((op.index, op.module, flag, val, new_val))
            else:
                out.append(tok)
        for a in append:
            out.append(a)
            changed.append((op.index, op.module, "(append)", None, a))
        new_ops.append(DrawOp(op.index, op.module, out, op.lineno, list(op.heredoc)))
    return {"begin": ir["begin"], "end": ir["end"], "ops": new_ops,
            "raw": ir.get("raw", []), "lines": ir["lines"], "path": ir["path"]}, changed

# ---------------------------------------------------------------------------
# 渲染器: IR -> 现代模式 bash 脚本 (忠实 re-emit, 引号原样保留)
# ---------------------------------------------------------------------------
_FMT_KNOWN = {"png", "pdf", "ps", "eps", "jpg", "jpeg", "tif", "tiff",
              "bmp", "gif", "ppm", "svg", "grd"}

def _ensure_pdf(begin_tokens):
    """画布编辑靠 PDF 反推 SVG, 所以渲染脚本必须带 pdf 输出。
    源脚本只写 png 时, 在生成物里补一个 pdf —— 源脚本本身不动。"""
    toks = list(begin_tokens)

    def _is_fmt(t):
        parts = [p for p in t.split(",") if p]
        return bool(parts) and all(p.lower() in _FMT_KNOWN for p in parts)

    fmt_pos = [j for j in range(2, len(toks))
               if not toks[j].startswith("-") and _is_fmt(toks[j])]
    if not fmt_pos:                       # 没写格式 -> 补全
        toks.append("png,pdf")
        return toks
    j = fmt_pos[0]
    fmts = [p for p in toks[j].split(",") if p]
    if "pdf" not in [f.lower() for f in fmts]:
        fmts.append("pdf")
    toks[j] = ",".join(fmts)
    for k in reversed(fmt_pos[1:]):       # 多处分开写的格式合一
        del toks[k]
    return toks

def emit_script(ir):
    # 按源文件行号把 begin / 各图层 / 保留的 shell 行 / end 依次还原
    entries = [(ir["begin"]["line"], "begin", None), (ir["end"]["line"], "end", None)]
    for op in ir["ops"]:
        entries.append((op.lineno, "op", op))
    for r in ir.get("raw", []):
        entries.append((r["line"], "raw", r["text"]))
    entries.sort(key=lambda e: e[0])

    parts = ["#!/usr/bin/env bash",
             "# 由 gmt_editor.py 自动生成 —— 请勿手改。改动来自 overlay.json。"]
    for _ln, kind, obj in entries:
        if kind == "begin":
            parts.append(" ".join(_ensure_pdf(ir["begin"]["tokens"])))
        elif kind == "end":
            parts.append(" ".join(ir["end"]["tokens"]))
        elif kind == "raw":
            parts.append(obj)
        else:
            parts.append("    " + " ".join(obj.tokens))
            for hl in (getattr(obj, "heredoc", None) or []):
                parts.append(hl)          # << EOF 数据块原样输出, 不能缩进
    return "\n".join(parts) + "\n"

def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

_DATA_EXT = (".nc", ".grd", ".txt", ".dat", ".csv", ".xy", ".xyz", ".cpt",
             ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".shp", ".gmt")

_JUNCTION_CACHE = {}

def _ancestors(wd, depth=4):
    """wd 的祖先目录 (父/祖父/...), 到盘根为止。"""
    out, p = [], wd
    for _ in range(depth):
        p = os.path.dirname(p)
        if not p or p == os.path.dirname(p) or p in out:
            break
        out.append(p)
    return out

_SUBDIR_CACHE = {}

def _subdirs(base, depth=2):
    """base 及其 depth 层内的子目录。盘根目录不做递归, 否则会扫全盘。
    结果缓存: 一个脚本里常有多个数据文件名, 不必每个都 walk 一遍。"""
    key = (os.path.normcase(base), depth)
    if key in _SUBDIR_CACHE:
        return _SUBDIR_CACHE[key]
    if os.path.dirname(base) == base:
        _SUBDIR_CACHE[key] = [base]
        return _SUBDIR_CACHE[key]
    out, base_n = [], base.rstrip("\\/").count(os.sep)
    for dp, dns, _ in os.walk(base):
        if dp.rstrip("\\/").count(os.sep) - base_n >= depth:
            dns[:] = []
        out.append(dp)
    _SUBDIR_CACHE[key] = out
    return out

def _find_data_dir(name, wd):
    """找数据文件所在目录。顺序: 本目录 -> 各级祖先 -> 本目录/父目录之下 2 层
    (后者覆盖"数据在同一级的另一个文件夹里"这种放法)。找不到返回 None。"""
    layers = [wd] + _ancestors(wd)
    for d in layers:
        if os.path.isfile(os.path.join(d, name)):
            return d
    for base in layers[:2]:
        for d in _subdirs(base, 2):
            if os.path.isfile(os.path.join(d, name)):
                return d
    return None

def _make_junction(wd, target):
    """在 wd 下建一个 ASCII 名目录联接指向 target, 返回该 ASCII 名; 失败返回 None。
    必须这么做: GMT 的 Windows 版用窄字符 API 打开文件, 路径里只要有中文
    (哪怕是相对路径 ../中文目录/x.nc) 就 Cannot find file —— 实测如此。"""
    key = (os.path.normcase(wd), os.path.normcase(target))
    if key in _JUNCTION_CACHE:
        nm = _JUNCTION_CACHE[key]
        return nm if nm and os.path.isdir(os.path.join(wd, nm)) else None
    if os.name != "nt":
        return None
    for nm in sorted(os.listdir(wd)):
        p = os.path.join(wd, nm)
        if nm.startswith("_gmtdata") and os.path.isdir(p):
            try:
                if os.path.samefile(p, target):
                    _JUNCTION_CACHE[key] = nm
                    return nm
            except OSError:
                pass
    nm = None
    for i in range(1, 20):
        cand = "_gmtdata%d" % i
        p = os.path.join(wd, cand)
        if os.path.exists(p):
            continue
        try:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", p, target],
                               capture_output=True, **_hidden_console_kwargs())
        except Exception:
            break
        if r.returncode == 0 and os.path.isdir(p):
            nm = cand
        break
    _JUNCTION_CACHE[key] = nm
    return nm

def _resolve_data_paths(text, workdir):
    """脚本引用的数据不在本目录时, 在上级/同级目录里找, 并把生成物改写成相对路径。
    只改写生成物 (rendered.sh), 源脚本不动。

    注意两个坑:
    1) 找不到时 GMT 只让那一条模块失败, 脚本照跑到底 -> rc=0、图照出, 但那一层
       (常见就是 grdimage 的地形底图) 静默消失。所以找不到要显式报告, 见 missing。
    2) 中文路径一律打不开, 含中文的相对路径也不行。数据在中文目录里时, 在 workdir
       下建 ASCII 名的目录联接再引用。
    返回 (新脚本, 未找到的文件名列表)。"""
    wd = os.path.abspath(workdir)
    fixed, missing = text, []
    for ln in text.split("\n"):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if ">" in s or "<" in s:      # echo ... > box.txt 这类生成/读取行不动
            continue
        for tok in tokenize(s):
            if tok.startswith("-") or tok.startswith("<") or "/" in tok or "\\" in tok:
                continue
            if not tok.lower().endswith(_DATA_EXT):
                continue
            if os.path.exists(os.path.join(wd, tok)):
                continue
            d = _find_data_dir(tok, wd)
            if not d:
                missing.append(tok)
                continue
            rel = os.path.relpath(d, wd).replace("\\", "/")
            prefix = "" if rel == "." else rel + "/"
            if not prefix.isascii():
                nm = _make_junction(wd, d)
                if not nm:
                    missing.append(tok)
                    continue
                prefix = nm + "/"
            fixed = fixed.replace(tok, prefix + tok)
    return fixed, missing

# ---------------------------------------------------------------------------
# 可移植的 shell / GMT 定位 (打包成 exe 双击运行时, 系统 PATH 里常常只有
# Git 的 cmd 目录 (git.exe) 而没有 bash.exe, 直接 subprocess(["bash",...])
# 会 FileNotFoundError。这里稳健地找出一个可用的 POSIX shell。)
# ---------------------------------------------------------------------------
def _is_bad_shell(p):
    """拒绝 WSL 的 '应用执行别名' bash (WindowsApps\\bash.exe) —— 它启动的是 WSL Linux 环境,
    里面没有 Windows 的 gmt.exe, 跑 GMT 脚本会 rc=127 command not found。"""
    return "windowsapps" in (p or "").lower()

def _app_base_dir():
    """程序所在目录: 打包后为 exe 同级, 开发运行时为源码目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

_RT_ASCII_CACHE = {"src": None, "view": None}

def _ascii_runtime_view(rt):
    """运行时目录若含中文/非 ASCII, 建一个 ASCII 名的目录联接再交给 GMT:
    GMT 的 Windows 版用窄字符 API, 路径里有中文就打不开 shorelines 等共享数据。
    联接不占空间、不需要管理员; 建不成时退回原路径。"""
    if rt.isascii() or os.name != "nt":
        return rt
    if _RT_ASCII_CACHE["src"] == rt:
        return _RT_ASCII_CACHE["view"]
    pub = os.environ.get("PUBLIC") or r"C:\Users\Public"
    base = os.path.join(pub, "GMT-VectorLab")
    link = os.path.join(base, "runtime-" + hashlib.sha256(rt.encode("utf-8")).hexdigest()[:10])
    view = rt
    try:
        os.makedirs(base, exist_ok=True)
        if os.path.isfile(os.path.join(link, "gmt", "bin", "gmt.exe")):
            view = link
        else:
            if os.path.lexists(link):
                try:
                    os.rmdir(link)          # 目录联接: 只删链接, 不动目标
                except OSError:
                    pass
            r = subprocess.run(["cmd", "/c", "mklink", "/J", link, rt],
                               capture_output=True, **_hidden_console_kwargs())
            if r.returncode == 0 and os.path.isfile(os.path.join(link, "gmt", "bin", "gmt.exe")):
                view = link
    except Exception:
        view = rt
    _RT_ASCII_CACHE["src"] = rt
    _RT_ASCII_CACHE["view"] = view
    return view

def _bundled_runtime():
    """内置运行时根目录 (含 gmt/bin/gmt.exe), 没有则返回 None。

    查找顺序: GVL_RUNTIME 环境变量 -> 程序目录/runtime -> 上一级/runtime。
    安装版与全量便携版都带 runtime/, 因此优先于系统 GMT。
    路径含非 ASCII 字符时, 返回等价的 ASCII 目录联接 (GMT 窄字符 API 打不开中文路径)。"""
    env = os.environ.get("GVL_RUNTIME", "")
    if env and os.path.isfile(os.path.join(env, "gmt", "bin", "gmt.exe")):
        return _ascii_runtime_view(os.path.abspath(env))
    base = _app_base_dir()
    for b in (base, os.path.dirname(base)):
        d = os.path.join(b, "runtime")
        if os.path.isfile(os.path.join(d, "gmt", "bin", "gmt.exe")):
            return _ascii_runtime_view(d)
    return None

def _ascii_user_dir():
    """GMT 在 Windows 上无法处理含中文/空格的主目录, 内置运行时改用纯 ASCII 缓存目录。"""
    cands = []
    la = os.environ.get("LOCALAPPDATA")
    pub = os.environ.get("PUBLIC") or (r"C:\Users\Public" if os.name == "nt" else None)
    pd = os.environ.get("ProgramData")
    if la:
        cands.append(os.path.join(la, "GMT-VectorLab", ".gmt"))
    if pub:
        cands.append(os.path.join(pub, "GMT-VectorLab", ".gmt"))
    if pd:
        cands.append(os.path.join(pd, "GMT-VectorLab", ".gmt"))
    cands.append(os.path.join(tempfile.gettempdir(), "GMT-VectorLab", ".gmt"))
    for c in cands:
        if not all(ord(ch) < 128 for ch in c):
            continue
        try:
            os.makedirs(os.path.join(c, "tmp"), exist_ok=True)
            return c
        except OSError:
            continue
    for c in cands:
        try:
            os.makedirs(os.path.join(c, "tmp"), exist_ok=True)
            return c
        except OSError:
            continue
    return None

def _find_shell():
    if os.name != "nt":
        for name in ("bash", "sh"):
            p = shutil.which(name)
            if p:
                return p
        return None
    # 0) 内置 runtime 的 bash/sh 最优先 (MinGit 只带 sh.exe, 实为 bash 5)
    rt = _bundled_runtime()
    if rt:
        for sub in (("bash", "bin", "bash.exe"),
                    ("bash", "usr", "bin", "bash.exe"),
                    ("bash", "usr", "bin", "sh.exe")):
            c = os.path.join(rt, *sub)
            if os.path.exists(c) and not _is_bad_shell(c):
                return c
    # 1) 优先 Git for Windows 的 bash (能可靠跑 GMT 现代模式脚本)
    git = shutil.which("git.exe") or shutil.which("git")
    roots = []
    if git and not _is_bad_shell(git):
        g = os.path.dirname(os.path.abspath(git))          # ...\Git\cmd 或 ...\Git\bin
        roots.append(os.path.dirname(g))                    # ...\Git
    for drv in ("C:", os.environ.get("SystemDrive", "C:")):
        roots += [drv + "\\Program Files\\Git", drv + "\\Program Files (x86)\\Git"]
    for extra in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if extra:
            roots.append(os.path.join(extra, "Git"))
    seen, cand = set(), []
    for r in roots:
        if not r or r.lower() in seen:
            continue
        seen.add(r.lower())
        for sub in (os.path.join("bin", "bash.exe"),
                    os.path.join("usr", "bin", "bash.exe"),
                    os.path.join("bin", "sh.exe")):
            cand.append(os.path.join(r, sub))
    for c in cand:
        if os.path.exists(c) and not _is_bad_shell(c):
            return c
    # 2) 再扫 PATH (含注册表 PATH), 但跳过 WSL 别名
    dirs = [p for p in (os.environ.get("PATH", "").split(os.pathsep) + _registry_path()) if p]
    dseen, ordered = set(), []
    for d in dirs:
        dl = d.lower()
        if dl not in dseen:
            dseen.add(dl); ordered.append(d)
    for d in ordered:
        for exe in ("bash.exe", "sh.exe"):
            c = os.path.join(d, exe)
            if os.path.exists(c) and not _is_bad_shell(c):
                return c
    # 3) 最后用 which (仍排除 WSL 别名)
    for name in ("bash.exe", "bash", "sh.exe", "sh"):
        p = shutil.which(name)
        if p and not _is_bad_shell(p):
            return p
    return None

_GMT_DIR_CACHE = {"done": False, "dir": None}

def _registry_path():
    """读 Windows 机器级 + 用户级 PATH (注册表), 用于补齐双击启动时可能不完整的 os.environ['PATH']。"""
    parts = []
    if os.name != "nt":
        return parts
    try:
        import winreg
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]
        for hive, sub in keys:
            try:
                with winreg.OpenKey(hive, sub) as k:
                    val, _ = winreg.QueryValueEx(k, "Path")
                    if val:
                        parts.extend([p for p in val.split(os.pathsep) if p])
            except OSError:
                pass
    except Exception:
        pass
    return parts

def _find_gmt_dir():
    """稳健定位 gmt.exe 所在目录: PATH(which) -> 合并注册表 PATH -> 常见安装根。"""
    if _GMT_DIR_CACHE["done"]:
        return _GMT_DIR_CACHE["dir"]
    found = None
    rt = _bundled_runtime()
    if rt:
        gd = os.path.join(rt, "gmt", "bin")
        if os.path.isfile(os.path.join(gd, "gmt.exe")):
            found = gd
    if not found:
        g = shutil.which("gmt.exe") or shutil.which("gmt")
        if g:
            found = os.path.dirname(os.path.abspath(g))
    if not found:
        # 合并当前 PATH + 注册表 PATH, 逐目录找 gmt.exe
        seen = set()
        cand_dirs = [p for p in (os.environ.get("PATH", "").split(os.pathsep) + _registry_path()) if p]
        for d in cand_dirs:
            dl = d.lower()
            if dl in seen:
                continue
            seen.add(dl)
            for exe in ("gmt.exe", "gmt"):
                if os.path.exists(os.path.join(d, exe)):
                    found = d
                    break
            if found:
                break
    if not found:
        # 常见安装根兜底
        roots = []
        for drv in ("C:", os.environ.get("SystemDrive", "C:")):
            roots += [drv + "\\programs", drv + "\\", drv + "\\Program Files", drv + "\\Program Files (x86)"]
        for extra in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if extra:
                roots.append(extra)
        import glob
        pats = []
        for r in roots:
            pats += [os.path.join(r, "gmt*", "bin"), os.path.join(r, "GMT*", "bin"),
                     os.path.join(r, "Programs", "GMT*", "bin"), os.path.join(r, "GMT", "*", "bin")]
        for pat in pats:
            try:
                for d in glob.glob(pat):
                    if os.path.exists(os.path.join(d, "gmt.exe")):
                        found = d
                        break
            except Exception:
                pass
            if found:
                break
    _GMT_DIR_CACHE["done"] = True
    _GMT_DIR_CACHE["dir"] = found
    return found

def _gmt_env():
    """确保子进程 PATH 既包含系统(注册表)PATH, 又显式含 GMT 目录 —— 避免双击启动时
    gmt.exe 不在 PATH 上导致 bash 返回 rc=127 (command not found)。

    有内置 runtime 时: 只在本进程环境里把内置目录排到最前, 并覆盖 GMT6_* 与
    GMT_USERDIR/GMT_TMPDIR, 不写注册表/不改系统 PATH —— 系统里已装的 GMT 不受影响,
    也不会被误用。"""
    env = dict(os.environ)
    rt = _bundled_runtime()
    if rt:
        gmt_bin = os.path.join(rt, "gmt", "bin")
        bash_bin = os.path.join(rt, "bash", "usr", "bin")
        cur = [p for p in env.get("PATH", "").split(os.pathsep) if p]
        merged, seen = [], set()
        for p in [gmt_bin] + ([bash_bin] if os.path.isdir(bash_bin) else []) + cur + _registry_path():
            pl = p.lower()
            if p and pl not in seen:
                seen.add(pl)
                merged.append(p)
        env["PATH"] = os.pathsep.join(merged)
        share = os.path.join(rt, "gmt", "share")
        env["GMT6_SHAREDIR"] = share
        env["GMT6_DATADIR"] = share
        env["GMT6_PLUGINDIR"] = os.path.join(gmt_bin, "gmt_plugins")
        # GDAL/PROJ 数据也跟着内置运行时走, 否则可能被系统里别的安装指到不匹配的版本
        gdal_data = os.path.join(share, "GDAL_DATA")
        proj_data = os.path.join(share, "proj")
        if os.path.isdir(gdal_data):
            env["GDAL_DATA"] = gdal_data
        if os.path.isdir(proj_data):
            env["PROJ_DATA"] = proj_data
            env["PROJ_LIB"] = proj_data
        # 系统里可能残留的旧变量会把内置 GMT 指到外部安装, 必须清掉
        for k in ("GMT_SHAREDIR", "GMT_DATADIR", "GMT_PLUGINDIR",
                  "GMT_LIBRARY_PATH", "GMT_CUSTOM_LIBS"):
            env.pop(k, None)
        ud = _ascii_user_dir()
        if ud:
            env["GMT_USERDIR"] = ud
            env["GMT_TMPDIR"] = os.path.join(ud, "tmp")
        return env
    cur = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    merged, seen = [], set()
    for p in cur + _registry_path():
        pl = p.lower()
        if p and pl not in seen:
            seen.add(pl)
            merged.append(p)
    gdir = _find_gmt_dir()
    if gdir and gdir.lower() not in seen:
        merged.insert(0, gdir)
    env["PATH"] = os.pathsep.join(merged)
    return env

def _hidden_console_kwargs():
    """打包成 windowed exe 后, 从 GUI 进程启动 bash.exe 这类控制台程序时,
    Windows 会给它分配一个可见控制台 -> 屏幕上蹦出一堆命令行框。这里让子进程
    不分配/隐藏控制台 (STARTUPINFO.SW_HIDE + CREATE_NO_WINDOW)。非 Windows 返回空。"""
    if os.name != "nt":
        return {}
    kw = {}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kw["startupinfo"] = si
    except Exception:
        pass
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if flag:
        kw["creationflags"] = flag
    return kw


def _to_msys_path(p):
    """c:\\programs\\gmt6\\bin -> /c/programs/gmt6/bin (Git Bash/MSYS 形式)。"""
    if not p:
        return p
    p = p.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    if m:
        return "/" + m.group(1).lower() + "/" + m.group(2)
    return p

def _with_gmt_path_first(text):
    """在生成的脚本里, 于 shebang 之后插入环境准备行:
      export PATH="<gmt bin>:$PATH"        —— 防 DLL 串味
      export GMT_SESSION_NAME="...$$"     —— 防现代模式会话 ID 抖动

    (1) Git Bash 启动时会把它的 /usr/bin 顶到 PATH 最前, 导致 gmt.exe 误加载 Git 的
        同名依赖 DLL (gdal/zlib/...), supplements 模块加载失败 -> rc=30。
    (2) GMT 6 现代模式不靠环境变量传会话, 而是按父进程 PID 找
        ~/.gmt/sessions/gmt_session.<ppid>。在 Git Bash(MSYS2) 下同一脚本内连续多次
        gmt.exe 拿到的 ppid 互不相同(实测 37548/38748/...), gmt begin 建的会话后续
        找不到 -> 退回 classic -> modern 模块名 coast/plot/text 解析失败 -> rc=30。
        显式给定会话名即可绕开 ppid 探测; 用 $$ 保证每次渲染的会话唯一, 便于并发。"""
    if os.name != "nt":
        return text
    lines = text.split("\n")
    idx = 1 if lines and lines[0].startswith("#!") else 0
    inserts = []
    gdir = _find_gmt_dir()
    if gdir:
        inserts.append('export PATH="%s:$PATH"' % _to_msys_path(gdir))
    inserts.append('export GMT_SESSION_NAME="gmt_vectorlab_$$"')
    lines[idx:idx] = inserts
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 直跑通道 (默认渲染方式): 不改脚本结构, 只做三件事 ——
#   1) 给每条 `gmt begin` 的格式列表补 pdf (画布靠 PDF 反推 SVG);
#   2) 去掉 `gmt end` 的 show (否则会唤起外部看图程序并阻塞);
#   3) 数据不在本目录时改写引用 (相对路径 / 中文目录走目录联接)。
# 之后整份脚本原样交给 bash: 变量、source、函数、if、heredoc、反斜杠续行、
# 进程替换全由 bash 自己解释, 因此任意结构的脚本都能跑, 不必"理解"它。
# ---------------------------------------------------------------------------
_FMT_PAT = "|".join(sorted(_FMT_KNOWN, key=len, reverse=True))
_FMT_GROUP_RE = re.compile(r"(?<![\w.,/-])((?:%s)(?:,(?:%s))*)(?![\w,])" % (_FMT_PAT, _FMT_PAT), re.I)
_BEGIN_LINE_RE = re.compile(r"^([ \t]*)gmt[ \t]+begin\b(.*)$", re.I)
_END_SHOW_RE = re.compile(r"(\bgmt[ \t]+end\b)[ \t]+show\b", re.I)

_SKIP_DIRS = {".git", "build", "dist", "node_modules", "__pycache__",
              ".idea", ".vscode", ".ipynb_checkpoints"}


def _read_text(path):
    """源脚本可能是 UTF-8(BOM) 或 GBK, 两种都读。"""
    b = open(path, "rb").read()
    for enc in ("utf-8-sig", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def _ensure_pdf_text(text):
    """文本级补 pdf / 去 show, 只动这两处, 其余字符原样保留。"""
    out = []
    for line in text.split("\n"):
        line = _END_SHOW_RE.sub(r"\1", line)
        m = _BEGIN_LINE_RE.match(line)
        if m:
            head, rest = m.group(1), m.group(2)
            body, hsep, cmt = rest.partition("#")
            groups = list(_FMT_GROUP_RE.finditer(body))
            if not groups:
                body = body.rstrip() + " png,pdf"
            else:
                g = groups[0]
                if "pdf" not in [x.lower() for x in g.group(1).split(",")]:
                    body = body[:g.end()] + ",pdf" + body[g.end():]
            line = head + "gmt begin" + body + hsep + cmt
        out.append(line)
    return "\n".join(out)


def _scan_roots(sdir):
    """脚本常在子目录里 `cd` 到上级再出图 (如 cd "$ROOT/gmt_sh"), 所以脚本目录
    与其父目录都要扫。"""
    roots, seen = [], set()
    for d in (sdir, os.path.dirname(sdir)):
        if d and os.path.isdir(d) and d.lower() not in seen:
            seen.add(d.lower())
            roots.append(d)
    return roots


def _snap_files(roots, exts, depth=3):
    """(路径 -> (mtime, size)) 快照, 用于跑完后认"这次新生成/更新的图"。"""
    snap = {}
    for root in roots:
        base_n = root.rstrip("\\/").count(os.sep)
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns
                      if d.lower() not in _SKIP_DIRS and not d.lower().startswith("_gmtdata")]
            if dp.rstrip("\\/").count(os.sep) - base_n >= depth:
                dns[:] = []
            for fn in fns:
                if os.path.splitext(fn)[1].lower() not in exts:
                    continue
                p = os.path.join(dp, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                snap[p] = (st.st_mtime, st.st_size)
    return snap


def render_direct(workdir, script_path, timeout=300):
    """原脚本直跑: 补 pdf -> 改写数据引用 -> bash 跑整份脚本 -> 认新出的 pdf/png。
    返回字段与 render_and_run 对齐, 另加 pdf / png / pdfs。"""
    sp = os.path.abspath(script_path)
    sdir = os.path.dirname(sp)
    orig_hash = sha256(sp)
    text, missing = _resolve_data_paths(_ensure_pdf_text(_read_text(sp)), sdir)
    roots = _scan_roots(sdir)

    shell = _find_shell()
    if not shell:
        return {"rendered": "", "stdout": "", "rc": -2, "changed": [], "missing": [],
                "pdf": None, "png": None, "pdfs": [], "orig_sha256": orig_hash,
                "script_untouched": True,
                "stderr": ("未找到可用的 POSIX shell (bash)。GMT 现代模式脚本需要一个 bash。"
                           "\n已尝试: PATH 上的 bash/sh、Git for Windows 安装目录、常见 Program Files\\Git。"
                           "\n请安装 Git for Windows (含 Git Bash) 并确保 gmt 在 PATH 上。")}

    # 副本放在脚本同目录: 脚本普遍用 $(dirname "$0") 推 ROOT, 换目录会算错。
    rendered = os.path.join(sdir, "rendered.sh")
    try:
        with open(rendered, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except OSError:
        fd, rendered = tempfile.mkstemp(prefix="_vectorlab_", suffix=".sh", dir=sdir)
        os.close(fd)
        with open(rendered, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    before = _snap_files(roots, (".pdf", ".png"))
    env = _gmt_env()
    env["GMT_SESSION_NAME"] = "gmt_vectorlab_%d" % os.getpid()
    rc, so, se = -1, "", ""
    try:
        proc = subprocess.run([shell, rendered], cwd=sdir, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              env=env, timeout=timeout, **_hidden_console_kwargs())
        rc, so, se = proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        rc = -3
        se = "渲染超时 (%d 秒), 脚本可能在等待输入或数据量过大。" % timeout
    except Exception as e:
        rc, se = -1, "启动 %s 失败: %s" % (os.path.basename(shell), e)

    after = _snap_files(roots, (".pdf", ".png"))
    fresh = [p for p, v in after.items() if before.get(p) != v]

    def _is_tmp(p):
        low = p.lower().replace("\\", "/")
        return "/.tmp/" in low or "/tmp/" in low or "/sessions/" in low

    def _newest(lst):
        return sorted(lst, key=lambda p: after[p][0], reverse=True)

    # 产物优先级: 这次新出且不在临时目录 -> 这次新出 -> 已有的。脚本常把图先渲到
    # work/.tmp 再拷到 out/, 临时目录里的那份也是完整产物, 但不能优先于正式输出。
    fresh_keep = [p for p in fresh if not _is_tmp(p)]
    pdfs = _newest([p for p in fresh_keep if p.lower().endswith(".pdf")])
    if not pdfs:
        pdfs = _newest([p for p in fresh if p.lower().endswith(".pdf")])
    if not pdfs:   # 脚本这次没重画 (if [ ! -f ] 缓存命中), 退回已有 pdf
        pdfs = _newest([p for p in after if p.lower().endswith(".pdf")])
    pdf = pdfs[0] if pdfs else None

    png = None
    cp = [p for p in fresh_keep if p.lower().endswith(".png")]
    if cp:
        png = _newest(cp)[0]
    elif pdf and os.path.exists(os.path.splitext(pdf)[0] + ".png"):
        png = os.path.splitext(pdf)[0] + ".png"
    if not png:
        cp = _newest([p for p in fresh if p.lower().endswith(".png")])
        png = cp[0] if cp else None

    err_txt = (se or "") + "\n" + (so or "")
    miss = set(missing)
    miss.update(re.findall(r"Cannot find file\s+(\S+)", err_txt))
    after_hash = sha256(sp)
    return {"rendered": rendered, "stdout": so, "stderr": se, "rc": rc, "changed": [],
            "missing": sorted(miss), "pdf": pdf, "png": png, "pdfs": pdfs,
            "orig_sha256": orig_hash, "script_untouched": orig_hash == after_hash}


def render_and_run(workdir, script_path, overlay_path, out_name="figure"):
    orig_hash = sha256(script_path)
    ir = parse_script(script_path)
    overlay = json.load(open(overlay_path, "r", encoding="utf-8")) if overlay_path and os.path.exists(overlay_path) else {"ops": []}
    edir, changed = apply_overlay(ir, overlay)
    # 自动化渲染: 去掉 'gmt end show' 的 show, 避免唤起查看器阻塞
    edir["end"]["tokens"] = [t for t in edir["end"]["tokens"] if t.lower() != "show"]
    text = emit_script(edir)
    text, missing = _resolve_data_paths(text, workdir)
    text = _with_gmt_path_first(text)
    rendered = os.path.join(workdir, "rendered.sh")
    with open(rendered, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    shell = _find_shell()
    if not shell:
        return {"rendered": rendered, "stdout": "", "rc": -2, "changed": changed,
                "stderr": ("未找到可用的 POSIX shell (bash)。GMT 现代模式脚本需要一个 bash。"
                           "\n已尝试: PATH 上的 bash/sh、Git for Windows 安装目录、常见 Program Files\\Git。"
                           "\n请安装 Git for Windows (含 Git Bash) 并确保 gmt 在 PATH 上。"),
                "orig_sha256": orig_hash, "script_untouched": orig_hash == sha256(script_path)}
    # 真渲染: 交给定位到的 shell 跑 GMT 现代模式 (隐藏控制台, 避免 windowed exe 弹命令行框)
    proc = subprocess.run([shell, rendered], cwd=workdir,
                          capture_output=True, text=True, env=_gmt_env(),
                          **_hidden_console_kwargs())
    # 关键安全断言: 源脚本没被动过
    after_hash = sha256(script_path)
    assert orig_hash == after_hash, "源脚本被改动了! (不应发生)"
    # 找不到的数据 + GMT 自己报的 Cannot find file, 合并成一份缺失清单。
    # 这类错误不会让 rc 变非零: GMT 只跳过那一条模块, 图照出但少了那一层。
    err_txt = (proc.stderr or "") + "\n" + (proc.stdout or "")
    miss = set(missing)
    miss.update(re.findall(r"Cannot find file\s+(\S+)", err_txt))
    toks = ir["begin"]["tokens"]
    nm = toks[2] if len(toks) >= 3 and not toks[2].startswith(("$", '"$', "'$")) else out_name
    pdf = os.path.join(workdir, nm + ".pdf")
    png = os.path.join(workdir, nm + ".png")
    return {"rendered": rendered, "stdout": proc.stdout or "", "stderr": proc.stderr or "",
            "rc": proc.returncode, "changed": changed, "missing": sorted(miss),
            "pdf": pdf if os.path.exists(pdf) else None,
            "png": png if os.path.exists(png) else None,
            "pdfs": [pdf] if os.path.exists(pdf) else [],
            "orig_sha256": orig_hash, "script_untouched": orig_hash == after_hash}

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_parse(a):
    ir = parse_script(a.script)
    print(f"源脚本: {ir['path']}")
    print(f"会话  : {' '.join(ir['begin']['tokens'])}  ...  {' '.join(ir['end']['tokens'])}")
    print(f"图层数: {len(ir['ops'])}  (每个 GMT 命令 = 一个可寻址图层)\n")
    for op in ir["ops"]:
        d = op.to_dict()
        print(f"  [图层 {d['index']}] 第 {d['line']} 行  模块=gmt {d['module']}")
        for k, v in d["options"].items():
            print(f"       {k:8} = {v!r}")
        print()
    if a.json:
        spec = {"begin": ir["begin"]["tokens"], "end": ir["end"]["tokens"],
                "ops": [op.to_dict() for op in ir["ops"]]}
        open(a.json, "w", encoding="utf-8").write(json.dumps(spec, ensure_ascii=False, indent=2))
        print(f"[已导出 IR -> {a.json}]")

def cmd_report(a):
    ir = parse_script(a.script)
    overlay = json.load(open(a.overlay, "r", encoding="utf-8"))
    _, changed = apply_overlay(ir, overlay)
    print(f"改动清单 (共 {len(changed)} 处, 源脚本不变):")
    for idx, mod, flag, old, new in changed:
        o = "(new)" if old is None else old
        print(f"  图层{idx} gmt {mod}  {flag}: {o!r}  ->  {new!r}")

def cmd_render(a):
    res = render_and_run(os.path.dirname(os.path.abspath(a.script)) or ".",
                         a.script, a.overlay)
    print(f"生成脚本 : {res['rendered']}")
    print(f"源脚本不变: {res['script_untouched']}  sha256={res['orig_sha256'][:16]}…")
    print(f"改动数   : {len(res['changed'])}")
    print(f"GMT 返回码: {res['rc']}")
    if res["rc"] != 0:
        print("---- GMT stderr ----"); print(res["stderr"])
    elif a.show:
        print(res["stdout"][-400:])

def cmd_verify(a):
    print(sha256(a.script))

def main():
    p = argparse.ArgumentParser(description="GMT VectorLab —— 命令行工具与渲染引擎")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("parse"); sp.add_argument("--script", required=True); sp.add_argument("--json"); sp.set_defaults(f=cmd_parse)
    sr = sub.add_parser("report"); sr.add_argument("--script", required=True); sr.add_argument("--overlay", required=True); sr.set_defaults(f=cmd_report)
    sd = sub.add_parser("render"); sd.add_argument("--script", required=True); sd.add_argument("--overlay"); sd.add_argument("--show", action="store_true"); sd.set_defaults(f=cmd_render)
    sv = sub.add_parser("verify"); sv.add_argument("--script", required=True); sv.set_defaults(f=cmd_verify)
    a = p.parse_args()
    a.f(a)

if __name__ == "__main__":
    main()
