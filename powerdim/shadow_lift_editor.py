"""Tkinter dialog for configuring the OLED VRR Black Flicker Tool's intensity.

Runs on its own dedicated thread (started by the tray) so it never blocks the
tray icon's own event loop or the app's Win32 message loop.
"""
import tkinter as tk
from tkinter import ttk

from .app import SHADOW_LIFT_INTENSITY_CHOICES_PERCENT

_INTENSITY_LABELS = {15: "Low", 30: "Medium", 50: "High"}


def open_shadow_lift_editor(app) -> None:
    root = tk.Tk()
    root.title("OLED VRR Black Flicker Tool")
    root.resizable(False, False)
    # Windows often won't hand foreground focus to a window raised from a
    # background thread (tray click), so it can open silently behind other
    # windows unless we force it forward.
    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.focus_force()

    frame = ttk.Frame(root, padding=12)
    frame.grid(row=0, column=0, sticky="nsew")

    ttk.Label(
        frame,
        text="Intensity: how much to raise near-black output to reduce flicker.",
        wraplength=280,
    ).grid(row=0, column=0, sticky="w", pady=(0, 8))

    selected = tk.IntVar(value=app.shadow_lift_intensity_percent)
    for i, percent in enumerate(SHADOW_LIFT_INTENSITY_CHOICES_PERCENT):
        ttk.Radiobutton(
            frame,
            text=_INTENSITY_LABELS.get(percent, f"{percent}%"),
            variable=selected,
            value=percent,
        ).grid(row=1 + i, column=0, sticky="w")

    def save() -> None:
        app.set_shadow_lift_intensity(selected.get())
        root.destroy()

    button_row = 1 + len(SHADOW_LIFT_INTENSITY_CHOICES_PERCENT)
    ttk.Button(frame, text="Save", command=save).grid(row=button_row, column=0, sticky="e", pady=(12, 0))

    root.mainloop()
