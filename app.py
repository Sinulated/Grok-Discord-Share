# --------------------------------------------------------------
# Grok to WEBP – By Sinulated.Art
# THE FINAL VERSION – 100% WORKING + COMPACT UI CONTROLS
# Updated:
#   - silent FFmpeg execution (no console windows on Windows)
#   - .env loading from cwd first + fallback
#   - centered & symmetrical bottom controls
#   - FFmpeg download to current working directory
#   - reliable Windows toast notifications via win11toast
#   - overlays fully removed when processing finishes (only drop overlay remains)
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
import win32clipboard
import win32con
import pyperclip
import tempfile
import urllib.request
import zipfile
import ctypes

try:
    from tkinterdnd2 import *
except ImportError:
    messagebox.showerror("Error", "Run: pip install tkinterdnd2")
    sys.exit()

try:
    from win11toast import toast
except ImportError:
    toast = None  # fallback if missing

from dotenv import load_dotenv

# ── Load .env ────────────────────────────────────────────────────────────────
env_path = os.path.join(os.getcwd(), ".env")
if os.path.isfile(env_path):
    load_dotenv(env_path)
else:
    try:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        fallback_env = os.path.join(base_dir, ".env")
        if os.path.isfile(fallback_env):
            load_dotenv(fallback_env)
    except Exception:
        pass

# ── Defaults ─────────────────────────────────────────────────────────────────
ARTIST_NAME = os.getenv("ARTIST_NAME", "Sinulated")
COMMENT = os.getenv("COMMENT", "Visit Sinulated.art For More!")

DEFAULT_QUALITY = int(os.getenv("START_QUALITY", "91"))
DEFAULT_QUALITY = max(60, min(100, DEFAULT_QUALITY))

DEFAULT_TEMPLATE = os.getenv("FILENAME_TEMPLATE", "Sinulated Preview {index:04d}")
DEFAULT_PREFIX = DEFAULT_TEMPLATE.removesuffix(" {index:04d}").rstrip()

DEFAULT_MAX_FILESIZE_MB = float(os.getenv("MAX_FILESIZE_MB", "10"))

# --------------------------------------------------------------
# Helper for silent FFmpeg execution (no console window on Windows)
# --------------------------------------------------------------
def silent_run_ffmpeg(args, **kwargs):
    kwargs.setdefault("check", True)
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    kwargs.setdefault("stderr", subprocess.DEVNULL)

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo

    return subprocess.run(args, **kwargs)

# --------------------------------------------------------------
# PyInstaller resource helper
# --------------------------------------------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# --------------------------------------------------------------
# FFmpeg path handling
# --------------------------------------------------------------
def get_ffmpeg_path():
    bundled_exe = resource_path(os.path.join("ffmpeg", "bin", "ffmpeg.exe"))
    if os.path.isfile(bundled_exe):
        return bundled_exe

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    cwd_ffmpeg = os.path.join(os.getcwd(), "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.isfile(cwd_ffmpeg):
        return cwd_ffmpeg

    return setup_ffmpeg_and_start()


def setup_ffmpeg_and_start():
    working_dir = os.getcwd()
    ffmpeg_dir = os.path.join(working_dir, "ffmpeg")
    ffmpeg_exe = os.path.join(ffmpeg_dir, "bin", "ffmpeg.exe")

    if os.path.isfile(ffmpeg_exe):
        return ffmpeg_exe
    if shutil.which("ffmpeg"):
        return "ffmpeg"

    splash = tk.Tk()
    splash.title("Grok to WEBP")
    splash.geometry("320x160")
    splash.configure(bg="#121212")
    splash.resizable(False, False)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)

    w = splash.winfo_screenwidth()
    h = splash.winfo_screenheight()
    x = (w - 320) // 2
    y = (h - 160) // 2
    splash.geometry(f"320x160+{x}+{y}")

    tk.Label(splash, text="Grok to WEBP", font=("Helvetica", 18, "bold"), bg="#121212", fg="#8000ff").pack(pady=15)
    tk.Label(splash, text="First time setup: Downloading FFmpeg (~90 MB)", bg="#121212", fg="white", font=("Helvetica", 10)).pack()
    tk.Label(splash, text="Please wait...", bg="#121212", fg="#aaaaaa", font=("Helvetica", 9)).pack(pady=4)

    progress = ttk.Progressbar(splash, length=280, mode='determinate')
    progress.pack(pady=10)
    status = tk.Label(splash, text="Starting download...", bg="#121212", fg="#cccccc", font=("Helvetica", 9))
    status.pack()

    def download():
        try:
            url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = os.path.join(working_dir, "ffmpeg_download.zip")

            def reporthook(block, size, total):
                if total > 0:
                    downloaded = block * size
                    percent = min(100, int(downloaded * 100 / total))
                    progress['value'] = percent
                    status.config(text=f"Downloaded {downloaded//1048576} MB / {total//1048576} MB")
                    splash.update_idletasks()

            status.config(text="Downloading FFmpeg...")
            urllib.request.urlretrieve(url, zip_path, reporthook)

            status.config(text="Extracting...")
            progress['value'] = 100
            splash.update_idletasks()

            os.makedirs(ffmpeg_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as z:
                for file in z.namelist():
                    if file.endswith("ffmpeg.exe"):
                        base = file.split("/")[0]
                        z.extractall(working_dir)
                        src = os.path.join(working_dir, base, "bin")
                        dst = os.path.join(ffmpeg_dir, "bin")
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.move(src, dst)
                        shutil.rmtree(os.path.join(working_dir, base))
                        break

            os.remove(zip_path)
            status.config(text="Ready! Starting app...")
            splash.after(1000, splash.destroy)

        except Exception as e:
            status.config(text="Failed!")
            messagebox.showerror("Error", f"FFmpeg setup failed:\n{e}")
            splash.destroy()
            sys.exit(1)

    threading.Thread(target=download, daemon=True).start()
    splash.mainloop()

    return os.path.join(ffmpeg_dir, "bin", "ffmpeg.exe")


ffmpeg_path = get_ffmpeg_path()

# --------------------------------------------------------------
# Main window + icon
# --------------------------------------------------------------
root = TkinterDnD.Tk()

icon_path = resource_path("512.png")
if os.path.isfile(icon_path):
    try:
        icon_img = tk.PhotoImage(file=icon_path)
        root.iconphoto(True, icon_img)
    except Exception as e:
        print("Failed to load icon:", e)

# ── SCROLLBAR THEMING ───────────────────────────────────────────────────────
style = ttk.Style()
style.theme_use('clam')

style.configure("Purple.Vertical.TScrollbar",
    background="#8000ff",
    troughcolor="#1e1e1e",
    arrowcolor="#dddddd",
    bordercolor="#333333",
    lightcolor="#444444",
    darkcolor="#222222",
    gripcount=0
)

style.map("Purple.Vertical.TScrollbar",
    background=[('active', '#9f40ff'), ('pressed', '#c060ff'), ('disabled', '#555555')],
    troughcolor=[('active', '#2a2a2a'), ('!disabled', '#1e1e1e')]
)

# --------------------------------------------------------------
# Main Application Class
# --------------------------------------------------------------

class DiscordWebPConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Grok to WEBP – By Sinulated.Art")
        self.root.configure(bg="#121212")
        self.root.geometry("540x460")
        self.root.minsize(540, 460)
        self.root.resizable(False, False)

        self.files = []
        self.items = {}
        self.processed = []
        self.processing_queue = []

        self.output_dir = os.path.join(os.getcwd(), "images")
        os.makedirs(self.output_dir, exist_ok=True)

        self.quality_var = tk.IntVar(value=DEFAULT_QUALITY)
        self.prefix_var = tk.StringVar(value=DEFAULT_PREFIX)
        self.maxsize_var = tk.DoubleVar(value=DEFAULT_MAX_FILESIZE_MB)

        self.setup_ui()
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<DropEnter>>', lambda e: self.show_overlay())
        self.root.dnd_bind('<<DropLeave>>', lambda e: self.hide_overlay())
        self.root.dnd_bind('<<Drop>>', self.handle_drop)

    def setup_ui(self):
        self.drop_zone = tk.Frame(self.root, bg="#121212")

        canvas = tk.Canvas(self.drop_zone, bg="#121212", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        canvas.create_rectangle(20, 20, 1, 1, outline="#8000ff", width=3, dash=(10, 6), tags="border")
        canvas.bind("<Configure>", lambda e: canvas.coords("border", 20, 20, e.width-20, e.height-10))

        tk.Label(canvas, text="Drop Videos Here", bg="#121212", fg="white", font=("Helvetica", 16, "bold")).place(relx=0.5, rely=0.3, anchor="center")
        tk.Label(canvas, text="or click to select", bg="#121212", fg="#999999", font=("Helvetica", 10)).place(relx=0.5, rely=0.45, anchor="center")
        tk.Button(canvas, text="Select Files", command=self.select_files,
                  bg="#8000ff", fg="white", font=("Helvetica", 11, "bold"), relief="flat", padx=30, pady=10
                  ).place(relx=0.5, rely=0.70, anchor="center")

        # Preview area
        self.preview = tk.Frame(self.root, bg="#121212")
        self.canvas = tk.Canvas(self.preview, bg="#121212", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self.preview,
            orient="vertical",
            command=self.canvas.yview,
            style="Purple.Vertical.TScrollbar"
        )
        self.grid = tk.Frame(self.canvas, bg="#121212")

        self.window_id = self.canvas.create_window((0, 0), window=self.grid, anchor="nw")

        def update_window_width(event):
            self.canvas.itemconfig(self.window_id, width=event.width)

        self.canvas.bind("<Configure>", update_window_width)
        self.grid.bind("<Configure>", self._update_scrollregion)

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Bottom controls - centered & symmetrical
        bottom = tk.Frame(self.root, bg="#121212")
        bottom.pack(side="bottom", pady=10, padx=10, fill="x")

        btn_frame = tk.Frame(bottom, bg="#121212")
        btn_frame.pack(anchor="center", pady=(0, 15))

        tk.Button(btn_frame, text="Clear All", command=self.clear_all,
                  bg="#ff3333", fg="white", padx=20, pady=9, font=("Helvetica", 10)).pack(side="left", padx=20)

        tk.Button(btn_frame, text="Process All", command=self.start_sequential_processing,
                  bg="#8000ff", fg="white", font=("Helvetica", 12, "bold"), padx=40, pady=12).pack(side="left", padx=20)

        tk.Button(btn_frame, text="Re-copy Last", command=self.recopy_last,
                  bg="#00cc00", fg="white", padx=20, pady=9, font=("Helvetica", 10)).pack(side="left", padx=20)

        settings_frame = tk.Frame(bottom, bg="#121212")
        settings_frame.pack(anchor="center", pady=6)

        tk.Label(settings_frame, text="Quality:", bg="#121212", fg="#cccccc",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 8))
        tk.Entry(settings_frame, textvariable=self.quality_var, width=5, justify="center",
                 bg="#222222", fg="white", insertbackground="white",
                 font=("Helvetica", 11), relief="flat", highlightthickness=1,
                 highlightbackground="#444444", highlightcolor="#8000ff").pack(side="left", padx=(0, 35), ipady=4)

        tk.Label(settings_frame, text="Prefix:", bg="#121212", fg="#cccccc",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 8))
        tk.Entry(settings_frame, textvariable=self.prefix_var, width=20, justify="center",
                 bg="#222222", fg="white", insertbackground="white",
                 font=("Helvetica", 11), relief="flat", highlightthickness=1,
                 highlightbackground="#444444", highlightcolor="#8000ff").pack(side="left", padx=(0, 35), ipady=4)

        tk.Label(settings_frame, text="Max MB:", bg="#121212", fg="#cccccc",
                 font=("Helvetica", 10)).pack(side="left", padx=(0, 8))
        tk.Entry(settings_frame, textvariable=self.maxsize_var, width=6, justify="center",
                 bg="#222222", fg="white", insertbackground="white",
                 font=("Helvetica", 11), relief="flat", highlightthickness=1,
                 highlightbackground="#444444", highlightcolor="#8000ff").pack(side="left", padx=(0, 12), ipady=4)

        self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)

        self.overlay = tk.Label(self.root, text="Drop Here", bg="#333333", fg="white", font=("Helvetica", 32, "bold"))
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.overlay.place_forget()

        # No complete_overlay anymore

    def _update_scrollregion(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def show_overlay(self):
        self.overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.overlay.lift()

    def hide_overlay(self):
        self.overlay.place_forget()

    def notify_user(self):
        """Show Windows toast notification (no click handler) + fallback flash"""
        try:
            if toast is not None:
                toast(
                    "Processing Complete!",
                    "Files copied to clipboard.",
                    icon=resource_path("512.png"),
                    duration="long"
                )
            else:
                raise ImportError("win11toast not available")
        except Exception as e:
            print("Toast failed:", e)
            # Fallback: classic flash
            try:
                hwnd = self.root.winfo_id()
                user32 = ctypes.windll.user32
                if user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, 9)
                user32.FlashWindow(hwnd, True)
                self.root.after(4000, lambda: user32.FlashWindow(hwnd, False))
            except:
                pass

    def select_files(self):
        files = filedialog.askopenfilenames(filetypes=[("Video Files", "*.mp4 *.webm *.mov *.avi *.mkv")])
        self.add_files(files)

    def handle_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        self.add_files(files)
        self.hide_overlay()

    def add_files(self, files):
        added = False
        for f in files:
            if f.lower().endswith((".mp4", ".webm", ".mov", ".avi", ".mkv")) and f not in self.files:
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
        frame = tk.Frame(self.grid, bg="#1e1e1e", width=160, height=200)
        frame.pack_propagate(False)
        frame.grid(row=len(self.items)//3, column=len(self.items)%3, padx=8, pady=8, sticky="n")

        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                thumb_path = tmp.name

            silent_run_ffmpeg(
                [ffmpeg_path, "-i", path, "-vframes", "1", "-q:v", "2", "-y", thumb_path],
                timeout=10
            )

            img = Image.open(thumb_path)
            img.thumbnail((130, 130), Image.Resampling.LANCZOS)
            bg = Image.new("RGB", (130, 130), (30, 30, 30))
            bg.paste(img, ((130 - img.width)//2, (130 - img.height)//2))
            photo = ImageTk.PhotoImage(bg)
            os.unlink(thumb_path)
        except Exception:
            bg = Image.new("RGB", (130, 130), (50, 50, 50))
            photo = ImageTk.PhotoImage(bg)

        lbl = tk.Label(frame, image=photo, bg="#1e1e1e", bd=0)
        lbl.image = photo
        lbl.pack(pady=10)

        spinner = tk.Canvas(frame, highlightthickness=0, width=130, height=130, bg="#1e1e1e")
        spinner.place(x=15, y=10)
        spinner.create_oval(40, 40, 90, 90, outline="#8000ff", width=6, tags="ring")
        spinner.place_forget()

        status = tk.Label(frame, text="Ready", bg="#1e1e1e", fg="#cccccc", font=("Helvetica", 9))
        status.pack(pady=4)

        name = os.path.basename(path)
        if len(name) > 28:
            name = name[:25] + "..."
        tk.Label(frame, text=name, bg="#1e1e1e", fg="#888888", font=("Helvetica", 8)).pack(pady=1)

        remove = tk.Button(frame, text="×", command=lambda p=path, f=frame: self.remove_item(p, f),
                          bg="#ff3333", fg="white", font=("Helvetica", 12, "bold"), relief="flat", width=2)
        remove.place(relx=1, rely=0, anchor="ne", x=-4, y=4)

        self.items[path] = {
            "frame": frame,
            "label": lbl,
            "spinner": spinner,
            "status": status,
            "angle": 0,
            "running": False,
            "processed": False,
            "attempt": 1
        }

        self._update_scrollregion()

    def remove_item(self, path, frame):
        frame.destroy()
        if path in self.files: self.files.remove(path)
        if path in self.processing_queue: self.processing_queue.remove(path)
        if path in self.items: del self.items[path]

        for idx, p in enumerate(self.files):
            self.items[p]["frame"].grid(row=idx//3, column=idx%3, padx=8, pady=8, sticky="n")

        self._update_scrollregion()

        if not self.files:
            self.preview.pack_forget()
            self.root.unbind("<MouseWheel>")
            self.root.unbind("<Button-4>")
            self.root.unbind("<Button-5>")
            self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)

    def start_sequential_processing(self):
        if not self.files: return
        self.processed.clear()
        self.processing_queue = [p for p in self.files if not self.items[p]["processed"]]

        for path in self.processing_queue:
            item = self.items[path]
            item["spinner"].place(x=15, y=10)
            item["status"].config(text=f"Queued ({item['attempt']})", fg="#aaaa00")
            item["running"] = True
            self.rotate_spinner(path)

        if self.processing_queue:
            self.process_next()

    def process_next(self):
        if not self.processing_queue:
            self.copy_to_clipboard()
            # Auto-hide drop overlay just in case
            self.overlay.place_forget()
            return

        path = self.processing_queue[0]
        item = self.items[path]

        item["status"].config(text=f"Converting... ({item['attempt']})", fg="#8000ff")

        prefix = self.prefix_var.get().strip()
        if not prefix:
            prefix = "Preview"

        try:
            existing_files = [
                f for f in os.listdir(self.output_dir)
                if f.startswith(prefix + " ") and f.lower().endswith(".webp")
            ]
            numbers = []
            prefix_len = len(prefix) + 1
            for fname in existing_files:
                try:
                    num_str = fname[prefix_len : -5].strip()
                    num = int(num_str)
                    numbers.append(num)
                except (ValueError, IndexError):
                    continue
            next_index = 1 if not numbers else max(numbers) + 1
        except Exception as e:
            print(f"Warning: Could not scan output directory cleanly: {e}")
            next_index = len(self.processed) + 1

        filename = f"{prefix} {next_index:04d}.webp"
        out_path = os.path.join(self.output_dir, filename)

        def done(success, result):
            if success:
                self.processed.append(result)
                self.finish_processing(path, result)
                item["spinner"].place_forget()
                self.processing_queue.pop(0)
                self.process_next()
            else:
                item["attempt"] += 1
                item["status"].config(text=f"Retrying... ({item['attempt']})", fg="#ffaa00")
                self.root.after(400, self.process_next)

        threading.Thread(target=self.convert_webp, args=(path, out_path, done), daemon=True).start()

    def convert_webp(self, src, dst, callback):
        try:
            quality = self.quality_var.get()
            max_size_bytes = int(self.maxsize_var.get() * 1_000_000)
        except:
            quality = 85
            max_size_bytes = 10_000_000

        quality = max(60, min(100, int(quality)))
        temp = "temp_discord.webp"

        while quality >= 60:
            try:
                silent_run_ffmpeg([
                    ffmpeg_path, "-i", src, "-an", "-c:v", "libwebp",
                    "-loop", "0", "-quality", str(quality),
                    "-compression_level", "6",
                    "-metadata", f"artist={ARTIST_NAME}",
                    "-metadata", f"description={COMMENT}",
                    "-metadata", f"comment={COMMENT}",
                    temp, "-y"
                ], timeout=90)

                if os.path.getsize(temp) <= max_size_bytes:
                    shutil.move(temp, dst)
                    callback(True, dst)
                    return

                if os.path.exists(temp):
                    os.remove(temp)
                quality -= 1

            except Exception as e:
                if os.path.exists(temp):
                    os.remove(temp)
                callback(False, str(e))
                return

        callback(False, "Could not get under size limit even at quality 60")

    def finish_processing(self, path, webp_path):
        item = self.items[path]
        item["running"] = False
        item["spinner"].place_forget()
        item["status"].config(text="Done!", fg="#00ff00")
        item["processed"] = True

        try:
            img = Image.open(webp_path)
            frames = []
            durations = []
            for frame in ImageSequence.Iterator(img):
                frame = frame.convert("RGBA")
                frame.thumbnail((130, 130), Image.Resampling.LANCZOS)
                bg = Image.new("RGBA", (130, 130), (0, 0, 0, 0))
                offset = ((130 - frame.width)//2, (130 - frame.height)//2)
                bg.paste(frame, offset, frame)
                frames.append(ImageTk.PhotoImage(bg))
                durations.append(frame.info.get("duration", 50))

            lbl = item["label"]
            lbl.config(image=frames[0])
            lbl.image = frames[0]
            lbl.frames = frames
            lbl.durations = durations
            lbl.frame_idx = 0

            def animate():
                if path in self.items and not self.items[path]["running"] and hasattr(lbl, "frames"):
                    idx = lbl.frame_idx % len(frames)
                    lbl.config(image=frames[idx])
                    lbl.image = frames[idx]
                    delay = durations[idx] if idx < len(durations) else 50
                    lbl.frame_idx += 1
                    self.root.after(delay, animate)
            animate()
        except Exception as e:
            print("Preview failed:", e)

    def rotate_spinner(self, path):
        if path not in self.items or not self.items[path]["running"]:
            return
        item = self.items[path]
        item["angle"] = (item["angle"] + 20) % 360
        canvas = item["spinner"]
        canvas.delete("ring")
        canvas.create_arc(40, 40, 90, 90, start=item["angle"], extent=320,
                          outline="#8000ff", width=6, style="arc", tags="ring")
        self.root.after(40, lambda: self.rotate_spinner(path))

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
        self.drop_zone.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        self._update_scrollregion()

    def copy_to_clipboard(self):
        if not self.processed: return
        try:
            paths = [os.path.abspath(p) for p in self.processed]
            data = b"".join(p.encode("utf-16le") + b"\0\0" for p in paths) + b"\0\0"
            drop = struct.pack("<IiiII", 20, 0, 0, 0, 1) + data
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_HDROP, drop)
            win32clipboard.CloseClipboard()
        except:
            pyperclip.copy("\n".join(self.processed))
            messagebox.showinfo("Copied", "Paths copied as text")

        self.notify_user()

    def recopy_last(self):
        if self.processed:
            self.copy_to_clipboard()


if __name__ == "__main__":
    app = DiscordWebPConverter(root)
    root.mainloop()
