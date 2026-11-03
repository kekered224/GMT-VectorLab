/* canvaskit.js —— 画布式元素编辑器 (自包含, 挂载到 ui.html 的三栏宿主, 明亮主题)
 *
 * 与 svgify.EDITOR_TEMPLATE 逻辑一致 (点选/拖拽/缩放/旋转/改字/样式/显隐/撤销重做/
 * 多选框选/平移/加文字/复制/导入套用), 但:
 *   - 全部封装在 init() 闭包里, 元素 id 前缀 cv_ 且用 document.getElementById 唯一定位,
 *     不与命令级 ui.html 全局冲突;
 *   - 分别挂载到 stage / props / list 三个宿主 (对应中栏画布、右栏属性、左栏文字列表);
 *   - 只注入 SVG, 不自己起页面。返回句柄 {collect, applyOverlay, resetElements, countDirty, destroy}。
 *
 * 用法: const handle = GMTCanvas.init({stage, props, list, svg, onChange}); */
window.GMTCanvas = (function () {
  const NS = 'http://www.w3.org/2000/svg';

  const STYLE = `
  .cv-main{display:grid;grid-template-rows:auto 1fr;height:100%;min-height:0;background:var(--bg)}
  .cv-bar{display:flex;align-items:center;gap:6px;padding:8px 12px;background:var(--surface);border-bottom:1px solid var(--border);flex-wrap:wrap}
  .cv-bar .cb{display:inline-flex;align-items:center;gap:5px;height:30px;padding:0 10px;border-radius:8px;border:1px solid var(--border-2);
    background:var(--surface);color:var(--ink);font-size:12.5px;font-weight:550;cursor:pointer;transition:.14s var(--ease)}
  .cb:hover{background:var(--surface-2)}.cb:active{transform:translateY(1px)}
  .cb.act{background:var(--accent);border-color:var(--accent);color:#fff}
  .cb.danger{color:var(--err);border-color:#f0c4c4}.cb.danger:hover{background:var(--err-soft)}
  .cb svg{width:14px;height:14px}
  .cv-sep{width:1px;height:22px;background:var(--border)}
  .cv-zoom{min-width:52px;text-align:center;font-variant-numeric:tabular-nums;color:var(--ink-2);font-size:12.5px;font-weight:600}
  .cv-hint{font-size:11px;color:var(--ink-3);margin-left:8px;line-height:1.4}
  .cv-cnt{margin-left:auto;font-size:12px;color:var(--ink-2)}
  .cv-cnt b{color:var(--accent-h)}
  .cv-stage{overflow:auto;background:var(--bg);position:relative;min-height:0}
  .cv-stage.pan{cursor:grab}.cv-stage.panning{cursor:grabbing}.cv-stage.addtxt{cursor:text}
  .cv-wrap{transform-origin:0 0;padding:22px;display:inline-block}
  .cv-wrap>svg{background:#fff;box-shadow:var(--sh-2);border-radius:2px}
  g.vec:hover path,g.txt:hover text{filter:drop-shadow(0 0 1.5px #ffb020)}
  .cv-ui-line{fill:none;stroke:var(--accent);stroke-width:1;vector-effect:non-scaling-stroke;pointer-events:none}
  .cv-ui-h{fill:#fff;stroke:var(--accent);stroke-width:1.4}
  .cv-ui-rot{fill:var(--accent);stroke:#fff;stroke-width:1.4;cursor:grab}
  /* 属性面板 */
  .cv-empty{color:var(--ink-3);font-size:12px;line-height:1.7;padding:8px 2px}
  .cv-props{padding:2px}
  .cv-ptype{font-size:12px;font-weight:600;color:var(--accent-h);background:var(--accent-soft);
    display:inline-block;padding:3px 9px;border-radius:7px;margin-bottom:10px;font-family:var(--mono);word-break:break-all}
  .cv-grp{border-top:1px solid var(--border);margin-top:12px;padding-top:10px}
  .cv-grp .t{font-size:11px;font-weight:650;letter-spacing:.5px;text-transform:uppercase;color:var(--ink-3);margin-bottom:8px}
  .cv-row{margin:9px 0;display:flex;align-items:center;gap:8px}
  .cv-row>label{width:44px;font-size:12px;color:var(--ink-2);font-weight:550;flex:none}
  .cv-num{display:flex;align-items:center;background:var(--surface);border:1px solid var(--border-2);border-radius:8px;height:30px;overflow:hidden;flex:none;width:82px}
  .cv-num:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-ring)}
  .cv-num input{border:none;outline:none;width:100%;padding:0 8px;font-size:13px;font-variant-numeric:tabular-nums;background:transparent;color:var(--ink)}
  input[type=range].cv-r{-webkit-appearance:none;appearance:none;height:6px;border-radius:99px;flex:1;min-width:50px;background:var(--surface-3);outline:none;cursor:pointer}
  input[type=range].cv-r::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;background:#fff;border:1px solid var(--border-2);box-shadow:var(--sh-1);cursor:grab}
  input[type=range].cv-r:active::-webkit-slider-thumb{box-shadow:0 0 0 4px var(--accent-ring)}
  input[type=color].cv-c{width:34px;height:30px;border:1px solid var(--border-2);border-radius:8px;background:none;padding:1px;cursor:pointer}
  .cv-row select,.cv-row input[type=text]{flex:1;min-width:0;height:30px;background:var(--surface);color:var(--ink);border:1px solid var(--border-2);border-radius:8px;padding:0 9px;font-size:13px;outline:none}
  .cv-row select:focus,.cv-row input[type=text]:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-ring)}
  .cv-tgl{display:inline-flex;gap:6px}.cv-tgl button{width:30px;height:30px;border-radius:8px;border:1px solid var(--border-2);background:var(--surface);cursor:pointer;font-weight:700}
  .cv-tgl button.on{background:var(--accent);border-color:var(--accent);color:#fff}
  .cv-btnrow{display:flex;gap:8px;margin-top:12px}
  .cv-btnrow .cb{flex:1;justify-content:center}
  /* 文字列表 */
  .cv-list .li{display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:12.5px;border-bottom:1px solid var(--surface-2)}
  .cv-list .li:hover{background:var(--surface-2)}
  .cv-list .li.on{background:var(--accent-soft)}
  .cv-list .li .eye{opacity:.7;font-size:12px;width:16px;text-align:center}
  .cv-list .li .eye:hover{opacity:1}
  .cv-list .li .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:var(--mono)}
  .cv-list .li .ix{color:var(--ink-3);font-size:11px}
  `;

  const ICON = {
    undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>',
    redo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13"/></svg>',
    txt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V5h16v2"/><path d="M12 5v14"/><path d="M9 19h6"/></svg>',
    dup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    hide: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3 8 10 8a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/></svg>',
    reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
  };

  function barHTML() {
    return `
    <div class="cv-main">
      <div class="cv-bar">
        <button class="cb" id="cv_undo" title="Ctrl+Z">${ICON.undo}撤销</button>
        <button class="cb" id="cv_redo" title="Ctrl+Shift+Z / Ctrl+Y">${ICON.redo}重做</button>
        <span class="cv-sep"></span>
        <button class="cb" id="cv_addtxt" title="点画布放一个文字">${ICON.txt}＋文字</button>
        <button class="cb" id="cv_dup" title="Ctrl+D">${ICON.dup}复制</button>
        <button class="cb" id="cv_hide">${ICON.hide}显隐</button>
        <span class="cv-sep"></span>
        <button class="cb danger" id="cv_reset">${ICON.reset}全部重置</button>
        <span class="cv-sep"></span>
        <button class="cb" id="cv_zout">－</button><span class="cv-zoom" id="cv_zoomlbl">100%</span><button class="cb" id="cv_zin">＋</button>
        <button class="cb" id="cv_zfit">适应</button><button class="cb" id="cv_z100">100%</button>
        <span class="cv-hint">点选 · 拖拽移动 · 拖角等比缩放 · 拖边单轴拉伸 · Shift+角自由 · 拖顶旋转 · Shift加选 · 空白框选 · Ctrl+滚轮缩放 · 空格/右键平移 · Delete隐藏 · 双击文字改内容</span>
        <span class="cv-cnt">元素改动 <b id="cv_cnt">0</b></span>
      </div>
      <div class="cv-stage" id="cv_stage"><div class="cv-wrap" id="cv_wrap">@@SVG@@</div></div>
    </div>`;
  }

  function panelHTML() {
    return `
    <div class="cv-empty" id="cv_empty">未选中元素。<br>在中间画布点击文字 / 线条 / 色块，直接拖拽移动、拖角缩放、拖顶旋转；或双击文字改内容。</div>
    <div class="cv-props" id="cv_props" style="display:none">
      <div class="cv-ptype" id="cv_ptype">元素</div>
      <div class="cv-row" id="cv_g_text"><label>内容</label><input type="text" id="cv_p_text"></div>
      <div class="cv-grp"><div class="t">位置 / 变换</div>
        <div class="cv-row"><label>X</label><div class="cv-num"><input type="number" id="cv_p_dx" step="1"></div><label style="width:24px">Y</label><div class="cv-num"><input type="number" id="cv_p_dy" step="1"></div></div>
        <div class="cv-row"><label>宽缩</label><input type="range" class="cv-r" id="cv_p_sx" min="0.1" max="8" step="0.02"><div class="cv-num"><input type="number" id="cv_p_sxN" step="0.05"></div></div>
        <div class="cv-row"><label>高缩</label><input type="range" class="cv-r" id="cv_p_sy" min="0.1" max="8" step="0.02"><div class="cv-num"><input type="number" id="cv_p_syN" step="0.05"></div></div>
        <div class="cv-row"><label>旋转</label><input type="range" class="cv-r" id="cv_p_rot" min="-180" max="180" step="1"><div class="cv-num"><input type="number" id="cv_p_rotN" step="1"></div></div>
        <div class="cv-row"><label>透明</label><input type="range" class="cv-r" id="cv_p_op" min="0" max="1" step="0.05"><div class="cv-num"><input type="number" id="cv_p_opN" step="0.05" min="0" max="1"></div></div>
      </div>
      <div class="cv-grp" id="cv_g_font"><div class="t">文字样式</div>
        <div class="cv-row"><label>字体</label><select id="cv_p_font">
          <option value="Helvetica,Arial,sans-serif">Helvetica/Arial</option><option value="Arial">Arial</option>
          <option value="Times New Roman,serif">Times/衬线</option><option value="Georgia,serif">Georgia</option>
          <option value="Courier New,monospace">Courier/等宽</option>
          <option value="Microsoft YaHei,微软雅黑,sans-serif">微软雅黑(中)</option><option value="SimHei,黑体,sans-serif">黑体(中)</option>
          <option value="SimSun,宋体,serif">宋体(中)</option><option value="KaiTi,楷体,serif">楷体(中)</option></select></div>
        <div class="cv-row"><label>字号</label><input type="range" class="cv-r" id="cv_p_size" min="4" max="96" step="0.5"><div class="cv-num"><input type="number" id="cv_p_sizeN" step="0.5"></div></div>
        <div class="cv-row"><label>颜色</label><input type="color" class="cv-c" id="cv_p_fill"><div class="cv-tgl"><button id="cv_p_bold">B</button><button id="cv_p_ital">I</button></div></div>
      </div>
      <div class="cv-grp" id="cv_g_vec"><div class="t">矢量样式</div>
        <div class="cv-row"><label>填充</label><input type="color" class="cv-c" id="cv_p_vfill"><button class="cb" id="cv_p_vfill0" style="height:30px;padding:0 10px">无</button></div>
        <div class="cv-row"><label>描边</label><input type="color" class="cv-c" id="cv_p_vstroke"></div>
        <div class="cv-row"><label>线宽</label><input type="range" class="cv-r" id="cv_p_vw" min="0" max="10" step="0.1"><div class="cv-num"><input type="number" id="cv_p_vwN" step="0.1"></div></div>
      </div>
      <div class="cv-btnrow"><button class="cb" id="cv_p_reset">${ICON.reset}复位此元素</button></div>
    </div>`;
  }

  function init(opts) {
    const stageHost = opts.stage;      // 中栏: 放画布工具条 + 可滚动画布
    const propsHost = opts.props;      // 右栏: 属性面板
    const listHost = opts.list;        // 左栏: 文字元素列表
    const cb = opts;
    const svgSrc = opts.svg || '';

    // 注入样式(一次) + 三段 HTML
    if (!document.getElementById('cv-style')) {
      const sty = document.createElement('style'); sty.id = 'cv-style'; sty.textContent = STYLE;
      document.head.appendChild(sty);
    }
    stageHost.innerHTML = barHTML().split('@@SVG@@').join(svgSrc);
    propsHost.innerHTML = panelHTML();
    if (listHost) listHost.innerHTML = '';

    const stage = document.getElementById('cv_stage');
    const wrap = document.getElementById('cv_wrap');
    const svg = wrap.querySelector('svg');
    if (!svg) return { collect: () => ({}), applyOverlay: () => 0, resetElements: () => {}, countDirty: () => 0, destroy: () => {} };

    const state = {};
    let selected = new Set(), zoom = 1, spaceDown = false, addMode = false, newN = 0;
    const hist = [], future = [];

    const el = id => document.getElementById(id);
    const gById = id => document.getElementById(id);
    function bboxOf(g) { return (g.dataset.bbox || '0 0 0 0').split(' ').map(Number); }
    function st(id) { return state[id] || (state[id] = { dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, op: 1 }); }
    function dirty(e) {
      return e && (e.dx || e.dy || (e.sx !== undefined && e.sx !== 1) || (e.sy !== undefined && e.sy !== 1) ||
        e.rot || (e.op !== undefined && e.op !== 1) || e.text !== undefined || e.fontFamily !== undefined ||
        e.fontSize !== undefined || e.bold !== undefined || e.italic !== undefined || e.fill !== undefined ||
        e.stroke !== undefined || e.width !== undefined || e.hidden);
    }
    function countDirty() { return Object.keys(state).filter(id => dirty(state[id])).length; }
    function notify() { el('cv_cnt').textContent = countDirty(); if (cb.onChange) cb.onChange(countDirty()); }
    function refresh() { notify(); buildList(); }
    function rotV(x, y, d) { const r = d * Math.PI / 180, c = Math.cos(r), s = Math.sin(r); return [x * c - y * s, x * s + y * c]; }
    function toRoot(g, px, py) {
      // 与 applyEl 的变换严格一致: 先绕中心缩放、再旋转、最后平移 (root = d + c + R(S(p-c)))。
      // 旧版先旋转后缩放, sx≠sy 且 rot≠0 时算出的角点与实际渲染错位, 手柄跟着飘。
      const e = st(g.id), b = bboxOf(g), cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
      const sx = e.sx == null ? 1 : e.sx, sy = e.sy == null ? 1 : e.sy;
      const [rx, ry] = rotV((px - cx) * sx, (py - cy) * sy, e.rot || 0);
      return [cx + rx + (e.dx || 0), cy + ry + (e.dy || 0)];
    }
    function corners(g) { const b = bboxOf(g); return [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]].map(c => toRoot(g, c[0], c[1])); }

    function applyEl(g) {
      const e = st(g.id), b = bboxOf(g), cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
      const sx = e.sx == null ? 1 : e.sx, sy = e.sy == null ? 1 : e.sy;
      g.setAttribute('transform', `translate(${e.dx || 0} ${e.dy || 0}) translate(${cx} ${cy}) rotate(${e.rot || 0}) scale(${sx} ${sy}) translate(${-cx} ${-cy})`);
      g.style.opacity = (e.op == null ? 1 : e.op); g.style.display = e.hidden ? 'none' : '';
      const t = g.querySelector('text'), p = g.querySelector('path');
      if (t) {
        if (e.fontFamily !== undefined) t.setAttribute('font-family', e.fontFamily);
        if (e.fontSize !== undefined) t.setAttribute('font-size', e.fontSize);
        if (e.fill !== undefined) t.setAttribute('fill', e.fill);
        t.setAttribute('font-weight', e.bold ? 'bold' : 'normal'); t.setAttribute('font-style', e.italic ? 'italic' : 'normal');
        if (e.text !== undefined) t.textContent = e.text;
      }
      if (p) {
        if (e.fill !== undefined) p.setAttribute('fill', e.fill);
        if (e.stroke !== undefined) p.setAttribute('stroke', e.stroke);
        if (e.width !== undefined) p.setAttribute('stroke-width', e.width);
      }
    }
    function renderAll() { for (const id in state) { const g = gById(id); if (g) applyEl(g); } drawUI(); refresh(); }

    function commit() { hist.push(JSON.stringify(state)); if (hist.length > 120) hist.shift(); future.length = 0; }
    function undo() { if (!hist.length) return; future.push(JSON.stringify(state)); clearState(); Object.assign(state, JSON.parse(hist.pop())); renderAll(); syncPanel(); }
    function redo() { if (!future.length) return; hist.push(JSON.stringify(state)); clearState(); Object.assign(state, JSON.parse(future.pop())); renderAll(); syncPanel(); }
    function clearState() { Object.keys(state).forEach(k => delete state[k]); }

    let ui = null;
    function clearUI() { if (ui) ui.remove(); ui = null; }
    function drawUI() {
      clearUI(); if (!selected.size) return;
      ui = document.createElementNS(NS, 'g'); ui.id = 'cvui'; svg.appendChild(ui);
      const hs = 7 / zoom;
      if (selected.size === 1) {
        const g = gById([...selected][0]); if (!g) return; const c = corners(g);
        line([c[0], c[1], c[2], c[3], c[0]]);
        const H = { nw: c[0], ne: c[1], se: c[2], sw: c[3] };
        H.n = mid(c[0], c[1]); H.e = mid(c[1], c[2]); H.s = mid(c[2], c[3]); H.w = mid(c[3], c[0]);
        for (const k in H) hbox(H[k], hs, k);
        const up = rotV(0, -22 / zoom, (st(g.id).rot || 0)); const rp = [H.n[0] + up[0], H.n[1] + up[1]];
        line([H.n, rp]);
        const r = document.createElementNS(NS, 'circle'); r.setAttribute('cx', rp[0]); r.setAttribute('cy', rp[1]);
        r.setAttribute('r', hs / 2); r.setAttribute('class', 'cv-ui-rot'); r.dataset.handle = 'rot'; ui.appendChild(r);
      } else {
        let X0 = 1e9, Y0 = 1e9, X1 = -1e9, Y1 = -1e9;
        selected.forEach(id => { const g = gById(id); if (!g) return; corners(g).forEach(p => { X0 = Math.min(X0, p[0]); Y0 = Math.min(Y0, p[1]); X1 = Math.max(X1, p[0]); Y1 = Math.max(Y1, p[1]); }); });
        const A = [X0, Y0], B = [X1, Y0], Cc = [X1, Y1], D = [X0, Y1];
        line([A, B, Cc, D, A]);
        // 多选也给手柄: 否则整组只能挪不能缩放 (之前这里只画框)
        const H = { nw: A, ne: B, se: Cc, sw: D, n: mid(A, B), e: mid(B, Cc), s: mid(Cc, D), w: mid(D, A) };
        for (const k in H) hbox(H[k], hs, k);
        const rp = [H.n[0], H.n[1] - 22 / zoom];
        line([H.n, rp]);
        const r = document.createElementNS(NS, 'circle'); r.setAttribute('cx', rp[0]); r.setAttribute('cy', rp[1]);
        r.setAttribute('r', hs / 2); r.setAttribute('class', 'cv-ui-rot'); r.dataset.handle = 'rot'; ui.appendChild(r);
      }
    }
    function mid(a, b) { return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; }
    function line(pts) { const p = document.createElementNS(NS, 'polyline'); p.setAttribute('points', pts.map(a => a[0] + ',' + a[1]).join(' ')); p.setAttribute('class', 'cv-ui-line'); ui.appendChild(p); }
    function hbox(c, s, h) { const r = document.createElementNS(NS, 'rect'); r.setAttribute('x', c[0] - s / 2); r.setAttribute('y', c[1] - s / 2); r.setAttribute('width', s); r.setAttribute('height', s); r.setAttribute('class', 'cv-ui-h'); r.dataset.handle = h;
      // PPT 式线型光标: 拖角/拖边显示对应方向的缩放箭头, 而不是手型
      const CUR = { nw: 'nwse-resize', se: 'nwse-resize', ne: 'nesw-resize', sw: 'nesw-resize', n: 'ns-resize', s: 'ns-resize', e: 'ew-resize', w: 'ew-resize' };
      r.style.cursor = CUR[h] || 'pointer'; ui.appendChild(r); }

    function svgPt(ev) { const p = svg.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY; return p.matrixTransform(svg.getScreenCTM().inverse()); }
    function targetG(ev) { return ev.target.closest ? ev.target.closest('g.vec,g.txt') : null; }

    function selectOnly(id) { selected = new Set([id]); syncPanel(); drawUI(); buildList(); }
    function toggleSel(id) { if (selected.has(id)) selected.delete(id); else selected.add(id); syncPanel(); drawUI(); buildList(); }

    function onDown(ev) {
      if (addMode) { ev.preventDefault(); return; }
      const h = ev.target.closest ? ev.target.closest('.cv-ui-h,.cv-ui-rot') : null;
      if (h) { startTransform(h, ev); return; }
      if (spaceDown || ev.button === 2) return;
      const g = targetG(ev);
      if (!g) { startMarquee(ev); return; }
      if (ev.shiftKey) { toggleSel(g.id); }
      else { if (!selected.has(g.id)) selectOnly(g.id); else syncPanel(); }
      startMove(ev);
    }
    svg.addEventListener('pointerdown', onDown);
    function startMove(ev) {
      if (!selected.size) return; commit();
      const p0 = svgPt(ev); const base = {}; selected.forEach(id => { const e = st(id); base[id] = [e.dx || 0, e.dy || 0]; });
      const mv = e2 => { const p = svgPt(e2); selected.forEach(id => { const g = gById(id); if (!g) return; const e = st(id); e.dx = base[id][0] + (p.x - p0.x); e.dy = base[id][1] + (p.y - p0.y); applyEl(g); }); drawUI(); };
      const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); refresh(); syncPanel(); };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    }
    function startTransform(h, ev) {
      if (!selected.size) return;
      const kind = h.dataset.handle;
      const ids = [...selected].filter(id => gById(id));
      if (!ids.length) return;
      commit();
      if (ids.length > 1) { startGroupTransform(ids, kind, ev); return; }
      const id = ids[0]; const g = gById(id); if (!g) return;
      const e = st(id), b = bboxOf(g), cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2;
      const sx0 = e.sx == null ? 1 : e.sx, sy0 = e.sy == null ? 1 : e.sy;
      const rot0 = e.rot || 0, dx0 = e.dx || 0, dy0 = e.dy || 0;
      const C0 = [cx + dx0, cy + dy0];             // 根坐标系里的中心 = 局部中心 + 平移 (与 applyEl 一致)
      if (kind === 'rot') {
        const p0 = svgPt(ev), ang0 = Math.atan2(p0.y - C0[1], p0.x - C0[0]);
        const mvR = e2 => { const p = svgPt(e2); let d = rot0 + (Math.atan2(p.y - C0[1], p.x - C0[0]) - ang0) * 180 / Math.PI; if (e2.shiftKey) d = Math.round(d / 15) * 15; e.rot = Math.round(d); applyEl(g); drawUI(); };
        const upR = () => { window.removeEventListener('pointermove', mvR); window.removeEventListener('pointerup', upR); refresh(); syncPanel(); };
        window.addEventListener('pointermove', mvR); window.addEventListener('pointerup', upR);
        return;
      }
      /* PPT 式缩放: 拖角 = 等比 (对角锚定), 拖边 = 单轴拉伸 (对边锚定), Shift+角 = 自由。
         锚点用原始 bbox 局部坐标; 拖动中锚点的屏幕位置保持不动。 */
      const AM = { nw: [b[2], b[3]], ne: [b[0], b[3]], se: [b[0], b[1]], sw: [b[2], b[1]],
                   n: [cx, b[3]], s: [cx, b[1]], e: [b[0], cy], w: [b[2], cy] };
      const Al = AM[kind];
      const vx = Al[0] - cx, vy = Al[1] - cy;      // 锚点相对中心 (未缩放), 只用于平移补偿
      const A0 = toRoot(g, Al[0], Al[1]);          // 锚点当前屏幕位置 (保持固定)
      const Hl = { nw: [b[0], b[1]], ne: [b[2], b[1]], se: [b[2], b[3]], sw: [b[0], b[3]],
                   n: [cx, b[1]], s: [cx, b[3]], e: [b[2], cy], w: [b[0], cy] };
      const HlA = [Hl[kind][0] - Al[0], Hl[kind][1] - Al[1]];  // 手柄-锚点 局部向量: 缩放分母(锚点固定, 手柄跟手)
      const mvFn = e2 => {
        const p = svgPt(e2);
        // 以锚点 A0 为参考, 指针在"去旋转、未缩放"局部系; 缩放分母用 (手柄-锚点) 向量 HlA,
        // 使手柄严格跟手、锚点保持不动。旧写法用中心距离作分母, 手柄会过冲一个平移量。
        const lr = rotV(p.x - A0[0], p.y - A0[1], -rot0);
        let s1x = sx0, s1y = sy0;
        const corner = (kind === 'nw' || kind === 'ne' || kind === 'se' || kind === 'sw');
        if (corner) {
          if (e2.shiftKey) {                        // 自由缩放: 两轴独立跟手
            if (Math.abs(HlA[0]) > 1e-6) s1x = Math.max(.02, lr[0] / HlA[0]);
            if (Math.abs(HlA[1]) > 1e-6) s1y = Math.max(.02, lr[1] / HlA[1]);
          } else {                                  // 等比: 指针到锚点距离 / (手柄-锚点)距离
            const q = Math.hypot(lr[0], lr[1]) / Math.max(1e-6, Math.hypot(HlA[0], HlA[1]));
            s1x = Math.max(.02, sx0 * q); s1y = Math.max(.02, sy0 * q);
          }
        } else if (kind === 'e' || kind === 'w') {
          if (Math.abs(HlA[0]) > 1e-6) s1x = Math.max(.02, lr[0] / HlA[0]);
        } else {                                    // n / s: 拖下边框向下 → sy>1 放大
          if (Math.abs(HlA[1]) > 1e-6) s1y = Math.max(.02, lr[1] / HlA[1]);
        }
        // 补偿平移, 使锚点屏幕位置不动
        const rv = rotV(vx * (sx0 - s1x), vy * (sy0 - s1y), rot0);
        e.sx = s1x; e.sy = s1y; e.dx = dx0 + rv[0]; e.dy = dy0 + rv[1];
        applyEl(g); drawUI();
      };
      const up = () => { window.removeEventListener('pointermove', mvFn); window.removeEventListener('pointerup', up); refresh(); syncPanel(); };
      window.addEventListener('pointermove', mvFn); window.addEventListener('pointerup', up);
    }
    // 多选变换: 拖角 = 整组等比缩放 (对角锚定), 拖边 = 单轴拉伸 (对边锚定), 拖顶 = 整组旋转 (绕包围盒中心)。
    // base 里记的是根坐标系中心 rcx/rcy = 局部中心 + 已有平移 —— 旧版用局部中心,
    // 元素先挪动过再组缩放时会漂移 bb.dx*(q-1)。
    function startGroupTransform(ids, kind, ev) {
      const base = {}; let X0 = 1e9, Y0 = 1e9, X1 = -1e9, Y1 = -1e9;
      ids.forEach(id => {
        const g = gById(id), b = bboxOf(g), e = st(id);
        base[id] = { dx: e.dx || 0, dy: e.dy || 0, sx: e.sx == null ? 1 : e.sx,
                     sy: e.sy == null ? 1 : e.sy, rot: e.rot || 0,
                     rcx: (b[0] + b[2]) / 2 + (e.dx || 0), rcy: (b[1] + b[3]) / 2 + (e.dy || 0) };
        corners(g).forEach(p => {
          X0 = Math.min(X0, p[0]); Y0 = Math.min(Y0, p[1]);
          X1 = Math.max(X1, p[0]); Y1 = Math.max(Y1, p[1]);
        });
      });
      // 锚点: 拖角 = 对角, 拖边 = 对边中点 (联合包围盒, 根坐标系)
      const A = [X0, Y0], B = [X1, Y0], Cc = [X1, Y1], D = [X0, Y1];
      const AM = { nw: Cc, ne: D, se: A, sw: B,
                   n: [(X0 + X1) / 2, Y1], s: [(X0 + X1) / 2, Y0],
                   e: [X0, (Y0 + Y1) / 2], w: [X1, (Y0 + Y1) / 2] };
      const A0 = AM[kind];
      const p0 = svgPt(ev);              // SVGPoint: 只能用 .x/.y, 不能当下标取
      const many = ids.length > 400;   // 几千个元素时过程中不重画辅助框, 否则每次移动都要遍历一遍
      const mv = e2 => {
        const p = svgPt(e2);
        if (kind === 'rot') {
          const C = [(X0 + X1) / 2, (Y0 + Y1) / 2];   // 旋转仍绕包围盒中心 (与 PPT 一致)
          const ang0 = Math.atan2(p0.y - C[1], p0.x - C[0]);
          let d = (Math.atan2(p.y - C[1], p.x - C[0]) - ang0) * 180 / Math.PI;
          if (e2.shiftKey) d = Math.round(d / 15) * 15;
          ids.forEach(id => {
            const g = gById(id), bb = base[id], e = st(id);
            e.rot = Math.round((bb.rot + d) * 10) / 10;
            const v = rotV(bb.rcx - C[0], bb.rcy - C[1], d);
            e.dx = bb.dx + (C[0] + v[0] - bb.rcx); e.dy = bb.dy + (C[1] + v[1] - bb.rcy);
            applyEl(g);
          });
        } else if (kind === 'nw' || kind === 'ne' || kind === 'se' || kind === 'sw') {
          // 等比: 指针到锚点距离 / 起点到锚点距离
          const dd0 = Math.max(1e-6, Math.hypot(p0.x - A0[0], p0.y - A0[1]));
          let q = Math.hypot(p.x - A0[0], p.y - A0[1]) / dd0;
          if (e2.shiftKey) q = Math.round(q * 20) / 20;
          q = Math.max(.02, q);
          ids.forEach(id => {
            const g = gById(id), bb = base[id], e = st(id);
            e.sx = Math.max(.02, bb.sx * q); e.sy = Math.max(.02, bb.sy * q);
            e.dx = bb.dx + (bb.rcx - A0[0]) * (q - 1); e.dy = bb.dy + (bb.rcy - A0[1]) * (q - 1);
            applyEl(g);
          });
        } else {
          // 单轴拉伸: e/w 只改宽, n/s 只改高
          const horiz = kind === 'e' || kind === 'w';
          let q;
          if (horiz) q = Math.abs(p.x - A0[0]) / Math.max(1e-6, Math.abs(p0.x - A0[0]));
          else q = Math.abs(p.y - A0[1]) / Math.max(1e-6, Math.abs(p0.y - A0[1]));
          q = Math.max(.02, q);
          ids.forEach(id => {
            const g = gById(id), bb = base[id], e = st(id);
            if (horiz) { e.sx = Math.max(.02, bb.sx * q); e.dx = bb.dx + (bb.rcx - A0[0]) * (q - 1); }
            else { e.sy = Math.max(.02, bb.sy * q); e.dy = bb.dy + (bb.rcy - A0[1]) * (q - 1); }
            applyEl(g);
          });
        }
        if (!many) drawUI();
      };
      const up = () => { window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); refresh(); syncPanel(); };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    }
    function startMarquee(ev) {
      const p0 = svgPt(ev); const box = document.createElementNS(NS, 'rect'); box.setAttribute('class', 'cv-ui-line'); box.style.stroke = '#4a82bd'; svg.appendChild(box);
      const mv = e2 => { const p = svgPt(e2); const x = Math.min(p0.x, p.x), y = Math.min(p0.y, p.y); box.setAttribute('x', x); box.setAttribute('y', y); box.setAttribute('width', Math.abs(p.x - p0.x)); box.setAttribute('height', Math.abs(p.y - p0.y)); };
      const up = e2 => {
        window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up); const p = svgPt(e2);
        const x0 = Math.min(p0.x, p.x), y0 = Math.min(p0.y, p.y), x1 = Math.max(p0.x, p.x), y1 = Math.max(p0.y, p.y); box.remove();
        if (x1 - x0 < 2 && y1 - y0 < 2) { if (!ev.shiftKey) { selected = new Set(); syncPanel(); drawUI(); buildList(); } return; }
        // 中心落在框内即选中 (原来要求四角全部在框内, 底图那种跨满全图的色块永远选不上)
        const add = new Set();
        svg.querySelectorAll('g.vec,g.txt').forEach(g => {
          const b = bboxOf(g), c = toRoot(g, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2);
          if (c[0] >= x0 && c[0] <= x1 && c[1] >= y0 && c[1] <= y1) add.add(g.id);
        });
        selected = ev.shiftKey ? new Set([...selected, ...add]) : add; syncPanel(); drawUI(); buildList();
      };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    }

    let pan = null;
    function stageDown(ev) { if (spaceDown || ev.button === 2) { pan = { x: ev.clientX, y: ev.clientY, l: stage.scrollLeft, t: stage.scrollTop }; stage.classList.add('panning'); ev.preventDefault(); } }
    function winMove(ev) { if (pan) { stage.scrollLeft = pan.l - (ev.clientX - pan.x); stage.scrollTop = pan.t - (ev.clientY - pan.y); } }
    function winUp() { pan = null; stage.classList.remove('panning'); }
    stage.addEventListener('pointerdown', stageDown);
    window.addEventListener('pointermove', winMove);
    window.addEventListener('pointerup', winUp);
    function noCtx(ev) { ev.preventDefault(); }
    stage.addEventListener('contextmenu', noCtx);
    function onDbl(ev) { const g = targetG(ev); if (!g || !g.classList.contains('txt')) return; selectOnly(g.id); el('cv_p_text').focus(); el('cv_p_text').select(); }
    svg.addEventListener('dblclick', onDbl);

    function setZoom(z) { zoom = Math.min(8, Math.max(.1, z)); wrap.style.transform = `scale(${zoom})`; el('cv_zoomlbl').textContent = Math.round(zoom * 100) + '%'; drawUI(); }
    function onWheel(ev) {
      if (ev.ctrlKey) {
        ev.preventDefault(); const r = stage.getBoundingClientRect(); const mx = ev.clientX - r.left + stage.scrollLeft, my = ev.clientY - r.top + stage.scrollTop;
        const nz = Math.min(8, Math.max(.1, zoom * (ev.deltaY < 0 ? 1.1 : .9)));
        stage.scrollLeft = mx * (nz / zoom) - (ev.clientX - r.left); stage.scrollTop = my * (nz / zoom) - (ev.clientY - r.top); setZoom(nz);
      }
    }
    stage.addEventListener('wheel', onWheel, { passive: false });
    el('cv_zin').onclick = () => setZoom(zoom * 1.2); el('cv_zout').onclick = () => setZoom(zoom / 1.2); el('cv_z100').onclick = () => setZoom(1);
    function zfit() { setZoom(1); const r = svg.getBoundingClientRect(); const k = Math.min((stage.clientHeight - 48) / (r.height / zoom), (stage.clientWidth - 48) / (r.width / zoom)); setZoom(k); }
    el('cv_zfit').onclick = zfit; setTimeout(zfit, 0);

    function onKeyDown(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (e.code === 'Space') { spaceDown = true; stage.classList.add('pan'); e.preventDefault(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); return; }
      if (e.ctrlKey && e.key.toLowerCase() === 'd') { e.preventDefault(); doDup(); return; }
      if (e.key === 'Delete') { selected.forEach(id => { const g = gById(id); if (g) { const en = st(id); en.hidden = !en.hidden; applyEl(g); } }); drawUI(); refresh(); buildList(); }
      if (sel0() && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
        commit(); const d = e.shiftKey ? 10 : 1; selected.forEach(id => { const g = gById(id); if (!g) return; const en = st(id); if (e.key === 'ArrowUp') en.dy -= d; if (e.key === 'ArrowDown') en.dy += d; if (e.key === 'ArrowLeft') en.dx -= d; if (e.key === 'ArrowRight') en.dx += d; applyEl(g); });
        drawUI(); refresh(); syncPanel(); e.preventDefault();
      }
    }
    function onKeyUp(e) { if (e.code === 'Space') { spaceDown = false; stage.classList.remove('pan'); } }
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    function sel0() { return selected.size ? [...selected][0] : null; }

    function toHex6(c) { if (!c || c === 'none') return '#000000'; if (c[0] === '#') return c.length === 4 ? '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3] : c; return '#000000'; }
    function syncPanel() {
      const id = sel0(); const g = id ? gById(id) : null;
      if (!g) { el('cv_props').style.display = 'none'; el('cv_empty').style.display = 'block'; return; }
      el('cv_empty').style.display = 'none'; el('cv_props').style.display = 'block';
      const isTxt = g.classList.contains('txt'), e = st(id);
      el('cv_ptype').textContent = (isTxt ? '文字 ' : '矢量 ') + id + (selected.size > 1 ? ` (+${selected.size - 1})` : '');
      el('cv_g_font').style.display = isTxt ? '' : 'none'; el('cv_g_vec').style.display = isTxt ? 'none' : '';
      const t = g.querySelector('text');
      el('cv_g_text').style.display = isTxt ? '' : 'none'; el('cv_p_text').value = e.text !== undefined ? e.text : (t ? t.textContent : '');
      // 属性面板每次选中都会走, 这里任何一次 null/NaN 抛错都会让后面的 drawUI 不执行,
      // 表现就是"点中了却看不到手柄、拖不动"。填充块没有 stroke-width 正属于这种情况。
      const nf = (v, d) => { const x = parseFloat(v); return isNaN(x) ? 0 : +x.toFixed(d); };
      el('cv_p_dx').value = Math.round(e.dx || 0); el('cv_p_dy').value = Math.round(e.dy || 0);
      el('cv_p_sx').value = e.sx == null ? 1 : e.sx; el('cv_p_sxN').value = nf(e.sx == null ? 1 : e.sx, 2);
      el('cv_p_sy').value = e.sy == null ? 1 : e.sy; el('cv_p_syN').value = nf(e.sy == null ? 1 : e.sy, 2);
      el('cv_p_rot').value = e.rot || 0; el('cv_p_rotN').value = e.rot || 0;
      el('cv_p_op').value = e.op == null ? 1 : e.op; el('cv_p_opN').value = nf(e.op == null ? 1 : e.op, 2);
      if (isTxt && t) { el('cv_p_font').value = e.fontFamily || t.getAttribute('font-family'); el('cv_p_size').value = e.fontSize || t.getAttribute('font-size'); el('cv_p_sizeN').value = nf(e.fontSize || t.getAttribute('font-size'), 1); el('cv_p_fill').value = toHex6(e.fill || t.getAttribute('fill')); el('cv_p_bold').classList.toggle('on', !!e.bold); el('cv_p_ital').classList.toggle('on', !!e.italic); }
      if (!isTxt) { const p = g.querySelector('path'); el('cv_p_vfill').value = toHex6(e.fill || (p && p.getAttribute('fill'))); el('cv_p_vstroke').value = toHex6(e.stroke || (p && p.getAttribute('stroke'))); el('cv_p_vw').value = e.width || (p && p.getAttribute('stroke-width')) || ''; el('cv_p_vwN').value = nf(e.width || (p && p.getAttribute('stroke-width')), 1); }
    }
    function eachSel(fn) { if (!selected.size) return; commit(); selected.forEach(id => { const g = gById(id); if (g) { fn(st(id)); applyEl(g); } }); drawUI(); refresh(); }
    function bind(id, fn) { const x = el(id); if (!x) return; x.addEventListener('input', () => { if (!selected.size) return; eachSel(e => fn(e, el(id))); if (id === 'cv_p_dx' || id === 'cv_p_dy') syncPanel(); }); }
    bind('cv_p_dx', (e, x) => e.dx = +x.value); bind('cv_p_dy', (e, x) => e.dy = +x.value);
    bind('cv_p_sx', (e, x) => { e.sx = +x.value; el('cv_p_sxN').value = x.value; }); bind('cv_p_sxN', (e, x) => { e.sx = +x.value; el('cv_p_sx').value = x.value; });
    bind('cv_p_sy', (e, x) => { e.sy = +x.value; el('cv_p_syN').value = x.value; }); bind('cv_p_syN', (e, x) => { e.sy = +x.value; el('cv_p_sy').value = x.value; });
    bind('cv_p_rot', (e, x) => { e.rot = +x.value; el('cv_p_rotN').value = x.value; }); bind('cv_p_rotN', (e, x) => { e.rot = +x.value; el('cv_p_rot').value = x.value; });
    bind('cv_p_op', (e, x) => { e.op = +x.value; el('cv_p_opN').value = x.value; }); bind('cv_p_opN', (e, x) => { e.op = +x.value; el('cv_p_op').value = x.value; });
    bind('cv_p_text', (e, x) => e.text = x.value); bind('cv_p_font', (e, x) => e.fontFamily = x.value);
    bind('cv_p_size', (e, x) => { e.fontSize = +x.value; el('cv_p_sizeN').value = x.value; }); bind('cv_p_sizeN', (e, x) => { e.fontSize = +x.value; el('cv_p_size').value = x.value; });
    bind('cv_p_fill', (e, x) => e.fill = x.value); bind('cv_p_vfill', (e, x) => e.fill = x.value); bind('cv_p_vstroke', (e, x) => e.stroke = x.value);
    bind('cv_p_vw', (e, x) => { e.width = +x.value; el('cv_p_vwN').value = x.value; }); bind('cv_p_vwN', (e, x) => { e.width = +x.value; el('cv_p_vw').value = x.value; });
    el('cv_p_vfill0').onclick = () => eachSel(e => e.fill = 'none');
    el('cv_p_bold').onclick = () => { if (!selected.size) return; eachSel(e => e.bold = !e.bold); el('cv_p_bold').classList.toggle('on', !!st(sel0()).bold); };
    el('cv_p_ital').onclick = () => { if (!selected.size) return; eachSel(e => e.italic = !e.italic); el('cv_p_ital').classList.toggle('on', !!st(sel0()).italic); };
    el('cv_p_reset').onclick = () => { if (!selected.size) return; commit(); selected.forEach(id => { const g = gById(id); if (!g) return; delete state[id]; g.removeAttribute('transform'); g.style.opacity = ''; g.style.display = ''; const t = g.querySelector('text'); if (t) t.textContent = g.dataset.content; }); drawUI(); refresh(); syncPanel(); buildList(); };

    el('cv_undo').onclick = undo; el('cv_redo').onclick = redo;
    el('cv_hide').onclick = () => { if (!selected.size) return; eachSel(e => e.hidden = !e.hidden); };
    el('cv_dup').onclick = doDup;
    function doDup() {
      const id = sel0(); const g = gById(id); if (!g) return; commit();
      const nid = 'dup_' + (newN++); const c = g.cloneNode(true); c.id = nid; c.removeAttribute('transform'); c.style.opacity = ''; c.style.display = ''; c.setAttribute('transform', 'translate(10 10)');
      (g.parentNode).appendChild(c);
      const e = { ...st(id), dx: (st(id).dx || 0) + 10, dy: (st(id).dy || 0) + 10 }; state[nid] = e; applyEl(c); selectOnly(nid);
    }
    el('cv_addtxt').onclick = () => {
      addMode = !addMode; el('cv_addtxt').classList.toggle('act', addMode); stage.classList.toggle('addtxt', addMode);
    };
    function onClickPlace(ev) {
      if (!addMode) return; const p = svgPt(ev); const txt = prompt('文字内容:', '标注'); if (txt === null) return;
      const nid = 'txt_new' + (newN++); const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'txt'); g.id = nid;
      g.dataset.bbox = `${p.x} ${p.y} ${p.x} ${p.y}`; g.dataset.content = txt;
      const t = document.createElementNS(NS, 'text'); t.setAttribute('x', p.x); t.setAttribute('y', p.y); t.setAttribute('font-size', '12'); t.setAttribute('fill', '#000000'); t.textContent = txt; g.appendChild(t);
      (svg.querySelector('#txt-layer') || svg).appendChild(g);
      state[nid] = { dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, op: 1 }; addMode = false; el('cv_addtxt').classList.remove('act'); stage.classList.remove('addtxt'); selectOnly(nid); refresh();
    }
    svg.addEventListener('click', onClickPlace);

    el('cv_reset').onclick = resetElements;

    function buildList() {
      if (!listHost) return;
      const gs = [...svg.querySelectorAll('g.txt')]; listHost.innerHTML = '';
      if (!gs.length) { listHost.innerHTML = '<div class="cv-empty" style="padding:12px 14px">图中没有文字元素</div>'; return; }
      gs.forEach(g => {
        const row = document.createElement('div'); row.className = 'li' + (selected.has(g.id) ? ' on' : '');
        const eye = document.createElement('span'); eye.className = 'eye'; eye.textContent = (st(g.id).hidden ? '✖' : '👁'); eye.title = '显隐';
        eye.onclick = e => { e.stopPropagation(); commit(); const en = st(g.id); en.hidden = !en.hidden; applyEl(g); buildList(); refresh(); };
        const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = g.dataset.content || g.id;
        const ix = document.createElement('span'); ix.className = 'ix'; ix.textContent = g.id;
        row.onclick = () => selectOnly(g.id); row.appendChild(eye); row.appendChild(nm); row.appendChild(ix); listHost.appendChild(row);
      });
    }

    function collect() {
      const out = {}; for (const id in state) { if (!dirty(state[id])) continue; const g = gById(id); if (!g) continue; const o = { ...state[id] }; o._bbox = g.dataset.bbox; if (g.classList.contains('txt')) o._content = g.dataset.content; out[id] = o; } return out;
    }
    function applyOverlay(obj) {
      if (!obj) return 0; let hit = 0;
      const txts = [...svg.querySelectorAll('g.txt')];
      const vecs = [...svg.querySelectorAll('g.vec')];
      for (const id in obj) {
        let g = gById(id); const e = obj[id];
        if (!g && e._content !== undefined) g = txts.find(x => x.dataset.content === e._content);
        if (!g && e._bbox) {
          const [ax, ay] = e._bbox.split(' ').map(Number);
          let best, bd = 1e18;
          vecs.forEach(x => { const [bx, by] = x.dataset.bbox.split(' ').map(Number); const d = Math.hypot(bx - ax, by - ay); if (d < bd) { bd = d; best = x; } });
          if (best && bd < 8) g = best;
        }
        if (g) { state[g.id] = Object.assign({ dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, op: 1 }, e); applyEl(g); hit++; }
      }
      renderAll(); buildList(); notify(); return hit;
    }
    function resetElements() {
      commit();
      for (const id in state) { const g = gById(id); if (g) { g.removeAttribute('transform'); g.style.opacity = ''; g.style.display = ''; const t = g.querySelector('text'); if (t) t.textContent = g.dataset.content; } }
      clearState(); selected = new Set(); drawUI(); refresh(); syncPanel(); buildList();
    }

    refresh(); syncPanel(); buildList();

    function destroy() {
      svg.removeEventListener('pointerdown', onDown); svg.removeEventListener('dblclick', onDbl); svg.removeEventListener('click', onClickPlace);
      stage.removeEventListener('pointerdown', stageDown); stage.removeEventListener('wheel', onWheel); stage.removeEventListener('contextmenu', noCtx);
      window.removeEventListener('pointermove', winMove); window.removeEventListener('pointerup', winUp);
      window.removeEventListener('keydown', onKeyDown); window.removeEventListener('keyup', onKeyUp);
      stageHost.innerHTML = ''; propsHost.innerHTML = ''; if (listHost) listHost.innerHTML = '';
    }

    return { collect, applyOverlay, resetElements, countDirty, buildList, destroy };
  }

  return { init };
})();
