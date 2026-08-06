# --------------------------------------------------------------
# Grok to WEBP – By Sinulated.Art
# UPDATED: GPU-accelerated video pipeline + modern UI refresh
#
# Key Changes:
#   • GPU support: detects CUDA (and falls back gracefully).
#     When available, uses -hwaccel cuda + scale_cuda for decode
#     & scaling, then hwdownload → libwebp (encoding remains CPU).
#     Preference is silent and automatic.
#   • Modern dark UI: refined palette, Segoe UI, better hierarchy,
#     GPU status badge, improved cards & controls.
#   • Code quality: cleaner helpers, robust temp handling,
#     safer binary searches, better error paths, pathlib usage,
#     reduced duplication.
#   • All previous features preserved (lossless images, width
#     binary search, quality binary search for video, size
#     estimation, clipboard, toast, retries, metadata, etc.).
# --------------------------------------------------------------

import os
import sys
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk, ImageSequence
import subprocess
import threading
import shutil
import struct
import tempfile
import urllib.request
import zipfile
import ctypes
import re
from pathlib import Path

try:
    from tkinterdnd2 import *
except ImportError:
    messagebox.showerror("Error", "Run: pip install tkinterdnd2")
    sys.exit(1)

try:
    from win11toast import toast
except ImportError:
    toast = None

try:
    import win32clipboard
    import win32con
except ImportError:
    win32clipboard = None
    win32con = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

from dotenv import load_dotenv

# ── Supported file types ─────────────────────────────────────────────────────
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".gif"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}

# ── Theme ────────────────────────────────────────────────────────────────────
BG           = "#0a0a0a"
CARD_BG      = "#141414"
CARD_BORDER  = "#252525"
ACCENT       = "#8000ff"
ACCENT_HOVER = "#9b3cff"
TEXT         = "#f0f0f0"
TEXT_MUTED   = "#888888"
TEXT_DIM     = "#555555"
SUCCESS      = "#22c55e"
WARNING      = "#f59e0b"
ERROR        = "#ef4444"
INPUT_BG     = "#1c1c1c"
INPUT_BORDER = "#333333"

# ── Load .env ────────────────────────────────────────────────────────────────
def _load_env():
    env_path = Path.cwd() / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
        return
    try:
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent
        fallback = base / ".env"
        if fallback.is_file():
            load_dotenv(fallback)
    except Exception:
        pass

_load_env()

# ── Defaults ─────────────────────────────────────────────────────────────────
ARTIST_NAME = os.getenv("ARTIST_NAME", "Sinulated")
COMMENT = os.getenv("COMMENT", "Visit Sinulated.art For More!")

DEFAULT_QUALITY = max(60, min(100, int(os.getenv("START_QUALITY", "91"))))
DEFAULT_TEMPLATE = os.getenv("FILENAME_TEMPLATE", "Sinulated Preview {index:04d}")
DEFAULT_PREFIX = DEFAULT_TEMPLATE.removesuffix(" {index:04d}").rstrip()
DEFAULT_MAX_FILESIZE_MB = float(os.getenv("MAX_FILESIZE_MB", "10"))
DEFAULT_MAX_WIDTH = int(os.getenv("MAX_WIDTH", "800"))

# --------------------------------------------------------------
# Silent FFmpeg helper (no console window on Windows)
# --------------------------------------------------------------
def silent_run_ffmpeg(args, timeout=None, **kwargs):
    kwargs.setdefault("check", True)
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    kwargs.setdefault("stderr", subprocess.DEVNULL)
    if timeout is not None:
        kwargs["timeout"] = timeout

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo

    return subprocess.run(args, **kwargs)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = Path(__file__).resolve().parent
    return str(Path(base_path) / relative_path)


# --------------------------------------------------------------
# FFmpeg path + first-run download
# --------------------------------------------------------------
def get_ffmpeg_path():
    bundled = resource_path(os.path.join("ffmpeg", "bin", "ffmpeg.exe"))
    if os.path.isfile(bundled):
        return bundled

    system = shutil.which("ffmpeg")
    if system:
        return system

    cwd = Path.cwd() / "ffmpeg" / "bin" / "ffmpeg.exe"
    if cwd.is_file():
        return str(cwd)

    return setup_ffmpeg_and_start()


def setup_ffmpeg_and_start():
    working_dir = Path.cwd()
    ffmpeg_dir = working_dir / "ffmpeg"
    ffmpeg_exe = ffmpeg_dir / "bin" / "ffmpeg.exe"

    if ffmpeg_exe.is_file():
        return str(ffmpeg_exe)
    if shutil.which("ffmpeg"):
        return "ffmpeg"

    splash = tk.Tk()
    splash.title("Grok to WEBP")
    splash.geometry("340x170")
    splash.configure(bg=BG)
    splash.resizable(False, False)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)

    w, h = splash.winfo_screenwidth(), splash.winfo_screenheight()
    splash.geometry(f"340x170+{(w-340)//2}+{(h-170)//2}")

    tk.Label(splash, text="Grok to WEBP", font=("Segoe UI", 18, "bold"),
             bg=BG, fg=ACCENT).pack(pady=(18, 6))
    tk.Label(splash, text="First-time setup · Downloading FFmpeg (~90 MB)",
             bg=BG, fg=TEXT, font=("Segoe UI", 10)).pack()
    tk.Label(splash, text="Please wait…", bg=BG, fg=TEXT_MUTED,
             font=("Segoe UI", 9)).pack(pady=2)

    progress = ttk.Progressbar(splash, length=290, mode="determinate")
    progress.pack(pady=12)
    status = tk.Label(splash, text="Starting…", bg=BG, fg=TEXT_MUTED,
                      font=("Segoe UI", 9))
    status.pack()

    def download():
        try:
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = working_dir / "ffmpeg_download.zip"

            def reporthook(block, size, total):
                if total > 0:
                    downloaded = block * size
                    percent = min(100, int(downloaded * 100 / total))
                    progress["value"] = percent
                    status.config(text=f"{downloaded // 1048576} MB / {total // 1048576} MB")
                    splash.update_idletasks()

            status.config(text="Downloading FFmpeg…")
            urllib.request.urlretrieve(url, str(zip_path), reporthook)

            status.config(text="Extracting…")
            progress["value"] = 100
            splash.update_idletasks()

            ffmpeg_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as z:
                for file in z.namelist():
                    if file.endswith("ffmpeg.exe"):
                        base = file.split("/")[0]
                        z.extractall(working_dir)
                        src = working_dir / base / "bin"
                        dst = ffmpeg_dir / "bin"
                        if dst.exists():
                            shutil.rmtree(dst)
                        shutil.move(str(src), str(dst))
                        shutil.rmtree(working_dir / base)
                        break

            zip_path.unlink(missing_ok=True)
            status.config(text="Ready! Starting…")
            splash.after(800, splash.destroy)
        except Exception as e:
            status.config(text="Failed")
            messagebox.showerror("Error", f"FFmpeg setup failed:\n{e}")
            splash.destroy()
            sys.exit(1)

    threading.Thread(target=download, daemon=True).start()
    splash.mainloop()
    return str(ffmpeg_exe)


ffmpeg_path = get_ffmpeg_path()


# --------------------------------------------------------------
# GPU detection (silent preference for CUDA when available)
# --------------------------------------------------------------
def detect_cuda_support():
    """Return True if this FFmpeg build + system can use CUDA hwaccel + scale_cuda."""
    try:
        # Check hwaccels
        r = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if "cuda" not in (r.stdout or "").lower():
            return False

        # Check that scale_cuda filter exists
        r2 = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-filters"],
            capture_output=True, text=True, timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if "scale_cuda" not in (r2.stdout or ""):
            return False

        return True
    except Exception:
        return False


CUDA_AVAILABLE = detect_cuda_support()


# --------------------------------------------------------------
# Video info + size estimation
# --------------------------------------------------------------
def get_video_info(path):
    try:
        result = subprocess.run(
            [ffmpeg_path, "-i", path],
            capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        lines = (result.stderr or "").splitlines()
        dur_line = next((l for l in lines if "Duration:" in l), None)
        if not dur_line:
            return None
        dur = dur_line.split("Duration: ")[1].split(",")[0]
        h, m, s = map(float, dur.split(":"))
        duration = h * 3600 + m * 60 + s

        vid_line = next((l for l in lines if "Video:" in l), None)
        if not vid_line:
            return None
        res_match = re.search(r"(\d+)x(\d+)", vid_line)
        w, h = map(int, res_match.groups()) if res_match else (0, 0)
        fps_match = re.search(r"(\d+(?:\.\d+)?) fps", vid_line)
        fps = float(fps_match.group(1)) if fps_match else 0.0
        return duration, w, h, fps
    except Exception:
        return None


def estimate_webp_size(src, quality, max_width=800, compression_level=6):
    """Estimate final WEBP size.
    Videos: short sample → extrapolate.
    Images: exact lossless size at target width.
    """
    ext = Path(src).suffix.lower()
    is_video = ext in VIDEO_EXTS

    if is_video:
        info = get_video_info(src)
        if not info:
            return None
        duration, _, _, _ = info
        sample_dur = min(2.0, duration / 2) if duration > 0 else 2.0

        sample_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        sample_webp = tempfile.NamedTemporaryFile(suffix=".webp", delete=False).name
        try:
            silent_run_ffmpeg(
                [ffmpeg_path, "-i", src, "-t", str(sample_dur), "-c", "copy", "-y", sample_path],
                timeout=30
            )
            silent_run_ffmpeg([
                ffmpeg_path, "-i", sample_path, "-an", "-c:v", "libwebp",
                "-loop", "0", "-quality", str(quality),
                "-compression_level", str(compression_level),
                "-vf", f"scale={max_width}:-2:flags=lanczos",
                "-y", sample_webp
            ], timeout=45)
            size_sample = os.path.getsize(sample_webp)
            return size_sample * (duration / sample_dur) * 0.95
        except Exception:
            return None
        finally:
            for p in (sample_path, sample_webp):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
    else:
        sample_webp = tempfile.NamedTemporaryFile(suffix=".webp", delete=False).name
        try:
            silent_run_ffmpeg([
                ffmpeg_path, "-i", src,
                "-vf", f"scale={max_width}:-2:flags=lanczos",
                "-c:v", "libwebp", "-lossless", "1",
                "-compression_level", str(compression_level),
                "-y", sample_webp
            ], timeout=30)
            return os.path.getsize(sample_webp)
        except Exception:
            return None
        finally:
            try:
                if os.path.exists(sample_webp):
                    os.remove(sample_webp)
            except Exception:
                pass


# --------------------------------------------------------------
# Main Application
# --------------------------------------------------------------
root = TkinterDnD.Tk()

icon_path = resource_path("512.png")
if os.path.isfile(icon_path):
    try:
        icon_img = tk.PhotoImage(file=icon_path)
        root.iconphoto(True, icon_img)
    except Exception:
        pass

# Scrollbar theme
style = ttk.Style()
style.theme_use("clam")
style.configure(
    "Purple.Vertical.TScrollbar",
    background=ACCENT,
    troughcolor="#1a1a1a",
    arrowcolor="#cccccc",
    bordercolor="#333333",
    lightcolor="#444444",
    darkcolor="#222222",
    gripcount=0,
)
style.map(
    "Purple.Vertical.TScrollbar",
    background=[("active", ACCENT_HOVER), ("pressed", "#b060ff"), ("disabled", "#444444")],
    troughcolor=[("active", "#222222"), ("!disabled", "#1a1a1a")],
)


class DiscordWebPConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Grok to WEBP  ·  Sinulated.Art")
        self.root.configure(bg=BG)
        self.root.geometry("580x520")
        self.root.minsize(560, 480)
        self.root.resizable(True, True)

        self.files = []
        self.items = {}
        self.processed = []
        self.processing_queue = []

        self.output_dir = Path.cwd() / "images"
        self.output_dir.mkdir(exist_ok=True)

        self.quality_var = tk.IntVar(value=DEFAULT_QUALITY)
        self.prefix_var = tk.StringVar(value=DEFAULT_PREFIX)
        self.maxsize_var = tk.DoubleVar(value=DEFAULT_MAX_FILESIZE_MB)
        self.max_width_var = tk.IntVar(value=DEFAULT_MAX_WIDTH)

        self.use_cuda = CUDA_AVAILABLE

        self.setup_ui()
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind("<<DropEnter>>", lambda e: self.show_overlay())
        self.root.dnd_bind("<<DropLeave>>", lambda e: self.hide_overlay())
        self.root.dnd_bind("<<Drop>>", self.handle_drop)

    # ── UI Construction ──────────────────────────────────────────────────────
    def setup_ui(self):
        # Header bar
        header = tk.Frame(self.root, bg=BG, height=42)
        header.pack(side="top", fill="x", padx=16, pady=(12, 0))
        header.pack_propagate(False)

        tk.Label(
            header, text="Grok to WEBP", font=("Segoe UI", 14, "bold"),
            bg=BG, fg=TEXT
        ).pack(side="left")

        # GPU badge
        gpu_text = "CUDA" if self.use_cuda else "CPU"
        gpu_color = SUCCESS if self.use_cuda else TEXT_MUTED
        gpu_badge = tk.Label(
            header, text=f"  {gpu_text}  ", font=("Segoe UI", 9, "bold"),
            bg="#1a1a1a", fg=gpu_color, padx=6, pady=2
        )
        gpu_badge.pack(side="right", padx=(8, 0))
        tk.Label(header, text="Accel", font=("Segoe UI", 9),
                 bg=BG, fg=TEXT_DIM).pack(side="right")

        # Drop zone
        self.drop_zone = tk.Frame(self.root, bg=BG)

        canvas = tk.Canvas(self.drop_zone, bg=BG, highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(
            24, 24, 1, 1, outline=ACCENT, width=2, dash=(8, 5), tags="border"
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.coords("border", 24, 24, e.width - 24, e.height - 16)
        )

        tk.Label(
            canvas, text="Drop Images & Videos Here", bg=BG, fg=TEXT,
            font=("Segoe UI", 16, "bold")
        ).place(relx=0.5, rely=0.32, anchor="center")
        tk.Label(
            canvas, text="or click to browse", bg=BG, fg=TEXT_MUTED,
            font=("Segoe UI", 10)
        ).place(relx=0.5, rely=0.42, anchor="center")

        select_btn = tk.Button(
            canvas, text="Select Files", command=self.select_files,
            bg=ACCENT, fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=28, pady=9, activebackground=ACCENT_HOVER,
            activeforeground="white", cursor="hand2", bd=0
        )
        select_btn.place(relx=0.5, rely=0.68, anchor="center")

        # Preview area (hidden until files added)
        self.preview = tk.Frame(self.root, bg=BG)
        self.canvas = tk.Canvas(self.preview, bg=BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self.preview, orient="vertical",
            command=self.canvas.yview, style="Purple.Vertical.TScrollbar"
        )
        self.grid = tk.Frame(self.canvas, bg=BG)
        self.window_id = self.canvas.create_window((0, 0), window=self.grid, anchor="nw")

        def update_window_width(event):
            self.canvas.itemconfig(self.window_id, width=event.width)

        self.canvas.bind("<Configure>", update_window_width)
        self.grid.bind("<Configure>", self._update_scrollregion)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Bottom controls
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(side="bottom", pady=(6, 14), padx=16, fill="x")

        # Action buttons
        btn_frame = tk.Frame(bottom, bg=BG)
        btn_frame.pack(anchor="center", pady=(0, 14))

        self._make_btn(btn_frame, "Clear All", self.clear_all, "#dc2626", padx=18).pack(
            side="left", padx=10
        )
        self._make_btn(
            btn_frame, "Process All", self.start_sequential_processing,
            ACCENT, font=("Segoe UI", 12, "bold"), padx=36, pady=11
        ).pack(side="left", padx=10)
        self._make_btn(btn_frame, "Re-copy Last", self.recopy_last, "#16a34a", padx=18).pack(
            side="left", padx=10
        )

        # Settings row
        settings = tk.Frame(bottom, bg=BG)
        settings.pack(anchor="center")

        self._add_setting(settings, "Quality", self.quality_var, 5)
        self._add_setting(settings, "Prefix", self.prefix_var, 16)
        self._add_setting(settings, "Max MB", self.maxsize_var, 5)
        self._add_setting(settings, "Max W", self.max_width_var, 5, last=True)

        self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)

        # Overlay
        self.overlay = tk.Label(
            self.root, text="Drop Here", bg="#1f1f1f", fg="white",
            font=("Segoe UI", 28, "bold")
        )
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.overlay.place_forget()

    def _make_btn(self, parent, text, cmd, bg, font=("Segoe UI", 10), padx=16, pady=8):
        return tk.Button(
            parent, text=text, command=cmd, bg=bg, fg="white",
            font=font, relief="flat", padx=padx, pady=pady,
            activebackground=bg, activeforeground="white",
            cursor="hand2", bd=0
        )

    def _add_setting(self, parent, label, var, width, last=False):
        tk.Label(
            parent, text=label, bg=BG, fg=TEXT_MUTED, font=("Segoe UI", 9)
        ).pack(side="left", padx=(0, 5))
        entry = tk.Entry(
            parent, textvariable=var, width=width, justify="center",
            bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
            font=("Segoe UI", 10), relief="flat",
            highlightthickness=1, highlightbackground=INPUT_BORDER,
            highlightcolor=ACCENT
        )
        entry.pack(side="left", padx=(0, 18 if not last else 0), ipady=3)

    def _update_scrollregion(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def show_overlay(self):
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.overlay.lift()

    def hide_overlay(self):
        self.overlay.place_forget()

    # ── Notifications ────────────────────────────────────────────────────────
    def notify_user(self):
        """Fire the completion toast / flash on a background thread.

        win11toast (and Windows toast dismiss handling) can block or
        interfere with Tkinter's main-loop when called on the UI thread.
        Running it in a daemon thread keeps the app responsive.
        """
        def _do_notify():
            try:
                if toast is not None:
                    # Keep icon path resolution off the main thread too
                    icon = resource_path("512.png")
                    toast(
                        "Processing Complete!",
                        "Files copied to clipboard.",
                        icon=icon if os.path.isfile(icon) else None,
                        duration="short",  # shorter = less time holding COM objects
                    )
                    return
            except Exception:
                pass

            # Fallback: flash the taskbar (must touch HWND on main thread)
            try:
                self.root.after(0, self._flash_window)
            except Exception:
                pass

        threading.Thread(target=_do_notify, daemon=True).start()

    def _flash_window(self):
        """Taskbar flash fallback – always runs on the main thread."""
        try:
            hwnd = self.root.winfo_id()
            user32 = ctypes.windll.user32
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)
            user32.FlashWindow(hwnd, True)
            self.root.after(3500, lambda: user32.FlashWindow(hwnd, False))
        except Exception:
            pass

    # ── File handling ────────────────────────────────────────────────────────
    def select_files(self):
        files = filedialog.askopenfilenames(
            filetypes=[
                ("Supported Files", "*.mp4 *.webm *.mov *.avi *.mkv *.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff"),
                ("Videos", "*.mp4 *.webm *.mov *.avi *.mkv *.gif"),
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tiff *.tif"),
            ]
        )
        self.add_files(files)

    def handle_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        self.add_files(files)
        self.hide_overlay()

    def add_files(self, files):
        added = False
        for f in files:
            if not os.path.isfile(f):
                continue
            ext = Path(f).suffix.lower()
            if (ext in VIDEO_EXTS or ext in IMAGE_EXTS) and f not in self.files:
                self.files.append(f)
                self.create_item(f)
                added = True
        if added:
            self.show_preview()
            self._update_scrollregion()
            self.canvas.yview_moveto(0)

    def show_preview(self):
        self.drop_zone.pack_forget()
        self.preview.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self.canvas.pack(side="left", fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.root.bind("<MouseWheel>", self._on_mousewheel)
        self.root.bind("<Button-4>", self._on_mousewheel)
        self.root.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

    def create_item(self, path):
        idx = len(self.items)
        frame = tk.Frame(self.grid, bg=CARD_BG, width=162, height=210)
        frame.pack_propagate(False)
        frame.grid(row=idx // 3, column=idx % 3, padx=8, pady=8, sticky="n")

        # Subtle border effect
        border = tk.Frame(frame, bg=CARD_BORDER)
        border.place(x=0, y=0, relwidth=1, relheight=1)
        inner = tk.Frame(frame, bg=CARD_BG)
        inner.place(x=1, y=1, relwidth=1, relheight=1, width=-2, height=-2)

        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                thumb_path = tmp.name
            silent_run_ffmpeg(
                [ffmpeg_path, "-i", path, "-vframes", "1", "-q:v", "2", "-y", thumb_path],
                timeout=12,
            )
            img = Image.open(thumb_path)
            img.thumbnail((128, 128), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (128, 128), (20, 20, 20))
            bg.paste(img, ((128 - img.width) // 2, (128 - img.height) // 2))
            photo = ImageTk.PhotoImage(bg)
            os.unlink(thumb_path)
        except Exception:
            bg = Image.new("RGB", (128, 128), (40, 40, 40))
            photo = ImageTk.PhotoImage(bg)

        lbl = tk.Label(inner, image=photo, bg=CARD_BG, bd=0)
        lbl.image = photo
        lbl.pack(pady=(12, 6))

        spinner = tk.Canvas(inner, highlightthickness=0, width=128, height=128, bg=CARD_BG)
        spinner.place(x=17, y=12)
        spinner.create_oval(36, 36, 92, 92, outline=ACCENT, width=5, tags="ring")
        spinner.place_forget()

        status = tk.Label(
            inner, text="Estimating…", bg=CARD_BG, fg=TEXT_MUTED,
            font=("Segoe UI", 9), wraplength=140, justify="center"
        )
        status.pack(pady=2)

        name = Path(path).name
        if len(name) > 26:
            name = name[:23] + "…"
        tk.Label(
            inner, text=name, bg=CARD_BG, fg=TEXT_DIM, font=("Segoe UI", 8)
        ).pack(pady=(0, 4))

        remove = tk.Button(
            frame, text="×", command=lambda p=path, f=frame: self.remove_item(p, f),
            bg="#dc2626", fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", width=2, cursor="hand2", bd=0
        )
        remove.place(relx=1, rely=0, anchor="ne", x=-3, y=3)

        self.items[path] = {
            "frame": frame,
            "label": lbl,
            "spinner": spinner,
            "status": status,
            "angle": 0,
            "running": False,
            "processed": False,
            "attempt": 1,
            "last_size_mb": None,
        }
        self._update_scrollregion()
        threading.Thread(target=self.update_estimate, args=(path,), daemon=True).start()

    def update_estimate(self, path):
        if path not in self.items:
            return
        q = self.quality_var.get()
        mw = self.max_width_var.get()
        est_bytes = estimate_webp_size(path, q, mw)
        if est_bytes is None:
            self.root.after(0, lambda: self.items[path]["status"].config(
                text="Est failed", fg=ERROR
            ))
            return

        est_mb = est_bytes / 1_000_000
        max_mb = self.maxsize_var.get()
        is_img = Path(path).suffix.lower() in IMAGE_EXTS

        if is_img:
            text = f"Est: {est_mb:.1f} MB (lossless)"
            color = SUCCESS if est_mb <= max_mb else WARNING
            if est_mb > max_mb:
                sugg_w = max(400, int(mw * (max_mb / est_mb) * 0.85))
                sugg_w = (sugg_w // 50) * 50
                text += f"\ntry W={sugg_w}"
        else:
            text = f"Est: {est_mb:.1f} MB"
            color = SUCCESS if est_mb <= max_mb else ERROR
            if est_mb > max_mb:
                sugg_q = max(60, min(100, int(q * (max_mb / est_mb))))
                text += f"\ntry Q={sugg_q}"

        self.root.after(0, lambda: self.items[path]["status"].config(text=text, fg=color))

    def remove_item(self, path, frame):
        frame.destroy()
        if path in self.files:
            self.files.remove(path)
        if path in self.processing_queue:
            self.processing_queue.remove(path)
        if path in self.items:
            del self.items[path]

        for idx, p in enumerate(self.files):
            self.items[p]["frame"].grid(row=idx // 3, column=idx % 3, padx=8, pady=8, sticky="n")

        self._update_scrollregion()
        if not self.files:
            self.preview.pack_forget()
            self.root.unbind("<MouseWheel>")
            self.root.unbind("<Button-4>")
            self.root.unbind("<Button-5>")
            self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)

    # ── Processing ───────────────────────────────────────────────────────────
    def start_sequential_processing(self):
        if not self.files:
            return
        self.processed.clear()
        self.processing_queue = [p for p in self.files if not self.items[p]["processed"]]

        for path in self.processing_queue:
            item = self.items[path]
            item["spinner"].place(x=17, y=12)
            item["status"].config(text=f"Queued ({item['attempt']})", fg=WARNING)
            item["running"] = True
            self.rotate_spinner(path)

        if self.processing_queue:
            self.process_next()

    def process_next(self):
        if not self.processing_queue:
            self.copy_to_clipboard()
            self.overlay.place_forget()
            return

        path = self.processing_queue[0]
        item = self.items[path]
        item["status"].config(text=f"Converting… ({item['attempt']})", fg=ACCENT)

        prefix = self.prefix_var.get().strip() or "Preview"

        try:
            existing = [
                f for f in os.listdir(self.output_dir)
                if f.startswith(prefix + " ") and f.lower().endswith(".webp")
            ]
            numbers = []
            prefix_len = len(prefix) + 1
            for fname in existing:
                try:
                    num_str = fname[prefix_len:-5].strip()
                    numbers.append(int(num_str))
                except (ValueError, IndexError):
                    continue
            next_index = 1 if not numbers else max(numbers) + 1
        except Exception:
            next_index = len(self.processed) + 1

        filename = f"{prefix} {next_index:04d}.webp"
        out_path = str(self.output_dir / filename)

        def done(success, result_path, last_size_mb=None):
            if path not in self.items:
                return
            item = self.items[path]
            if last_size_mb is not None:
                item["last_size_mb"] = last_size_mb

            if success:
                self.processed.append(result_path)
                self.finish_processing(path, result_path)
                item["spinner"].place_forget()
                self.processing_queue.pop(0)
                self.process_next()
            else:
                item["attempt"] += 1
                if item["attempt"] > 5:
                    item["status"].config(text="Failed (too large)", fg=ERROR)
                    item["spinner"].place_forget()
                    item["running"] = False
                    self.processing_queue.pop(0)
                    self.process_next()
                    return

                retry_text = f"Retrying… ({item['attempt']})"
                if item["last_size_mb"] is not None:
                    retry_text += f" · {item['last_size_mb']:.1f} MB"
                item["status"].config(text=retry_text, fg=WARNING)
                self.root.after(350, self.process_next)

        threading.Thread(
            target=self.convert_webp, args=(path, out_path, done), daemon=True
        ).start()

    def _build_video_cmd(self, src, dst, quality, max_w, use_cuda):
        """Build FFmpeg args for video → animated WEBP.
        Prefer CUDA decode + scale_cuda when available.
        """
        base = [ffmpeg_path]
        if use_cuda:
            base += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]

        base += ["-i", src, "-an"]

        if use_cuda:
            # GPU scale → download → libwebp
            vf = f"scale_cuda={max_w}:-2:interp_algo=lanczos,hwdownload,format=yuv420p"
        else:
            vf = f"scale={max_w}:-2:flags=lanczos"

        base += [
            "-vf", vf,
            "-c:v", "libwebp",
            "-loop", "0",
            "-quality", str(quality),
            "-compression_level", "6",
            "-metadata", f"artist={ARTIST_NAME}",
            "-metadata", f"description={COMMENT}",
            "-metadata", f"comment={COMMENT}",
            "-y", dst,
        ]
        return base

    def convert_webp(self, src, dst, callback):
        """Convert single file.
        Videos → quality binary search (GPU preferred when available)
        Images → lossless + width binary search if needed
        """
        try:
            start_quality = self.quality_var.get()
            max_size_bytes = int(self.maxsize_var.get() * 1_000_000)
            max_w = max(300, min(2048, self.max_width_var.get()))
        except Exception:
            start_quality = 85
            max_size_bytes = 10_000_000
            max_w = 800

        ext = Path(src).suffix.lower()
        is_video = ext in VIDEO_EXTS

        if is_video:
            # ── VIDEO PATH ───────────────────────────────────────────────────
            low, high = 50, min(100, start_quality)
            best_quality = -1
            best_size = float("inf")
            min_size = float("inf")
            best_temp = tempfile.NamedTemporaryFile(suffix=".webp", delete=False).name
            temp = tempfile.NamedTemporaryFile(suffix=".webp", delete=False).name
            attempts = 0
            max_attempts = 12
            last_size_mb = None
            use_cuda = self.use_cuda  # can be flipped to False on failure

            def try_encode(q, cuda_flag):
                nonlocal last_size_mb
                cmd = self._build_video_cmd(src, temp, q, max_w, cuda_flag)
                silent_run_ffmpeg(cmd, timeout=180)
                size = os.path.getsize(temp)
                last_size_mb = size / 1_000_000.0
                return size

            # First attempt at user quality
            quality = high
            try:
                size = try_encode(quality, use_cuda)
                min_size = min(min_size, size)
                attempts += 1
                if size <= max_size_bytes:
                    shutil.move(temp, best_temp)
                    best_quality = quality
                    best_size = size
                    result_size_mb = best_size / 1_000_000.0

                    def safe_callback():
                        if src not in self.items:
                            return
                        shutil.move(best_temp, dst)
                        callback(True, dst, result_size_mb)
                    self.root.after(0, safe_callback)
                    if os.path.exists(temp):
                        os.remove(temp)
                    return
                else:
                    if os.path.exists(temp):
                        os.remove(temp)
            except Exception:
                # If CUDA failed, permanently fall back for this file
                if use_cuda:
                    use_cuda = False
                if os.path.exists(temp):
                    os.remove(temp)

            # Binary search lower qualities
            high = high - 1
            while low <= high and attempts < max_attempts:
                attempts += 1
                mid = (low + high) // 2
                try:
                    size = try_encode(mid, use_cuda)
                    min_size = min(min_size, size)
                    if size <= max_size_bytes:
                        if mid > best_quality:
                            best_quality = mid
                            best_size = size
                            if os.path.exists(best_temp):
                                os.remove(best_temp)
                            shutil.move(temp, best_temp)
                        low = mid + 1
                    else:
                        high = mid - 1
                        if os.path.exists(temp):
                            os.remove(temp)
                except Exception:
                    if use_cuda:
                        use_cuda = False  # fall back for remaining tries
                    if os.path.exists(temp):
                        os.remove(temp)
                    high = mid - 1

            success = best_quality != -1
            result_size_mb = best_size / 1_000_000.0 if success else (min_size / 1_000_000.0)

            def safe_callback():
                if src not in self.items:
                    return
                if success:
                    shutil.move(best_temp, dst)
                    callback(True, dst, result_size_mb)
                else:
                    if os.path.exists(best_temp):
                        os.remove(best_temp)
                    callback(False, None, result_size_mb)
            self.root.after(0, safe_callback)
            if os.path.exists(temp):
                os.remove(temp)

        else:
            # ── IMAGE PATH (lossless, width search) ──────────────────────────
            target_w = max_w
            min_w = 300
            low, high = min_w, target_w
            best_w = -1
            best_size = float("inf")
            best_temp = tempfile.NamedTemporaryFile(suffix=".webp", delete=False).name
            temp = tempfile.NamedTemporaryFile(suffix=".webp", delete=False).name
            attempts = 0
            max_attempts = 10
            last_size_mb = None

            def try_lossless(w):
                nonlocal last_size_mb
                silent_run_ffmpeg([
                    ffmpeg_path, "-i", src,
                    "-vf", f"scale={w}:-2:flags=lanczos",
                    "-c:v", "libwebp", "-lossless", "1",
                    "-compression_level", "6",
                    "-metadata", f"artist={ARTIST_NAME}",
                    "-metadata", f"description={COMMENT}",
                    "-metadata", f"comment={COMMENT}",
                    "-y", temp
                ], timeout=60)
                size = os.path.getsize(temp)
                last_size_mb = size / 1_000_000.0
                return size

            # Full target width first
            try:
                size = try_lossless(target_w)
                attempts += 1
                if size <= max_size_bytes:
                    shutil.move(temp, best_temp)
                    best_w = target_w
                    best_size = size
                    result_size_mb = best_size / 1_000_000.0

                    def safe_callback():
                        if src not in self.items:
                            return
                        shutil.move(best_temp, dst)
                        callback(True, dst, result_size_mb)
                    self.root.after(0, safe_callback)
                    if os.path.exists(temp):
                        os.remove(temp)
                    return
                else:
                    if os.path.exists(temp):
                        os.remove(temp)
            except Exception:
                if os.path.exists(temp):
                    os.remove(temp)

            # Binary search largest width that still fits
            high = target_w - 40
            while low <= high and attempts < max_attempts:
                attempts += 1
                mid = (low + high) // 2
                try:
                    size = try_lossless(mid)
                    if size <= max_size_bytes:
                        if mid > best_w:
                            best_w = mid
                            best_size = size
                            if os.path.exists(best_temp):
                                os.remove(best_temp)
                            shutil.move(temp, best_temp)
                        low = mid + 1
                    else:
                        high = mid - 1
                        if os.path.exists(temp):
                            os.remove(temp)
                except Exception:
                    if os.path.exists(temp):
                        os.remove(temp)
                    high = mid - 1

            success = best_w != -1
            result_size_mb = best_size / 1_000_000.0 if success else (last_size_mb or 0)

            def safe_callback():
                if src not in self.items:
                    return
                if success:
                    shutil.move(best_temp, dst)
                    callback(True, dst, result_size_mb)
                else:
                    if os.path.exists(best_temp):
                        os.remove(best_temp)
                    callback(False, None, result_size_mb)
            self.root.after(0, safe_callback)
            if os.path.exists(temp):
                os.remove(temp)

    def finish_processing(self, path, webp_path):
        if path not in self.items:
            return
        item = self.items[path]
        item["running"] = False
        item["spinner"].place_forget()
        item["status"].config(text="Done!", fg=SUCCESS)
        item["processed"] = True

        # Heavy frame extraction runs off the main thread so long
        # animated WebPs don't freeze the UI right before the toast.
        def _build_preview():
            try:
                img = Image.open(webp_path)
                pil_frames, durations = [], []
                for frame in ImageSequence.Iterator(img):
                    frame = frame.convert("RGBA")
                    frame.thumbnail((128, 128), Image.Resampling.LANCZOS)
                    bg = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
                    offset = ((128 - frame.width) // 2, (128 - frame.height) // 2)
                    bg.paste(frame, offset, frame)
                    pil_frames.append(bg)
                    durations.append(frame.info.get("duration", 50))

                # PhotoImage objects must be created on the main thread
                def _apply():
                    if path not in self.items:
                        return
                    try:
                        frames = [ImageTk.PhotoImage(f) for f in pil_frames]
                        lbl = self.items[path]["label"]
                        lbl.config(image=frames[0])
                        lbl.image = frames[0]
                        lbl.frames = frames
                        lbl.durations = durations
                        lbl.frame_idx = 0

                        def animate():
                            if (path in self.items
                                    and not self.items[path]["running"]
                                    and hasattr(lbl, "frames")):
                                idx = lbl.frame_idx % len(frames)
                                lbl.config(image=frames[idx])
                                lbl.image = frames[idx]
                                delay = durations[idx] if idx < len(durations) else 50
                                lbl.frame_idx += 1
                                self.root.after(delay, animate)
                        animate()
                    except Exception as e:
                        print("Preview apply failed:", e)

                self.root.after(0, _apply)
            except Exception as e:
                print("Preview build failed:", e)

        threading.Thread(target=_build_preview, daemon=True).start()

    def rotate_spinner(self, path):
        if path not in self.items or not self.items[path]["running"]:
            return
        item = self.items[path]
        item["angle"] = (item["angle"] + 18) % 360
        canvas = item["spinner"]
        canvas.delete("ring")
        canvas.create_arc(
            36, 36, 92, 92, start=item["angle"], extent=300,
            outline=ACCENT, width=5, style="arc", tags="ring"
        )
        self.root.after(36, lambda: self.rotate_spinner(path))

    def clear_all(self):
        for item in self.items.values():
            item["frame"].destroy()
        self.items.clear()
        self.files.clear()
        self.processed.clear()
        self.processing_queue.clear()
        self.root.unbind("<MouseWheel>")
        self.root.unbind("<Button-4>")
        self.root.unbind("<Button-5>")
        self.preview.pack_forget()
        self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=28, pady=20)
        self._update_scrollregion()

    def copy_to_clipboard(self):
        if not self.processed:
            return
        try:
            if win32clipboard is None:
                raise RuntimeError("win32clipboard unavailable")
            paths = [os.path.abspath(p) for p in self.processed]
            data = b"".join(p.encode("utf-16le") + b"\0\0" for p in paths) + b"\0\0"
            drop = struct.pack("<IiiII", 20, 0, 0, 0, 1) + data
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_HDROP, drop)
            win32clipboard.CloseClipboard()
        except Exception:
            if pyperclip:
                pyperclip.copy("\n".join(self.processed))
                messagebox.showinfo("Copied", "Paths copied as text")
            else:
                messagebox.showwarning("Clipboard", "Could not copy files to clipboard.")

        self.notify_user()

    def recopy_last(self):
        if self.processed:
            self.copy_to_clipboard()


if __name__ == "__main__":
    app = DiscordWebPConverter(root)
    root.mainloop()
