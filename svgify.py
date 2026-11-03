#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
svgify.py —— 把 GMT 出的 PDF 重建成"每个元素独立可寻址、文字仍是真文字"的 SVG,
             并生成自包含的浏览器编辑器 editor.html (v3)。

v3 新增 (向产品完成度靠):
  - 选中框上的 8 个缩放手柄 + 旋转手柄: 拖角自由缩放(可非等比)、拖顶旋转
  - 多选: Shift 点选 / 空白处框选(橡皮筋); 成组拖动
  - 撤销/重做 (Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y), 复制 (Ctrl+D)
  - 文字元素列表 (点名字直接选中, 眼睛切换显隐)
  - 新建文字标注工具 (＋文字 -> 点画布 -> 输入)
  - 保留: 字体(含中文)/字号/粗斜/颜色/矢量填充描边线宽/旋转/透明度/隐藏/复位,
          画布缩放平移, 导出 overlay/SVG/PNG, 导入并套用

用法: python svgify.py base.pdf --svg base.svg --html editor.html
"""
import sys, os, json, html, base64, argparse
import fitz

# 矢量元素上限: 超过就把矢量层整层栅格化 (20 万点散点会炸成 60 多万条 path / 200 MB+,
# 浏览器画布扛不住)。文字层始终保留矢量, 仍可点选、改字、改字体。
VEC_LIMIT = int(os.environ.get("GMT_MAX_VEC", "20000"))


def tohex(c):
    if c is None:
        return None
    try:
        r, g, b = c[0], c[1], c[2]
    except Exception:
        return None
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _xy(p):
    return (p.x, p.y) if hasattr(p, "x") else (p[0], p[1])


# PDF 里存的是 PostScript 字体名 ("Times-Bold" / "Helvetica" / "Arial-BoldMT"),
# 浏览器不认这些名字, 直接写进 font-family 会回退到默认字体, 与原图不一致。
_PS_FAMILIES = {
    "times": ("Times New Roman", "Times", "serif"),
    "helvetica": ("Helvetica", "Arial", "sans-serif"),
    "arial": ("Arial", "Helvetica", "sans-serif"),
    "arialmt": ("Arial", "Helvetica", "sans-serif"),
    "timesnewroman": ("Times New Roman", "Times", "serif"),
    "timesnewromanps": ("Times New Roman", "Times", "serif"),
    "helveticamt": ("Helvetica", "Arial", "sans-serif"),
    "courier": ("Courier New", "Courier", "monospace"),
    "symbol": ("Symbol",),
    "zapfdingbats": ("Zapf Dingbats", "Segoe UI Symbol"),
    "song": ("SimSun", "Songti SC", "Noto Serif CJK SC", "serif"),
    "stsong": ("SimSun", "Songti SC", "serif"),
    "stsonglight": ("SimSun", "Songti SC", "serif"),
    "hei": ("Microsoft YaHei", "SimHei", "sans-serif"),
    "stheiti": ("Microsoft YaHei", "SimHei", "sans-serif"),
    "kai": ("KaiTi", "STKaiti", "serif"),
    "fangsong": ("FangSong", "STFangsong", "serif"),
    "songti": ("SimSun", "Songti SC", "serif"),
    "heiti": ("Microsoft YaHei", "SimHei", "sans-serif"),
}
_PS_STYLES = {"bold", "italic", "bolditalic", "oblique", "boldoblique", "roman",
              "light", "medium", "semibold", "demibold", "black", "heavy"}


def _ps_font(name, flags=0):
    """PostScript 字体名 + fitz flags -> (css font-family, bold, italic)。"""
    n = (name or "").strip()
    bold = bool(flags & 16)
    italic = bool(flags & 2)
    stem = n
    if "," in stem:                      # "Arial,Bold"
        stem, _, suf = stem.partition(",")
        s = suf.strip().lower()
        bold = bold or ("bold" in s)
        italic = italic or ("italic" in s or "oblique" in s)
    low = stem.lower()
    if "-" in low:                       # "Times-Bold" / "Helvetica-Oblique"
        head, _, suf = low.rpartition("-")
        if suf in _PS_STYLES:
            low = head
            bold = bold or ("bold" in suf)
            italic = italic or ("italic" in suf or "oblique" in suf)
    if low.endswith("mt"):               # "Arial-BoldMT" / "TimesNewRomanPSMT"
        low = low[:-2]
        bold = bold or ("bold" in low)
        italic = italic or ("italic" in low)
        low = low.replace("bold", "").replace("italic", "").replace("oblique", "")
        low = low.strip("-")
    fam = _PS_FAMILIES.get(low)
    if fam is None:
        fam = (n,) if n else ("Helvetica", "Arial", "sans-serif")
        if "sans" in low:
            fam = fam + ("sans-serif",)
        elif "mono" in low:
            fam = fam + ("monospace",)
        elif "serif" in low:
            fam = fam + ("serif",)
    css = ", ".join("&quot;%s&quot;" % f if " " in f else f for f in fam)
    return css, bold, italic


def _rect(r):
    """Rect / Quad / Point / 4 个标量 / 点序列 -> (x0, y0, x1, y1)。
    "qu" 项的 it[1] 是 fitz.Quad (4 个 Point), 直接解包再 min/max 会拿 Point 互相比较。"""
    if r is None:
        return 0.0, 0.0, 0.0, 0.0
    if hasattr(r, "x0") and hasattr(r, "x1"):
        return r.x0, r.y0, r.x1, r.y1
    if hasattr(r, "points"):          # fitz.Quad
        r = r.points
    if hasattr(r, "x") and hasattr(r, "y"):   # fitz.Point
        return r.x, r.y, r.x, r.y
    pts = list(r)
    if len(pts) == 4 and all(isinstance(v, (int, float)) for v in pts):
        x0, y0, x1, y1 = pts
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)
    xs = [p.x if hasattr(p, "x") else p[0] for p in pts]
    ys = [p.y if hasattr(p, "y") else p[1] for p in pts]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _same(a, b, tol=1e-2):
    return a is not None and abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def items_to_d(items, close_path=False):
    d, last = [], None
    for it in items:
        op = it[0]
        if op == "l":
            x1, y1 = _xy(it[1]); x2, y2 = _xy(it[2])
            if not _same(last, (x1, y1)):
                d.append(f"M{x1:.2f} {y1:.2f}")
            d.append(f"L{x2:.2f} {y2:.2f}"); last = (x2, y2)
        elif op == "c":
            x1, y1 = _xy(it[1]); c1x, c1y = _xy(it[2]); c2x, c2y = _xy(it[3]); x2, y2 = _xy(it[4])
            if not _same(last, (x1, y1)):
                d.append(f"M{x1:.2f} {y1:.2f}")
            d.append(f"C{c1x:.2f} {c1y:.2f} {c2x:.2f} {c2y:.2f} {x2:.2f} {y2:.2f}"); last = (x2, y2)
        elif op in ("re", "qu"):
            x0, y0, x1, y1 = _rect(it[1])
            d.append(f"M{x0:.2f} {y0:.2f}H{x1:.2f}V{y1:.2f}H{x0:.2f}Z"); last = None
    if close_path and last is not None:
        d.append("Z")
    return "".join(d)


def _collect_spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln.get("spans", []):
                if s["text"].strip() == "":
                    continue
                out.append(s)
    return out


def _raster_no_text(page, spans, zoom):
    """渲染底图但先抹掉文字 (文字层另用矢量叠加), 否则文字会叠出重影。
    redaction 只删文字对象, 线条/图形/图片保留 (fill=None 不涂白)。"""
    for s in spans:
        try:
            page.add_redact_annot(fitz.Rect(s["bbox"]), fill=None)
        except Exception:
            pass
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,
                             graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                             text=fitz.PDF_REDACT_TEXT_REMOVE)
    except Exception:
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
        except Exception:
            pass
    return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)


def build_svg(pdf_path, max_vec=None, raster_zoom=4.0):
    doc = fitz.open(pdf_path); page = doc[0]
    W, H = page.rect.width, page.rect.height
    spans = _collect_spans(page)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.2f} {H:.2f}" '
             f'width="{W:.2f}" height="{H:.2f}" font-family="Helvetica,Arial,sans-serif">',
             f'<rect x="0" y="0" width="{W:.2f}" height="{H:.2f}" fill="white" class="bg"/>',
             '<g id="vec-layer">']
    n_vec = 0
    limit = VEC_LIMIT if max_vec is None else max_vec
    # 先看内容流字节数 (毫秒级): 20 万点散点的内容流 145 MB, 普通图 0.2 MB。
    # 光枚举 get_drawings() 就要 30 秒, 大图不该走那条路。
    heavy = False
    if limit:
        try:
            heavy = sum(len(doc.xref_stream(x) or b"") for x in page.get_contents()) > 4 * 1024 * 1024
        except Exception:
            heavy = False
    drawings = [] if heavy else page.get_drawings()
    if limit and len(drawings) > limit:
        heavy = True
    if heavy:
        # 元素过多 (超大散点/栅格化曲面): 矢量层整层转位图, 文字层仍是矢量
        pix = _raster_no_text(page, spans, raster_zoom)
        b64 = base64.b64encode(pix.tobytes("png")).decode()
        parts.append(f'<image x="0" y="0" width="{W:.2f}" height="{H:.2f}" '
                     f'preserveAspectRatio="none" href="data:image/png;base64,{b64}"/>')
        drawings = []
    for dr in drawings:
        d = items_to_d(dr["items"], dr.get("closePath", False))
        if not d:
            continue
        fill = tohex(dr.get("fill")); stroke = tohex(dr.get("color"))
        w = dr.get("width") or 0.5
        fo = dr.get("fill_opacity"); so = dr.get("stroke_opacity")
        fos = "" if fo in (None, 1) else f' fill-opacity="{fo:.2f}"'
        sos = "" if so in (None, 1) else f' stroke-opacity="{so:.2f}"'
        layer = str(dr.get("layer", ""))
        x0, y0, x1, y1 = _rect(dr["rect"])
        fr = "evenodd" if dr.get("even_odd") else "nonzero"
        parts.append(
            f'<g class="vec" id="vec_{n_vec}" data-bbox="{x0:.1f} {y0:.1f} {x1:.1f} {y1:.1f}" '
            f'data-layer="{html.escape(layer)}">'
            f'<path d="{d}" fill="{fill or "none"}" stroke="{stroke or "none"}" '
            f'stroke-width="{w:.2f}" fill-rule="{fr}"{fos}{sos}/></g>')
        n_vec += 1
    parts.append('</g><g id="txt-layer">')
    n_txt = 0
    for s in spans:
        txt = s["text"]
        ox, oy = _xy(fitz.Point(s["origin"])) if "origin" in s else (s["bbox"][0], s["bbox"][3])
        x0, y0, x1, y1 = s["bbox"]
        col = tohex((((s["color"] >> 16) & 255) / 255,
                     ((s["color"] >> 8) & 255) / 255, (s["color"] & 255) / 255)) or "#000000"
        fam, bold, italic = _ps_font(s.get("font", ""), s.get("flags", 0))
        wt = ' font-weight="bold"' if bold else ""
        it = ' font-style="italic"' if italic else ""
        parts.append(
            f'<g class="txt" id="txt_{n_txt}" data-bbox="{x0:.1f} {y0:.1f} {x1:.1f} {y1:.1f}" '
            f'data-content="{html.escape(txt)}" data-psfont="{html.escape(str(s.get("font", "")))}">'
            f'<text x="{ox:.2f}" y="{oy:.2f}" font-size="{s["size"]:.2f}" '
            f'font-family="{fam}"{wt}{it} fill="{col}">{html.escape(txt)}</text></g>')
        n_txt += 1
    parts.append('</g></svg>')
    return "\n".join(parts), n_vec, n_txt


EDITOR_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>GMT 图元编辑器 v3</title>
<style>
 :root{--bg:#1e1f24;--panel:#26272d;--line:#3a3b42;--txt:#e6e6e6;--mut:#9aa0aa;--acc:#3b6ea5}
 *{box-sizing:border-box}
 body{margin:0;font-family:system-ui,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--txt);height:100vh;display:flex;flex-direction:column;overflow:hidden}
 #bar{display:flex;gap:6px;align-items:center;padding:8px 12px;background:var(--panel);border-bottom:1px solid var(--line);flex-wrap:wrap}
 button{background:var(--acc);color:#fff;border:0;border-radius:6px;padding:6px 10px;cursor:pointer;font-size:13px}
 button:hover{filter:brightness(1.15)} button.warn{background:#a55b3b} button.ok{background:#3a8a4d} button.gh{background:#3a3b42}
 button.act{background:#c47f2a}
 .sep{width:1px;height:22px;background:var(--line);margin:0 2px}
 #zoomlbl{min-width:48px;text-align:center;font-variant-numeric:tabular-nums;color:var(--mut)}
 #main{flex:1;display:flex;min-height:0}
 #stage{flex:1;overflow:auto;background:#14151a;position:relative;cursor:default}
 #stage.pan{cursor:grab} #stage.panning{cursor:grabbing} #stage.addtxt{cursor:text}
 #wrap{transform-origin:0 0;padding:24px;display:inline-block}
 #wrap>div{background:#fff;box-shadow:0 6px 30px rgba(0,0,0,.6);display:inline-block}
 svg{display:block}
 g.vec:hover path,g.txt:hover text{filter:drop-shadow(0 0 1.5px #ffd24a)}
 .ui-line{fill:none;stroke:#ff5b5b;stroke-width:1;vector-effect:non-scaling-stroke;pointer-events:none}
 .ui-h{fill:#fff;stroke:#ff5b5b;stroke-width:1.2;cursor:pointer}
 .ui-rot{fill:#ff5b5b;stroke:#fff;stroke-width:1.2;cursor:grab}
 #panel{width:288px;background:var(--panel);border-left:1px solid var(--line);padding:12px;overflow:auto;font-size:13px}
 #panel h3{margin:0 0 8px;font-size:13px;color:var(--acc)}
 .row{margin:7px 0;display:flex;align-items:center;gap:8px}
 .row label{width:50px;color:var(--mut);flex:none}
 .row input[type=number]{width:60px;background:#1a1b20;color:#fff;border:1px solid var(--line);border-radius:5px;padding:4px}
 .row input[type=range]{flex:1}
 .row input[type=color]{width:32px;height:26px;border:1px solid var(--line);background:none;padding:0}
 .row select,.row input[type=text]{flex:1;min-width:0;background:#1a1b20;color:#fff;border:1px solid var(--line);border-radius:5px;padding:4px}
 .tgl{display:flex;gap:6px}.tgl button{padding:4px 9px;background:#3a3b42}.tgl button.on{background:var(--acc)}
 .grp{border-top:1px solid var(--line);margin-top:10px;padding-top:6px}.grp .t{font-size:11px;color:var(--mut);margin-bottom:2px}
 #empty{color:var(--mut);font-size:12px;line-height:1.6}
 #hint{font-size:11px;color:var(--mut)} #cnt{color:#ffd479;font-weight:600}
 .btnrow{display:flex;gap:6px;margin-top:8px}.btnrow button{flex:1}
 #txtlist{max-height:150px;overflow:auto;border:1px solid var(--line);border-radius:6px;background:#1a1b20}
 #txtlist .li{display:flex;align-items:center;gap:6px;padding:3px 8px;cursor:pointer;font-size:12px;border-bottom:1px solid #2a2b31}
 #txtlist .li:hover{background:#22232a} #txtlist .li.on{background:#2f4460}
 #txtlist .li .eye{cursor:pointer;width:16px;text-align:center;opacity:.8}
 #txtlist .li .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style></head><body>
<div id="bar">
  <button id="undo" class="gh" title="Ctrl+Z">↶撤销</button>
  <button id="redo" class="gh" title="Ctrl+Y">↷重做</button>
  <span class="sep"></span>
  <button id="addtxt" title="点画布放一个文字">＋文字</button>
  <button id="dup" class="gh" title="Ctrl+D">复制</button>
  <button id="hide" class="gh">显隐</button>
  <button id="reset" class="warn">全部重置</button>
  <span class="sep"></span>
  <button id="exp">导出overlay</button>
  <button id="imp">导入套用</button>
  <button id="expsvg" class="ok">导出SVG</button>
  <button id="exppng" class="ok">导出PNG</button>
  <input type="file" id="file" accept=".json" style="display:none">
  <span class="sep"></span>
  <button id="zout" class="gh">－</button><span id="zoomlbl">100%</span><button id="zin" class="gh">＋</button>
  <button id="zfit" class="gh">适应</button><button id="z100" class="gh">100%</button>
  <span id="hint" style="margin-left:8px">点选 · 拖拽移动 · 拖角缩放 · 拖顶旋转 · Shift加选 · 空白框选 · Ctrl+滚轮缩放 · 空格/右键拖动平移 · Delete隐藏 · 双击文字改内容</span>
  <span style="margin-left:auto">改动 <span id="cnt">0</span></span>
</div>
<div id="main">
  <div id="stage"><div id="wrap">__SVG__</div></div>
  <div id="panel">
    <div class="grp" style="border-top:0;margin-top:0"><div class="t">文字元素（点击选中）</div><div id="txtlist"></div></div>
    <div id="empty" style="margin-top:10px">未选中元素。<br>点击图中文字/线条/色块，或拖拽其边角手柄缩放旋转。</div>
    <div id="props" style="display:none">
      <h3 id="ptype">元素</h3>
      <div class="row"><label>内容</label><input type="text" id="p_text"></div>
      <div class="grp"><div class="t">位置 / 变换</div>
        <div class="row"><label>X</label><input type="number" id="p_dx" step="1"><label style="width:24px">Y</label><input type="number" id="p_dy" step="1"></div>
        <div class="row"><label>宽缩</label><input type="range" id="p_sx" min="0.1" max="8" step="0.02"><input type="number" id="p_sxN" step="0.05" style="width:56px"></div>
        <div class="row"><label>高缩</label><input type="range" id="p_sy" min="0.1" max="8" step="0.02"><input type="number" id="p_syN" step="0.05" style="width:56px"></div>
        <div class="row"><label>旋转</label><input type="range" id="p_rot" min="-180" max="180" step="1"><input type="number" id="p_rotN" step="1" style="width:56px"></div>
        <div class="row"><label>透明</label><input type="range" id="p_op" min="0" max="1" step="0.05"><input type="number" id="p_opN" step="0.05" min="0" max="1" style="width:56px"></div>
      </div>
      <div class="grp" id="g_font"><div class="t">文字样式</div>
        <div class="row"><label>字体</label><select id="p_font">
          <option value="Helvetica,Arial,sans-serif">Helvetica/Arial</option><option value="Arial">Arial</option>
          <option value="Times New Roman,serif">Times/衬线</option><option value="Georgia,serif">Georgia</option>
          <option value="Courier New,monospace">Courier/等宽</option>
          <option value="Microsoft YaHei,微软雅黑,sans-serif">微软雅黑(中)</option><option value="SimHei,黑体,sans-serif">黑体(中)</option>
          <option value="SimSun,宋体,serif">宋体(中)</option><option value="KaiTi,楷体,serif">楷体(中)</option></select></div>
        <div class="row"><label>字号</label><input type="range" id="p_size" min="4" max="96" step="0.5"><input type="number" id="p_sizeN" step="0.5" style="width:56px"></div>
        <div class="row"><label>颜色</label><input type="color" id="p_fill"><div class="tgl"><button id="p_bold">B</button><button id="p_ital">I</button></div></div>
      </div>
      <div class="grp" id="g_vec"><div class="t">矢量样式</div>
        <div class="row"><label>填充</label><input type="color" id="p_vfill"><button id="p_vfill0" class="gh" style="padding:4px 8px">无</button></div>
        <div class="row"><label>描边</label><input type="color" id="p_vstroke"></div>
        <div class="row"><label>线宽</label><input type="range" id="p_vw" min="0" max="10" step="0.1"><input type="number" id="p_vwN" step="0.1" style="width:56px"></div>
      </div>
      <div class="btnrow"><button id="p_reset" class="gh">复位此元素</button></div>
    </div>
  </div>
</div>
<script>
const svg=document.querySelector('#wrap svg'), stage=document.getElementById('stage'), wrap=document.getElementById('wrap');
const NS='http://www.w3.org/2000/svg';
const state={}; let selected=new Set(); let zoom=1, spaceDown=false, addMode=false, newN=0;
const hist=[], future=[];
const byId=id=>document.getElementById(id);
function el(id){return byId(id);}
function bboxOf(g){return (g.dataset.bbox||'0 0 0 0').split(' ').map(Number);}
function st(id){return state[id]||(state[id]={dx:0,dy:0,sx:1,sy:1,rot:0,op:1});}
function dirty(e){return e&&(e.dx||e.dy||(e.sx!==undefined&&e.sx!==1)||(e.sy!==undefined&&e.sy!==1)||e.rot||(e.op!==undefined&&e.op!==1)||e.text!==undefined||e.fontFamily!==undefined||e.fontSize!==undefined||e.bold!==undefined||e.italic!==undefined||e.fill!==undefined||e.stroke!==undefined||e.width!==undefined||e.hidden);}
function refresh(){el('cnt').textContent=Object.keys(state).filter(id=>dirty(state[id])).length;buildList();}
function rotV(x,y,d){const r=d*Math.PI/180,c=Math.cos(r),s=Math.sin(r);return[x*c-y*s,x*s+y*c];}
function toRoot(g,px,py){const e=st(g.id),b=bboxOf(g),cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;let[vx,vy]=rotV(px-cx,py-cy,e.rot||0);return[cx+vx*(e.sx==null?1:e.sx)+(e.dx||0),cy+vy*(e.sy==null?1:e.sy)+(e.dy||0)];}
function corners(g){const b=bboxOf(g);return[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]]].map(c=>toRoot(g,c[0],c[1]));}

function applyEl(g){
  const e=st(g.id),b=bboxOf(g),cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;
  const sx=e.sx==null?1:e.sx, sy=e.sy==null?1:e.sy;
  g.setAttribute('transform',`translate(${e.dx||0} ${e.dy||0}) translate(${cx} ${cy}) rotate(${e.rot||0}) scale(${sx} ${sy}) translate(${-cx} ${-cy})`);
  g.style.opacity=(e.op==null?1:e.op); g.style.display=e.hidden?'none':'';
  const t=g.querySelector('text'),p=g.querySelector('path');
  if(t){if(e.fontFamily!==undefined)t.setAttribute('font-family',e.fontFamily);
    if(e.fontSize!==undefined)t.setAttribute('font-size',e.fontSize);
    if(e.fill!==undefined)t.setAttribute('fill',e.fill);
    t.setAttribute('font-weight',e.bold?'bold':'normal');t.setAttribute('font-style',e.italic?'italic':'normal');
    if(e.text!==undefined)t.textContent=e.text;}
  if(p){if(e.fill!==undefined)p.setAttribute('fill',e.fill);
    if(e.stroke!==undefined)p.setAttribute('stroke',e.stroke);
    if(e.width!==undefined)p.setAttribute('stroke-width',e.width);}
}
function renderAll(){for(const id in state){const g=byId(id);if(g)applyEl(g);}drawUI();refresh();}

// ---- 历史 ----
function commit(){hist.push(JSON.stringify(state));if(hist.length>120)hist.shift();future.length=0;}
function undo(){if(!hist.length)return;future.push(JSON.stringify(state));Object.keys(state).forEach(k=>delete state[k]);Object.assign(state,JSON.parse(hist.pop()));renderAll();syncPanel();}
function redo(){if(!future.length)return;hist.push(JSON.stringify(state));Object.keys(state).forEach(k=>delete state[k]);Object.assign(state,JSON.parse(future.pop()));renderAll();syncPanel();}

// ---- UI 覆盖层 ----
let ui=null;
function clearUI(){if(ui)ui.remove();ui=null;}
function drawUI(){clearUI();if(!selected.size)return;ui=document.createElementNS(NS,'g');ui.id='ui';svg.appendChild(ui);
  const hs=7/zoom;
  if(selected.size===1){const g=byId([...selected][0]);if(!g)return;const c=corners(g);
    line([c[0],c[1],c[2],c[3],c[0]]);
    const names=['nw','ne','se','sw'];const H={nw:c[0],ne:c[1],se:c[2],sw:c[3]};
    H.n=mid(c[0],c[1]);H.e=mid(c[1],c[2]);H.s=mid(c[2],c[3]);H.w=mid(c[3],c[0]);
    for(const k in H)hbox(H[k],hs,k);
    const up=rotV(0,-22/zoom,(st(g.id).rot||0));const rp=[H.n[0]+up[0],H.n[1]+up[1]];
    line([H.n,rp]);const r=document.createElementNS(NS,'circle');r.setAttribute('cx',rp[0]);r.setAttribute('cy',rp[1]);r.setAttribute('r',hs/2);r.setAttribute('class','ui-rot');r.dataset.handle='rot';ui.appendChild(r);
  }else{let X0=1e9,Y0=1e9,X1=-1e9,Y1=-1e9;selected.forEach(id=>{const g=byId(id);if(!g)return;corners(g).forEach(p=>{X0=Math.min(X0,p[0]);Y0=Math.min(Y0,p[1]);X1=Math.max(X1,p[0]);Y1=Math.max(Y1,p[1]);});});
    line([[X0,Y0],[X1,Y0],[X1,Y1],[X0,Y1],[X0,Y0]]);}
}
function mid(a,b){return[(a[0]+b[0])/2,(a[1]+b[1])/2];}
function line(pts){const p=document.createElementNS(NS,'polyline');p.setAttribute('points',pts.map(a=>a[0]+','+a[1]).join(' '));p.setAttribute('class','ui-line');ui.appendChild(p);}
function hbox(c,s,h){const r=document.createElementNS(NS,'rect');r.setAttribute('x',c[0]-s/2);r.setAttribute('y',c[1]-s/2);r.setAttribute('width',s);r.setAttribute('height',s);r.setAttribute('class','ui-h');r.dataset.handle=h;ui.appendChild(r);}

// ---- 指针坐标 ----
function svgPt(ev){const p=svg.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;return p.matrixTransform(svg.getScreenCTM().inverse());}
function targetG(ev){return ev.target.closest('g.vec,g.txt');}

// ---- 选择 ----
function selectOnly(id){selected=new Set([id]);syncPanel();drawUI();}
function toggle(id){if(selected.has(id))selected.delete(id);else selected.add(id);syncPanel();drawUI();}

// ---- 主交互 ----
svg.addEventListener('pointerdown',ev=>{
  if(addMode){ev.preventDefault();return;}
  const h=ev.target.closest('.ui-h,.ui-rot');
  if(h){startTransform(h,ev);return;}
  if(spaceDown||ev.button===2)return;
  const g=targetG(ev);
  if(!g){startMarquee(ev);return;}
  if(ev.shiftKey){toggle(g.id);}
  else{if(!selected.has(g.id))selectOnly(g.id);else syncPanel();}
  startMove(ev);
});
function startMove(ev){if(!selected.size)return;commit();
  const p0=svgPt(ev);const base={};selected.forEach(id=>{const e=st(id);base[id]=[e.dx||0,e.dy||0];});
  const mv=e2=>{const p=svgPt(e2);selected.forEach(id=>{const g=byId(id);if(!g)return;const e=st(id);e.dx=base[id][0]+(p.x-p0.x);e.dy=base[id][1]+(p.y-p0.y);applyEl(g);});drawUI();};
  const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);refresh();syncPanel();};
  window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up);
}
function startTransform(h,ev){const id=[...selected][0];const g=byId(id);if(!g)return;commit();
  const e=st(id),b=bboxOf(g),cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;const kind=h.dataset.handle;
  const c=corners(g);const centerRoot=toRoot(g,cx,cy);
  const anchorMap={nw:c[2],ne:c[3],se:c[0],sw:c[1],n:c[2],s:c[0],e:c[3],w:c[1]};
  const anchor=anchorMap[kind]||centerRoot;
  const sx0=e.sx==null?1:e.sx, sy0=e.sy==null?1:e.sy, rot0=e.rot||0;
  const a=rotV(anchor[0]-centerRoot[0],anchor[1]-centerRoot[1],-rot0);
  const p0=svgPt(ev),ang0=Math.atan2(p0[1]-centerRoot[1],p0[0]-centerRoot[0]);
  const mv=e2=>{const p=svgPt(e2);
    if(kind==='rot'){let ang=Math.atan2(p[1]-centerRoot[1],p[0]-centerRoot[0]);let d=rot0+(ang-ang0)*180/Math.PI;if(e2.shiftKey)d=Math.round(d/15)*15;e.rot=Math.round(d);applyEl(g);drawUI();return;}
    const b2=rotV(p[0]-centerRoot[0],p[1]-centerRoot[1],-(e.rot||0));
    if(kind==='se'||kind==='nw'||kind==='ne'||kind==='sw'){if(Math.abs(a[0])>1)e.sx=Math.max(.05,sx0*(b2[0]/a[0]));if(Math.abs(a[1])>1)e.sy=Math.max(.05,sy0*(b2[1]/a[1]));}
    else if(kind==='e'||kind==='w'){if(Math.abs(a[0])>1)e.sx=Math.max(.05,sx0*(b2[0]/a[0]));}
    else if(kind==='n'||kind==='s'){if(Math.abs(a[1])>1)e.sy=Math.max(.05,sy0*(b2[1]/a[1]));}
    applyEl(g);drawUI();};
  const up=()=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);refresh();syncPanel();};
  window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up);
}
// 框选
function startMarquee(ev){const p0=svgPt(ev);const box=document.createElementNS(NS,'rect');box.setAttribute('class','ui-line');box.style.stroke='#4a82bd';svg.appendChild(box);
  const mv=e2=>{const p=svgPt(e2);const x=Math.min(p0.x,p.x),y=Math.min(p0.y,p.y);box.setAttribute('x',x);box.setAttribute('y',y);box.setAttribute('width',Math.abs(p.x-p0.x));box.setAttribute('height',Math.abs(p.y-p0.y));};
  const up=e2=>{window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);const p=svgPt(e2);
    const x0=Math.min(p0.x,p.x),y0=Math.min(p0.y,p.y),x1=Math.max(p0.x,p.x),y1=Math.max(p0.y,p.y);box.remove();
    if(x1-x0<2&&y1-y0<2){if(!ev.shiftKey){selected=new Set();syncPanel();drawUI();}return;}
    const add=new Set();document.querySelectorAll('g.vec,g.txt').forEach(g=>{const c=corners(g);if(c.every(pt=>pt[0]>=x0&&pt[0]<=x1&&pt[1]>=y0&&pt[1]<=y1))add.add(g.id);});
    selected=ev.shiftKey?new Set([...selected,...add]):add;syncPanel();drawUI();};
  window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up);
}
// 画布平移
let pan=null;
stage.addEventListener('pointerdown',ev=>{if(spaceDown||ev.button===2){pan={x:ev.clientX,y:ev.clientY,l:stage.scrollLeft,t:stage.scrollTop};stage.classList.add('panning');ev.preventDefault();}});
window.addEventListener('pointermove',ev=>{if(pan){stage.scrollLeft=pan.l-(ev.clientX-pan.x);stage.scrollTop=pan.t-(ev.clientY-pan.y);}});
window.addEventListener('pointerup',()=>{pan=null;stage.classList.remove('panning');});
stage.addEventListener('contextmenu',ev=>ev.preventDefault());
svg.addEventListener('dblclick',ev=>{const g=targetG(ev);if(!g||!g.classList.contains('txt'))return;selectOnly(g.id);el('p_text').focus();el('p_text').select();});

// ---- 缩放 ----
function setZoom(z){zoom=Math.min(8,Math.max(.1,z));wrap.style.transform=`scale(${zoom})`;el('zoomlbl').textContent=Math.round(zoom*100)+'%';drawUI();}
stage.addEventListener('wheel',ev=>{if(ev.ctrlKey){ev.preventDefault();const r=stage.getBoundingClientRect();const mx=ev.clientX-r.left+stage.scrollLeft,my=ev.clientY-r.top+stage.scrollTop;const nz=Math.min(8,Math.max(.1,zoom*(ev.deltaY<0?1.1:.9)));stage.scrollLeft=mx*(nz/zoom)-(ev.clientX-r.left);stage.scrollTop=my*(nz/zoom)-(ev.clientY-r.top);setZoom(nz);}},{passive:false});
el('zin').onclick=()=>setZoom(zoom*1.2);el('zout').onclick=()=>setZoom(zoom/1.2);el('z100').onclick=()=>setZoom(1);
function zfit(){setZoom(1);const r=svg.getBoundingClientRect();const k=Math.min((stage.clientHeight-48)/(r.height/zoom),(stage.clientWidth-48)/(r.width/zoom));setZoom(k);}
el('zfit').onclick=zfit;window.addEventListener('load',zfit);

// ---- 键盘 ----
window.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;
  if(e.code==='Space'){spaceDown=true;stage.classList.add('pan');e.preventDefault();}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();return;}
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();return;}
  if((e.ctrlKey||e.ctrlKey)&&e.key.toLowerCase()==='d'){e.preventDefault();doDup();return;}
  if(e.key==='Delete'){selected.forEach(id=>{const g=byId(id);if(g){const en=st(id);en.hidden=!en.hidden;applyEl(g);}});drawUI();refresh();}
  if(sel0()&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){commit();const d=e.shiftKey?10:1;selected.forEach(id=>{const g=byId(id);if(!g)return;const en=st(id);if(e.key==='ArrowUp')en.dy-=d;if(e.key==='ArrowDown')en.dy+=d;if(e.key==='ArrowLeft')en.dx-=d;if(e.key==='ArrowRight')en.dx+=d;applyEl(g);});drawUI();refresh();syncPanel();e.preventDefault();}});
window.addEventListener('keyup',e=>{if(e.code==='Space'){spaceDown=false;stage.classList.remove('pan');}});
function sel0(){return selected.size?[...selected][0]:null;}

// ---- 面板 ----
function toHex6(c){if(!c||c==='none')return'#000000';if(c[0]==='#')return c.length===4?'#'+c[1]+c[1]+c[2]+c[2]+c[3]+c[3]:c;return'#000000';}
function syncPanel(){const id=sel0();const g=id?byId(id):null;
  if(!g){el('props').style.display='none';el('empty').style.display='block';return;}
  el('empty').style.display='none';el('props').style.display='block';
  const isTxt=g.classList.contains('txt'),e=st(id);
  el('ptype').textContent=(isTxt?'文字 ':'矢量 ')+id+(selected.size>1?` (+${selected.size-1})`:'');
  el('g_font').style.display=isTxt?'':'none';el('g_vec').style.display=isTxt?'none':'';
  const t=g.querySelector('text');
  el('p_text').style.display=isTxt?'':'none';el('p_text').value=e.text!==undefined?e.text:(t?t.textContent:'');
  el('p_dx').value=Math.round(e.dx||0);el('p_dy').value=Math.round(e.dy||0);
  el('p_sx').value=e.sx==null?1:e.sx;el('p_sxN').value=+(e.sx==null?1:e.sx).toFixed(2);
  el('p_sy').value=e.sy==null?1:e.sy;el('p_syN').value=+(e.sy==null?1:e.sy).toFixed(2);
  el('p_rot').value=e.rot||0;el('p_rotN').value=e.rot||0;
  el('p_op').value=e.op==null?1:e.op;el('p_opN').value=+(e.op==null?1:e.op).toFixed(2);
  if(isTxt&&t){el('p_font').value=e.fontFamily||t.getAttribute('font-family');el('p_size').value=e.fontSize||t.getAttribute('font-size');el('p_sizeN').value=+(e.fontSize||t.getAttribute('font-size')).toFixed(1);el('p_fill').value=toHex6(e.fill||t.getAttribute('fill'));el('p_bold').classList.toggle('on',!!e.bold);el('p_ital').classList.toggle('on',!!e.italic);}
  if(!isTxt){const p=g.querySelector('path');el('p_vfill').value=toHex6(e.fill||p.getAttribute('fill'));el('p_vstroke').value=toHex6(e.stroke||p.getAttribute('stroke'));el('p_vw').value=e.width||p.getAttribute('stroke-width');el('p_vwN').value=+(e.width||p.getAttribute('stroke-width')).toFixed(1);}
}
function eachSel(fn){if(!selected.size)return;commit();selected.forEach(id=>{const g=byId(id);if(g){fn(st(id));applyEl(g);}});drawUI();refresh();}
function bind(id,fn){el(id).addEventListener('input',()=>{if(!selected.size)return;eachSel(e=>fn(e,el(id)));if(el(id).id.startsWith('p_dx')||el(id).id.startsWith('p_dy'))syncPanel();});}
bind('p_dx',(e,x)=>e.dx=+x.value);bind('p_dy',(e,x)=>e.dy=+x.value);
bind('p_sx',(e,x)=>{e.sx=+x.value;el('p_sxN').value=x.value;});bind('p_sxN',(e,x)=>{e.sx=+x.value;el('p_sx').value=x.value;});
bind('p_sy',(e,x)=>{e.sy=+x.value;el('p_syN').value=x.value;});bind('p_syN',(e,x)=>{e.sy=+x.value;el('p_sy').value=x.value;});
bind('p_rot',(e,x)=>{e.rot=+x.value;el('p_rotN').value=x.value;});bind('p_rotN',(e,x)=>{e.rot=+x.value;el('p_rot').value=x.value;});
bind('p_op',(e,x)=>{e.op=+x.value;el('p_opN').value=x.value;});bind('p_opN',(e,x)=>{e.op=+x.value;el('p_op').value=x.value;});
bind('p_text',(e,x)=>e.text=x.value);bind('p_font',(e,x)=>e.fontFamily=x.value);
bind('p_size',(e,x)=>{e.fontSize=+x.value;el('p_sizeN').value=x.value;});bind('p_sizeN',(e,x)=>{e.fontSize=+x.value;el('p_size').value=x.value;});
bind('p_fill',(e,x)=>e.fill=x.value);bind('p_vfill',(e,x)=>e.fill=x.value);bind('p_vstroke',(e,x)=>e.stroke=x.value);
bind('p_vw',(e,x)=>{e.width=+x.value;el('p_vwN').value=x.value;});bind('p_vwN',(e,x)=>{e.width=+x.value;el('p_vw').value=x.value;});
el('p_vfill0').onclick=()=>eachSel(e=>e.fill='none');
el('p_bold').onclick=()=>{if(!selected.size)return;eachSel(e=>e.bold=!e.bold);el('p_bold').classList.toggle('on',!!st(sel0()).bold);};
el('p_ital').onclick=()=>{if(!selected.size)return;eachSel(e=>e.italic=!e.italic);el('p_ital').classList.toggle('on',!!st(sel0()).italic);};
el('p_reset').onclick=()=>{if(!selected.size)return;commit();selected.forEach(id=>{const g=byId(id);if(!g)return;delete state[id];g.removeAttribute('transform');g.style.opacity='';g.style.display='';const t=g.querySelector('text');if(t)t.textContent=g.dataset.content;});drawUI();refresh();syncPanel();};

// ---- 工具栏动作 ----
el('undo').onclick=undo;el('redo').onclick=redo;
el('hide').onclick=()=>{if(!selected.size)return;eachSel(e=>e.hidden=!e.hidden);};
el('dup').onclick=doDup;
function doDup(){const id=sel0();const g=byId(id);if(!g)return;commit();const nid='dup_'+(newN++);const c=g.cloneNode(true);c.id=nid;c.removeAttribute('transform');c.style.opacity='';c.style.display='';c.setAttribute('transform','translate(10 10)');(g.parentNode).appendChild(c);
  const e={...st(id),dx:(st(id).dx||0)+10,dy:(st(id).dy||0)+10};state[nid]=e;applyEl(c);selectOnly(nid);}
el('addtxt').onclick=()=>{addMode=!addMode;el('addtxt').classList.toggle('act',addMode);stage.classList.toggle('addtxt',addMode);if(addMode)el('hint').textContent='点击画布放置文字（再点“＋文字”退出）';else el('hint').textContent='点选 · 拖拽移动 · 拖角缩放 · 拖顶旋转 · Shift加选 · 空白框选 · Ctrl+滚轮缩放 · 空格/右键拖动平移 · Delete隐藏 · 双击文字改内容';};
svg.addEventListener('click',ev=>{if(!addMode)return;const p=svgPt(ev);const txt=prompt('文字内容:','标注');if(txt===null){return;}
  const nid='txt_new'+(newN++);const g=document.createElementNS(NS,'g');g.setAttribute('class','txt');g.id=nid;g.dataset.bbox=`${p.x} ${p.y} ${p.x} ${p.y}`;g.dataset.content=txt;
  const t=document.createElementNS(NS,'text');t.setAttribute('x',p.x);t.setAttribute('y',p.y);t.setAttribute('font-size','12');t.setAttribute('fill','#000000');t.textContent=txt;g.appendChild(t);byId('txt-layer').appendChild(g);
  state[nid]={dx:0,dy:0,sx:1,sy:1,rot:0,op:1};addMode=false;el('addtxt').classList.remove('act');stage.classList.remove('addtxt');selectOnly(nid);refresh();});

// ---- 文字列表 ----
function buildList(){const box=el('txtlist');const gs=[...document.querySelectorAll('g.txt')];box.innerHTML='';
  gs.forEach(g=>{const row=document.createElement('div');row.className='li'+(selected.has(g.id)?' on':'');
    const eye=document.createElement('span');eye.className='eye';eye.textContent=(st(g.id).hidden?'✖':'👁');eye.title='显隐';
    eye.onclick=e=>{e.stopPropagation();commit();const en=st(g.id);en.hidden=!en.hidden;applyEl(g);buildList();refresh();};
    const nm=document.createElement('span');nm.className='nm';nm.textContent=g.dataset.content||g.id;
    row.onclick=()=>selectOnly(g.id);row.appendChild(eye);row.appendChild(nm);box.appendChild(row);});}

// ---- 导入/导出 ----
el('reset').onclick=()=>{commit();for(const id in state){const g=byId(id);if(g){g.removeAttribute('transform');g.style.opacity='';g.style.display='';const t=g.querySelector('text');if(t)t.textContent=g.dataset.content;}}for(const k in state)delete state[k];selected=new Set();drawUI();refresh();syncPanel();};
function collect(){const out={};for(const id in state){const g=byId(id);if(!g)continue;const o={...state[id]};o._bbox=g.dataset.bbox;if(g.classList.contains('txt'))o._content=g.dataset.content;out[id]=o;}return out;}
el('exp').onclick=()=>{const b=new Blob([JSON.stringify(collect(),null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='overlay_elements.json';a.click();};
el('expsvg').onclick=()=>{const c=svg.cloneNode(true);const u=c.querySelector('#ui');u&&u.remove();const b=new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n'+c.outerHTML],{type:'image/svg+xml'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='figure_edited.svg';a.click();};
el('exppng').onclick=()=>{const c=svg.cloneNode(true);const u=c.querySelector('#ui');u&&u.remove();const vb=c.getAttribute('viewBox').split(' ').map(Number);c.setAttribute('width',vb[2]);c.setAttribute('height',vb[3]);
  const str=new XMLSerializer().serializeToString(c);const url=URL.createObjectURL(new Blob([str],{type:'image/svg+xml'}));const img=new Image();
  img.onload=()=>{const S=2,cv=document.createElement('canvas');cv.width=vb[2]*S;cv.height=vb[3]*S;const ctx=cv.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,cv.width,cv.height);ctx.drawImage(img,0,0,cv.width,cv.height);cv.toBlob(bl=>{const a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download='figure_edited.png';a.click();});URL.revokeObjectURL(url);};img.src=url;};
el('imp').onclick=()=>el('file').click();
el('file').onchange=async ev=>{const f=ev.target.files[0];if(!f)return;commit();const data=JSON.parse(await f.text());let hit=0;
  for(const id in data){let g=byId(id);const e=data[id];
    if(!g){if(e._content!==undefined)g=[...document.querySelectorAll('g.txt')].find(x=>x.dataset.content===e._content);
      else if(e._bbox){const[ax,ay]=e._bbox.split(' ').map(Number);g=[...document.querySelectorAll('g.vec')].map(x=>{const[bx,by]=x.dataset.bbox.split(' ').map(Number);return{d:Math.hypot(bx-ax,by-ay),x};}).sort((p,q)=>p.d-q.d)[0]?.x;}}
    if(g){state[g.id]=Object.assign({dx:0,dy:0,sx:1,sy:1,rot:0,op:1},e);if(e.scale!==undefined&&e.sx===undefined){state[g.id].sx=e.scale;state[g.id].sy=e.scale;}applyEl(g);hit++;}}
  alert('已套用 '+hit+' 个元素');renderAll();};
buildList();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf"); ap.add_argument("--svg", default="figure.svg"); ap.add_argument("--html", default="editor.html")
    a = ap.parse_args()
    svg, n_vec, n_txt = build_svg(a.pdf)
    open(a.svg, "w", encoding="utf-8").write(svg)
    open(a.html, "w", encoding="utf-8").write(EDITOR_TEMPLATE.replace("__SVG__", svg))
    print(f"{a.pdf} -> {a.svg} ({len(svg)} bytes) + {a.html}")
    print(f"可寻址元素: 矢量 {n_vec} (g.vec) + 文字 {n_txt} (g.txt, 真<text>)")


if __name__ == "__main__":
    main()
