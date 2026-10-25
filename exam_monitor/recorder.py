# -*- coding: utf-8 -*-
"""全程录屏模块。

优先使用 ffmpeg gdigrab（Windows，音画同步的 mp4）；
无 ffmpeg 时用 mss + OpenCV 逐帧截图合成 mp4，并同时保存 JPEG 帧序列，
保证任何环境下都有可用的录像证据。
"""

import glob
import os
import shutil
import subprocess
import sys
import threading
import time

import cv2
import mss
import numpy as np

from . import config

IS_WIN = sys.platform.startswith("win")


def has_ffmpeg():
    return shutil.which("ffmpeg") is not None


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
            self.method = "mss+opencv"
            self._thread = threading.Thread(target=self._mss_loop,
                                            daemon=True)
            self._thread.start()

    @staticmethod
    def _grab_backend():
        """按平台选择 ffmpeg 抓屏输入。"""
        if IS_WIN:
            return ["-f", "gdigrab", "-framerate", None, "-i", "desktop"]
        if sys.platform == "darwin":
            return ["-f", "avfoundation", "-i", "1:none"]
        return ["-f", "x11grab", "-framerate", None, "-i", None]

    def _start_ffmpeg(self):
        import os as _os
        self._grab_backend = "x11grab"
        backend = ScreenRecorder._pick_backend()
        self._grab_backend = backend[0]
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + backend[1] + [
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            self.video_path,
        ]
        self._ffmpeg_proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _pick_backend():
        """返回 (名称, 参数列表)；探测不到可用抓屏设备则抛异常。"""
        plat = sys.platform
        if plat.startswith("win"):
            return ("gdigrab", ["-f", "gdigrab", "-framerate",
                                str(SCREEN_FPS_SAFE), "-i", "desktop"])
        if plat == "darwin":
            return ("avfoundation", ["-f", "avfoundation",
                                     "-framerate", str(SCREEN_FPS_SAFE),
                                     "-i", "1:none"])
        disp = os.environ.get("DISPLAY", ":0")
        return ("x11grab", ["-f", "x11grab", "-video_size",
                            _x11_size(disp), "-framerate",
                            str(SCREEN_FPS_SAFE), "-i", disp])

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
            self._extract_frames_backup()
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

    # ------------------------------------------------------------------
    def zip_frames(self):
        """把 JPEG 帧序列打包为 frames.zip，返回路径。"""
        import zipfile
        zp = os.path.join(self.out_dir, config.FRAMES_ZIP)
        files = sorted(glob.glob(os.path.join(self.frames_dir, "*.jpg")))
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
