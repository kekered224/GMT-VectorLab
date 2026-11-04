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
  .cv-stage.pan{cursor:grab}.cv-stage.panning{cursor:grabbing}.cv-stage.addtxt{cursor:text}.cv-stage.draw{cursor:crosshair}
  .cv-draft{pointer-events:none}
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
  /* 插入菜单 */
  .cv-ins{position:relative;display:inline-flex}
  .cv-menu{position:absolute;left:0;top:34px;z-index:50;width:318px;padding:7px;background:var(--surface);
    border:1px solid var(--border-2);border-radius:12px;box-shadow:var(--sh-3);display:none}
  .cv-menu.open{display:block}
  .cv-menu-t{font-size:10.5px;font-weight:650;letter-spacing:.6px;text-transform:uppercase;color:var(--ink-3);padding:6px 7px 4px}
  .cv-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:3px}
  .cv-sh{display:flex;flex-direction:column;align-items:center;gap:4px;padding:7px 2px 6px;border:1px solid transparent;
    border-radius:8px;background:transparent;cursor:pointer;color:var(--ink-2);font-size:10.5px;line-height:1.2}
  .cv-sh:hover{background:var(--surface-2);color:var(--ink)}
  .cv-sh.act{background:var(--accent-soft);border-color:var(--accent-ring);color:var(--accent-h)}
  .cv-sh svg{width:21px;height:21px}
  .cv-mi{display:flex;align-items:center;gap:9px;width:100%;padding:8px 8px;border:none;border-radius:8px;
    background:transparent;cursor:pointer;color:var(--ink);font-size:12.5px;text-align:left}
  .cv-mi:hover{background:var(--surface-2)}
  .cv-mi svg{width:17px;height:17px;color:var(--ink-2)}
  .chev{width:12px;height:12px;flex:none;color:var(--ink-3);transition:transform .15s var(--ease)}
  .cv-ex.closed>.cv-ex-h .chev,.cv-sec.closed .cv-sec-h .chev{transform:rotate(-90deg)}
  /* 元素浏览器 (VS Code 风格) */
  .cv-ex{display:flex;flex-direction:column;min-height:0;height:100%;border-top:1px solid var(--border)}
  .cv-ex-h{display:flex;align-items:center;gap:7px;width:100%;padding:11px 14px 8px;border:none;background:transparent;
    cursor:pointer;font-size:11px;font-weight:650;letter-spacing:.6px;text-transform:uppercase;color:var(--ink-3);text-align:left}
  .cv-ex-h:hover{color:var(--ink-2)}
  .cv-ex-h .cnt{margin-left:auto;font-size:10px;font-weight:600;letter-spacing:0;text-transform:none;
    background:var(--surface-2);color:var(--ink-3);border-radius:99px;padding:1px 7px}
  .cv-ex-b{display:flex;flex-direction:column;flex:1;min-height:0}
  .cv-ex.closed .cv-ex-b{display:none}
  .cv-tabs{display:flex;gap:2px;padding:1px 8px 6px}
  .cv-tabs button{flex:1;height:25px;border:1px solid transparent;border-radius:6px;background:transparent;
    color:var(--ink-2);font-size:11.5px;cursor:pointer;white-space:nowrap}
  .cv-tabs button:hover{background:var(--surface-2)}
  .cv-tabs button.on{background:var(--surface-3);border-color:var(--border-2);color:var(--ink);font-weight:600}
  .cv-find{position:relative;margin:0 8px 6px}
  .cv-find input{width:100%;height:28px;padding:0 8px 0 25px;border:1px solid var(--border-2);border-radius:7px;
    background:var(--surface);color:var(--ink);font-size:12px;outline:none}
  .cv-find input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-ring)}
  .cv-find svg{position:absolute;left:7px;top:7px;width:13px;height:13px;color:var(--ink-3);pointer-events:none}
  .cv-rows{flex:1;min-height:0;overflow:auto;padding:1px 7px 10px;overscroll-behavior:contain}
  .cv-el{display:flex;align-items:center;gap:7px;padding:5px 7px;border-radius:6px;cursor:pointer;
    border:1px solid transparent;font-size:12px}
  .cv-el:hover{background:var(--surface-2)}
  .cv-el.on{background:var(--accent-soft);border-color:var(--accent-ring)}
  .cv-el .ti{width:16px;height:16px;flex:none;display:grid;place-items:center;color:var(--ink-3)}
  .cv-el .ti svg{width:13px;height:13px}
  .cv-el.on .ti{color:var(--accent-h)}
  .cv-el .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .cv-el .ix{flex:none;max-width:66px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
    font-family:var(--mono);font-size:10px;color:var(--ink-3)}
  .cv-el .eye{width:20px;height:20px;flex:none;display:grid;place-items:center;border:none;border-radius:5px;
    background:transparent;color:var(--ink-3);cursor:pointer;padding:0}
  .cv-el .eye:hover{background:var(--surface-3);color:var(--ink)}
  .cv-el .eye svg{width:13px;height:13px}
  .cv-el .more{width:18px;height:18px;flex:none;display:grid;place-items:center;border:none;border-radius:5px;
    background:transparent;color:var(--ink-3);cursor:pointer;padding:0;opacity:0;pointer-events:none;transition:opacity .12s}
  .cv-el:hover .more,.cv-el.on .more{opacity:1;pointer-events:auto}
  .cv-el .more:hover{background:var(--surface-3);color:var(--ink)}
  .cv-el .more svg{width:13px;height:13px}
  .cv-el .nm input{width:100%;height:20px;padding:0 4px;border:1px solid var(--accent);border-radius:4px;
    background:var(--surface);color:var(--ink);font-size:12px;font-family:inherit;outline:none}
  .cv-el.t-off .nm,.cv-el.t-off .ix{opacity:.45}
  /* 元素右键菜单 */
  .cv-ctx{position:fixed;z-index:120;display:none;min-width:196px;padding:5px;background:var(--surface);
    border:1px solid var(--border-2);border-radius:10px;box-shadow:var(--sh-3)}
  .cv-ctx.open{display:block}
  .cv-ctx-t{padding:6px 9px 5px;font-size:10.5px;font-weight:650;color:var(--ink-3);
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cv-ctxi{display:flex;align-items:center;gap:9px;width:100%;padding:7px 9px;border:none;border-radius:7px;
    background:transparent;color:var(--ink);font-size:12.5px;text-align:left;cursor:pointer}
  .cv-ctxi:hover{background:var(--surface-2)}
  .cv-ctxi svg{width:15px;height:15px;flex:none;color:var(--ink-3)}
  .cv-ctxi .k{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--ink-3);
    border:1px solid var(--border);border-radius:4px;padding:0 4px}
  .cv-ctxi.danger,.cv-ctxi.danger svg{color:var(--err)}
  .cv-ctxi.danger:hover{background:var(--err-soft)}
  .cv-ctxsep{height:1px;margin:4px 6px;background:var(--border)}
  .cv-cap{padding:10px 10px;font-size:11px;color:var(--ink-3);line-height:1.6}
  .cv-exfoot{padding:7px 12px 9px;border-top:1px solid var(--border);font-size:11px;color:var(--ink-3);
    display:flex;align-items:center;gap:6px}
  .cv-exfoot b{color:var(--ink-2);font-weight:600}
  /* 属性面板可折叠分组 */
  .cv-sec{border-top:1px solid var(--border);margin-top:8px;padding-top:1px}
  .cv-sec-h{display:flex;align-items:center;gap:6px;width:100%;padding:8px 0 7px;border:none;background:none;
    cursor:pointer;font-size:11px;font-weight:650;letter-spacing:.5px;text-transform:uppercase;color:var(--ink-3);text-align:left}
  .cv-sec-h:hover{color:var(--ink-2)}
  .cv-sec-b{padding:0 0 4px}
  .cv-sec.closed .cv-sec-b{display:none}
  `;

  const ICON = {
    undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>',
    redo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13"/></svg>',
    txt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7V5h16v2"/><path d="M12 5v14"/><path d="M9 19h6"/></svg>',
    dup: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    hide: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 10 8 10 8a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.5 13.5 0 0 0 2 12s3 8 10 8a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/></svg>',
    reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
    pt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/></svg>',
    line: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 19 20 5"/><circle cx="4" cy="19" r="2"/><circle cx="20" cy="5" r="2"/></svg>',
    poly: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3 21 10l-3.5 10h-11L3 10z"/></svg>',
    done: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m4 12 5 5L20 6"/></svg>',
    no: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
    chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
    vec: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19 10 6l10 8-8 4z"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>',
    eyeOff: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 3 18 18"/><path d="M10.5 5.2A9.9 9.9 0 0 1 12 5c6.5 0 10 7 10 7a15.9 15.9 0 0 1-3.1 4.1"/><path d="M6.6 6.6C3.6 8.5 2 12 2 12s3.5 7 10 7c1.4 0 2.6-.3 3.8-.8"/></svg>',
    find: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    more: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>',
    focus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M9 3H5a2 2 0 0 0-2 2v4M15 3h4a2 2 0 0 1 2 2v4M21 15v4a2 2 0 0 1-2 2h-4M9 21H5a2 2 0 0 1-2-2v-4"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  };

  /* ---------- 形状几何 (画布与导出共用同一套定义) ----------
     点: _pts=[[x,y]]; 折线/多边形: _pts=顶点序列; 预设形状: _pts=[[x0,y0],[x1,y1]] 包围盒两角。 */
  const SHAPE_DEF = {
    point: { fill: '#e4572e', stroke: '#e4572e', width: 0, r: 3.5 },
    line: { fill: 'none', stroke: '#1f6feb', width: 1.6, r: 0 },
    poly: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, r: 0 },
    rect: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    roundrect: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    ellipse: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    triangle: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    diamond: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    pentagon: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    hexagon: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    star: { fill: '#fbd9a3', stroke: '#c27c0e', width: 1.4, box: 1 },
    arrow: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    doublearrow: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
    parallelogram: { fill: '#cfe3f7', stroke: '#1f6feb', width: 1.4, box: 1 },
  };
  const SHAPE_LABEL = {
    point: '点', line: '折线', poly: '多边形', rect: '矩形', roundrect: '圆角矩形',
    ellipse: '椭圆', triangle: '三角形', diamond: '菱形', pentagon: '五边形',
    hexagon: '六边形', star: '星形', arrow: '箭头', doublearrow: '双向箭头', parallelogram: '平行四边形',
  };
  const isBoxShape = k => !!(SHAPE_DEF[k] && SHAPE_DEF[k].box);

  function f2(v) { return +Number(v).toFixed(2); }
  function ellipseD(cx, cy, rx, ry) {
    const kx = rx * 0.5523, ky = ry * 0.5523;
    return `M${f2(cx - rx)} ${f2(cy)}C${f2(cx - rx)} ${f2(cy - ky)} ${f2(cx - kx)} ${f2(cy - ry)} ${f2(cx)} ${f2(cy - ry)}` +
           `C${f2(cx + kx)} ${f2(cy - ry)} ${f2(cx + rx)} ${f2(cy - ky)} ${f2(cx + rx)} ${f2(cy)}` +
           `C${f2(cx + rx)} ${f2(cy + ky)} ${f2(cx + kx)} ${f2(cy + ry)} ${f2(cx)} ${f2(cy + ry)}` +
           `C${f2(cx - kx)} ${f2(cy + ry)} ${f2(cx - rx)} ${f2(cy + ky)} ${f2(cx - rx)} ${f2(cy)}Z`;
  }
  function circleD(cx, cy, r) { return ellipseD(cx, cy, r, r); }
  function ring(n, cx, cy, rx, ry, inner, startDeg) {
    const pts = [], st = (startDeg == null ? -90 : startDeg) * Math.PI / 180;
    for (let i = 0; i < n * 2; i++) {
      const a = st + i * Math.PI / n, k = (inner && i % 2) ? inner : 1;
      pts.push([cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]);
    }
    return pts;
  }
  function pathFrom(pts, close) {
    if (!pts.length) return '';
    let d = `M${f2(pts[0][0])} ${f2(pts[0][1])}`;
    for (let i = 1; i < pts.length; i++) d += `L${f2(pts[i][0])} ${f2(pts[i][1])}`;
    return d + (close ? 'Z' : '');
  }
  function boxD(kind, x0, y0, x1, y1) {
    const w = x1 - x0, h = y1 - y0, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    if (kind === 'rect') return `M${f2(x0)} ${f2(y0)}L${f2(x1)} ${f2(y0)}L${f2(x1)} ${f2(y1)}L${f2(x0)} ${f2(y1)}Z`;
    if (kind === 'ellipse') return ellipseD(cx, cy, Math.abs(w) / 2, Math.abs(h) / 2);
    if (kind === 'roundrect') {
      const r = Math.min(Math.abs(w), Math.abs(h)) * 0.22;
      return `M${f2(x0 + r)} ${f2(y0)}L${f2(x1 - r)} ${f2(y0)}Q${f2(x1)} ${f2(y0)} ${f2(x1)} ${f2(y0 + r)}` +
             `L${f2(x1)} ${f2(y1 - r)}Q${f2(x1)} ${f2(y1)} ${f2(x1 - r)} ${f2(y1)}` +
             `L${f2(x0 + r)} ${f2(y1)}Q${f2(x0)} ${f2(y1)} ${f2(x0)} ${f2(y1 - r)}` +
             `L${f2(x0)} ${f2(y0 + r)}Q${f2(x0)} ${f2(y0)} ${f2(x0 + r)} ${f2(y0)}Z`;
    }
    if (kind === 'triangle') return pathFrom([[cx, y0], [x1, y1], [x0, y1]], true);
    if (kind === 'diamond') return pathFrom([[cx, y0], [x1, cy], [cx, y1], [x0, cy]], true);
    if (kind === 'pentagon') return pathFrom(ring(5, cx, cy, Math.abs(w) / 2, Math.abs(h) / 2, 1, -90), true);
    if (kind === 'hexagon') return pathFrom(ring(6, cx, cy, Math.abs(w) / 2, Math.abs(h) / 2, 1, -90), true);
    if (kind === 'star') return pathFrom(ring(5, cx, cy, Math.abs(w) / 2, Math.abs(h) / 2, 0.38, -90), true);
    if (kind === 'parallelogram') {
      const o = Math.abs(w) * 0.22;
      return pathFrom([[x0 + o, y0], [x1, y0], [x1 - o, y1], [x0, y1]], true);
    }
    if (kind === 'arrow' || kind === 'doublearrow') {
      const sh = Math.abs(h) * 0.22, hw = Math.abs(w) * 0.36;
      if (kind === 'arrow') {
        return pathFrom([[x0, cy - sh], [x1 - hw, cy - sh], [x1 - hw, y0], [x1, cy],
                         [x1 - hw, y1], [x1 - hw, cy + sh], [x0, cy + sh]], true);
      }
      return pathFrom([[x0, cy], [x0 + hw, y0], [x0 + hw, cy - sh], [x1 - hw, cy - sh],
                       [x1 - hw, y0], [x1, cy], [x1 - hw, y1], [x1 - hw, cy + sh],
                       [x0 + hw, cy + sh], [x0 + hw, y1]], true);
    }
    return `M${f2(x0)} ${f2(y0)}L${f2(x1)} ${f2(y0)}L${f2(x1)} ${f2(y1)}L${f2(x0)} ${f2(y1)}Z`;
  }
  function shapeD(kind, pts, r) {
    if (kind === 'point' || pts.length === 1) {
      const p = pts[0] || [0, 0];
      return circleD(p[0], p[1], r);
    }
    if (isBoxShape(kind) && pts.length >= 2) {
      const x0 = Math.min(pts[0][0], pts[1][0]), x1 = Math.max(pts[0][0], pts[1][0]);
      const y0 = Math.min(pts[0][1], pts[1][1]), y1 = Math.max(pts[0][1], pts[1][1]);
      return boxD(kind, x0, y0, x1, y1);
    }
    return pathFrom(pts, kind === 'poly');
  }
  function bboxOfPts(kind, pts, r) {
    if (kind === 'point' || pts.length === 1) {
      const [x, y] = pts[0]; return [f2(x - r), f2(y - r), f2(x + r), f2(y + r)];
    }
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    pts.forEach(p => { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); });
    const pad = 1.2;   // 水平/竖直线的 bbox 不能退化成 0, 否则缩放锚点算不出来
    return [f2(x0 - pad), f2(y0 - pad), f2(x1 + pad), f2(y1 + pad)];
  }
  function shapeIcon(kind) {
    const d = kind === 'point' ? circleD(12, 12, 7)
      : (kind === 'line' ? 'M4 19L20 5'
      : (kind === 'poly' ? pathFrom([[12, 4], [20, 10], [17, 20], [7, 20], [4, 10]], true)
      : shapeD(kind, [[4, 5], [20, 19]], 0)));
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="${d}"/></svg>`;
  }

  function barHTML() {
    const boxKinds = ['rect', 'roundrect', 'ellipse', 'triangle', 'diamond', 'pentagon', 'hexagon', 'star', 'arrow', 'doublearrow', 'parallelogram'];
    return `
    <div class="cv-main">
      <div class="cv-bar">
        <button class="cb" id="cv_undo" title="Ctrl+Z">${ICON.undo}撤销</button>
        <button class="cb" id="cv_redo" title="Ctrl+Shift+Z / Ctrl+Y">${ICON.redo}重做</button>
        <span class="cv-sep"></span>
        <div class="cv-ins" id="cv_ins">
          <button class="cb" id="cv_insbtn" title="插入文本或预设形状">${ICON.plus}插入 ${ICON.chev}</button>
          <div class="cv-menu" id="cv_menu">
            <div class="cv-menu-t">文本</div>
            <button class="cv-mi" data-ins="text">${ICON.txt}<span>文本框</span></button>
            <div class="cv-menu-t">线条</div>
            <div class="cv-grid">
              <button class="cv-sh" data-ins="point" title="点（连续放置，Esc 退出）">${shapeIcon('point')}<span>点</span></button>
              <button class="cv-sh" data-ins="line" title="折线：连续点击，双击或 Enter 完成；按住 Shift 约束水平/竖直/45°">${shapeIcon('line')}<span>折线</span></button>
              <button class="cv-sh" data-ins="poly" title="多边形：连续点击，双击或 Enter 完成；按住 Shift 约束 45°">${shapeIcon('poly')}<span>多边形</span></button>
            </div>
            <div class="cv-menu-t">预设形状（拖拽绘制，Shift 正方形/正圆）</div>
            <div class="cv-grid">
              ${boxKinds.map(k => `<button class="cv-sh" data-ins="${k}" title="${SHAPE_LABEL[k]}">${shapeIcon(k)}<span>${SHAPE_LABEL[k]}</span></button>`).join('')}
            </div>
          </div>
        </div>
        <button class="cb" id="cv_done" style="display:none" title="完成当前折线/面 (Enter)">${ICON.done}完成</button>
        <button class="cb" id="cv_cancel" style="display:none" title="取消当前绘制 (Esc)">${ICON.no}取消</button>
        <button class="cb" id="cv_dup" title="Ctrl+D / Ctrl+拖动复制">${ICON.dup}复制</button>
        <button class="cb" id="cv_hide">${ICON.hide}显隐</button>
        <span class="cv-sep"></span>
        <button class="cb danger" id="cv_reset">${ICON.reset}全部重置</button>
        <span class="cv-sep"></span>
        <button class="cb" id="cv_zout">－</button><span class="cv-zoom" id="cv_zoomlbl">100%</span><button class="cb" id="cv_zin">＋</button>
        <button class="cb" id="cv_zfit">适应</button><button class="cb" id="cv_z100">100%</button>
        <span class="cv-hint">拖拽移动 · 拖角缩放（Shift 等比）· 拖顶旋转 · Shift/Ctrl 点击多选 · Ctrl+拖动复制 · Ctrl+滚轮缩放 · 右键平移或元素菜单 · 双击文字改内容 · 左栏双击改名</span>
        <span class="cv-cnt">元素改动 <b id="cv_cnt">0</b></span>
      </div>
      <div class="cv-stage" id="cv_stage"><div class="cv-wrap" id="cv_wrap">@@SVG@@</div></div>
    </div>`;
  }

  function panelHTML() {
    const sec = (id, key, title, body) => `
      <div class="cv-sec" id="${id}" data-sec="${key}">
        <button class="cv-sec-h" type="button">${ICON.chev}<span>${title}</span></button>
        <div class="cv-sec-b">${body}</div>
      </div>`;
    return `
    <div class="cv-empty" id="cv_empty">未选中元素。<br>在中间画布点击文字 / 线条 / 色块，直接拖拽移动、拖角缩放、拖顶旋转；或双击文字改内容。</div>
    <div class="cv-props" id="cv_props" style="display:none">
      <div class="cv-ptype" id="cv_ptype">元素</div>
      <div class="cv-row" id="cv_g_text"><label>内容</label><input type="text" id="cv_p_text"></div>
      ${sec('cv_g_xf', 'xf', '位置 / 变换', `
        <div class="cv-row"><label>X</label><div class="cv-num"><input type="number" id="cv_p_dx" step="1"></div><label style="width:24px">Y</label><div class="cv-num"><input type="number" id="cv_p_dy" step="1"></div></div>
        <div class="cv-row"><label>宽缩</label><input type="range" class="cv-r" id="cv_p_sx" min="0.1" max="8" step="0.02"><div class="cv-num"><input type="number" id="cv_p_sxN" step="0.05"></div></div>
        <div class="cv-row"><label>高缩</label><input type="range" class="cv-r" id="cv_p_sy" min="0.1" max="8" step="0.02"><div class="cv-num"><input type="number" id="cv_p_syN" step="0.05"></div></div>
        <div class="cv-row"><label>旋转</label><input type="range" class="cv-r" id="cv_p_rot" min="-180" max="180" step="1"><div class="cv-num"><input type="number" id="cv_p_rotN" step="1"></div></div>
        <div class="cv-row"><label>透明</label><input type="range" class="cv-r" id="cv_p_op" min="0" max="1" step="0.05"><div class="cv-num"><input type="number" id="cv_p_opN" step="0.05" min="0" max="1"></div></div>`)}
      ${sec('cv_g_font', 'font', '文字样式', `
        <div class="cv-row"><label>字体</label><select id="cv_p_font">
          <option value="Helvetica,Arial,sans-serif">Helvetica/Arial</option><option value="Arial">Arial</option>
          <option value="Times New Roman,serif">Times/衬线</option><option value="Georgia,serif">Georgia</option>
          <option value="Courier New,monospace">Courier/等宽</option>
          <option value="Microsoft YaHei,微软雅黑,sans-serif">微软雅黑(中)</option><option value="SimHei,黑体,sans-serif">黑体(中)</option>
          <option value="SimSun,宋体,serif">宋体(中)</option><option value="KaiTi,楷体,serif">楷体(中)</option></select></div>
        <div class="cv-row"><label>字号</label><input type="range" class="cv-r" id="cv_p_size" min="4" max="96" step="0.5"><div class="cv-num"><input type="number" id="cv_p_sizeN" step="0.5"></div></div>
        <div class="cv-row"><label>颜色</label><input type="color" class="cv-c" id="cv_p_fill"><div class="cv-tgl"><button id="cv_p_bold">B</button><button id="cv_p_ital">I</button></div></div>`)}
      ${sec('cv_g_vec', 'vec', '矢量样式', `
        <div class="cv-row"><label>填充</label><input type="color" class="cv-c" id="cv_p_vfill"><button class="cb" id="cv_p_vfill0" style="height:30px;padding:0 10px">无</button></div>
        <div class="cv-row"><label>描边</label><input type="color" class="cv-c" id="cv_p_vstroke"></div>
        <div class="cv-row"><label>线宽</label><input type="range" class="cv-r" id="cv_p_vw" min="0" max="10" step="0.1"><div class="cv-num"><input type="number" id="cv_p_vwN" step="0.1"></div></div>`)}
      <div class="cv-btnrow"><button class="cb" id="cv_p_reset" title="只复位选中元素的位置/缩放/旋转，不影响其他元素">${ICON.reset}复位变换</button><button class="cb danger" id="cv_p_del" title="删除选中元素（原 GMT 元素导出时隐藏）">${ICON.trash}删除</button></div>
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
    if (listHost) {
      listHost.innerHTML = `
      <div class="cv-ex" id="cv_ex">
        <button class="cv-ex-h" id="cv_exh" type="button">${ICON.chev}<span>元素</span><span class="cnt" id="cv_excnt">0</span></button>
        <div class="cv-ex-b">
          <div class="cv-tabs" id="cv_tabs">
            <button data-f="all" class="on">全部</button><button data-f="txt">文字</button><button data-f="vec">矢量</button><button data-f="new">自绘</button>
          </div>
          <div class="cv-find">${ICON.find}<input id="cv_find" placeholder="筛选元素…" autocomplete="off" spellcheck="false"></div>
          <div class="cv-rows" id="cv_rows"></div>
          <div class="cv-exfoot" id="cv_exfoot"></div>
        </div>
      </div>`;
    }
    let listFilter = 'all', listQuery = '';
    const el = id => document.getElementById(id);
    const gById = id => document.getElementById(id);
    function readUI(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } }
    function saveUI(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
    if (listHost) {
      const ex = el('cv_ex');
      if (readUI('gvl.cv.ex', '0') === '1') ex.classList.add('closed');
      el('cv_exh').onclick = () => {
        ex.classList.toggle('closed'); saveUI('gvl.cv.ex', ex.classList.contains('closed') ? '1' : '0');
      };
      el('cv_tabs').querySelectorAll('button').forEach(b => b.onclick = () => {
        listFilter = b.dataset.f;
        el('cv_tabs').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
        buildList();
      });
      let ft = 0;
      el('cv_find').addEventListener('input', e => {
        listQuery = e.target.value.trim(); clearTimeout(ft); ft = setTimeout(buildList, 120);
      });
    }
    propsHost.querySelectorAll('.cv-sec').forEach(sec => {
      const key = 'gvl.cv.sec.' + sec.dataset.sec;
      if (readUI(key, '0') === '1') sec.classList.add('closed');
      const h = sec.querySelector('.cv-sec-h');
      if (h) h.onclick = () => { sec.classList.toggle('closed'); saveUI(key, sec.classList.contains('closed') ? '1' : '0'); };
    });

    const stage = document.getElementById('cv_stage');
    const wrap = document.getElementById('cv_wrap');
    const svg = wrap.querySelector('svg');
    if (!svg) return { collect: () => ({}), applyOverlay: () => 0, resetElements: () => {}, countDirty: () => 0, destroy: () => {} };

    const state = {};
    let selected = new Set(), zoom = 1, spaceDown = false, addMode = false, newN = 0, autoFit = true;
    let drawTool = null, draft = [], draftG = null;   // 点/线/面绘制状态
    const hist = [], future = [];

    function bboxOf(g) { return (g.dataset.bbox || '0 0 0 0').split(' ').map(Number); }
    function st(id) { return state[id] || (state[id] = { dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, op: 1 }); }
    function dirty(e) {
      return e && (e.dx || e.dy || (e.sx !== undefined && e.sx !== 1) || (e.sy !== undefined && e.sy !== 1) ||
        e.rot || (e.op !== undefined && e.op !== 1) || e.text !== undefined || e.fontFamily !== undefined ||
        e.fontSize !== undefined || e.bold !== undefined || e.italic !== undefined || e.fill !== undefined ||
        e.stroke !== undefined || e.width !== undefined || e.hidden || e._new || e.name !== undefined);
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

    /* ---------- 新增形状（点 / 折线 / 多边形 / 预设形状） ----------
       新形状与 GMT 元素一样是 <g class="vec"><path/></g>, 因此天然支持选中/移动/缩放/旋转/
       改填充描边/显隐/撤销; 额外在 state 里记 _new/_shape/_pts (PDF 点坐标) + _r, 供
       collect() 导出、applyOverlay() 重建、reapply.py 烘焙。 */
    function rebuildShape(id, e) {
      if (!e || !e._shape || !(e._pts || []).length) return null;
      const def = SHAPE_DEF[e._shape] || SHAPE_DEF.line, r = e._r == null ? def.r : e._r;
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('class', 'vec'); g.id = id; g.dataset.new = '1'; g.dataset.shape = e._shape;
      g.dataset.bbox = (e._bbox && e._bbox.split(' ').length === 4) ? e._bbox : bboxOfPts(e._shape, e._pts, r).join(' ');
      const p = document.createElementNS(NS, 'path');
      p.setAttribute('d', shapeD(e._shape, e._pts, r));
      p.setAttribute('fill', e.fill !== undefined ? e.fill : def.fill);
      p.setAttribute('stroke', e.stroke !== undefined ? e.stroke : def.stroke);
      p.setAttribute('stroke-width', e.width !== undefined ? e.width : def.width);
      g.appendChild(p); svg.appendChild(g);
      return g;
    }
    function nextId(prefix) { let id; do { id = prefix + (newN++); } while (gById(id) || state[id]); return id; }
    function createShape(kind, pts) {
      const nid = nextId('shp_');
      const def = SHAPE_DEF[kind], ps = pts.map(q => [f2(q[0]), f2(q[1])]);
      commit();
      state[nid] = { dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, op: 1,
                     _new: 1, _shape: kind, _pts: ps, _r: def.r, _bbox: bboxOfPts(kind, ps, def.r).join(' ') };
      rebuildShape(nid, state[nid]);
      selectOnly(nid); notify(); buildList();
      return nid;
    }
    // 撤销/重做后让画布上的"新增形状"与 state 对齐: 多出来的删掉, 缺的补回来。
    function syncNewShapes() {
      svg.querySelectorAll('g.vec[data-new]').forEach(g => { if (!state[g.id]) g.remove(); });
      for (const id in state) if (state[id]._shape && !gById(id)) rebuildShape(id, state[id]);
    }

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
    function undo() { if (!hist.length) return; future.push(JSON.stringify(state)); clearState(); Object.assign(state, JSON.parse(hist.pop())); syncNewShapes(); renderAll(); syncPanel(); }
    function redo() { if (!future.length) return; hist.push(JSON.stringify(state)); clearState(); Object.assign(state, JSON.parse(future.pop())); syncNewShapes(); renderAll(); syncPanel(); }
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

    function revealInList(id) {
      if (!listHost) return;
      const ex = el('cv_ex');
      if (ex && ex.classList.contains('closed')) { ex.classList.remove('closed'); saveUI('gvl.cv.ex', '0'); }
      const rows = el('cv_rows'); if (!rows) return;
      const findRow = () => [...rows.querySelectorAll('.cv-el')].find(r => r.dataset.id === id);
      let row = findRow();
      if (!row && (listFilter !== 'all' || listQuery)) {   // 被筛选藏起来了: 清空筛选, 保证选中项可见
        listFilter = 'all'; listQuery = '';
        const f = el('cv_find'); if (f) f.value = '';
        const tabs = el('cv_tabs');
        if (tabs) tabs.querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.f === 'all'));
        buildList(); row = findRow();
      }
      if (row) row.scrollIntoView({ block: 'nearest' });
    }
    function selectOnly(id) { selected = new Set([id]); syncPanel(); drawUI(); buildList(); revealInList(id); }
    function toggleSel(id) { if (selected.has(id)) selected.delete(id); else selected.add(id); syncPanel(); drawUI(); buildList(); revealInList(id); }

    function onDown(ev) {
      if (drawTool) {                                  // 绘制模式: 预设形状按住拖拽, 其余点按落点
        if (isBoxShape(drawTool)) startBoxDraw(ev);
        ev.preventDefault(); return;
      }
      if (addMode) { ev.preventDefault(); return; }
      const h = ev.target.closest ? ev.target.closest('.cv-ui-h,.cv-ui-rot') : null;
      if (h) { startTransform(h, ev); return; }
      if (spaceDown || ev.button === 2) return;
      const g = targetG(ev);
      if (!g) { startMarquee(ev); return; }
      if (ev.shiftKey || ev.ctrlKey || ev.metaKey) {
        // PPT 手感: Shift/Ctrl+点击 = 加选/取消; Ctrl 按住拖过 5px 才是"复制并拖动",
        // 纯点击不会先复制一份出来。
        if (ev.shiftKey) { toggleSel(g.id); return; }
        const wasSel = selected.has(g.id), sx = ev.clientX, sy = ev.clientY;
        let armed = true, moved = false;
        const cleanup0 = () => {
          window.removeEventListener('pointermove', move0);
          window.removeEventListener('pointerup', stop0);
        };
        const stop0 = () => {
          if (!armed) return;
          armed = false; cleanup0();
          if (!moved) toggleSel(g.id);
        };
        const move0 = e2 => {
          if (!armed || Math.abs(e2.clientX - sx) + Math.abs(e2.clientY - sy) < 5) return;
          moved = true; armed = false; cleanup0();
          if (!wasSel) { selected.add(g.id); syncPanel(); drawUI(); buildList(); }
          if (!selected.size) return;
          commit();
          const copies = [...selected].map(id => duplicateElement(id)).filter(Boolean);
          if (copies.length) { selected = new Set(copies); syncPanel(); drawUI(); buildList(); }
          startMove(e2, true);
        };
        window.addEventListener('pointermove', move0);
        window.addEventListener('pointerup', stop0);
        return;
      }
      if (!selected.has(g.id)) selectOnly(g.id); else syncPanel();
      startMove(ev);
    }
    svg.addEventListener('pointerdown', onDown);
    function startMove(ev, skipCommit) {
      if (!selected.size) return; if (!skipCommit) commit();
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
      /* PPT 式缩放: 拖角 = 自由缩放 (对角锚定, Shift 等比), 拖边 = 单轴拉伸 (对边锚定)。
         锚点用原始 bbox 局部坐标; 拖动中锚点的屏幕位置保持不动。 */
      const AM = { nw: [b[2], b[3]], ne: [b[0], b[3]], se: [b[0], b[1]], sw: [b[2], b[1]],
                   n: [cx, b[3]], s: [cx, b[1]], e: [b[0], cy], w: [b[2], cy] };
      const Al = AM[kind];
      const vx = Al[0] - cx, vy = Al[1] - cy;      // 锚点相对中心 (未缩放), 只用于平移补偿
      const A0 = toRoot(g, Al[0], Al[1]);          // 锚点当前屏幕位置 (保持固定)
      const Hl = { nw: [b[0], b[1]], ne: [b[2], b[1]], se: [b[2], b[3]], sw: [b[0], b[3]],
                   n: [cx, b[1]], s: [cx, b[3]], e: [b[2], cy], w: [b[0], cy] };
      const HlA = [Hl[kind][0] - Al[0], Hl[kind][1] - Al[1]];  // 手柄-锚点 局部向量: 缩放分母(锚点固定, 手柄跟手)
      // 按下瞬间指针相对锚点的向量 (已含当前 sx/sy): Shift 等比时用它做"相对比例",
      // 否则已有缩放会被再乘一遍, 拖第一下就跳。
      const pS = svgPt(ev);
      const lrS = rotV(pS.x - A0[0], pS.y - A0[1], -rot0);
      const mvFn = e2 => {
        const p = svgPt(e2);
        // 以锚点 A0 为参考, 指针在"去旋转、未缩放"局部系; 缩放分母用 (手柄-锚点) 向量 HlA,
        // 使手柄严格跟手、锚点保持不动。旧写法用中心距离作分母, 手柄会过冲一个平移量。
        const lr = rotV(p.x - A0[0], p.y - A0[1], -rot0);
        let s1x = sx0, s1y = sy0;
        const corner = (kind === 'nw' || kind === 'ne' || kind === 'se' || kind === 'sw');
        if (corner) {
          if (e2.shiftKey) {                        // 等比: 取位移更大的轴算比例, 另一轴同倍; 手柄在该轴上严格跟手
            const hasX = Math.abs(lrS[0]) > 1e-6, hasY = Math.abs(lrS[1]) > 1e-6;
            const useX = hasX && (!hasY || Math.abs(lr[0] - lrS[0]) >= Math.abs(lr[1] - lrS[1]));
            const q = useX ? lr[0] / lrS[0] : (hasY ? lr[1] / lrS[1] : 1);
            s1x = Math.max(.02, sx0 * q); s1y = Math.max(.02, sy0 * q);
          } else {                                  // 自由缩放: 两轴独立跟手
            if (Math.abs(HlA[0]) > 1e-6) s1x = Math.max(.02, lr[0] / HlA[0]);
            if (Math.abs(HlA[1]) > 1e-6) s1y = Math.max(.02, lr[1] / HlA[1]);
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
          // 等比: 取位移更大的轴算比例, 另一轴同倍 (手柄在该轴上跟手)
          const dx0 = p0.x - A0[0], dy0 = p0.y - A0[1];
          const dx1 = p.x - A0[0], dy1 = p.y - A0[1];
          const hasX = Math.abs(dx0) > 1e-6, hasY = Math.abs(dy0) > 1e-6;
          const useX = hasX && (!hasY || Math.abs(dx1 - dx0) >= Math.abs(dy1 - dy0));
          let q = useX ? dx1 / dx0 : (hasY ? dy1 / dy0 : 1);
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
        if (x1 - x0 < 2 && y1 - y0 < 2) { if (!ev.shiftKey && !ev.ctrlKey && !ev.metaKey) { selected = new Set(); syncPanel(); drawUI(); buildList(); } return; }
        // 中心落在框内即选中 (原来要求四角全部在框内, 底图那种跨满全图的色块永远选不上)
        const add = new Set();
        svg.querySelectorAll('g.vec,g.txt').forEach(g => {
          const b = bboxOf(g), c = toRoot(g, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2);
          if (c[0] >= x0 && c[0] <= x1 && c[1] >= y0 && c[1] <= y1) add.add(g.id);
        });
        selected = (ev.shiftKey || ev.ctrlKey || ev.metaKey) ? new Set([...selected, ...add]) : add; syncPanel(); drawUI(); buildList();
      };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
    }

    let pan = null, panMoved = false;
    function stageDown(ev) { if (spaceDown || ev.button === 2) { panMoved = false; pan = { x: ev.clientX, y: ev.clientY, l: stage.scrollLeft, t: stage.scrollTop, moved: false }; stage.classList.add('panning'); ev.preventDefault(); } }
    function winMove(ev) { if (pan) { if (Math.abs(ev.clientX - pan.x) + Math.abs(ev.clientY - pan.y) > 4) pan.moved = true; stage.scrollLeft = pan.l - (ev.clientX - pan.x); stage.scrollTop = pan.t - (ev.clientY - pan.y); } }
    function winUp() { panMoved = !!(pan && pan.moved); pan = null; stage.classList.remove('panning'); }
    stage.addEventListener('pointerdown', stageDown);
    window.addEventListener('pointermove', winMove);
    window.addEventListener('pointerup', winUp);
    function onCtx(ev) {
      ev.preventDefault();
      if (panMoved) { panMoved = false; return; }   // 右键拖动 = 平移画布, 不弹菜单
      if (drawTool || addMode) return;
      const g = targetG(ev); if (!g) return;
      if (!selected.has(g.id)) selectOnly(g.id);
      ctxOpen(g.id, ev.clientX, ev.clientY);
    }
    stage.addEventListener('contextmenu', onCtx);
    function onDbl(ev) {
      if (drawTool) { ev.preventDefault(); finishDraft(); return; }
      const g = targetG(ev); if (!g || !g.classList.contains('txt')) return; selectOnly(g.id); el('cv_p_text').focus(); el('cv_p_text').select();
    }
    svg.addEventListener('dblclick', onDbl);

    function setZoom(z) { zoom = Math.min(8, Math.max(.1, z)); wrap.style.transform = `scale(${zoom})`; el('cv_zoomlbl').textContent = Math.round(zoom * 100) + '%'; drawUI(); }
    function onWheel(ev) {
      if (ev.ctrlKey) {
        ev.preventDefault(); const r = stage.getBoundingClientRect(); const mx = ev.clientX - r.left + stage.scrollLeft, my = ev.clientY - r.top + stage.scrollTop;
        const nz = Math.min(8, Math.max(.1, zoom * (ev.deltaY < 0 ? 1.1 : .9)));
        stage.scrollLeft = mx * (nz / zoom) - (ev.clientX - r.left); stage.scrollTop = my * (nz / zoom) - (ev.clientY - r.top);
        autoFit = false; setZoom(nz);
      }
    }
    stage.addEventListener('wheel', onWheel, { passive: false });
    el('cv_zin').onclick = () => { autoFit = false; setZoom(zoom * 1.2); };
    el('cv_zout').onclick = () => { autoFit = false; setZoom(zoom / 1.2); };
    el('cv_z100').onclick = () => { autoFit = false; setZoom(1); };
    function zfit() { autoFit = true; setZoom(1); const r = svg.getBoundingClientRect(); const k = Math.min((stage.clientHeight - 48) / (r.height / zoom), (stage.clientWidth - 48) / (r.width / zoom)); setZoom(k); }
    el('cv_zfit').onclick = zfit; setTimeout(zfit, 0);
    // 窗口最大化/还原/拖边缩放后, 画布跟着可视区重新适配; 用户手动缩放过则保持原比例。
    let _sw = 0, _sh = 0, _fitRaf = 0;
    const ro = new ResizeObserver(() => {
      const w = stage.clientWidth, h = stage.clientHeight;
      if (Math.abs(w - _sw) < 2 && Math.abs(h - _sh) < 2) return;
      _sw = w; _sh = h;
      if (autoFit) { cancelAnimationFrame(_fitRaf); _fitRaf = requestAnimationFrame(zfit); }   // 避免 RO 回调里同步改布局
    });
    ro.observe(stage);

    function onKeyDown(e) {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
      if (drawTool && e.key === 'Escape') { e.preventDefault(); clearDraft(); setDrawTool(null); return; }
      if (drawTool && e.key === 'Enter') { e.preventDefault(); finishDraft(); return; }
      if (e.code === 'Space') { spaceDown = true; stage.classList.add('pan'); e.preventDefault(); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); return; }
      if (e.ctrlKey && e.key.toLowerCase() === 'd') { e.preventDefault(); doDup(); return; }
      if (e.key === 'Escape' && ctx.classList.contains('open')) { hideCtx(); return; }
      if (e.key === 'Delete') { e.preventDefault(); deleteSel(); return; }
      if (e.key === 'F2' && selected.size === 1) { e.preventDefault(); startRename([...selected][0]); return; }
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
      el('cv_ptype').textContent = (isTxt ? '文字 ' : '矢量 ') +
        ((labelOf(g) && labelOf(g) !== id) ? labelOf(g) + ' · ' + id : id) +
        (selected.size > 1 ? ` (+${selected.size - 1})` : '');
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

    /* ---------- 单元素操作: 复位变换 / 重命名 / 删除 / 缩放到元素 ---------- */
    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g,
        c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    function autoLabel(g) {
      if (!g) return '';
      if (g.classList.contains('txt')) return g.dataset.content || g.id;
      if (g.dataset.new === '1') return SHAPE_LABEL[g.dataset.shape] || '形状';
      return g.dataset.layer || '矢量';
    }
    function labelOf(g) { const e = g && state[g.id]; return (e && e.name) || autoLabel(g); }
    function resetXf(id) {
      const g = gById(id); if (!g) return;
      const e = st(id);
      e.dx = 0; e.dy = 0; e.sx = 1; e.sy = 1; e.rot = 0;
      applyEl(g);
    }
    // 只复位选中元素的位置/缩放/旋转, 保留透明度、文字、样式、显隐与自绘几何;
    // 用于"把上层临时挪开 -> 删掉下面那个 -> 再把上层放回去"的场景。
    function resetSelXf() {
      if (!selected.size) return; commit();
      selected.forEach(id => resetXf(id));
      drawUI(); refresh(); syncPanel();
    }
    function removable(g) {
      return !!g && (g.dataset.new === '1' || /^txt_new/.test(g.id) ||
        !!(state[g.id] && state[g.id]._clone));
    }
    // 原 GMT 元素不能从 SVG 里真的删掉(导出还要用), 用 hidden 让它在画布和导出中消失;
    // 自绘形状与复制出来的副本才是真正移除。
    function deleteSel() {
      if (!selected.size) return; commit();
      const ids = [...selected];
      ids.forEach(id => {
        const g = gById(id); if (!g) return;
        if (removable(g)) { g.remove(); delete state[id]; return; }
        const e = st(id); e.hidden = true; applyEl(g);
      });
      selected = new Set(ids.filter(id => { const g = gById(id); return g && !(state[id] && state[id].hidden); }));
      drawUI(); refresh(); syncPanel();
    }
    function toggleHidden(id) {
      const g = gById(id); if (!g) return;
      const e = st(id); e.hidden = !e.hidden; applyEl(g);
    }
    function zoomToEl(id) {
      const g = gById(id); if (!g) return;
      const cs = corners(g);
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      cs.forEach(p => { x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); });
      const w = Math.max(1, x1 - x0), h = Math.max(1, y1 - y0);
      autoFit = false;
      const k = Math.min(8, Math.max(.1, Math.min((stage.clientWidth - 120) / w, (stage.clientHeight - 120) / h)));
      setZoom(k);
      requestAnimationFrame(() => {
        const r = g.getBoundingClientRect(), sr = stage.getBoundingClientRect();
        stage.scrollLeft += (r.left + r.width / 2) - (sr.left + stage.clientWidth / 2);
        stage.scrollTop += (r.top + r.height / 2) - (sr.top + stage.clientHeight / 2);
      });
    }
    function startRename(id) {
      const g = gById(id); if (!g || !listHost) return;
      const rows = el('cv_rows'); if (!rows) return;
      const findRow = () => [...rows.querySelectorAll('.cv-el')].find(r => r.dataset.id === id);
      let row = findRow();
      if (!row) {   // 被筛选/搜索藏起来了: 先清空筛选, 再开始改名
        listFilter = 'all'; listQuery = '';
        el('cv_find').value = '';
        el('cv_tabs').querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.f === 'all'));
        buildList(); row = findRow();
      }
      if (!row) return;
      const nm = row.querySelector('.nm'); if (!nm) return;
      const base = autoLabel(g), prev = (state[id] && state[id].name) || base;
      const inp = document.createElement('input');
      inp.type = 'text'; inp.value = prev; inp.maxLength = 40;
      nm.textContent = ''; nm.appendChild(inp);
      inp.focus(); inp.select();
      let done = false;
      const finish = ok => {
        if (done) return; done = true;
        const v = inp.value.trim();
        if (ok && v !== prev) {
          commit();
          const e = st(id);
          if (v && v !== base) e.name = v; else delete e.name;
          refresh();
        } else {
          buildList();
        }
      };
      inp.onkeydown = e2 => {
        e2.stopPropagation();
        if (e2.key === 'Enter') { e2.preventDefault(); finish(true); }
        else if (e2.key === 'Escape') { e2.preventDefault(); finish(false); }
      };
      inp.onblur = () => finish(true);
      inp.onpointerdown = e2 => e2.stopPropagation();
      inp.onclick = e2 => e2.stopPropagation();
    }

    /* ---------- 左栏元素右键菜单 (仿 PS 图层菜单) ---------- */
    const ctx = document.createElement('div');
    ctx.className = 'cv-ctx';
    document.body.appendChild(ctx);
    function hideCtx() { ctx.classList.remove('open'); }
    function closeCtxOutside(e) { if (ctx.classList.contains('open') && !ctx.contains(e.target)) hideCtx(); }
    document.addEventListener('pointerdown', closeCtxOutside);
    document.addEventListener('scroll', hideCtx, true);
    window.addEventListener('resize', hideCtx);
    function ctxOpen(id, x, y) {
      const g = gById(id); if (!g) return;
      const multi = selected.size > 1, en = st(id), rm = removable(g);
      const items = [
        ['focus', ICON.focus, '缩放到元素', ''],
        'sep',
        ['reset', ICON.reset, '复位变换', multi ? '选中 ' + selected.size + ' 个' : ''],
        ['rename', ICON.edit, '重命名', 'F2'],
        'sep',
        ['toggle', en.hidden ? ICON.eye : ICON.eyeOff, en.hidden ? '显示元素' : '隐藏元素', ''],
        ['dup', ICON.dup, '复制元素', 'Ctrl+D'],
        ['del', ICON.trash, rm ? '删除元素' : '删除元素（导出时隐藏）', 'Del', 'danger'],
      ];
      ctx.innerHTML = `<div class="cv-ctx-t">${esc(labelOf(g))}${multi ? ` · 共 ${selected.size} 个` : ''}</div>` +
        items.map(it => it === 'sep' ? '<div class="cv-ctxsep"></div>'
          : `<button class="cv-ctxi${it[4] ? ' ' + it[4] : ''}" type="button" data-act="${it[0]}">${it[1]}<span>${it[2]}</span>${it[3] ? `<kbd class="k">${it[3]}</kbd>` : ''}</button>`).join('');
      ctx.classList.add('open');
      const w = ctx.offsetWidth, h = ctx.offsetHeight;
      ctx.style.left = Math.max(6, Math.min(x, window.innerWidth - w - 6)) + 'px';
      ctx.style.top = Math.max(6, Math.min(y, window.innerHeight - h - 6)) + 'px';
      ctx.querySelectorAll('[data-act]').forEach(b => b.onclick = () => {
        const act = b.dataset.act, ids = selected.size ? [...selected] : [id];
        hideCtx();
        if (act === 'focus') zoomToEl(id);
        else if (act === 'rename') startRename(id);
        else if (act === 'reset') resetSelXf();
        else if (act === 'toggle') { commit(); ids.forEach(toggleHidden); drawUI(); refresh(); syncPanel(); }
        else if (act === 'dup') doDup();
        else if (act === 'del') deleteSel();
      });
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
    el('cv_p_reset').onclick = resetSelXf;
    el('cv_p_del').onclick = deleteSel;

    el('cv_undo').onclick = undo; el('cv_redo').onclick = redo;
    el('cv_hide').onclick = () => { if (!selected.size) return; eachSel(e => e.hidden = !e.hidden); };
    el('cv_dup').onclick = doDup;
    function duplicateElement(id) {
      const g = gById(id); if (!g) return null;
      const nid = nextId(g.classList.contains('txt') ? 'txt_dup_' : 'dup_');
      const c = g.cloneNode(true); c.id = nid;
      (g.parentNode || svg).appendChild(c);
      const src = st(id);
      const e = { ...src, dx: (src.dx || 0) + 10, dy: (src.dy || 0) + 10 };
      if (src._pts) e._pts = src._pts.map(p => [p[0], p[1]]);
      if (g.dataset.new !== '1') {      // 原 GMT 元素: 存下克隆的几何/文字, 导出时才能真的多出一个
        const cc = g.cloneNode(true); cc.id = nid;
        cc.removeAttribute('transform'); cc.style.opacity = ''; cc.style.display = '';
        e._clone = cc.outerHTML;
      }
      state[nid] = e; applyEl(c); return nid;
    }
    function doDup() {
      if (!selected.size) return; commit();
      const copies = [...selected].map(id => duplicateElement(id)).filter(Boolean);
      if (!copies.length) return;
      selected = new Set(copies); syncPanel(); drawUI(); buildList(); refresh();
    }

    /* ---------- 插入菜单: 文本 + 线条 + 预设形状 (PPT 式分类) ---------- */
    const insWrap = el('cv_ins'), insBtn = el('cv_insbtn'), menu = el('cv_menu');
    function menuOpen(v) { menu.classList.toggle('open', v); insBtn.classList.toggle('act', v || !!drawTool || addMode); }
    insBtn.onclick = e => { e.stopPropagation(); menuOpen(!menu.classList.contains('open')); };
    menu.querySelectorAll('[data-ins]').forEach(b => {
      b.onclick = e => {
        e.stopPropagation(); menuOpen(false);
        const k = b.dataset.ins;
        if (k === 'text') {
          setDrawTool(null); addMode = true; stage.classList.add('addtxt'); insBtn.classList.add('act');
        } else {
          addMode = false; stage.classList.remove('addtxt'); setDrawTool(k);
        }
      };
    });
    function closeMenuOutside(e) { if (!insWrap.contains(e.target)) menuOpen(false); }
    document.addEventListener('pointerdown', closeMenuOutside);

    /* ---------- 绘制工具: 点 / 折线 / 多边形 / 预设形状 ----------
       点: 单击即落一个点 (工具保持, 可连续放); 线/面: 连续单击落顶点 (按住 Shift 约束水平/竖直/45°),
       双击或 Enter 完成, Esc 取消并退出; 预设形状: 按住拖拽出包围盒 (Shift 正方形/正圆), 单击给默认大小。
       预览用 .cv-draft 图层, pointer-events:none, 不干扰点选。 */
    function setDrawTool(t) {
      if (drawTool === t) t = null;               // 再点一次同一个按钮 = 退出
      if (t !== drawTool) clearDraft();
      drawTool = t;
      if (t) { addMode = false; stage.classList.remove('addtxt'); }
      menu.querySelectorAll('[data-ins]').forEach(b => b.classList.toggle('act', !!t && b.dataset.ins === t));
      insBtn.classList.toggle('act', !!t || addMode || menu.classList.contains('open'));
      stage.classList.toggle('draw', !!t);
    }
    function clearDraft() {
      draft.length = 0;
      if (draftG) { draftG.remove(); draftG = null; }
      el('cv_done').style.display = 'none'; el('cv_cancel').style.display = 'none';
    }
    function snap45(from, p) {
      const dx = p[0] - from[0], dy = p[1] - from[1];
      const step = Math.PI / 4, a = Math.round(Math.atan2(dy, dx) / step) * step;
      return [from[0] + Math.cos(a) * Math.hypot(dx, dy), from[1] + Math.sin(a) * Math.hypot(dx, dy)];
    }
    function draftRender(cursor, shift) {
      if (draftG) { draftG.remove(); draftG = null; }
      if (!drawTool || drawTool === 'point' || (!draft.length && !cursor)) return;
      if (cursor && draft.length && shift) cursor = snap45(draft[draft.length - 1], cursor);
      const pts = (cursor && draft.length) ? [...draft, cursor] : [...draft];
      const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'cv-draft');
      if (pts.length > 1) {
        const p = document.createElementNS(NS, 'path');
        p.setAttribute('d', shapeD('line', pts, 0));
        p.setAttribute('fill', 'none'); p.setAttribute('stroke', '#1f6feb');
        p.setAttribute('stroke-width', 1.2); p.setAttribute('stroke-dasharray', '4 3');
        g.appendChild(p);
      }
      draft.forEach(q => {
        const c = document.createElementNS(NS, 'circle');
        c.setAttribute('cx', q[0]); c.setAttribute('cy', q[1]);
        c.setAttribute('r', Math.max(2, 3 / zoom)); c.setAttribute('fill', '#1f6feb');
        g.appendChild(c);
      });
      svg.appendChild(g); draftG = g;
    }
    function addDraftPoint(p, shift) {
      if (drawTool === 'point') { createShape('point', [[p.x, p.y]]); return; }
      let q = [p.x, p.y];
      if (shift && draft.length) q = snap45(draft[draft.length - 1], q);
      draft.push(q);
      el('cv_done').style.display = ''; el('cv_cancel').style.display = '';
      draftRender();
    }
    function finishDraft() {
      if (!drawTool || drawTool === 'point') return;
      const pts = [];
      draft.forEach(q => {                          // 双击会重复落点, 这里把重合点并掉
        const last = pts[pts.length - 1];
        if (!last || Math.hypot(last[0] - q[0], last[1] - q[1]) > 2) pts.push(q);
      });
      if (pts.length >= 2) createShape(drawTool === 'poly' && pts.length < 3 ? 'line' : drawTool, pts);
      clearDraft();
      if (drawTool !== 'point') setDrawTool(null);   // 线/面画完回选中模式; 点保持, 方便连续落点
    }
    let boxDrawing = false;
    function startBoxDraw(ev) {
      if (boxDrawing) return; boxDrawing = true;
      const kind = drawTool, p0 = svgPt(ev);
      const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'cv-draft');
      const p = document.createElementNS(NS, 'path');
      p.setAttribute('fill', 'none'); p.setAttribute('stroke', '#1f6feb');
      p.setAttribute('stroke-width', '1.2'); p.setAttribute('stroke-dasharray', '4 3');
      g.appendChild(p); svg.appendChild(g); draftG = g;
      const boxPts = (p1, shift) => {
        let x1 = p1.x, y1 = p1.y;
        if (shift) {
          const dx = x1 - p0.x, dy = y1 - p0.y, s = Math.max(Math.abs(dx), Math.abs(dy));
          x1 = p0.x + (dx < 0 ? -s : s); y1 = p0.y + (dy < 0 ? -s : s);
        }
        return [[Math.min(p0.x, x1), Math.min(p0.y, y1)], [Math.max(p0.x, x1), Math.max(p0.y, y1)]];
      };
      const mv = e2 => { p.setAttribute('d', shapeD(kind, boxPts(svgPt(e2), e2.shiftKey), 0)); };
      const up = e2 => {
        window.removeEventListener('pointermove', mv); window.removeEventListener('pointerup', up);
        boxDrawing = false;
        let pts = boxPts(svgPt(e2), e2.shiftKey);
        if (pts[1][0] - pts[0][0] < 3 && pts[1][1] - pts[0][1] < 3) {
          const w = 90, h = 64;                    // 单击 = 默认大小, 居中落点
          pts = [[p0.x - w / 2, p0.y - h / 2], [p0.x + w / 2, p0.y + h / 2]];
        }
        clearDraft(); createShape(kind, pts); setDrawTool(null);
      };
      window.addEventListener('pointermove', mv); window.addEventListener('pointerup', up);
      ev.preventDefault();
    }
    el('cv_done').onclick = finishDraft;
    el('cv_cancel').onclick = () => { clearDraft(); setDrawTool(null); };
    function onDrawMove(ev) {
      if (!drawTool || drawTool === 'point' || isBoxShape(drawTool) || !draft.length) return;
      const p = svgPt(ev); draftRender([p.x, p.y], ev.shiftKey);
    }
    svg.addEventListener('pointermove', onDrawMove);

    function onClickPlace(ev) {
      if (drawTool) { addDraftPoint(svgPt(ev), ev.shiftKey); return; }
      if (!addMode) return; const p = svgPt(ev); const txt = prompt('文字内容:', '标注'); if (txt === null) return;
      const nid = nextId('txt_new'); const g = document.createElementNS(NS, 'g'); g.setAttribute('class', 'txt'); g.id = nid;
      g.dataset.bbox = `${p.x} ${p.y} ${p.x} ${p.y}`; g.dataset.content = txt;
      const t = document.createElementNS(NS, 'text'); t.setAttribute('x', p.x); t.setAttribute('y', p.y); t.setAttribute('font-size', '12'); t.setAttribute('fill', '#000000'); t.textContent = txt; g.appendChild(t);
      (svg.querySelector('#txt-layer') || svg).appendChild(g);
      state[nid] = { dx: 0, dy: 0, sx: 1, sy: 1, rot: 0, op: 1 }; addMode = false; insBtn.classList.remove('act'); stage.classList.remove('addtxt'); selectOnly(nid); refresh();
    }
    svg.addEventListener('click', onClickPlace);

    el('cv_reset').onclick = resetElements;

    function buildList() {
      if (!listHost) return;
      const rows = el('cv_rows'); if (!rows) return;
      const gs = [...svg.querySelectorAll('g.txt,g.vec')].filter(g => g.id && g.id !== 'cvui');
      const kindOf = g => g.classList.contains('txt') ? 'txt' : (g.dataset.new === '1' ? 'new' : 'vec');
      const cnt = { txt: 0, vec: 0, new: 0 };
      gs.forEach(g => cnt[kindOf(g)]++);
      el('cv_excnt').textContent = gs.length;
      el('cv_exfoot').innerHTML = `<b>${cnt.txt}</b> 文字 · <b>${cnt.vec}</b> 矢量 · <b>${cnt.new}</b> 自绘` +
        '<span style="margin-left:auto;opacity:.75">右键更多</span>';
      const q = listQuery.toLowerCase();
      const vis = gs.filter(g => {
        const k = kindOf(g);
        if (listFilter !== 'all' && k !== listFilter) return false;
        if (!q) return true;
        const nm = labelOf(g);
        return (g.id + ' ' + nm).toLowerCase().includes(q);
      });
      rows.innerHTML = '';
      if (!vis.length) {
        rows.innerHTML = `<div class="cv-cap">${q ? '没有匹配的元素' : '暂无元素。点上方「插入」添加文本或形状。'}</div>`;
        return;
      }
      const MAX = 400, shown = vis.slice(0, MAX);
      shown.forEach(g => {
        const kind = kindOf(g), en = state[g.id] || {};
        const row = document.createElement('div');
        row.dataset.id = g.id;
        row.className = 'cv-el' + (selected.has(g.id) ? ' on' : '') + (en.hidden ? ' t-off' : '');
        const ti = document.createElement('span'); ti.className = 'ti';
        ti.innerHTML = kind === 'txt' ? ICON.txt : (kind === 'new' ? shapeIcon(g.dataset.shape) : ICON.vec);
        const nm = document.createElement('span'); nm.className = 'nm';
        const label = labelOf(g);
        nm.textContent = label; nm.title = label + '（双击改名）';
        nm.ondblclick = e2 => { e2.stopPropagation(); startRename(g.id); };
        const ix = document.createElement('span'); ix.className = 'ix'; ix.textContent = g.id; ix.title = g.id;
        const eye = document.createElement('button'); eye.type = 'button'; eye.className = 'eye';
        eye.title = en.hidden ? '显示' : '隐藏'; eye.innerHTML = en.hidden ? ICON.eyeOff : ICON.eye;
        eye.onclick = e2 => {
          e2.stopPropagation(); commit();
          const x = st(g.id); x.hidden = !x.hidden; applyEl(g); buildList(); refresh(); syncPanel();
        };
        const more = document.createElement('button'); more.type = 'button'; more.className = 'more';
        more.title = '更多操作（右键）'; more.innerHTML = ICON.more;
        more.onclick = e2 => {
          e2.stopPropagation();
          const r = more.getBoundingClientRect();   // 选中会重建列表, 先量位置
          if (!selected.has(g.id)) selectOnly(g.id);
          ctxOpen(g.id, r.left, r.bottom + 4);
        };
        row.onclick = e2 => {
          if (e2.ctrlKey || e2.metaKey) toggleSel(g.id); else selectOnly(g.id);
        };
        row.oncontextmenu = e2 => {
          e2.preventDefault(); e2.stopPropagation();
          if (!selected.has(g.id)) selectOnly(g.id);
          ctxOpen(g.id, e2.clientX, e2.clientY);
        };
        row.appendChild(ti); row.appendChild(nm); row.appendChild(ix); row.appendChild(eye); row.appendChild(more);
        rows.appendChild(row);
      });
      if (vis.length > MAX) {
        const cap = document.createElement('div'); cap.className = 'cv-cap';
        cap.textContent = `元素较多，仅显示前 ${MAX} 个；用上方筛选缩小范围。`;
        rows.appendChild(cap);
      }
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
        if (!g && e._shape && (e._pts || []).length) g = rebuildShape(id, e);   // 工程/overlay 里的新增点线面
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
      commit(); hideCtx();
      for (const id in state) {
        const g = gById(id); if (!g) continue;
        if (g.dataset.new === '1') { g.remove(); continue; }   // 自己画的点线面直接撤掉
        g.removeAttribute('transform'); g.style.opacity = ''; g.style.display = '';
        const t = g.querySelector('text'); if (t) t.textContent = g.dataset.content;
      }
      clearState(); selected = new Set(); clearDraft(); drawUI(); refresh(); syncPanel(); buildList();
    }

    refresh(); syncPanel(); buildList();

    function destroy() {
      if (ro) ro.disconnect(); cancelAnimationFrame(_fitRaf);
      document.removeEventListener('pointerdown', closeMenuOutside);
      document.removeEventListener('pointerdown', closeCtxOutside);
      document.removeEventListener('scroll', hideCtx, true);
      window.removeEventListener('resize', hideCtx);
      ctx.remove();
      svg.removeEventListener('pointerdown', onDown); svg.removeEventListener('dblclick', onDbl); svg.removeEventListener('click', onClickPlace); svg.removeEventListener('pointermove', onDrawMove);
      stage.removeEventListener('pointerdown', stageDown); stage.removeEventListener('wheel', onWheel); stage.removeEventListener('contextmenu', onCtx);
      window.removeEventListener('pointermove', winMove); window.removeEventListener('pointerup', winUp);
      window.removeEventListener('keydown', onKeyDown); window.removeEventListener('keyup', onKeyUp);
      stageHost.innerHTML = ''; propsHost.innerHTML = ''; if (listHost) listHost.innerHTML = '';
    }

    return { collect, applyOverlay, resetElements, countDirty, buildList, destroy };
  }

  return { init };
})();
