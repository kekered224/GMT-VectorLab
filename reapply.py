#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reapply.py —— 元素级 overlay 的"重套用"器 (编辑器 JS 逻辑的 Python 镜像, v2)

把 editor.html 导出的 overlay_elements.json 重新贴到一张(可能结构不同的)SVG 上:
  - 文字元素: 优先按 _content 内容匹配 (跨渲染最稳), 找不到再退回 id
  - 矢量元素: 优先按 id (同渲染精确), 否则按 _bbox 就近匹配
支持属性: dx,dy(平移) / scale(缩放) / rot(旋转) / op(透明度) / hidden(隐藏) /
          text(文字内容) / fontFamily,fontSize,bold,italic,fill(文字样式) /
          fill,stroke,width(矢量样式)

用法:
    python reapply.py newdata.svg overlay_elements.json --png moved_newdata.png
"""
import re, json, html, argparse
import fitz

G_OPEN = re.compile(r'<g class="(vec|txt)" id="([^"]+)"([^>]*)>')


def parse_elements(svg_text):
    lines = svg_text.split("\n")
    els = {}
    for i, ln in enumerate(lines):
        m = G_OPEN.search(ln)
        if not m:
            continue
        cls, gid, rest = m.groups()
        bbox = re.search(r'data-bbox="([^"]+)"', rest)
        content = re.search(r'data-content="([^"]*)"', rest)
        els[gid] = {"cls": cls, "line": i,
                    "bbox": bbox.group(1) if bbox else "",
                    "content": content.group(1) if content else None}
    return lines, els


def match_target(gid, e, lines, els):
    # 文字元素: 内容优先 (跨渲染最稳, id 会串号), 再退回 id
    want = e.get("_content")
    if want is not None:
        for g, info in els.items():
            if info["cls"] == "txt" and info["content"] == want:
                return g
    # 矢量/兜底: 先按 id (同渲染精确命中)
    if gid in els:
        return gid
    # 最后按 _bbox 就近 (矢量)
    if e.get("_bbox"):
        ax, ay = map(float, e["_bbox"].split()[:2])
        best, bd = None, 1e18
        for g, info in els.items():
            if info["cls"] != "vec" or not info["bbox"]:
                continue
            bx, by = map(float, info["bbox"].split()[:2])
            d = (bx - ax) ** 2 + (by - ay) ** 2
            if d < bd:
                bd, best = d, g
        if best is not None and bd ** 0.5 < 8:
            return best
    return None


def set_attr(tag, name, val):
    val = str(val)
    p1 = r'\b' + re.escape(name) + r'="[^"]*"'
    p2 = r'\b' + re.escape(name) + r'=[^\s">]+'
    if re.search(p1, tag):
        return re.sub(p1, f'{name}="{val}"', tag, count=1)
    if re.search(p2, tag):
        return re.sub(p2, f'{name}="{val}"', tag, count=1)
    if tag.endswith("/>"):
        return tag[:-2] + f' {name}="{val}"' + "/>"
    return tag[:-1] + f' {name}="{val}"' + ">"


SHAPE_DEF = {
    "point": ("#e4572e", "#e4572e", 0),
    "line": ("none", "#1f6feb", 1.6),
    "poly": ("#cfe3f7", "#1f6feb", 1.4),
    "rect": ("#cfe3f7", "#1f6feb", 1.4),
    "roundrect": ("#cfe3f7", "#1f6feb", 1.4),
    "ellipse": ("#cfe3f7", "#1f6feb", 1.4),
    "triangle": ("#cfe3f7", "#1f6feb", 1.4),
    "diamond": ("#cfe3f7", "#1f6feb", 1.4),
    "pentagon": ("#cfe3f7", "#1f6feb", 1.4),
    "hexagon": ("#cfe3f7", "#1f6feb", 1.4),
    "star": ("#fbd9a3", "#c27c0e", 1.4),
    "arrow": ("#cfe3f7", "#1f6feb", 1.4),
    "doublearrow": ("#cfe3f7", "#1f6feb", 1.4),
    "parallelogram": ("#cfe3f7", "#1f6feb", 1.4),
}
BOX_SHAPES = {"rect", "roundrect", "ellipse", "triangle", "diamond",
              "pentagon", "hexagon", "star", "arrow", "doublearrow", "parallelogram"}


def _circle_d(cx, cy, r):
    return _ellipse_d(cx, cy, r, r)


def _ellipse_d(cx, cy, rx, ry):
    kx, ky = rx * 0.5523, ry * 0.5523
    return (f"M{cx-rx:.2f} {cy:.2f}C{cx-rx:.2f} {cy-ky:.2f} {cx-kx:.2f} {cy-ry:.2f} {cx:.2f} {cy-ry:.2f}"
            f"C{cx+kx:.2f} {cy-ry:.2f} {cx+rx:.2f} {cy-ky:.2f} {cx+rx:.2f} {cy:.2f}"
            f"C{cx+rx:.2f} {cy+ky:.2f} {cx+kx:.2f} {cy+ry:.2f} {cx:.2f} {cy+ry:.2f}"
            f"C{cx-kx:.2f} {cy+ry:.2f} {cx-rx:.2f} {cy+ky:.2f} {cx-rx:.2f} {cy:.2f}Z")


def _path_d(pts, close=False):
    d = "M%.2f %.2f" % pts[0]
    for x, y in pts[1:]:
        d += "L%.2f %.2f" % (x, y)
    return d + ("Z" if close else "")


def _ring(n, cx, cy, rx, ry, inner=1.0, start_deg=-90):
    import math
    st = math.radians(start_deg)
    out = []
    for i in range(n * 2):
        a = st + i * math.pi / n
        k = inner if (inner and i % 2) else 1.0
        out.append((cx + math.cos(a) * rx * k, cy + math.sin(a) * ry * k))
    return out


def _box_d(kind, x0, y0, x1, y1):
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if kind == "rect":
        return _path_d([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True)
    if kind == "ellipse":
        return _ellipse_d(cx, cy, abs(w) / 2, abs(h) / 2)
    if kind == "roundrect":
        r = min(abs(w), abs(h)) * 0.22
        return (f"M{x0+r:.2f} {y0:.2f}L{x1-r:.2f} {y0:.2f}Q{x1:.2f} {y0:.2f} {x1:.2f} {y0+r:.2f}"
                f"L{x1:.2f} {y1-r:.2f}Q{x1:.2f} {y1:.2f} {x1-r:.2f} {y1:.2f}"
                f"L{x0+r:.2f} {y1:.2f}Q{x0:.2f} {y1:.2f} {x0:.2f} {y1-r:.2f}"
                f"L{x0:.2f} {y0+r:.2f}Q{x0:.2f} {y0:.2f} {x0+r:.2f} {y0:.2f}Z")
    if kind == "triangle":
        return _path_d([(cx, y0), (x1, y1), (x0, y1)], True)
    if kind == "diamond":
        return _path_d([(cx, y0), (x1, cy), (cx, y1), (x0, cy)], True)
    if kind == "pentagon":
        return _path_d(_ring(5, cx, cy, abs(w) / 2, abs(h) / 2), True)
    if kind == "hexagon":
        return _path_d(_ring(6, cx, cy, abs(w) / 2, abs(h) / 2), True)
    if kind == "star":
        return _path_d(_ring(5, cx, cy, abs(w) / 2, abs(h) / 2, 0.38), True)
    if kind == "parallelogram":
        o = abs(w) * 0.22
        return _path_d([(x0 + o, y0), (x1, y0), (x1 - o, y1), (x0, y1)], True)
    if kind in ("arrow", "doublearrow"):
        sh, hw = abs(h) * 0.22, abs(w) * 0.36
        if kind == "arrow":
            return _path_d([(x0, cy - sh), (x1 - hw, cy - sh), (x1 - hw, y0), (x1, cy),
                            (x1 - hw, y1), (x1 - hw, cy + sh), (x0, cy + sh)], True)
        return _path_d([(x0, cy), (x0 + hw, y0), (x0 + hw, cy - sh), (x1 - hw, cy - sh),
                        (x1 - hw, y0), (x1, cy), (x1 - hw, y1), (x1 - hw, cy + sh),
                        (x0 + hw, cy + sh), (x0 + hw, y1)], True)
    return _path_d([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True)


def shape_d(e):
    """编辑器里新增的点/线/预设形状 -> SVG path d (坐标与 PDF 点一致)。"""
    pts = [(float(p[0]), float(p[1])) for p in (e.get("_pts") or []) if len(p) >= 2]
    kind = e.get("_shape") or "line"
    if not pts:
        return ""
    if kind == "point" or len(pts) == 1:
        return _circle_d(pts[0][0], pts[0][1], float(e.get("_r") or 3.5))
    if kind in BOX_SHAPES:
        x0, x1 = sorted((pts[0][0], pts[1][0]))
        y0, y1 = sorted((pts[0][1], pts[1][1]))
        if x1 - x0 < 1 or y1 - y0 < 1:
            x1, y1 = x0 + 60, y0 + 40
        return _box_d(kind, x0, y0, x1, y1)
    return _path_d(pts, kind == "poly")


def shape_bbox(e):
    pts = [(float(p[0]), float(p[1])) for p in (e.get("_pts") or []) if len(p) >= 2]
    if not pts:
        return None
    kind = e.get("_shape") or "line"
    r = float(e.get("_r") or 3.5) if kind == "point" else 0.0
    if kind == "point" or len(pts) == 1:
        x, y = pts[0]
        return x - r, y - r, x + r, y + r
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    pad = 1.2
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def new_shape_line(gid, e):
    """把一条 _shape 记录变成 <g class="vec"><path/></g> 的一行, 并套用样式/变换。"""
    d = shape_d(e)
    bb = shape_bbox(e)
    if not d or bb is None:
        return None
    kind = e.get("_shape") or "line"
    fill, stroke, w = SHAPE_DEF.get(kind, SHAPE_DEF["line"])
    line = ('<g class="vec" id="%s" data-bbox="%.2f %.2f %.2f %.2f">'
            '<path d="%s" fill="%s" stroke="%s" stroke-width="%s"/></g>'
            % (html.escape(gid, quote=True), bb[0], bb[1], bb[2], bb[3], d, fill, stroke, w))
    return apply_one(line, e, "vec")


def tf(e, cx, cy):
    dx, dy = e.get("dx", 0), e.get("dy", 0)
    if "scale" in e and "sx" not in e:
        sx = sy = e["scale"]
    else:
        sx = e.get("sx", 1)
        sy = e.get("sy", 1)
    r = e.get("rot", 0)
    return (f"translate({dx} {dy}) translate({cx} {cy}) rotate({r}) "
            f"scale({sx} {sy}) translate({-cx} {-cy})")


def build_style(e):
    sty = []
    if e.get("op") not in (None, 1):
        sty.append(f"opacity:{e['op']}")
    if e.get("hidden"):
        sty.append("display:none")
    return ";".join(sty)


def apply_one(line, e, cls):
    m = re.match(r'(<g [^>]*>)([\s\S]*)', line)
    gtag, rest = m.group(1), m.group(2)
    b = list(map(float, re.search(r'data-bbox="([^"]+)"', gtag).group(1).split()))
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    gtag = set_attr(gtag, "transform", tf(e, cx, cy))
    st = build_style(e)
    if st:
        gtag = set_attr(gtag, "style", st)
    if cls == "txt":
        mt = re.search(r'(<text\b[^>]*>)([\s\S]*?)(</text>)', rest)
        if mt:
            ot, inner, ct = mt.group(1), mt.group(2), mt.group(3)
            for k, a in [("fontFamily", "font-family"), ("fontSize", "font-size"), ("fill", "fill")]:
                if e.get(k) is not None:
                    ot = set_attr(ot, a, e[k])
            if e.get("bold") is not None:
                ot = set_attr(ot, "font-weight", "bold" if e["bold"] else "normal")
            if e.get("italic") is not None:
                ot = set_attr(ot, "font-style", "italic" if e["italic"] else "normal")
            if e.get("text") is not None:
                inner = html.escape(str(e["text"]))
            rest = rest[:mt.start()] + ot + inner + ct + rest[mt.end():]
    else:
        mm = re.search(r'<path[^>]*/?>', rest)
        if mm:
            ni = mm.group(0)
            if e.get("fill") is not None:
                ni = set_attr(ni, "fill", e["fill"])
            if e.get("stroke") is not None:
                ni = set_attr(ni, "stroke", e["stroke"])
            if e.get("width") is not None:
                ni = set_attr(ni, "stroke-width", e["width"])
            rest = rest.replace(mm.group(0), ni)
    return gtag + rest


def apply_edits(svg_text, edits):
    lines, els = parse_elements(svg_text)
    report = []
    inserts = []
    for gid, e in edits.items():
        # 编辑器里新增的点/线/面: 原图里不存在, 直接插到 </svg> 前 (最上层);
        # 同一 id 已存在 (对已烘焙的 SVG 再套一次) 则退回普通改属性。
        if e.get("_shape") and e.get("_pts"):
            if gid in els:
                info = els[gid]
                lines[info["line"]] = apply_one(lines[info["line"]], e, info["cls"])
                report.append((gid, "-> " + gid, "形状刷新"))
            else:
                nid, k = gid, 2
                while nid in els or any(nid == it[0] for it in inserts):
                    nid, k = "%s_%d" % (gid, k), k + 1
                nl = new_shape_line(nid, e)
                if nl is None:
                    report.append((gid, "MISS", "形状为空"))
                else:
                    inserts.append((nid, nl))
                    report.append((gid, "insert " + nid,
                                   "%s %d 点" % (e.get("_shape"), len(e.get("_pts")))))
            continue
        # 画布上复制出来的原 GMT 元素: 原图里没有这个 id, 用编辑器存下的克隆几何插入一份。
        if e.get("_clone"):
            if gid in els:
                info = els[gid]
                lines[info["line"]] = apply_one(lines[info["line"]], e, info["cls"])
                report.append((gid, "-> " + gid, "副本刷新"))
            else:
                nid, k = gid, 2
                while nid in els or any(nid == it[0] for it in inserts):
                    nid, k = "%s_%d" % (gid, k), k + 1
                raw = re.sub(r'\bid="[^"]*"', lambda _m: 'id="%s"' % nid, e["_clone"], count=1)
                cls = "txt" if 'class="txt"' in raw else "vec"
                try:
                    nl = apply_one(raw, e, cls)
                except Exception as ex:
                    report.append((gid, "MISS", "副本无效: %s" % ex))
                else:
                    inserts.append((nid, nl))
                    report.append((gid, "insert " + nid, "复制" + ("文字" if cls == "txt" else "矢量")))
            continue
        tgt = match_target(gid, e, lines, els)
        if tgt is None:
            report.append((gid, "MISS", e.get("_content") or e.get("_bbox") or ""))
            continue
        info = els[tgt]
        lines[info["line"]] = apply_one(lines[info["line"]], e, info["cls"])
        bits = []
        if e.get("dx") or e.get("dy"):
            bits.append(f"({e.get('dx',0)},{e.get('dy',0)})")
        if e.get("scale") not in (None, 1):
            bits.append(f"x{e['scale']}")
        if e.get("rot"):
            bits.append(f"rot{e['rot']}")
        if e.get("text") is not None:
            bits.append(f"text={e['text']!r}")
        if e.get("fontSize") is not None:
            bits.append(f"size={e['fontSize']}")
        if e.get("fontFamily") is not None:
            bits.append(f"font={e['fontFamily'].split(',')[0]}")
        if e.get("fill") is not None:
            bits.append(f"fill={e['fill']}")
        if e.get("hidden"):
            bits.append("HIDDEN")
        report.append((gid, "-> " + tgt, " ".join(bits)))
    if inserts:
        idx = next((i for i in range(len(lines) - 1, -1, -1) if "</svg>" in lines[i]), len(lines))
        lines[idx:idx] = [ln for _nid, ln in inserts]
    return "\n".join(lines), report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("svg"); ap.add_argument("edits"); ap.add_argument("--png"); ap.add_argument("--out")
    a = ap.parse_args()
    svg = open(a.svg, encoding="utf-8").read()
    edits = json.load(open(a.edits, encoding="utf-8"))
    new_svg, rep = apply_edits(svg, edits)
    out = a.out or a.svg.replace(".svg", "_edited.svg")
    open(out, "w", encoding="utf-8").write(new_svg)
    print(f"{a.svg} + {a.edits} -> {out}")
    print("套用报告:")
    for gid, tgt, detail in rep:
        print(f"  {gid:12} {tgt:12} {detail}")
    if a.png:
        d = fitz.open(out); d[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(a.png)
        print(f"渲染 -> {a.png}")


if __name__ == "__main__":
    main()
