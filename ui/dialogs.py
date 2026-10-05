import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ui.theme import apply_theme, style_toplevel
from utils.project import (
    DEFAULT_PROJECT_FILENAME,
    ProjectError,
    load_project,
    save_project,
)

JSON_FILETYPES = [("JSON files", "*.json")]


def short_path(path) -> str:
    path = str(path)
    home = str(Path.home())
    return "~" + path[len(home) :] if path.startswith(home) else path


def center_on(window, parent=None):
    window.update_idletasks()
    w, h = window.winfo_reqwidth(), window.winfo_reqheight()
    if parent is not None and parent.winfo_viewable():
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 3
    else:
        x = (window.winfo_screenwidth() - w) // 2
        y = (window.winfo_screenheight() - h) // 3
    window.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class ModernDialog(simpledialog.Dialog):
    """simpledialog.Dialog with themed padding and a right-aligned button row."""

    primary_text = "Save"

    def body(self, master):
        style_toplevel(self)
        style_toplevel(master)
        self._body_master = master
        self.resizable(True, False)
        frame = ttk.Frame(master, padding=(24, 20, 24, 4))
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        self.after_idle(lambda: center_on(self, self.parent))
        return self.build(frame)

    def build(self, frame):
        raise NotImplementedError

    def add_extra_buttons(self, box):
        pass

    def buttonbox(self):
        self._body_master.pack_configure(fill="both", expand=True, padx=0, pady=0)
        box = ttk.Frame(self, padding=(24, 12, 24, 20))
        box.pack(fill="x")
        ttk.Button(
            box,
            text=self.primary_text,
            style="Accent.TButton",
            command=self.ok,
            default="active",
        ).pack(side="right")
        ttk.Button(box, text="Cancel", command=self.cancel).pack(
            side="right", padx=(0, 8)
        )
        self.add_extra_buttons(box)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)


def field_label(parent, text, row, pady=(0, 6)):
    ttk.Label(parent, text=text.upper(), style="Caption.TLabel").grid(
        row=row, column=0, columnspan=2, sticky="w", pady=pady
    )


class NewProjectDialog(ModernDialog):
    primary_text = "Create project"

    def __init__(self, parent, pl_path="", en_path="", name="", **kwargs):
        self.initial = {"pl": pl_path, "en": en_path, "name": name}
        super().__init__(parent, **kwargs)

    def build(self, frame):
        ttk.Label(frame, text="New project", style="Title.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ttk.Label(
            frame,
            text="A project file remembers where your PL and EN files live,\n"
            "so next time you open everything with a single file.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))

        field_label(frame, "Project name (optional)", 2)
        self.name_entry = ttk.Entry(frame, width=56)
        self.name_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.name_entry.insert(0, self.initial["name"])

        self.pl_entry = self._file_row(frame, "Polish file (PL)", 4, "pl")
        self.en_entry = self._file_row(frame, "English file (EN)", 6, "en")
        return self.name_entry if not self.initial["pl"] else self.pl_entry

    def _file_row(self, frame, label, row, lang):
        field_label(frame, label, row)
        entry = ttk.Entry(frame)
        entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 14))
        entry.insert(0, self.initial[lang])
        ttk.Button(
            frame, text="Browse…", command=lambda: self._browse(entry, label)
        ).grid(row=row + 1, column=1, sticky="e", padx=(8, 0), pady=(0, 14))
        return entry

    def _browse(self, entry, label):
        current = entry.get().strip()
        other = self.pl_entry.get().strip() or self.initial["pl"]
        initialdir = (
            str(Path(current or other).parent) if (current or other) else os.getcwd()
        )
        path = filedialog.askopenfilename(
            parent=self,
            title=f"Select {label}",
            initialdir=initialdir,
            filetypes=JSON_FILETYPES,
        )
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    def validate(self):
        for entry, label in ((self.pl_entry, "Polish"), (self.en_entry, "English")):
            if not Path(entry.get().strip()).expanduser().is_file():
                messagebox.showerror(
                    "Missing file",
                    f"Choose an existing {label} JSON file.",
                    parent=self,
                )
                return False
        return True

    def apply(self):
        self.result = {
            "name": self.name_entry.get().strip(),
            "pl": str(Path(self.pl_entry.get().strip()).expanduser()),
            "en": str(Path(self.en_entry.get().strip()).expanduser()),
        }


def open_project_interactive(parent):
    """Ask for a project file and load it. Returns TranslationProject or None."""
    path = filedialog.askopenfilename(
        parent=parent,
        title="Open translation project",
        filetypes=JSON_FILETYPES,
    )
    if not path:
        return None
    try:
        return load_project(path)
    except ProjectError as e:
        messagebox.showerror("Cannot open project", str(e), parent=parent)
        return None


def create_project_interactive(parent, pl_path="", en_path=""):
    """Collect PL/EN files, save a project file and return the TranslationProject."""
    dlg = NewProjectDialog(
        parent, pl_path=pl_path, en_path=en_path, title="New project"
    )
    if not dlg.result:
        return None
    pl, en, name = dlg.result["pl"], dlg.result["en"], dlg.result["name"]
    try:
        initialdir = os.path.commonpath([str(Path(pl).parent), str(Path(en).parent)])
    except ValueError:
        initialdir = str(Path(pl).parent)
    initialfile = (
        f"{name}.project.json"
        if name and "/" not in name and "\\" not in name
        else DEFAULT_PROJECT_FILENAME
    )
    target = filedialog.asksaveasfilename(
        parent=parent,
        title="Save project file",
        initialdir=initialdir,
        initialfile=initialfile,
        defaultextension=".json",
        filetypes=JSON_FILETYPES,
    )
    if not target:
        return None
    try:
        return save_project(target, pl, en, name=name or None)
    except OSError as e:
        messagebox.showerror("Cannot save project", str(e), parent=parent)
        return None


def _recent_item(parent, project, on_click):
    frame = ttk.Frame(parent, style="Card.TFrame", padding=(16, 10), cursor="hand2")
    name = ttk.Label(
        frame,
        text=project.display_name,
        style="Card.TLabel",
        font=parent.winfo_toplevel().fonts["bold"],
    )
    name.pack(anchor="w")
    path = ttk.Label(frame, text=short_path(project.path), style="Card.Small.TLabel")
    path.pack(anchor="w")

    def set_hover(on):
        frame.configure(style="Hover.TFrame" if on else "Card.TFrame")
        name.configure(style="Hover.TLabel" if on else "Card.TLabel")
        path.configure(style="Hover.Small.TLabel" if on else "Card.Small.TLabel")

    for widget in (frame, name, path):
        widget.bind("<Enter>", lambda _e: set_hover(True))
        widget.bind("<Leave>", lambda _e: set_hover(False))
        widget.bind("<Button-1>", lambda _e: on_click(project))
    return frame


def run_welcome(recent_paths):
    """Show the start screen. Returns the chosen TranslationProject or None."""
    root = tk.Tk()
    root.title("Translation Manager")
    apply_theme(root)
    result = {}

    def finish(project):
        if project:
            result["project"] = project
            root.destroy()

    outer = ttk.Frame(root, padding=(40, 36, 40, 32))
    outer.pack(fill="both", expand=True)

    ttk.Label(outer, text="Translation Manager", style="Hero.TLabel").pack(anchor="w")
    ttk.Label(
        outer,
        text="Open a project file to load your PL and EN translations together.",
        style="Muted.TLabel",
    ).pack(anchor="w", pady=(6, 24))

    actions = ttk.Frame(outer)
    actions.pack(anchor="w", fill="x")
    ttk.Button(
        actions,
        text="Open project…",
        style="Accent.TButton",
        command=lambda: finish(open_project_interactive(root)),
    ).pack(side="left")
    ttk.Button(
        actions,
        text="New project…",
        command=lambda: finish(create_project_interactive(root)),
    ).pack(side="left", padx=(8, 0))

    recent = []
    for p in recent_paths:
        try:
            recent.append(load_project(p))
        except ProjectError:
            continue
    if recent:
        ttk.Label(outer, text="RECENT PROJECTS", style="Caption.TLabel").pack(
            anchor="w", pady=(32, 8)
        )
        for project in recent[:6]:
            _recent_item(outer, project, finish).pack(fill="x", pady=(0, 6))

    root.minsize(560, 0)
    center_on(root)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.bind("<Escape>", lambda _e: root.destroy())
    root.mainloop()
    return result.get("project")
