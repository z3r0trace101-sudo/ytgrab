"""Tkinter desktop interface for ytgrab."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ytgrab.core.downloader import download_media
from ytgrab.core.errors import YtGrabError
from ytgrab.core.media_info import fetch_media_info
from ytgrab.core.models import (
    DownloadRequest,
    FailedEvent,
    FinishedEvent,
    MediaInfo,
    ProgressEvent,
)
from ytgrab.support.paths import downloads_folder

logger = logging.getLogger(__name__)


class MainWindow:
    """Own the UI state and marshal worker results back to Tk's main thread."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ytgrab")
        self.root.geometry("700x560")
        self.root.minsize(620, 500)

        self._events: queue.Queue[object] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._media_info: MediaInfo | None = None
        self._state = "IDLE"

        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="Video (MP4)")
        self.quality_var = tk.StringVar(value="Best available")
        self.folder_var = tk.StringVar(value=str(downloads_folder()))
        self.title_var = tk.StringVar(value="Paste a YouTube video link to begin.")
        self.details_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0.0)

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_state("IDLE")
        self.root.after(100, self._poll_events)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="ytgrab", font=("Segoe UI", 22, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            outer,
            text="Download content you own or have permission to download.",
        ).pack(anchor="w", pady=(0, 18))

        ttk.Label(outer, text="YouTube URL").pack(anchor="w")
        url_row = ttk.Frame(outer)
        url_row.pack(fill="x", pady=(4, 12))
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.check_button = ttk.Button(
            url_row, text="Check link", command=self._start_fetch
        )
        self.check_button.pack(side="left", padx=(8, 0))

        info = ttk.LabelFrame(outer, text="Video information", padding=12)
        info.pack(fill="x", pady=(0, 12))
        ttk.Label(info, textvariable=self.title_var, wraplength=620).pack(anchor="w")
        ttk.Label(info, textvariable=self.details_var).pack(anchor="w", pady=(6, 0))

        options = ttk.LabelFrame(outer, text="Download", padding=12)
        options.pack(fill="x", pady=(0, 12))
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Type").grid(row=0, column=0, sticky="w", pady=4)
        self.mode_combo = ttk.Combobox(
            options,
            textvariable=self.mode_var,
            values=("Video (MP4)", "Audio (MP3)"),
            state="readonly",
        )
        self.mode_combo.grid(row=0, column=1, sticky="ew", pady=4)
        self.mode_combo.bind("<<ComboboxSelected>>", self._mode_changed)

        ttk.Label(options, text="Video quality").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.quality_combo = ttk.Combobox(
            options, textvariable=self.quality_var, state="readonly"
        )
        self.quality_combo.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(options, text="Save to").grid(row=2, column=0, sticky="w", pady=4)
        folder_row = ttk.Frame(options)
        folder_row.grid(row=2, column=1, sticky="ew", pady=4)
        folder_row.columnconfigure(0, weight=1)
        ttk.Entry(folder_row, textvariable=self.folder_var).grid(
            row=0, column=0, sticky="ew"
        )
        self.folder_button = ttk.Button(
            folder_row, text="Browse…", command=self._choose_folder
        )
        self.folder_button.grid(row=0, column=1, padx=(8, 0))

        self.download_button = ttk.Button(
            outer, text="Download", command=self._start_download
        )
        self.download_button.pack(fill="x", pady=(0, 10))

        self.progress = ttk.Progressbar(
            outer, variable=self.progress_var, maximum=100
        )
        self.progress.pack(fill="x")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))

    def _mode_changed(self, _event: object = None) -> None:
        self._update_quality_values()

    def _update_quality_values(self) -> None:
        if self.mode_var.get().startswith("Audio"):
            self.quality_combo["values"] = ("Best available",)
            self.quality_var.set("Best available")
            return
        resolutions = self._media_info.resolutions if self._media_info else ()
        values = ["Best available", *[f"{height}p" for height in resolutions]]
        self.quality_combo["values"] = values or ("Best available",)
        if self.quality_var.get() not in values:
            self.quality_var.set(values[0])

    def _start_fetch(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._media_info = None
        self.title_var.set("Checking link…")
        self.details_var.set("")
        self.status_var.set("Fetching video information…")
        self._apply_state("FETCHING")
        url = self.url_var.get()
        self._worker = threading.Thread(
            target=self._fetch_worker, args=(url,), daemon=True
        )
        self._worker.start()

    def _fetch_worker(self, url: str) -> None:
        try:
            info = fetch_media_info(url)
        except Exception as exc:
            self._events.put(FailedEvent(exc))
        else:
            self._events.put(info)

    def _start_download(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        mode = "audio" if self.mode_var.get().startswith("Audio") else "video"
        height = None
        if mode == "video" and self.quality_var.get() != "Best available":
            height = int(self.quality_var.get().rstrip("p"))
        request = DownloadRequest(
            url=self.url_var.get(),
            mode=mode,
            output_folder=self.folder_var.get(),
            video_height=height,
        )
        self.status_var.set("Starting download…")
        self.progress_var.set(0)
        self._apply_state("DOWNLOADING")
        self._worker = threading.Thread(
            target=self._download_worker, args=(request,), daemon=True
        )
        self._worker.start()

    def _download_worker(self, request: DownloadRequest) -> None:
        try:
            result = download_media(request, self._events.put)
        except Exception as exc:
            self._events.put(FailedEvent(exc))
        else:
            self._events.put(result)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, event: object) -> None:
        if isinstance(event, MediaInfo):
            self._media_info = event
            self.title_var.set(event.title)
            uploader = event.uploader or "Unknown uploader"
            duration = _format_duration(event.duration_seconds)
            self.details_var.set(
                f"{uploader}  •  {duration}  •  "
                f"{', '.join(f'{r}p' for r in event.resolutions) or 'unknown quality'}"
            )
            self._update_quality_values()
            self.status_var.set("Ready to download")
            self._apply_state("READY")
            return

        if isinstance(event, ProgressEvent):
            self.status_var.set(_progress_text(event))
            if event.percent is not None:
                self.progress["mode"] = "determinate"
                self.progress_var.set(event.percent)
            else:
                self.progress["mode"] = "indeterminate"
                self.progress.start(10)
            if event.percent is not None and event.stage == "Processing…":
                self.progress.stop()
            return

        if isinstance(event, FinishedEvent):
            self.progress.stop()
            self.progress["mode"] = "determinate"
            self.progress_var.set(100)
            self.status_var.set("Download complete")
            self._apply_state("DONE")
            answer = messagebox.askyesno(
                "Download complete",
                f"Saved to:\n{event.path}\n\nOpen the containing folder?",
            )
            if answer:
                os.startfile(str(Path(event.path).parent))
            return

        if isinstance(event, FailedEvent):
            self.progress.stop()
            self._apply_state("ERROR")
            self.status_var.set(
                "Download failed" if self._state == "ERROR" else "Error"
            )
            error = event.error
            if isinstance(error, YtGrabError):
                logger.error(
                    "%s: %s", type(error).__name__, error.detail or str(error)
                )
                message = error.user_message
            else:
                logger.error(
                    "Unexpected UI worker error: %s",
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )
                message = (
                    "Something unexpected went wrong. "
                    "Details were saved to the log."
                )
            messagebox.showerror("ytgrab", message)

    def _apply_state(self, state: str) -> None:
        self._state = state
        fetching = state == "FETCHING"
        busy = state in {"FETCHING", "DOWNLOADING"}
        ready = state in {"READY", "DONE", "ERROR"}
        self.check_button["state"] = "disabled" if busy else "normal"
        self.download_button["state"] = (
            "normal" if ready and not fetching else "disabled"
        )
        self.folder_button["state"] = "disabled" if busy else "normal"
        self.mode_combo["state"] = "disabled" if busy else "readonly"
        self.quality_combo["state"] = "disabled" if busy else "readonly"
        self.url_entry["state"] = "disabled" if busy else "normal"


    def _on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno(
                "Download in progress",
                "A download is still running. Close ytgrab anyway?",
            ):
                return
        self.root.destroy()

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get())
        if chosen:
            self.folder_var.set(chosen)


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Unknown duration"
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _progress_text(event: ProgressEvent) -> str:
    text = event.stage
    if event.percent is not None:
        text += f"  {event.percent:.0f}%"
    extras = [value for value in (event.speed, event.eta) if value]
    if extras:
        text += "  •  " + "  •  ".join(extras)
    return text
