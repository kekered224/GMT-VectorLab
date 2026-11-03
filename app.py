#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py —— GMT VectorLab 桌面程序 (pywebview + WebView2)

一个真正的原生窗口桌面 App, 不开浏览器、不占端口:
  - 前端 ui.html (明亮简洁风) 内联 fieldkit.js 后交给 WebView2 渲染;
  - Python 通过 js_api 直接给 JS 提供 get_ir / render / save_overlay / open_overlay;
  - 渲染走 core.py: 命令级 overlay -> GMT 重渲染 -> (可选) 烘焙 #2 元素 overlay;
  - 源脚本永远只读 (sha256 前后比对)。

目录约定 (打包成 exe 后尤其重要):
  RES_DIR  = 随程序打包的资源 (ui.html / fieldkit.js) —— PyInstaller 下是 sys._MEIPASS
  WORK_DIR = 用户工作目录 (放 plot.sh 与数据, GMT 在此出图) —— 默认当前工作目录, 可用环境变量 GMT_WORK 覆盖

开发运行:  python app.py
"""
import os, sys, json, base64, traceback

import webview
from webview import FileDialog

import core

# pywebview 在 WinForms 宿主上会刷大量无害的 AccessibilityObject 递归告警, 降噪
import logging
logging.getLogger("pywebview").setLevel(logging.CRITICAL)


def _res_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _work_dir():
    return os.environ.get("GMT_WORK") or os.getcwd()


RES = _res_dir()
WORK = _work_dir()
SCRIPT = os.environ.get("GMT_SCRIPT", "plot.sh")


class Api:
    def __init__(self):
        self.win = None
        self.work = WORK
        self.script = None

    def _scan(self, work):
        try:
            names = [f for f in os.listdir(work)
                     if f.lower().endswith(".sh") and f != "rendered.sh"]
        except OSError:
            names = []
        names.sort()
        default = "plot.sh" if "plot.sh" in names else (names[0] if names else None)
        return names, default

    def _resolve(self, script):
        if script:
            return script
        if self.script and os.path.exists(os.path.join(self.work, self.script)):
            return self.script
        return self._scan(self.work)[1]

    # ---- 工作目录里的候选脚本 ----
    def list_scripts(self):
        try:
            names, default = self._scan(self.work)
            return {"work": self.work, "scripts": names, "default": default,
                    "current": self.script or default}
        except Exception:
            return {"error": traceback.format_exc()}

    # ---- 源脚本时间戳 (前端轮询, 用于外部改脚本后自动重载) ----
    def script_stamp(self, script=None):
        try:
            s = self._resolve(script)
            if not s:
                return {"error": "尚未选择 GMT 脚本"}
            sp = os.path.join(self.work, s)
            st = os.stat(sp)
            return {"script": s, "mtime": st.st_mtime, "size": st.st_size}
        except Exception:
            return {"error": traceback.format_exc()}

    # ---- 打开任意 GMT 脚本 (其所在目录成为工作目录) ----
    def open_script(self):
        try:
            if not self.win:
                return None
            res = self.win.create_file_dialog(
                FileDialog.OPEN, file_types=("GMT 脚本 (*.sh)", "所有文件 (*.*)"))
            if not res:
                return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            self.work = os.path.dirname(os.path.abspath(path))
            self.script = os.path.basename(path)
            names, _default = self._scan(self.work)
            return {"work": self.work, "script": self.script, "scripts": names}
        except Exception:
            return {"error": traceback.format_exc()}

    # ---- 源脚本 -> IR ----
    def get_ir(self, script=None):
        try:
            self.script = self._resolve(script)
            if not self.script:
                return {"error": "工作目录里没有 .sh 脚本。\n点右上角「打开脚本」选择你的 GMT 脚本 (任意名字、任意位置)。"}
            sp = os.path.join(self.work, self.script)
            if not os.path.exists(sp):
                return {"error": "未找到源脚本 %s\n请用「打开脚本」重新选择。" % sp}
            return core.get_ir(self.work, self.script)
        except Exception:
            return {"error": traceback.format_exc()}

    # ---- 渲染 (命令级 + 可选元素级) ----
    def render(self, overlay_json, elements_json=None, script=None):
        try:
            self.script = self._resolve(script)
            if not self.script:
                return {"rc": -1, "error": "尚未选择 GMT 脚本", "stderr": "",
                        "changed": [], "sha_ok": False, "baked_elements": 0}
            overlay = json.loads(overlay_json) if overlay_json else {"ops": []}
            elements = json.loads(elements_json) if elements_json else None
            out = core.render(self.work, self.script, overlay, elements)
            out["script"] = self.script
            out["work"] = self.work
            png = out.get("png_path")
            if png and os.path.exists(png):
                b64 = base64.b64encode(open(png, "rb").read()).decode()
                out["image"] = "data:image/png;base64," + b64
            return out
        except Exception:
            return {"rc": -1, "error": traceback.format_exc(), "stderr": traceback.format_exc(),
                    "changed": [], "sha_ok": False, "baked_elements": 0}

    # ---- 画布模式: 命令级重渲染 -> 可编辑 SVG (+ 顺带回 IR, 省一次往返) ----
    def get_canvas(self, overlay_json=None, script=None, fresh=False):
        try:
            self.script = self._resolve(script)
            if not self.script:
                return {"rc": -1, "error": "尚未选择 GMT 脚本", "svg": "", "stderr": "",
                        "changed": [], "sha_ok": False}
            overlay = json.loads(overlay_json) if overlay_json else {"ops": []}
            out = core.svg_for(self.work, self.script, overlay, fresh=bool(fresh))
            out["script"] = self.script
            out["work"] = self.work
            try:
                out["ir"] = core.get_ir(self.work, self.script)
            except Exception:
                pass
            png = out.get("png_path")
            if png and os.path.exists(png):
                b64 = base64.b64encode(open(png, "rb").read()).decode()
                out["image"] = "data:image/png;base64," + b64
            return out
        except Exception:
            return {"rc": -1, "error": traceback.format_exc(), "stderr": traceback.format_exc(),
                    "svg": "", "changed": [], "sha_ok": False}

    # ---- 应用元素 overlay -> 高清 final.png 预览 ----
    def bake(self, overlay_json, elements_json, script=None):
        try:
            self.script = self._resolve(script)
            if not self.script:
                return {"rc": -1, "error": "尚未选择 GMT 脚本", "baked_elements": 0}
            overlay = json.loads(overlay_json) if overlay_json else {"ops": []}
            elements = json.loads(elements_json) if elements_json else {}
            out = core.bake(self.work, self.script, overlay, elements)
            out["script"] = self.script
            out["work"] = self.work
            png = out.get("png_path")
            if png and os.path.exists(png):
                b64 = base64.b64encode(open(png, "rb").read()).decode()
                out["image"] = "data:image/png;base64," + b64
            return out
        except Exception:
            return {"rc": -1, "error": traceback.format_exc(), "baked_elements": 0}

    # ---- 渲染 (+可选烘焙元素) 后按格式导出图片 ----
    def export_png(self, overlay_json, elements_json, script=None, fmt="png", scale=4, quality=92):
        try:
            self.script = self._resolve(script)
            if not self.script:
                return {"error": "尚未选择 GMT 脚本"}
            overlay = json.loads(overlay_json) if overlay_json else {"ops": []}
            elements = json.loads(elements_json) if elements_json else {}
            out = core.export_figure(self.work, self.script, overlay, elements,
                                     fmt=fmt, scale=scale, quality=quality)
            if out.get("error") or not out.get("data"):
                return {"error": out.get("error") or "未生成图件, 无法导出"}
            if not self.win:
                return None
            ext = "jpg" if out.get("fmt") == "jpg" else "png"
            res = self.win.create_file_dialog(
                FileDialog.SAVE,
                save_filename=(out.get("name") or self.script.rsplit(".", 1)[0]) + "." + ext,
                file_types=("JPG 图片 (*.jpg)",) if ext == "jpg" else ("PNG 图片 (*.png)",))
            if not res:
                return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            if not path.lower().endswith("." + ext):
                path += "." + ext
            with open(path, "wb") as g:
                g.write(base64.b64decode(out["data"]))
            return {"saved": path, "fmt": ext, "width": out.get("width"),
                    "height": out.get("height"), "baked_elements": out.get("baked_elements", 0)}
        except Exception:
            return {"error": traceback.format_exc()}

    # ---- 原生保存 overlay ----
    def save_overlay(self, json_str):
        try:
            if not self.win:
                return None
            res = self.win.create_file_dialog(
                FileDialog.SAVE, save_filename="overlay_gui.json",
                file_types=("JSON 文件 (*.json)",))
            if not res:
                return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            if not path.lower().endswith(".json"):
                path += ".json"
            open(path, "w", encoding="utf-8").write(json_str)
            return path
        except Exception:
            return {"error": traceback.format_exc()}

    # ---- 原生打开元素 overlay ----
    def open_overlay(self):
        try:
            if not self.win:
                return None
            res = self.win.create_file_dialog(
                FileDialog.OPEN, file_types=("JSON 文件 (*.json)",))
            if not res:
                return None
            path = res[0] if isinstance(res, (list, tuple)) else res
            return open(path, "r", encoding="utf-8").read()
        except Exception:
            return None


def build_html():
    """读 ui.html, 把 fieldkit.js / canvaskit.js 内联进去 (避免 file:// 相对加载与打包路径问题)。"""
    html = open(os.path.join(RES, "ui.html"), encoding="utf-8").read()
    for name in ("fieldkit.js", "canvaskit.js"):
        tag = '<script src="%s"></script>' % name
        if tag in html:
            try:
                js = open(os.path.join(RES, name), encoding="utf-8").read()
                html = html.replace(tag, "<script>\n" + js + "\n</script>")
            except OSError:
                pass
    return html


def main():
    if os.environ.get("GMT_SELFTEST"):
        import gmt_editor as GE
        summary = {"work": WORK, "script": SCRIPT}
        try:
            summary["shell"] = GE._find_shell()
            summary["gmt_on_path"] = "gmt6" in GE._gmt_env().get("PATH", "")
            out = core.render(WORK, SCRIPT, {"ops": []})
            png = out.get("png_path")
            summary["render"] = {
                "rc": out.get("rc"),
                "sha_ok": out.get("sha_ok"),
                "error": out.get("error"),
                "png": png,
                "png_exists": bool(png and os.path.exists(png)),
                "stderr_tail": (out.get("stderr") or "")[-500:],
            }
        except Exception:
            summary["exception"] = traceback.format_exc()
        dest = os.path.join(WORK, "gmt_vectorlab_selftest.json")
        try:
            open(dest, "w", encoding="utf-8").write(json.dumps(summary, ensure_ascii=False, indent=2))
        except Exception:
            pass
        return

    api = Api()
    win = webview.create_window(
        "GMT VectorLab · 画布式改图",
        html=build_html(),
        js_api=api,
        width=1360, height=880, min_size=(1080, 680),
        background_color="#f5f6f8", text_select=True, zoomable=True,
    )
    api.win = win
    webview.start(debug=bool(os.environ.get("GMT_DEBUG")))


if __name__ == "__main__":
    print("[GMT VectorLab] 资源目录:", RES)
    print("[GMT VectorLab] 工作目录:", WORK, " 源脚本:", SCRIPT)
    main()
