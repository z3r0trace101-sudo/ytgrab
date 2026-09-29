"""Application startup and Windows desktop integration."""

import logging
import os
import tkinter as tk
from tkinter import ttk

from ytgrab.support.logging_setup import configure_logging
from ytgrab.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _enable_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness when running on Windows."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        logger.debug("Could not enable Windows DPI awareness", exc_info=True)


def main() -> None:
    """Create and run the Tkinter application."""
    configure_logging()
    _enable_dpi_awareness()
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    MainWindow(root)
    root.mainloop()
