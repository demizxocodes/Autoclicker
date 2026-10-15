"""Main window: profiles, the click-point list, run settings, start/stop."""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .model import (
    BUTTONS,
    CLICK_TYPES,
    MIN_DELAY,
    TIME_UNITS,
    ClickPoint,
    Profile,
    ProfileStore,
    next_point_name,
)
from .picker import pick_location
from .runner import ROUNDS_DONE, STOPPED, TIME_UP, ClickRunner
from . import winclick

HOTKEY = "F6"
SAVE_DELAY_MS = 400
POLL_MS = 50

CLICK_TYPE_BY_LABEL = {label: n for n, label in CLICK_TYPES.items()}


class App:
    def __init__(self, root: tk.Tk, store: ProfileStore, clickers: dict, window_at=lambda x, y: None):
        self.root = root
        self.store = store
        self.clickers = clickers  # "mouse" and "background" click functions
        self.window_at = window_at
        self.events: queue.Queue = queue.Queue()  # messages from worker threads
        self.runner: ClickRunner | None = None
        self.selected: int | None = None
        self._loading = False
        self._save_job = None

        root.title("Autoclicker")
        root.minsize(680, 560)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_profile_bar()
        self._build_points()
        self._build_editor()
        self._build_run_settings()
        self._build_controls()

        self.load_profile(store.last_profile)
        root.after(POLL_MS, self._poll_events)

    # ---------- layout ----------

    def _build_profile_bar(self):
        bar = ttk.Frame(self.root, padding=(10, 10, 10, 0))
        bar.pack(fill="x")
        ttk.Label(bar, text="Profile:").pack(side="left")
        self.profile_var = tk.StringVar()
        self.profile_box = ttk.Combobox(bar, textvariable=self.profile_var, state="readonly", width=24)
        self.profile_box.pack(side="left", padx=(6, 6))
        self.profile_box.bind("<<ComboboxSelected>>", lambda e: self.load_profile(self.profile_var.get()))
        for label, cmd in (
            ("New", self.new_profile),
            ("Copy", self.copy_profile),
            ("Rename", self.rename_profile),
            ("Delete", self.delete_profile),
        ):
            ttk.Button(bar, text=label, command=cmd, width=8).pack(side="left", padx=2)
        ttk.Label(bar, text="(saved automatically)", foreground="gray").pack(side="right")

    def _build_points(self):
        frame = ttk.LabelFrame(self.root, text="Click sequence (runs top to bottom, then repeats)", padding=8)
        frame.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        cols = ("name", "x", "y", "delay", "button", "type", "window")
        headings = ("Point", "X", "Y", "Wait before click", "Button", "Click", "Window")
        widths = (55, 60, 60, 115, 65, 65, 160)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=8, selectmode="browse")
        for col, head, width in zip(cols, headings, widths):
            self.tree.heading(col, text=head)
            self.tree.column(col, width=width, anchor="w" if col == "window" else "center")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self.repick_point())

        side = ttk.Frame(frame, padding=(8, 0, 0, 0))
        side.pack(side="left", fill="y")
        self.point_buttons = []
        for label, cmd in (
            ("+ Add point", self.add_point),
            ("Re-pick location", self.repick_point),
            ("Remove", self.remove_point),
            ("Move up", lambda: self.move_point(-1)),
            ("Move down", lambda: self.move_point(1)),
        ):
            b = ttk.Button(side, text=label, command=cmd, width=16)
            b.pack(fill="x", pady=2)
            self.point_buttons.append(b)

    def _build_editor(self):
        frame = ttk.LabelFrame(self.root, text="Selected point", padding=8)
        frame.pack(fill="x", padx=10, pady=(10, 0))
        self.name_var = tk.StringVar()
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        self.delay_var = tk.StringVar()
        self.button_var = tk.StringVar()
        self.type_var = tk.StringVar()

        self.editor_widgets = []

        def add(label, widget, col):
            ttk.Label(frame, text=label).grid(row=0, column=col, sticky="w", padx=(0 if col == 0 else 10, 4))
            widget.grid(row=0, column=col + 1, sticky="w")
            self.editor_widgets.append(widget)

        add("Name", ttk.Entry(frame, textvariable=self.name_var, width=8), 0)
        add("X", ttk.Spinbox(frame, textvariable=self.x_var, from_=-99999, to=99999, width=7), 2)
        add("Y", ttk.Spinbox(frame, textvariable=self.y_var, from_=-99999, to=99999, width=7), 4)
        add(
            "Wait (sec)",
            ttk.Spinbox(frame, textvariable=self.delay_var, from_=MIN_DELAY, to=86400, increment=0.1, width=8),
            6,
        )
        add("Button", ttk.Combobox(frame, textvariable=self.button_var, values=BUTTONS, state="readonly", width=7), 8)
        add(
            "Click",
            ttk.Combobox(frame, textvariable=self.type_var, values=list(CLICK_TYPE_BY_LABEL), state="readonly", width=7),
            10,
        )
        ttk.Label(
            frame,
            text="'Wait' = how long to wait before this point is clicked. Double-click a row to re-pick its location.",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=12, sticky="w", pady=(6, 0))

        for var in (self.name_var, self.x_var, self.y_var, self.delay_var, self.button_var, self.type_var):
            var.trace_add("write", lambda *a: self._on_edit())
        self._set_editor_enabled(False)

    def _build_run_settings(self):
        frame = ttk.LabelFrame(self.root, text="How long to run", padding=8)
        frame.pack(fill="x", padx=10, pady=(10, 0))
        self.mode_var = tk.StringVar()
        self.rounds_var = tk.StringVar()
        self.duration_var = tk.StringVar()
        self.unit_var = tk.StringVar()

        ttk.Radiobutton(frame, text="Until I stop it", variable=self.mode_var, value="forever").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Radiobutton(frame, text="Stop after", variable=self.mode_var, value="rounds").grid(
            row=0, column=1, sticky="w", padx=(20, 4)
        )
        ttk.Spinbox(frame, textvariable=self.rounds_var, from_=1, to=1_000_000, width=7).grid(row=0, column=2)
        ttk.Label(frame, text="rounds").grid(row=0, column=3, padx=(4, 0))
        ttk.Radiobutton(frame, text="Stop after", variable=self.mode_var, value="time").grid(
            row=0, column=4, sticky="w", padx=(20, 4)
        )
        ttk.Spinbox(frame, textvariable=self.duration_var, from_=0.1, to=100_000, increment=1, width=7).grid(
            row=0, column=5
        )
        ttk.Combobox(frame, textvariable=self.unit_var, values=list(TIME_UNITS), state="readonly", width=8).grid(
            row=0, column=6, padx=(4, 0)
        )
        ttk.Label(frame, text="One round = every point in the list clicked once.", foreground="gray").grid(
            row=1, column=0, columnspan=7, sticky="w", pady=(6, 0)
        )

        self.background_var = tk.BooleanVar()
        how = ttk.Frame(frame)
        how.grid(row=2, column=0, columnspan=7, sticky="w", pady=(10, 0))
        ttk.Label(how, text="Clicking:").pack(side="left")
        ttk.Radiobutton(
            how, text="In the background (my mouse stays free)", variable=self.background_var, value=True
        ).pack(side="left", padx=(8, 0))
        ttk.Radiobutton(how, text="Move the real mouse", variable=self.background_var, value=False).pack(
            side="left", padx=(16, 0)
        )
        ttk.Label(
            frame,
            text="Background works with most apps, even behind other windows (not minimized). "
            "If an app or game ignores it, use 'Move the real mouse'.",
            foreground="gray",
        ).grid(row=3, column=0, columnspan=7, sticky="w", pady=(4, 0))

        for var in (self.mode_var, self.rounds_var, self.duration_var, self.unit_var, self.background_var):
            var.trace_add("write", lambda *a: self._on_settings_edit())

    def _build_controls(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="x")
        style = ttk.Style()
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=8)
        self.start_button = ttk.Button(frame, text=f"Start  ({HOTKEY})", style="Big.TButton", command=self.toggle)
        self.start_button.pack(side="left")
        self.status_var = tk.StringVar(value=f"Ready. Press {HOTKEY} anywhere to start or stop.")
        ttk.Label(frame, textvariable=self.status_var).pack(side="left", padx=12)

    # ---------- profiles ----------

    @property
    def profile(self) -> Profile:
        return self.store.profiles[self.store.last_profile]

    def _refresh_profile_box(self):
        self.profile_box["values"] = sorted(self.store.profiles, key=str.lower)
        self.profile_var.set(self.store.last_profile)

    def load_profile(self, name: str):
        self.store.last_profile = name
        self._refresh_profile_box()
        s = self.profile.settings
        self._loading = True
        self.mode_var.set(s.mode)
        self.rounds_var.set(str(s.rounds))
        self.duration_var.set(f"{s.duration:g}")
        self.unit_var.set(s.duration_unit)
        self.background_var.set(s.background)
        self._loading = False
        self.selected = None
        self._refresh_tree(select=0 if self.profile.points else None)
        self.schedule_save()

    def _ask_new_name(self, title, initial=""):
        name = simpledialog.askstring(title, "Profile name:", initialvalue=initial, parent=self.root)
        if name is None:
            return None
        name = name.strip()
        if not name:
            return None
        if name in self.store.profiles:
            messagebox.showerror("Autoclicker", f"A profile called '{name}' already exists.")
            return None
        return name

    def new_profile(self):
        name = self._ask_new_name("New profile")
        if name:
            self.store.profiles[name] = Profile()
            self.load_profile(name)

    def copy_profile(self):
        name = self._ask_new_name("Copy profile", f"{self.store.last_profile} copy")
        if name:
            self.store.profiles[name] = Profile.from_dict(self.profile.to_dict())
            self.load_profile(name)

    def rename_profile(self):
        old = self.store.last_profile
        name = self._ask_new_name("Rename profile", old)
        if name:
            self.store.profiles[name] = self.store.profiles.pop(old)
            self.load_profile(name)

    def delete_profile(self):
        name = self.store.last_profile
        if not messagebox.askyesno("Autoclicker", f"Delete profile '{name}' and its click points?"):
            return
        del self.store.profiles[name]
        if not self.store.profiles:
            self.store.profiles["Default"] = Profile()
        self.load_profile(sorted(self.store.profiles, key=str.lower)[0])

    def schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(SAVE_DELAY_MS, self.save_now)

    def save_now(self):
        self._save_job = None
        try:
            self.store.save()
        except OSError as exc:
            self.status_var.set(f"Could not save profiles: {exc}")

    # ---------- point list ----------

    def _row_values(self, p: ClickPoint):
        return (p.name, p.x, p.y, f"{p.delay:g} s", p.button, CLICK_TYPES[p.clicks], p.window_title or "-")

    def _refresh_tree(self, select: int | None = None):
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.profile.points):
            self.tree.insert("", "end", iid=str(i), values=self._row_values(p))
        if select is not None and 0 <= select < len(self.profile.points):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        else:
            self.selected = None
            self._load_editor()

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        self.selected = int(sel[0]) if sel else None
        self._load_editor()

    def _set_editor_enabled(self, enabled: bool):
        for w in self.editor_widgets:
            if isinstance(w, ttk.Combobox):
                w.configure(state="readonly" if enabled else "disabled")
            else:
                w.configure(state="normal" if enabled else "disabled")

    def _load_editor(self):
        self._loading = True
        if self.selected is None:
            for var in (self.name_var, self.x_var, self.y_var, self.delay_var, self.button_var, self.type_var):
                var.set("")
            self._set_editor_enabled(False)
        else:
            p = self.profile.points[self.selected]
            self._set_editor_enabled(True)
            self.name_var.set(p.name)
            self.x_var.set(str(p.x))
            self.y_var.set(str(p.y))
            self.delay_var.set(f"{p.delay:g}")
            self.button_var.set(p.button)
            self.type_var.set(CLICK_TYPES[p.clicks])
        self._loading = False

    def _on_edit(self):
        if self._loading or self.selected is None:
            return
        p = self.profile.points[self.selected]
        # Apply each field that currently parses; ignore half-typed values.
        name = self.name_var.get().strip()
        if name:
            p.name = name
        try:
            p.x = int(self.x_var.get())
        except ValueError:
            pass
        try:
            p.y = int(self.y_var.get())
        except ValueError:
            pass
        try:
            delay = float(self.delay_var.get())
            if delay >= MIN_DELAY:
                p.delay = delay
        except ValueError:
            pass
        if self.button_var.get() in BUTTONS:
            p.button = self.button_var.get()
        if self.type_var.get() in CLICK_TYPE_BY_LABEL:
            p.clicks = CLICK_TYPE_BY_LABEL[self.type_var.get()]
        self.tree.item(str(self.selected), values=self._row_values(p))
        self.schedule_save()

    def add_point(self):
        name = next_point_name(self.profile.points)

        def got(pos):
            if pos is None:
                return
            # New points copy the previous point's wait so a sequence is quick to build.
            delay = self.profile.points[-1].delay if self.profile.points else 1.0
            point = ClickPoint(name=name, x=pos[0], y=pos[1], delay=delay)
            self._remember_window(point)
            self.profile.points.append(point)
            self._refresh_tree(select=len(self.profile.points) - 1)
            self.schedule_save()

        pick_location(self.root, name, got)

    def repick_point(self):
        if self.selected is None:
            return
        index = self.selected
        p = self.profile.points[index]

        def got(pos):
            if pos is None:
                return
            p.x, p.y = pos
            self._remember_window(p)
            self._refresh_tree(select=index)
            self.schedule_save()

        pick_location(self.root, p.name, got)

    def _remember_window(self, p: ClickPoint):
        spot = self.window_at(p.x, p.y)
        if spot:
            p.window_title, p.window_class = spot.title, spot.class_name
            p.rel_x, p.rel_y = spot.rel_x, spot.rel_y

    def remove_point(self):
        if self.selected is None:
            return
        index = self.selected
        del self.profile.points[index]
        self._refresh_tree(select=min(index, len(self.profile.points) - 1))
        self.schedule_save()

    def move_point(self, step: int):
        if self.selected is None:
            return
        i, j = self.selected, self.selected + step
        points = self.profile.points
        if not 0 <= j < len(points):
            return
        points[i], points[j] = points[j], points[i]
        self._refresh_tree(select=j)
        self.schedule_save()

    # ---------- run settings ----------

    def _on_settings_edit(self):
        if self._loading:
            return
        s = self.profile.settings
        s.mode = self.mode_var.get() or s.mode
        try:
            if int(self.rounds_var.get()) >= 1:
                s.rounds = int(self.rounds_var.get())
        except ValueError:
            pass
        try:
            if float(self.duration_var.get()) > 0:
                s.duration = float(self.duration_var.get())
        except ValueError:
            pass
        if self.unit_var.get() in TIME_UNITS:
            s.duration_unit = self.unit_var.get()
        s.background = self.background_var.get()
        self.schedule_save()

    def _validate_settings(self) -> str | None:
        mode = self.mode_var.get()
        if mode == "rounds":
            try:
                if int(self.rounds_var.get()) < 1:
                    raise ValueError
            except ValueError:
                return "Number of rounds must be a whole number of 1 or more."
        if mode == "time":
            try:
                if float(self.duration_var.get()) <= 0:
                    raise ValueError
            except ValueError:
                return "Run time must be a number greater than 0."
        if self.background_var.get():
            if not winclick.SUPPORTED:
                return "Background clicking only works on Windows. Choose 'Move the real mouse'."
            missing = [p.name for p in self.profile.points if not p.window_class]
            if missing:
                return (
                    f"Point(s) {', '.join(missing)} don't know which window they belong to yet. "
                    "Select each one and click 'Re-pick location', or choose 'Move the real mouse'."
                )
        return None

    # ---------- running ----------

    @property
    def running(self) -> bool:
        return self.runner is not None and self.runner.running

    def toggle(self):
        if self.running:
            self.runner.stop()
        else:
            self.start()

    def start(self):
        if not self.profile.points:
            messagebox.showinfo("Autoclicker", "Add at least one click point first.")
            return
        error = self._validate_settings()
        if error:
            messagebox.showerror("Autoclicker", error)
            return
        self.save_now()
        self.runner = ClickRunner(
            self.profile.points,
            self.profile.settings,
            self.clickers["background" if self.profile.settings.background else "mouse"],
            on_progress=lambda rnd, i: self.events.put(("progress", rnd, i)),
            on_finish=lambda reason: self.events.put(("finished", reason)),
        )
        self._run_points = [p.name for p in self.profile.points]
        self._run_delays = [p.delay for p in self.profile.points]
        self.start_button.configure(text=f"Stop  ({HOTKEY})")
        for b in self.point_buttons:
            b.state(["disabled"])
        self.runner.start()

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "toggle":
                    self.toggle()
                elif kind == "progress":
                    _, rnd, i = event
                    self.status_var.set(
                        f"Running · round {rnd} · waiting {self._run_delays[i]:g} s, then clicking "
                        f"{self._run_points[i]}   ({HOTKEY} to stop)"
                    )
                elif kind == "finished":
                    self._on_finished(event[1])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll_events)

    def _on_finished(self, reason: str):
        self.start_button.configure(text=f"Start  ({HOTKEY})")
        for b in self.point_buttons:
            b.state(["!disabled"])
        messages = {
            STOPPED: "Stopped.",
            ROUNDS_DONE: "Finished all rounds.",
            TIME_UP: "Time is up, stopped.",
        }
        self.status_var.set(messages.get(reason, reason) + f"  Press {HOTKEY} to start again.")

    def on_close(self):
        if self.runner:
            self.runner.stop()
            self.runner.join(1)
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self.save_now()
        self.root.destroy()


def _enable_dpi_awareness():
    """Make Tk and the mouse use the same real pixel coordinates on scaled displays."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main():
    _enable_dpi_awareness()

    from pynput import keyboard, mouse

    controller = mouse.Controller()
    buttons = {"left": mouse.Button.left, "right": mouse.Button.right, "middle": mouse.Button.middle}

    def mouse_click(point: ClickPoint):
        controller.position = (point.x, point.y)
        controller.click(buttons[point.button], point.clicks)

    store = ProfileStore()
    store.load()

    root = tk.Tk()
    app = App(
        root,
        store,
        {"mouse": mouse_click, "background": winclick.background_click},
        window_at=winclick.window_at,
    )

    def on_key(key):
        if key == keyboard.Key.f6:
            app.events.put(("toggle",))

    listener = keyboard.Listener(on_press=on_key)
    listener.daemon = True
    listener.start()
    try:
        root.mainloop()
    finally:
        listener.stop()
