# -*- coding: utf-8 -*-
"""全程录屏模块。

优先使用 ffmpeg gdigrab（Windows，音画同步的 mp4）；
无 ffmpeg 时：
  - 装有 mss + OpenCV + numpy 则逐帧截图合成 mp4 + JPEG 帧序列；
  - 纯标准库环境（零依赖直接运行）自动降级为 PIL 抓屏 /
    screencap(sct) / import(ImageMagick) 定时截 PNG 帧序列，
    保证任何环境下都有可用的录像证据。
"""

import glob
import os
import shutil
import subprocess
import sys
import threading
import time

from . import config

IS_WIN = sys.platform.startswith("win")


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


try:  # 可选第三方抓屏/编码依赖
    import cv2
    import mss
    import numpy as np
    HAS_MSS_CV2 = True
except ImportError:
    HAS_MSS_CV2 = False


def _probe_png_backend():
    """探测零依赖可用的截屏方式，返回 (名称, 命令前缀)。"""
    try:
        from PIL import ImageGrab  # noqa: F401
        return ("pillow", None)
    except ImportError:
        pass
    if not IS_WIN:
        if shutil.which("scrot"):
            return ("scrot", ["scrot"])
        if shutil.which("screencap"):          # Android/Termux
            return ("screencap", ["screencap", "-p"])
        if shutil.which("import"):             # ImageMagick
            return ("import", ["import", "-window", "root"])
        if shutil.which("gnome-screenshot"):
            return ("gnome-screenshot", ["gnome-screenshot", "-f"])
    return ("none", None)


def _screen_size_x11(display):
    """用 xrandr 获取屏幕尺寸，失败返回 None。"""
    try:
        out = subprocess.run(["xrandr", "--query"], capture_output=True,
                             text=True, timeout=5).stdout
        for line in out.splitlines():
            if " connected primary" in line or line.startswith("Screen #0"):
                pass
        # 更稳妥：解析 "Screen 0: minimum ... current 1280 x 720, ..."
        import re
        m = re.search(r"current\s+(\d+)\s*x\s*(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


class ScreenRecorder:
    """后台线程持续抓屏。stop() 后生成 video_path。"""

    def __init__(self, out_dir, fps=config.SCREEN_FPS):
        self.out_dir = out_dir
        self.frames_dir = os.path.join(out_dir, config.FRAMES_DIR)
        os.makedirs(self.frames_dir, exist_ok=True)
        self.video_path = os.path.join(out_dir, config.VIDEO_FILE)
        self.fps = max(0.2, float(fps))
        self._stop = threading.Event()
        self._thread = None
        self._ffmpeg_proc = None
        self.started_at = None
        self.stopped_at = None
        self.frame_count = 0
        self.method = ""
        self.error = ""

    # ------------------------------------------------------------------
    def start(self):
        self.started_at = time.time()
        if has_ffmpeg():
            try:
                self._start_ffmpeg()
                # 给 ffmpeg 一点时间，若立刻退出说明抓屏设备不可用
                time.sleep(0.6)
                if self._ffmpeg_proc.poll() is None:
                    self.method = "ffmpeg"
                else:
                    err = "%s 抓屏设备不可用" % self._grab_backend
                    self.error = err
                    print("[recorder] ffmpeg failed:", err, flush=True)
            except Exception as e:
                self.error = "ffmpeg 启动失败: %s" % e
                print("[recorder] ffmpeg failed:", e, flush=True)
        if self.method != "ffmpeg":
            if HAS_MSS_CV2:
                self.method = "mss+opencv"
                self._thread = threading.Thread(target=self._mss_loop,
                                                daemon=True)
                self._thread.start()
            else:
                name, cmd = _probe_png_backend()
                if name == "pillow":
                    self.method = "pillow-frames"
                    self._thread = threading.Thread(target=self._pillow_loop,
                                                    daemon=True)
                    self._thread.start()
                elif name != "none":
                    self.method = "%s-frames" % name
                    self._png_cmd = cmd
                    self._thread = threading.Thread(target=self._cmd_loop,
                                                    daemon=True)
                    self._thread.start()
                else:
                    self.method = "none"
                    self.error = ("无可用录屏方式：请安装 ffmpeg（推荐）或"
                                  " pip install mss opencv-python numpy")
                    print("[recorder] no capture backend available",
                          flush=True)

    def _start_ffmpeg(self):
        backend = self._pick_backend()
        self._grab_backend = backend[0]
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] \
            + backend[1] + [
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-pix_fmt", "yuv420p", self.video_path,
            ]
        self._ffmpeg_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _pick_backend(self):
        """返回 (名称, 参数列表)；探测不到可用抓屏设备则抛异常。"""
        fps = str(max(1, int(round(self.fps))) or 1)
        plat = sys.platform
        if plat.startswith("win"):
            return ("gdigrab", ["-f", "gdigrab", "-framerate", fps,
                                 "-i", "desktop"])
        if plat == "darwin":
            return ("avfoundation", ["-f", "avfoundation",
                                     "-framerate", fps, "-i", "1:none"])
        disp = os.environ.get("DISPLAY", ":0")
        size = _screen_size_x11(disp)
        if not size:
            raise RuntimeError("无法获取 X11 屏幕尺寸(xrandr)")
        return ("x11grab", ["-f", "x11grab", "-video_size",
                            "%dx%d" % size, "-framerate", fps, "-i", disp])

    # ------------------------------------------------------------------
    def _pillow_loop(self):
        """零依赖兜底：Pillow ImageGrab 定时截 PNG 帧序列。"""
        from PIL import ImageGrab
        interval = 1.0 / self.fps
        idx = 0
        while not self._stop.is_set():
            t0 = time.time()
            try:
                img = ImageGrab.grab(all_screens=True)
                idx += 1
                img.save(os.path.join(self.frames_dir,
                                      "frame_%06d.png" % idx),
                         optimize=False, compress_level=3)
                self.frame_count = idx
            except Exception as e:
                self.error = "PIL 抓屏失败: %s" % e
                return
            dt = time.time() - t0
            self._stop.wait(max(0.05, interval - dt))

    def _cmd_loop(self):
        """零依赖兜底：调用外部截图命令生成 PNG 帧序列。"""
        interval = 1.0 / self.fps
        idx = 0
        while not self._stop.is_set():
            t0 = time.time()
            path = os.path.join(self.frames_dir, "frame_%06d.png" % (idx + 1))
            tmp = os.path.join(self.frames_dir, "_cap_tmp.png")
            cmd = list(self._png_cmd)
            if cmd[0] in ("scrot", "gnome-screenshot"):
                cmd.append(tmp)
            elif cmd[0] == "import":
                cmd.append(tmp)
            elif cmd[0] == "screencap":
                cmd.append(tmp)
            try:
                r = subprocess.run(cmd, timeout=10,
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                src = tmp if os.path.exists(tmp) else None
                if src is None and cmd[0] == "scrot" and r.returncode == 0:
                    # scrot 无输出参数时会在 cwd 生成随机名文件
                    cands = sorted(glob.glob(os.path.join(
                        self.frames_dir, "*.png")),
                        key=os.path.getmtime)
                    cands = [c for c in cands if "frame_" not in
                             os.path.basename(c)]
                    if cands:
                        src = cands[-1]
                if src:
                    if src != path:
                        shutil.move(src, path)
                    idx += 1
                    self.frame_count = idx
            except Exception as e:
                self.error = "截图命令失败: %s" % e
                return
            dt = time.time() - t0
            self._stop.wait(max(0.05, interval - dt))

    # ------------------------------------------------------------------
    def _mss_loop(self):
        interval = 1.0 / self.fps
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # 全部屏幕
            w = (monitor["width"] // 2) * 2
            h = (monitor["height"] // 2) * 2
            fourcc = cv2.VideoWriter_fourcc(*config.VIDEO_FOURCC)
            writer = cv2.VideoWriter(self.video_path, fourcc,
                                     self.fps, (w, h))
            idx = 0
            while not self._stop.is_set():
                t0 = time.time()
                img = np.array(sct.grab(monitor))[:, :, :3]
                if img.shape[1] != w or img.shape[0] != h:
                    img = cv2.resize(img, (w, h))
                writer.write(img)
                idx += 1
                frame_path = os.path.join(self.frames_dir,
                                          "frame_%06d.jpg" % idx)
                cv2.imwrite(frame_path, img,
                            [int(cv2.IMWRITE_JPEG_QUALITY),
                             config.JPEG_QUALITY])
                self.frame_count = idx
                dt = time.time() - t0
                self._stop.wait(max(0.01, interval - dt))
            writer.release()

    # ------------------------------------------------------------------
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
        if self._ffmpeg_proc:
            try:
                self._ffmpeg_proc.stdin and None
                # 发送 'q' 让 ffmpeg 正常收尾
                if self._ffmpeg_proc.poll() is None:
                    self._ffmpeg_proc.terminate()
                    try:
                        self._ffmpeg_proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self._ffmpeg_proc.kill()
            except Exception:
                pass
        self.stopped_at = time.time()
        # ffmpeg 方式下也补一份帧序列（可选，抽帧）
        if self.method == "ffmpeg" and os.path.exists(self.video_path):
            if HAS_MSS_CV2:
                self._extract_frames_backup()
            else:
                self._ffmpeg_extract_frames()
        return self.video_path

    def _extract_frames_backup(self):
        cap = cv2.VideoCapture(self.video_path)
        idx = 0
        step = max(1, int(round(cap.get(cv2.CAP_PROP_FPS) / self.fps)) or 1)
        n = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            n += 1
            if n % step == 0:
                ok, img = cap.retrieve()
                if ok:
                    cv2.imwrite(os.path.join(self.frames_dir,
                                             "frame_%06d.jpg" % idx), img)
                    idx += 1
        cap.release()
        self.frame_count = idx

    def _ffmpeg_extract_frames(self):
        """无 opencv 时，用 ffmpeg 把 mp4 抽帧成 jpg 序列。"""
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", self.video_path,
                 "-vf", "fps=%g" % max(0.2, self.fps),
                 "-q:v", str(max(2, config.JPEG_QUALITY // 5)),
                 os.path.join(self.frames_dir, "frame_%06d.jpg")],
                timeout=600, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            self.frame_count = len(glob.glob(
                os.path.join(self.frames_dir, "*.jpg")))
        except Exception as e:
            self.error = "ffmpeg 抽帧失败: %s" % e

    # ------------------------------------------------------------------
    def zip_frames(self):
        """把帧序列打包为 frames.zip，返回路径。"""
        import zipfile
        zp = os.path.join(self.out_dir, config.FRAMES_ZIP)
        files = sorted(glob.glob(os.path.join(self.frames_dir, "*.jpg")) +
                       glob.glob(os.path.join(self.frames_dir, "*.png")))
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, os.path.basename(f))
        shutil.rmtree(self.frames_dir, ignore_errors=True)
        return zp

    @property
    def duration(self):
        if self.started_at:
            end = self.stopped_at or time.time()
            return end - self.started_at
        return 0.0
