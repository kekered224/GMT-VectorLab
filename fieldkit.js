// fieldkit.js —— GMT 选项值字符串 <-> 结构化控件 的双向转换 (无 DOM, 可被 node 单测)
//
// 目标: 把 "命令级" 的 GMT 选项 (如 -R110/122/2/22, -W0.5p,black, -St0.35c)
//       拆成能画成 数值框+滑块 / 颜色选择 / 文本框 的结构; 再能忠实拼回 GMT 字符串。
// 原则: 认不出的 -> kind="raw" (纯文本框), 永远不是死路; 每个数值都给 slider+number。

(function (root) {
  "use strict";

  var NUM = /-?\d+(?:\.\d+)?/g;

  // 抽出字符串里所有数字, 返回 {skeleton, nums}; skeleton 用 \u0000i\u0000 占位
  function extractNums(str) {
    var nums = [], skel = "", last = 0, m, i = 0;
    NUM.lastIndex = 0;
    while ((m = NUM.exec(str)) !== null) {
      skel += str.slice(last, m.index) + "\u0000" + i + "\u0000";
      nums.push(parseFloat(m[0]));
      last = m.index + m[0].length;
      i++;
    }
    skel += str.slice(last);
    return { skeleton: skel, nums: nums };
  }

  function rebuild(skeleton, nums) {
    return skeleton.replace(/\u0000(\d+)\u0000/g, function (_, k) {
      var v = nums[+k];
      return (v === undefined || v === null || isNaN(v)) ? "0" : String(v);
    });
  }

  // 由当前值推滑块范围/步长 (number 输入才是精确控制, slider 只是方便)
  function sliderMeta(v) {
    v = Number(v) || 0;
    var a = Math.abs(v);
    var step = a >= 10 ? 1 : a >= 1 ? 0.1 : 0.05;
    var min, max;
    if (v > 0) { min = 0; max = Math.max(v * 3, v + 10); }
    else if (v < 0) { min = Math.min(v * 3, v - 10); max = 0; }
    else { min = 0; max = 10; }
    return { min: min, max: max, step: step };
  }

  var STYLES = { solid: 1, dashed: 1, dotted: 1, dash: 1, dot: 1,
                 "solid": 1, "-": 1, "+": 1 };
  var SYM_TYPES = [
    ["c", "圆 circle"], ["s", "方 square"], ["t", "三角 triangle"],
    ["i", "倒三角 inv.tri"], ["d", "菱形 diamond"], ["h", "六边形 hexagon"],
    ["g", "八边形 octagon"], ["p", "五边形 pentagon"], ["star", "星 star"],
    ["x", "X 十字"], ["+", "加号"], ["-", "减号"], ["w", "扇形 wedge"],
    ["a", "箭头 arc"], ["m", "自定义 custom"]
  ];

  function isNum(s) { return /^-?\d+(?:\.\d+)?$/.test(String(s).trim()); }

  // ---- 判定某 (module, flag, value) 该用哪种控件 ----
  function kindOf(module, baseflag, value) {
    switch (baseflag) {
      case "-R": return /\/.*\/.*\//.test(value) ? "region" : "raw";
      case "-J": return "numbers";
      case "-B": return value.indexOf('+t"') >= 0 ? "title" : "raw";
      case "-W": return "pen";
      case "-G": return "color";
      case "-S": return module === "coast" ? "color" : "symbol";
      case "-F": return value.indexOf("+f") >= 0 ? "fontsize" : "raw";
      case "-D": return "numbers";
      default: return "raw";
    }
  }

  // ---- 解析成结构化 data ----
  function parseField(module, key, value) {
    var baseflag = key.split("#")[0];
    var kind = kindOf(module, baseflag, value);
    var d = { kind: kind };

    if (kind === "region") {
      var parts = value.split("/");
      var nums = [];
      for (var i = 0; i < parts.length; i++) {
        var mm = /^(-?\d+(?:\.\d+)?)(.*)$/.exec(parts[i]);
        if (mm) { nums.push(parseFloat(mm[1])); if (i === parts.length - 1) d.suffix = mm[2]; }
        else { return { kind: "raw", text: value }; }
      }
      if (nums.length < 4) return { kind: "raw", text: value };
      d.w = nums[0]; d.e = nums[1]; d.s = nums[2]; d.n = nums[3];
      d.suffix = d.suffix || "";
      return d;
    }
    if (kind === "numbers") {
      var en = extractNums(value);
      if (!en.nums.length) return { kind: "raw", text: value };
      d.skeleton = en.skeleton; d.nums = en.nums; d.raw = value;
      return d;
    }
    if (kind === "title") {
      var idx = value.indexOf('+t"');
      var pre = value.slice(0, idx + 3);
      var rest = value.slice(idx + 3);
      var q = rest.indexOf('"');
      d.title = q >= 0 ? rest.slice(0, q) : rest;
      d.suffix = q >= 0 ? rest.slice(q + 1) : "";
      d.prefix = pre.slice(0, -3); // 不含 +t"
      return d;
    }
    if (kind === "pen") {
      var toks = value.split(","), width = null, unit = "p", style = "", color = "";
      for (var j = 0; j < toks.length; j++) {
        var t = toks[j];
        var wm = /^([\d.]+)([a-z]*)$/.exec(t);
        if (wm && width === null) { width = parseFloat(wm[1]); unit = wm[2] || "p"; }
        else if (STYLES[t]) { style = t; }
        else if (!color) { color = t; }
      }
      if (width === null) return { kind: "raw", text: value };
      d.width = width; d.unit = unit; d.style = style; d.color = color;
      return d;
    }
    if (kind === "color") { d.value = value; return d; }
    if (kind === "symbol") {
      var sm = /^([a-zA-Z]+)([\d.]+)([a-z]*)$/.exec(value);
      if (!sm) return { kind: "raw", text: value };
      d.type = sm[1]; d.size = parseFloat(sm[2]); d.unit = sm[3] || "c";
      return d;
    }
    if (kind === "fontsize") {
      var re = /\+f([\d.]+)([a-z]+),([^,]+),([^+]+)/;
      var fm = re.exec(value);
      if (!fm) return { kind: "raw", text: value };
      d.pre = value.slice(0, fm.index);
      d.post = value.slice(fm.index + fm[0].length);
      d.size = parseFloat(fm[1]); d.unit = fm[2]; d.family = fm[3]; d.color = fm[4];
      return d;
    }
    return { kind: "raw", text: value };
  }

  // ---- 拼回 GMT 字符串 ----
  function formatField(d) {
    switch (d.kind) {
      case "region":
        return [d.w, d.e, d.s, d.n].join("/") + (d.suffix || "");
      case "numbers":
        return rebuild(d.skeleton, d.nums);
      case "title":
        return d.prefix + '+t"' + d.title + '"' + d.suffix;
      case "pen": {
        var a = [];
        if (d.width !== null && d.width !== undefined && !isNaN(d.width)) a.push(d.width + (d.unit || "p"));
        if (d.style) a.push(d.style);
        if (d.color) a.push(d.color);
        return a.join(",");
      }
      case "color":
        return d.value;
      case "symbol":
        return d.type + d.size + (d.unit || "");
      case "fontsize":
        return d.pre + "+f" + d.size + d.unit + "," + d.family + "," + d.color + d.post;
      default:
        return d.text;
    }
  }

  // ---- 校验 (返回问题数组, 空=通过) ----
  function validate(d) {
    var errs = [];
    if (d.kind === "region") {
      if (!(d.w < d.e)) errs.push("区域: 西(west) 必须 < 东(east)");
      if (!(d.s < d.n)) errs.push("区域: 南(south) 必须 < 北(north)");
    }
    if (d.kind === "symbol" && !(d.size > 0)) errs.push("符号尺寸须 > 0");
    if (d.kind === "pen" && d.width !== null && !(d.width > 0)) errs.push("线宽须 > 0");
    if (d.kind === "numbers") d.nums.forEach(function (v, i) { if (isNaN(v)) errs.push("数值#" + i + " 非法"); });
    return errs;
  }

  var api = {
    NUM: NUM, extractNums: extractNums, rebuild: rebuild, sliderMeta: sliderMeta,
    kindOf: kindOf, parseField: parseField, formatField: formatField, validate: validate,
    SYM_TYPES: SYM_TYPES, isNum: isNum
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FK = api;
})(typeof window !== "undefined" ? window : globalThis);
