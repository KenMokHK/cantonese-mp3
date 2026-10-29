"""Type text and save a Cantonese MP3. Needs an internet connection."""

from __future__ import annotations

import asyncio
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import edge_tts

from text_clean import prepare_spoken_text

VOICES = (
    ("曉曼（女聲）", "zh-HK-HiuMaanNeural", "你好，我係曉曼。呢個係女聲示範。"),
    ("曉佳（女聲）", "zh-HK-HiuGaaiNeural", "你好，我係曉佳。呢個係女聲示範。"),
    ("雲龍（男聲）", "zh-HK-WanLungNeural", "你好，我係雲龍。呢個係男聲示範。"),
)
DEMO_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CantoneseMP3" / "voice-demos"
INVALID_NAME_CHARS = '<>:"/\\|?*'


def safe_filename(name: str) -> str:
    cleaned = "".join("_" if ch in INVALID_NAME_CHARS else ch for ch in name).strip().rstrip(".")
    return cleaned or "cantonese"


def rate_label(value: float) -> str:
    rounded = int(round(value))
    if rounded == 0:
        return "正常"
    if rounded > 0:
        return f"快 {rounded}%"
    return f"慢 {abs(rounded)}%"


def mci(command: str) -> int:
    buffer = ctypes.create_unicode_buffer(255)
    return ctypes.windll.winmm.mciSendStringW(command, buffer, 254, 0)


def stop_demo_audio() -> None:
    mci("close voicedemo")


def play_mp3(path: Path) -> None:
    stop_demo_audio()
    quoted = str(path).replace('"', "")
    error = mci(f'open "{quoted}" type mpegvideo alias voicedemo')
    if error:
        error = mci(f'open "{quoted}" alias voicedemo')
    if error:
        os.startfile(path)  # noqa: S606
        return
    mci("play voicedemo")


async def synthesize(text: str, voice: str, rate: str, destination: Path, on_progress=None) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    try:
        rate_number = int(rate.replace("%", "").replace("+", ""))
    except ValueError:
        rate_number = 0
    speed = max(0.5, 1 + rate_number / 100)
    expected = max(8000, len(text) / (4.4 * speed) * 6000)
    received = 0
    with destination.open("wb") as handle:
        async for message in communicate.stream():
            if message["type"] != "audio":
                continue
            handle.write(message["data"])
            received += len(message["data"])
            if on_progress:
                on_progress(min(95, received / expected * 100))
    if on_progress:
        on_progress(100)


class CantoneseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("廣東話轉 MP3")
        self.geometry("820x740")
        self.minsize(680, 600)
        self.configure(bg="#f4f1ea")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_file: Path | None = None
        self.demo_token = 0

        self.voice_var = tk.StringVar(value=VOICES[0][0])
        self.speed_var = tk.DoubleVar(value=-6)
        self.folder_var = tk.StringVar(value=str(Path.home() / "Downloads"))
        self.name_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="貼上文字，然後按「產生 MP3」。選擇聲線會播放短示範。")
        self.percent_var = tk.StringVar(value="")

        self._build()
        self.after(100, self._poll)

    def _build(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", background="#f4f1ea", foreground="#1f2a24", font=("Microsoft JhengHei UI", 18, "bold"))
        style.configure("Sub.TLabel", background="#f4f1ea", foreground="#5c675f", font=("Microsoft JhengHei UI", 10))
        style.configure("Field.TLabel", background="#f4f1ea", foreground="#1f2a24", font=("Microsoft JhengHei UI", 10))
        style.configure("Status.TLabel", background="#e7efe8", foreground="#1f2a24", font=("Microsoft JhengHei UI", 10))
        style.configure("Go.TButton", font=("Microsoft JhengHei UI", 11, "bold"))

        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        ttk.Label(outer, text="廣東話轉 MP3", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text="輸入或貼上文字，儲存成 MP3。表情符號會轉成可以讀出嚟嘅字。",
            style="Sub.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        text_frame = ttk.Frame(outer)
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            wrap="word",
            font=("Microsoft JhengHei UI", 12),
            relief="flat",
            padx=10,
            pady=10,
            undo=True,
            bg="#fffdf8",
            fg="#1c1c1c",
            insertbackground="#1c1c1c",
        )
        scroll = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        options = ttk.Frame(outer)
        options.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        options.columnconfigure(1, weight=1)
        options.columnconfigure(4, weight=1)

        ttk.Label(options, text="聲線", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.voice_box = ttk.Combobox(
            options,
            textvariable=self.voice_var,
            values=[label for label, _voice, _demo in VOICES],
            state="readonly",
            width=18,
        )
        self.voice_box.grid(row=0, column=1, sticky="w", padx=(8, 8))
        self.voice_box.bind("<<ComboboxSelected>>", self._on_voice)
        self.demo_button = ttk.Button(options, text="試聽", command=self._on_voice)
        self.demo_button.grid(row=0, column=2, sticky="w")

        ttk.Label(options, text="語速", style="Field.TLabel").grid(row=0, column=3, sticky="w", padx=(16, 0))
        self.speed = ttk.Scale(options, from_=-30, to=30, variable=self.speed_var, command=self._on_speed)
        self.speed.grid(row=0, column=4, sticky="ew", padx=(8, 8))
        self.speed_label = ttk.Label(options, text=rate_label(self.speed_var.get()), style="Field.TLabel", width=10)
        self.speed_label.grid(row=0, column=5, sticky="w")

        ttk.Label(options, text="儲存至", style="Field.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.folder_entry = ttk.Entry(options, textvariable=self.folder_var)
        self.folder_entry.grid(row=1, column=1, columnspan=4, sticky="ew", padx=(8, 8), pady=(10, 0))
        self.browse_button = ttk.Button(options, text="瀏覽", command=self._browse)
        self.browse_button.grid(row=1, column=5, sticky="w", pady=(10, 0))

        ttk.Label(options, text="檔名", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.name_entry = ttk.Entry(options, textvariable=self.name_var)
        self.name_entry.grid(row=2, column=1, columnspan=4, sticky="ew", padx=(8, 8), pady=(10, 0))
        ttk.Label(options, text="留空就用日期時間", style="Sub.TLabel").grid(row=2, column=5, sticky="w", pady=(10, 0))

        progress_row = ttk.Frame(outer)
        progress_row.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        progress_row.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_row, textvariable=self.percent_var, style="Field.TLabel", width=6).grid(row=0, column=1, padx=(8, 0))

        buttons = ttk.Frame(outer)
        buttons.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        self.make_button = ttk.Button(buttons, text="產生 MP3", style="Go.TButton", command=self._start)
        self.make_button.pack(side="left")
        self.play_button = ttk.Button(buttons, text="播放", command=self._play, state="disabled")
        self.play_button.pack(side="left", padx=(8, 0))
        self.open_button = ttk.Button(buttons, text="開啟資料夾", command=self._open_folder)
        self.open_button.pack(side="left", padx=(8, 0))
        self.clear_button = ttk.Button(buttons, text="清空", command=self._clear)
        self.clear_button.pack(side="left", padx=(8, 0))

        status = tk.Frame(self, bg="#e7efe8")
        status.pack(fill="x", side="bottom")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel", padding=(12, 8)).pack(anchor="w")

    def _on_speed(self, _value: str) -> None:
        self.speed_label.configure(text=rate_label(float(self.speed_var.get())))

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if chosen:
            self.folder_var.set(chosen)

    def _clear(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.text.delete("1.0", "end")
        self._set_progress(0)
        self.status_var.set("已清空。")

    def _voice_info(self) -> tuple[str, str]:
        label = self.voice_var.get()
        for name, voice, demo in VOICES:
            if name == label:
                return voice, demo
        return VOICES[0][1], VOICES[0][2]

    def _rate(self) -> str:
        return f"{int(round(self.speed_var.get())):+d}%"

    def _output_path(self) -> Path:
        folder = Path(self.folder_var.get().strip() or str(Path.home() / "Downloads"))
        raw_name = self.name_var.get().strip()
        if not raw_name:
            raw_name = "cantonese_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = safe_filename(raw_name)
        if not filename.lower().endswith(".mp3"):
            filename += ".mp3"
        return folder / filename

    def _set_progress(self, value: float) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=100)
        self.progress["value"] = value
        self.percent_var.set(f"{int(value)}%")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.make_button.configure(state=state)
        self.browse_button.configure(state=state)
        self.demo_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.voice_box.configure(state="disabled" if busy else "readonly")
        self.name_entry.configure(state=state)
        self.folder_entry.configure(state=state)
        self.speed.configure(state=state)
        if busy:
            self.play_button.configure(state="disabled")
        elif self.last_file:
            self.play_button.configure(state="normal")

    def _on_voice(self, _event=None) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.demo_token += 1
        token = self.demo_token
        voice, demo = self._voice_info()
        rate = self._rate()
        self.status_var.set("正在準備聲線示範…")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        self.percent_var.set("")
        threading.Thread(target=self._run_demo, args=(token, voice, demo, rate), daemon=True).start()

    def _run_demo(self, token: int, voice: str, demo: str, rate: str) -> None:
        try:
            safe_rate = rate.replace("%", "").replace("+", "p").replace("-", "m")
            DEMO_DIR.mkdir(parents=True, exist_ok=True)
            path = DEMO_DIR / f"{voice}_{safe_rate}.mp3"
            if not path.exists() or path.stat().st_size < 1000:
                asyncio.run(synthesize(demo, voice, rate, path))
            if token != self.demo_token:
                return
            play_mp3(path)
            self.events.put(("demo", "正在播放聲線示範。"))
        except Exception as exc:
            if token == self.demo_token:
                self.events.put(("demo-error", str(exc)))

    def _apply_clean(self, raw: str) -> str:
        spoken, removed = prepare_spoken_text(raw)
        if spoken != raw.strip():
            self.text.delete("1.0", "end")
            self.text.insert("1.0", spoken)
        if removed:
            self.status_var.set(f"已移除 {removed} 個表情符號，並整理成可朗讀文字。")
        return spoken

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        spoken = self._apply_clean(self.text.get("1.0", "end"))
        if not spoken:
            messagebox.showinfo("廣東話轉 MP3", "請輸入可以朗讀嘅文字。表情符號已經移除。")
            return
        destination = self._output_path()
        if destination.exists():
            overwrite = messagebox.askyesno("廣東話轉 MP3", f"檔案已存在，要覆蓋嗎？\n{destination}")
            if not overwrite:
                return
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("廣東話轉 MP3", f"無法建立資料夾。\n{exc}")
            return

        stop_demo_audio()
        voice, _demo = self._voice_info()
        rate = self._rate()
        self._set_busy(True)
        self._set_progress(0)
        self.status_var.set("正在產生廣東話 MP3…")
        self.worker = threading.Thread(
            target=self._run_synth,
            args=(spoken, voice, rate, destination),
            daemon=True,
        )
        self.worker.start()

    def _run_synth(self, text: str, voice: str, rate: str, destination: Path) -> None:
        def report(value: float) -> None:
            self.events.put(("progress", value))

        try:
            asyncio.run(synthesize(text, voice, rate, destination, report))
        except Exception as exc:
            self.events.put(("error", str(exc)))
            return
        self.events.put(("done", destination))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self._set_progress(float(payload))
                elif kind == "done":
                    path = Path(str(payload))
                    self.last_file = path
                    self._set_progress(100)
                    self._set_busy(False)
                    size_kb = path.stat().st_size / 1024
                    self.status_var.set(f"已儲存：{path}  （{size_kb:.0f} KB）")
                elif kind == "error":
                    self._set_progress(0)
                    self._set_busy(False)
                    self.status_var.set("產生失敗。請檢查網絡後再試。")
                    messagebox.showerror("廣東話轉 MP3", f"無法產生 MP3。請確認已連接網絡。\n\n{payload}")
                elif kind == "demo":
                    self._set_progress(100)
                    self.status_var.set(str(payload))
                elif kind == "demo-error":
                    self._set_progress(0)
                    self.status_var.set("聲線示範失敗。請檢查網絡。")
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _play(self) -> None:
        if self.last_file and self.last_file.exists():
            os.startfile(self.last_file)  # noqa: S606

    def _open_folder(self) -> None:
        target = self.last_file.parent if self.last_file else Path(self.folder_var.get())
        if not target.exists():
            messagebox.showinfo("廣東話轉 MP3", "資料夾還未建立。")
            return
        os.startfile(target)  # noqa: S606

    def _on_close(self) -> None:
        stop_demo_audio()
        self.destroy()


def cli_save(text: str, destination: str) -> None:
    spoken, _removed = prepare_spoken_text(text)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    status = path.with_suffix(".status.txt")
    try:
        asyncio.run(synthesize(spoken, VOICES[0][1], "-6%", path))
    except Exception as exc:
        status.write_text(f"error\n{exc}", encoding="utf-8")
        raise
    status.write_text(f"ok\n{path.stat().st_size}", encoding="utf-8")


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = CantoneseApp()
    app.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--save":
        cli_save(sys.argv[2], sys.argv[3])
    else:
        main()
