#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.py —— GMT VectorLab 的共享内核 (被 app.py 复用)

职责: 源脚本 <-> IR <-> overlay, 命令级重渲染 GMT, 可选烘焙 #2 元素 overlay。
返回统一的 dict (含 png_path), 由调用方决定如何把图片交给前端
(HTTP -> /fig URL; pywebview -> data URI)。
"""
import os, sys, json, time, base64, tempfile, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gmt_editor as GE
import svgify
import reapply


_IR_CACHE = {}


def get_ir(workdir, script):
    """源脚本 -> IR dict。按脚本指纹缓存 (每次画布重建都会要一次)。"""
    sp = os.path.join(workdir, script) if not os.path.isabs(script) else script
    key = _fingerprint(sp, None)
    hit = _IR_CACHE.get(key) if key else None
    if hit is not None:
        return dict(hit)
    ir = GE.parse_script(sp)
    out = {
        "script": os.path.basename(sp),
        "sha256": GE.sha256(sp),
        "begin": " ".join(ir["begin"]["tokens"]),
        "end": " ".join(ir["end"]["tokens"]),
        "ops": [op.to_dict() for op in ir["ops"]],
    }
    if key:
        _IR_CACHE[key] = out
        if len(_IR_CACHE) > _CACHE_MAX:
            _IR_CACHE.pop(next(iter(_IR_CACHE)))
    return dict(out)


def _overlay_tmp(overlay):
    """把 overlay dict 落临时 json, 返回路径 (调用方负责删除)。"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(overlay or {"ops": []}, tf, ensure_ascii=False)
        return tf.name


def _session_name(sp):
    """从 gmt begin <NAME> 解析输出会话名 (可能不是 figure)。"""
    try:
        toks = GE.parse_script(sp)["begin"]["tokens"]  # ['gmt','begin',NAME,format,...]
        return toks[2] if len(toks) >= 3 else "figure"
    except Exception:
        return "figure"


def _gmt_cause(stderr, stdout):
    """从 GMT 的 stderr/stdout 里挑一句最能说明失败原因的话, 供错误提示直接可见。"""
    for blob in (stderr or "", stdout or ""):
        lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
        for ln in lines:
            if "[ERROR]" in ln or "ERROR:" in ln.upper():
                return ln[:200]
        if lines:
            return lines[-1][:200]
    return "无 stderr 输出 (多为数据文件缺失/路径不对, 或 `gmt begin` 未含 pdf 输出格式)"


def _legacy_run(workdir, sp, overlay):
    """命令级重写通道: 解析脚本 -> 套 overlay -> 重新拼 rendered.sh 再跑。
    只在有命令级参数改动时使用 (直跑无法体现"改某条命令的参数")。"""
    ov_path = _overlay_tmp(overlay)
    try:
        return GE.render_and_run(workdir, sp, ov_path)
    finally:
        try:
            os.unlink(ov_path)
        except OSError:
            pass


def _run_and_locate(workdir, sp, overlay):
    """渲染一份图并定位产物 (pdf/png)。默认走直跑通道 (原脚本原样执行), 有命令级
    参数改动时才重写命令; 两者互为兜底, 谁成功用谁。
    out 含 rc/stdout/stderr/changed/sha_ok/sha256, 失败时含 error。"""
    out = {"baked_elements": 0}
    ops = (overlay or {}).get("ops") or []
    if ops:
        res = _legacy_run(workdir, sp, overlay)
        if res.get("rc") != 0 or not res.get("pdf"):
            alt = GE.render_direct(workdir, sp)
            if alt.get("rc") == 0 and alt.get("pdf"):
                res = alt
    else:
        res = GE.render_direct(workdir, sp)
        if res.get("rc") != 0 or not res.get("pdf"):
            alt = _legacy_run(workdir, sp, overlay)
            if alt.get("rc") == 0 and alt.get("pdf"):
                res = alt

    out.update({
        "rc": res.get("rc", -1),
        "stdout": (res.get("stdout") or "")[-2000:],
        "stderr": (res.get("stderr") or "")[-4000:],
        "changed": [{"index": c[0], "module": c[1], "flag": c[2], "old": c[3], "new": c[4]}
                    for c in (res.get("changed") or [])],
        "sha_ok": res.get("script_untouched", False),
        "sha256": res.get("orig_sha256", ""),
    })
    if res.get("rc", -1) != 0:
        rc = res.get("rc")
        if rc == -2:
            out["error"] = res.get("stderr") or "未找到可用的 POSIX shell (bash)"
        elif rc == -3:
            out["error"] = res.get("stderr") or "渲染超时"
        elif rc == 127:
            out["error"] = ("命令未找到 (rc=127)：多半是 GMT 的 `gmt.exe` 没在程序能看到的 PATH 上。"
                            "请确认已安装 GMT 6（本工具会自动在 系统PATH / 注册表PATH / "
                            "常见安装目录 如 C:\\programs\\gmt6\\bin、C:\\GMT\\*\\bin 里找）。"
                            "若装在别处, 把 GMT 的 bin 目录加入系统 PATH 后重开程序。")
        else:
            out["error"] = "GMT 渲染返回非零 (rc=%s): %s" % (
                rc, _gmt_cause(res.get("stderr") or "", res.get("stdout") or ""))
        return out, None, None, _session_name(sp)

    base_pdf = res.get("pdf")
    base_png = res.get("png")
    name = os.path.splitext(os.path.basename(base_pdf))[0] if base_pdf else _session_name(sp)
    if not base_png:
        for p in ([os.path.splitext(base_pdf)[0] + ".png"] if base_pdf else []) + \
                 [os.path.join(workdir, name + ".png"), os.path.join(workdir, "figure.png")]:
            if os.path.exists(p):
                base_png = p
                break
    out["png_path"] = base_png
    out["name"] = name
    out["pdf_path"] = base_pdf
    if res.get("pdfs") and len(res["pdfs"]) > 1:
        out["pdfs"] = res["pdfs"][:20]

    stderr_txt = res.get("stderr") or ""
    if not base_png and not base_pdf:
        out["error"] = ("GMT 未生成图件 (退出码 0 但没找到 %s.png/.pdf)。多为数据文件缺失/路径不对。" % name)
        return out, None, None, name
    miss = res.get("missing") or []
    if miss:
        # 数据缺失不会让 rc 非零, 只会让对应模块 (典型就是 grdimage 地形底图) 静默跳过。
        # 必须前置成显式告警, 否则用户看到的是"能打开但图层丢了"。
        out["warn"] = ("以下数据文件在脚本目录及其上下级都没找到, 对应图层未绘制:\n  "
                       + "\n  ".join(miss)
                       + "\n\n请把脚本和数据放在同一目录, 或把数据补到脚本所在目录的上一级。")
        out["missing"] = miss
    elif "[ERROR]" in stderr_txt:
        out["warn"] = stderr_txt[-800:]
    return out, base_png, base_pdf, name


def _bake_svg(workdir, base_pdf, elements):
    """把元素 overlay 烘焙到 base_pdf 反推的 SVG, 出高清 final.png。
    返回 (final_png, report_list) 或抛异常。"""
    import fitz
    svg, _nv, _nt = svgify.build_svg(base_pdf)
    edited, rep = reapply.apply_edits(svg, elements)
    tmp_svg = os.path.join(workdir, "final.svg")
    open(tmp_svg, "w", encoding="utf-8").write(edited)
    d = fitz.open(tmp_svg)
    final = os.path.join(workdir, "final.png")
    d[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(final)
    d.close()
    return final, rep


def render(workdir, script, overlay, elements=None):
    """命令级 overlay -> GMT 重渲染; 若给 elements 再烘焙成 final.png。
    返回 dict: rc/stderr/changed/sha_ok/sha256/png_path/baked_elements[/error]。"""
    sp = os.path.join(workdir, script) if not os.path.isabs(script) else script
    if not os.path.exists(sp):
        return {"rc": -1, "error": "源脚本不存在: " + script, "stderr": "", "changed": [],
                "sha_ok": False, "sha256": "", "baked_elements": 0}

    t0 = time.time()
    out, base_png, base_pdf, _name = _run_and_locate(workdir, sp, overlay)
    if out.get("error"):
        out["t_total"] = time.time() - t0
        return out

    if elements and base_pdf and os.path.exists(base_pdf):
        try:
            final, rep = _bake_svg(workdir, base_pdf, elements)
            out["png_path"] = final
            out["baked_elements"] = len(rep)
            out["report"] = [[g, t, d] for g, t, d in rep]
        except Exception as e:
            out["element_error"] = "元素烘焙失败: %s" % e
    out["t_total"] = time.time() - t0
    return out


def _fingerprint(sp, payload):
    """缓存键: 脚本路径 + mtime + size + 请求内容。脚本或改动一变, 键就变。"""
    try:
        st = os.stat(sp)
    except OSError:
        return None
    return (os.path.abspath(sp), st.st_mtime, st.st_size,
            json.dumps(payload or {}, sort_keys=True, ensure_ascii=False))


# 画布重建是最贵的一步 (大脚本: GMT 一跑就是两分钟, PDF->SVG 再十几秒),
# 而切模式、撤销、载入元素这些操作要的是同一张图 —— 按脚本指纹缓存结果。
_CACHE = {}
_CACHE_MAX = 4


def _cache_get(key):
    return _CACHE.get(key) if key else None


def _cache_put(key, value):
    if key is None:
        return
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = value


def svg_for(workdir, script, overlay, fresh=False):
    """命令级 overlay -> GMT 重渲染 -> 可寻址 SVG (供画布编辑)。
    fresh=True 时忽略缓存强制重渲染 (数据文件变了但脚本没改时必须走这条)。
    返回 dict: svg/png_path/name/rc/stderr/changed/sha_ok/sha256[/error/warn/cached/t_*]。"""
    sp = os.path.join(workdir, script) if not os.path.isabs(script) else script
    if not os.path.exists(sp):
        return {"rc": -1, "error": "源脚本不存在: " + script, "stderr": "", "changed": [],
                "sha_ok": False, "sha256": "", "svg": ""}

    key = _fingerprint(sp, overlay)
    if not fresh:
        hit = _cache_get(key)
        if hit is not None:
            out = dict(hit)
            out["cached"] = True
            out["t_total"] = 0.0
            return out

    t0 = time.time()
    out, base_png, base_pdf, name = _run_and_locate(workdir, sp, overlay)
    out["t_render"] = time.time() - t0
    if out.get("error"):
        out["svg"] = ""
        out["cached"] = False
        out["t_total"] = out["t_render"]
        return out
    if not (base_pdf and os.path.exists(base_pdf)):
        return {"rc": out.get("rc", 0), "error": "缺少 PDF, 无法生成可编辑画布 (请确认脚本 `gmt begin` 含 pdf 输出格式)",
                "svg": "", "png_path": base_png, "name": name,
                "changed": out.get("changed", []), "sha_ok": out.get("sha_ok", False),
                "sha256": out.get("sha256", ""), "stderr": out.get("stderr", ""),
                "cached": False, "t_render": out["t_render"], "t_total": out["t_render"]}
    t1 = time.time()
    try:
        svg, n_vec, n_txt = svgify.build_svg(base_pdf)
    except Exception as e:
        return {"rc": out.get("rc", 0), "error": "SVG 构建失败: %s" % e, "svg": "",
                "png_path": base_png, "name": name, "changed": out.get("changed", []),
                "sha_ok": out.get("sha_ok", False), "sha256": out.get("sha256", ""),
                "stderr": out.get("stderr", ""), "cached": False,
                "t_render": out["t_render"], "t_svg": time.time() - t1,
                "t_total": time.time() - t0}
    out.update({"svg": svg, "n_vec": n_vec, "n_txt": n_txt, "png_path": base_png, "name": name,
                "cached": False, "t_svg": time.time() - t1, "t_total": time.time() - t0})
    _cache_put(key, dict(out))
    return out


def bake(workdir, script, overlay, elements):
    """命令级 overlay 重渲染 + 元素 overlay 烘焙 -> 高清 final.png。
    返回 dict: png_path/baked_elements/report/rc/sha_ok[/error/warn/element_error]。"""
    sp = os.path.join(workdir, script) if not os.path.isabs(script) else script
    if not os.path.exists(sp):
        return {"rc": -1, "error": "源脚本不存在: " + script, "stderr": "", "changed": [],
                "sha_ok": False, "sha256": "", "baked_elements": 0}

    t0 = time.time()
    out, base_png, base_pdf, name = _run_and_locate(workdir, sp, overlay)
    if out.get("error"):
        out["t_total"] = time.time() - t0
        return out
    if not (elements and base_pdf and os.path.exists(base_pdf)):
        out["png_path"] = base_png
        out["baked_elements"] = 0
        out["t_total"] = time.time() - t0
        return out
    try:
        final, rep = _bake_svg(workdir, base_pdf, elements)
        out["png_path"] = final
        out["baked_elements"] = len(rep)
        out["report"] = [[g, t, d] for g, t, d in rep]
    except Exception as e:
        out["element_error"] = "元素烘焙失败: %s" % e
    out["t_total"] = time.time() - t0
    return out


def export_figure(workdir, script, overlay, elements=None, fmt="png", scale=2, quality=92):
    """渲染 (+可选烘焙元素改动) 后按指定格式/倍数导出图片字节。
    fmt: "png" | "jpg"; scale: 相对 PDF 页面的放大倍数; quality: JPG 质量 1-100。
    返回 dict: data(base64)/fmt/name/width/height[/error]。"""
    import fitz
    sp = os.path.join(workdir, script) if not os.path.isabs(script) else script
    if not os.path.exists(sp):
        return {"error": "源脚本不存在: " + script}
    fmt = "jpg" if str(fmt).lower() in ("jpg", "jpeg") else "png"
    try:
        scale = max(0.5, min(12.0, float(scale)))
    except (TypeError, ValueError):
        scale = 2.0
    out, base_png, base_pdf, name = _run_and_locate(workdir, sp, overlay)
    if out.get("error"):
        return out
    src_doc = None
    if elements and base_pdf and os.path.exists(base_pdf):
        try:
            _final, rep = _bake_svg(workdir, base_pdf, elements)
            out["baked_elements"] = len(rep)
            src_doc = fitz.open(os.path.join(workdir, "final.svg"))   # _bake_svg 落盘的 edited svg
        except Exception as e:
            out["element_error"] = "元素烘焙失败: %s" % e
    if src_doc is None:
        if not (base_pdf and os.path.exists(base_pdf)):
            return {"rc": out.get("rc", 0), "error": "缺少 PDF, 无法导出 (请确认脚本 `gmt begin` 含 pdf 输出格式)",
                    "stderr": out.get("stderr", "")}
        src_doc = fitz.open(base_pdf)
    try:
        page = src_doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        if fmt == "jpg":
            data = pix.tobytes("jpeg", jpg_quality=max(1, min(100, int(quality))))
        else:
            data = pix.tobytes("png")
    finally:
        src_doc.close()
    out.update({"data": base64.b64encode(data).decode(), "fmt": fmt, "name": name,
                "width": pix.width, "height": pix.height, "scale": scale})
    return out
