"""Tkinter dialog for configuring global hotkeys.

Runs on its own dedicated thread (started by the tray) so it never blocks the
tray icon's own event loop or the app's Win32 message loop.
"""
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from . import hotkeys as hotkeys_mod
from .hotkeys import ACTION_LABELS, ACTION_SET_VALUE, HotkeyBinding

_VALUE_CHOICES = [str(v) for v in range(100, -1, -10)]
_ACTION_NAME_BY_LABEL = {label: action for action, label in ACTION_LABELS.items()}


def _make_keyboard_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 16, 60, 52), radius=6, fill=(240, 240, 240, 255), outline=(70, 70, 70, 255), width=2)
    key_w, key_h, gap = 7, 7, 3
    for row in range(3):
        for col in range(6):
            x = 9 + col * (key_w + gap)
            y = 21 + row * (key_h + gap)
            draw.rectangle((x, y, x + key_w, y + key_h), fill=(90, 130, 220, 255))
    space_y = 21 + 3 * (key_h + gap)
    draw.rectangle((9, space_y, 9 + 4 * (key_w + gap), space_y + key_h), fill=(90, 130, 220, 255))
    return img


def open_hotkey_editor(app) -> None:
    root = tk.Tk()
    root.title("PowerDim Hotkeys")
    root.resizable(False, False)
    # Kept on root to prevent garbage collection from clearing the window icon.
    root.icon_image = ImageTk.PhotoImage(_make_keyboard_icon())
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

    # Edited locally and only pushed to the running app (and disk) on Save,
    # so a cancelled dialog never disturbs the hotkeys currently in effect.
    pending = list(app.hotkey_bindings)

    columns = ("action", "hotkey", "value")
    tree = ttk.Treeview(root, columns=columns, show="headings", height=6, selectmode="browse")
    tree.heading("action", text="Action")
    tree.heading("hotkey", text="Hotkey")
    tree.heading("value", text="Target")
    tree.column("action", width=150)
    tree.column("hotkey", width=120, anchor="center")
    tree.column("value", width=60, anchor="center")
    tree.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 4), sticky="nsew")

    def refresh() -> None:
        tree.delete(*tree.get_children())
        for i, binding in enumerate(pending):
            value = f"{binding.value}%" if binding.action == ACTION_SET_VALUE else ""
            tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(ACTION_LABELS[binding.action], hotkeys_mod.hotkey_label(binding.modifiers, binding.vk), value),
            )

    add_frame = ttk.LabelFrame(root, text="Add Hotkey")
    add_frame.grid(row=1, column=0, columnspan=4, padx=10, pady=8, sticky="ew")

    action_var = tk.StringVar(value=ACTION_LABELS[hotkeys_mod.ACTION_BRIGHTNESS_UP])
    key_var = tk.StringVar(value=hotkeys_mod.KEY_CHOICES[0])
    value_var = tk.StringVar(value="50")
    modifier_vars = {name: tk.BooleanVar(value=(name in ("Ctrl", "Alt"))) for name, _flag in hotkeys_mod.MODIFIER_FLAGS}

    ttk.Label(add_frame, text="Action").grid(row=0, column=0, padx=6, pady=6, sticky="w")
    ttk.Combobox(
        add_frame, textvariable=action_var, values=list(ACTION_LABELS.values()), width=20, state="readonly"
    ).grid(row=0, column=1, columnspan=3, padx=6, sticky="w")

    ttk.Label(add_frame, text="Modifiers").grid(row=1, column=0, padx=6, pady=6, sticky="w")
    for i, (name, _flag) in enumerate(hotkeys_mod.MODIFIER_FLAGS):
        ttk.Checkbutton(add_frame, text=name, variable=modifier_vars[name]).grid(
            row=1, column=1 + i, padx=2, sticky="w"
        )

    ttk.Label(add_frame, text="Key").grid(row=2, column=0, padx=6, pady=6, sticky="w")
    ttk.Combobox(
        add_frame, textvariable=key_var, values=hotkeys_mod.KEY_CHOICES, width=10, state="readonly"
    ).grid(row=2, column=1, padx=6, sticky="w")

    value_label = ttk.Label(add_frame, text="Target %")
    value_combo = ttk.Combobox(add_frame, textvariable=value_var, values=_VALUE_CHOICES, width=6, state="readonly")

    def on_action_changed(*_args) -> None:
        if action_var.get() == ACTION_LABELS[ACTION_SET_VALUE]:
            value_label.grid(row=2, column=2, padx=(12, 6), sticky="w")
            value_combo.grid(row=2, column=3, sticky="w")
        else:
            value_label.grid_forget()
            value_combo.grid_forget()

    action_var.trace_add("write", on_action_changed)
    on_action_changed()

    def add_binding() -> None:
        modifiers = 0
        for name, flag in hotkeys_mod.MODIFIER_FLAGS:
            if modifier_vars[name].get():
                modifiers |= flag
        if modifiers == 0:
            messagebox.showerror("PowerDim Hotkeys", "Select at least one modifier (Ctrl/Alt/Shift/Win).")
            return
        action = _ACTION_NAME_BY_LABEL[action_var.get()]
        vk = hotkeys_mod.KEY_NAME_TO_VK[key_var.get()]
        value = int(value_var.get()) if action == ACTION_SET_VALUE else 100
        pending.append(HotkeyBinding(action=action, modifiers=modifiers, vk=vk, value=value))
        refresh()

    def delete_selected() -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("PowerDim Hotkeys", "Select a hotkey to delete first.")
            return
        del pending[int(selection[0])]
        refresh()

    def save() -> None:
        failed = app.set_hotkey_bindings(pending)
        if failed:
            # Drop only the ones that failed (e.g. already claimed by another
            # app, or blocked entirely under RDP) and keep the dialog open so
            # the user can see why and adjust instead of losing their edits.
            pending[:] = [b for b in pending if b not in failed]
            refresh()
            names = "\n".join(hotkeys_mod.hotkey_label(b.modifiers, b.vk) for b in failed)
            messagebox.showwarning(
                "PowerDim Hotkeys",
                f"These hotkeys could not be registered (already in use by another "
                f"application, or blocked entirely -- e.g. some hotkeys can't be "
                f"registered over Remote Desktop) and were not saved:\n{names}",
            )
            return
        root.destroy()

    ttk.Button(add_frame, text="Add", command=add_binding).grid(row=1, column=5, rowspan=2, padx=(12, 6))

    button_bar = ttk.Frame(root)
    button_bar.grid(row=2, column=0, columnspan=4, pady=(0, 10))
    ttk.Button(button_bar, text="Delete Selected", command=delete_selected).grid(row=0, column=0, padx=6)
    ttk.Button(button_bar, text="Save", command=save).grid(row=0, column=1, padx=6)
    ttk.Button(button_bar, text="Cancel", command=root.destroy).grid(row=0, column=2, padx=6)

    refresh()
    root.mainloop()
