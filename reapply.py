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
    for gid, e in edits.items():
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
