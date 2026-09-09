"""Tkinter dialog for managing schedule entries.

Runs on its own dedicated thread (started by the tray) so it never blocks the
tray icon's own event loop or the app's Win32 message loop.
"""
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from . import schedule as schedule_mod

_HOUR_CHOICES = [str(h) for h in range(1, 13)]
_MINUTE_CHOICES = ["00", "15", "30", "45"]
_AMPM_CHOICES = ["AM", "PM"]
_BRIGHTNESS_CHOICES = [str(v) for v in range(100, -1, -10)]


def _make_calendar_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 10, 60, 60), radius=6, fill=(255, 255, 255, 255), outline=(70, 70, 70, 255), width=2)
    draw.rectangle((6, 12, 58, 22), fill=(200, 55, 55, 255))
    draw.rectangle((16, 4, 21, 16), fill=(90, 90, 90, 255))
    draw.rectangle((43, 4, 48, 16), fill=(90, 90, 90, 255))
    for x in (20, 32, 44):
        draw.line((x, 26, x, 56), fill=(210, 210, 210, 255))
    for y in (32, 42, 52):
        draw.line((8, y, 56, y), fill=(210, 210, 210, 255))
    return img


def _to_24h(hour12: int, ampm: str) -> int:
    hour12 = hour12 % 12
    return hour12 + (12 if ampm == "PM" else 0)


def _to_12h(hour24: int) -> tuple[int, str]:
    ampm = "PM" if hour24 >= 12 else "AM"
    hour12 = hour24 % 12 or 12
    return hour12, ampm


def open_schedule_editor(app) -> None:
    root = tk.Tk()
    root.title("PowerDim Schedule")
    root.geometry("480x360")
    root.minsize(480, 360)
    # Kept on root to prevent garbage collection from clearing the window icon.
    root.icon_image = ImageTk.PhotoImage(_make_calendar_icon())
    # False (not the process-wide default) so this doesn't get clobbered by
    # another editor dialog's own icon -- Tk's "-default" icon on Windows is
    # shared at the window-class level across the whole process, not per-window.
    root.iconphoto(False, root.icon_image)
    # Windows often won't hand foreground focus to a window raised from a
    # background thread (tray click), so it can open silently behind other
    # windows unless we force it forward.
    root.lift()
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.focus_force()

    entries = schedule_mod.load_entries()
    selected_entry = None  # the ScheduleEntry currently loaded into the form, if any
    suspend_autosave = False  # True while the form is being updated programmatically

    columns = ("time", "brightness", "enabled")
    tree = ttk.Treeview(root, columns=columns, show="headings", height=8, selectmode="browse")
    tree.heading("time", text="Time")
    tree.heading("brightness", text="Brightness")
    tree.heading("enabled", text="Status")
    tree.column("time", width=100, anchor="center")
    tree.column("brightness", width=100, anchor="center")
    tree.column("enabled", width=100, anchor="center")
    tree.tag_configure("active_now", background="#d6f5d6")
    tree.tag_configure("disabled", foreground="#999999")
    tree.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 4), sticky="nsew")

    hint = ttk.Label(
        root,
        text="Select a row to edit it. The highlighted row is active right now.",
        foreground="#555555",
    )
    hint.grid(row=1, column=0, columnspan=4, padx=10, sticky="w")

    def ordered_entries():
        return sorted(entries, key=lambda e: e.minutes_of_day)

    def refresh() -> None:
        tree.delete(*tree.get_children())
        active = schedule_mod.active_entry(entries, datetime.now())
        for entry in ordered_entries():
            tags = []
            if not entry.enabled:
                tags.append("disabled")
            elif entry is active:
                tags.append("active_now")
            hour12, ampm = _to_12h(entry.hour)
            tree.insert(
                "",
                tk.END,
                iid=str(id(entry)),
                values=(
                    f"{hour12}:{entry.minute:02d} {ampm}",
                    f"{entry.brightness}%",
                    "Active" if entry.enabled else "Inactive",
                ),
                tags=tags,
            )

    def persist() -> None:
        schedule_mod.save_entries(entries)
        app.reload_schedule()
        refresh()
        if selected_entry is not None:
            tree.selection_set(str(id(selected_entry)))

    hour_var = tk.StringVar(value="9")
    minute_var = tk.StringVar(value="00")
    ampm_var = tk.StringVar(value="AM")
    brightness_var = tk.StringVar(value="100")
    enabled_var = tk.BooleanVar(value=True)

    form = ttk.LabelFrame(root, text="Entry")
    form.grid(row=2, column=0, columnspan=4, padx=10, pady=8, sticky="ew")

    ttk.Label(form, text="Time").grid(row=0, column=0, padx=6, pady=6)
    ttk.Combobox(form, textvariable=hour_var, values=_HOUR_CHOICES, width=3, state="readonly").grid(
        row=0, column=1, padx=(6, 0)
    )
    ttk.Combobox(form, textvariable=minute_var, values=_MINUTE_CHOICES, width=3, state="readonly").grid(
        row=0, column=2, padx=(0, 0)
    )
    ttk.Combobox(form, textvariable=ampm_var, values=_AMPM_CHOICES, width=4, state="readonly").grid(
        row=0, column=3, padx=6
    )
    ttk.Label(form, text="Brightness %").grid(row=0, column=4, padx=6)
    ttk.Combobox(
        form, textvariable=brightness_var, values=_BRIGHTNESS_CHOICES, width=6, state="readonly"
    ).grid(row=0, column=5, padx=6)
    ttk.Checkbutton(form, text="Active", variable=enabled_var).grid(row=0, column=6, padx=6)

    def clear_form() -> None:
        nonlocal selected_entry, suspend_autosave
        selected_entry = None
        suspend_autosave = True
        hour_var.set("9")
        minute_var.set("00")
        ampm_var.set("AM")
        brightness_var.set("100")
        enabled_var.set(True)
        suspend_autosave = False
        tree.selection_remove(*tree.selection())

    def parse_form():
        try:
            hour12 = int(hour_var.get())
            minute = int(minute_var.get())
            brightness = int(brightness_var.get())
        except ValueError:
            messagebox.showerror("PowerDim Schedule", "Hour, minute, and brightness must be whole numbers.")
            return None
        ampm = ampm_var.get()
        if not (1 <= hour12 <= 12 and 0 <= minute <= 59 and ampm in ("AM", "PM")):
            messagebox.showerror("PowerDim Schedule", "Time must be a valid 12-hour AM/PM time.")
            return None
        if not (0 <= brightness <= 100):
            messagebox.showerror("PowerDim Schedule", "Brightness must be between 0 and 100.")
            return None
        return _to_24h(hour12, ampm), minute, brightness

    def on_row_selected(_event) -> None:
        nonlocal selected_entry, suspend_autosave
        selection = tree.selection()
        if not selection:
            return
        entry = next((e for e in entries if str(id(e)) == selection[0]), None)
        if entry is None:
            return
        suspend_autosave = True
        selected_entry = entry
        hour12, ampm = _to_12h(entry.hour)
        hour_var.set(str(hour12))
        minute_var.set(f"{entry.minute:02d}")
        ampm_var.set(ampm)
        brightness_var.set(str(entry.brightness))
        enabled_var.set(entry.enabled)
        suspend_autosave = False

    tree.bind("<<TreeviewSelect>>", on_row_selected)

    def autosave(*_args) -> None:
        # Only live-updates an already-selected entry; new entries require
        # the explicit Add button so they aren't created just by typing.
        if suspend_autosave or selected_entry is None:
            return
        parsed = parse_form()
        if parsed is None:
            return
        hour, minute, brightness = parsed
        selected_entry.hour, selected_entry.minute, selected_entry.brightness = hour, minute, brightness
        selected_entry.enabled = enabled_var.get()
        persist()

    for var in (hour_var, minute_var, ampm_var, brightness_var, enabled_var):
        var.trace_add("write", autosave)

    def add_entry() -> None:
        nonlocal selected_entry
        if selected_entry is not None:
            messagebox.showinfo("PowerDim Schedule", "Click Clear first to add a new entry.")
            return
        parsed = parse_form()
        if parsed is None:
            return
        hour, minute, brightness = parsed
        selected_entry = schedule_mod.ScheduleEntry(
            hour=hour, minute=minute, brightness=brightness, enabled=enabled_var.get()
        )
        entries.append(selected_entry)
        persist()

    def delete_entry() -> None:
        nonlocal selected_entry
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("PowerDim Schedule", "Select an entry to delete first.")
            return
        entry = next((e for e in entries if str(id(e)) == selection[0]), None)
        if entry is not None:
            entries.remove(entry)
            selected_entry = None
            persist()
        clear_form()

    button_bar = ttk.Frame(root)
    button_bar.grid(row=3, column=0, columnspan=4, pady=(0, 10))
    ttk.Button(button_bar, text="Add Entry", command=add_entry).grid(row=0, column=0, padx=6)
    ttk.Button(button_bar, text="Delete Selected", command=delete_entry).grid(row=0, column=1, padx=6)
    ttk.Button(button_bar, text="Clear", command=clear_form).grid(row=0, column=2, padx=6)

    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    refresh()
    root.mainloop()
    # Re-check right away so a newly added/edited entry is felt immediately
    # instead of waiting for the next scheduled poll.
    app.check_schedule_now()
