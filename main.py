#!/usr/bin/env python3
import copy
import json
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
from pathlib import Path
import deepl
from dotenv import load_dotenv
import os
from tkinter import ttk
from enums.menu_option_label_enum import MenuOptionLabelEnum
from enums.action_enum import ActionEnum
import logging
import concurrent.futures
from utils.logging_config import configure_logging
import sys
import re
from utils.utils import TypeUtils
from utils.project import (
    ProjectError,
    TranslationProject,
    load_project,
    save_project,
)
from ui.theme import Palette, apply_theme, style_toplevel, text_widget_options
from ui.dialogs import (
    ModernDialog,
    create_project_interactive,
    field_label,
    open_project_interactive,
    run_welcome,
    short_path,
)
import time
from pytionalization import I18n, configure_i18n, translate

i18n = I18n(
    sources={
        "pl": "assets/pl.json",
        "en": "assets/en.json",
    }
)
print(i18n.t("UI.MENU.FILES", locale="en"))

load_dotenv()
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
translator = deepl.Translator(DEEPL_API_KEY)

CONFIG_PATH = Path.home() / ".translation_app_config.json"
MAX_RECENT_PROJECTS = 8
MOD = "Command" if sys.platform == "darwin" else "Control"

AVAILABLE_LANGS = [
    ("en", "English"),
    ("pl", "Polski"),
]


def update_config_value(key: str, value):
    cfg = load_json(CONFIG_PATH)
    cfg[key] = value
    save_json(cfg, CONFIG_PATH)


def remember_project(project: TranslationProject):
    """Persist the opened files (and project file, if any) for the next start."""
    cfg = load_json(CONFIG_PATH)
    cfg["pl_file"] = project.pl_path
    cfg["en_file"] = project.en_path
    if project.path:
        cfg["project_file"] = project.path
        recent = [p for p in cfg.get("recent_projects", []) if p != project.path]
        cfg["recent_projects"] = [project.path] + recent[: MAX_RECENT_PROJECTS - 1]
    else:
        cfg.pop("project_file", None)
    save_json(cfg, CONFIG_PATH)


def startup_project(config):
    """Project to open without asking: the last project, else the last PL/EN pair."""
    project_file = config.get("project_file")
    if project_file:
        try:
            return load_project(project_file)
        except ProjectError as e:
            logging.warning("Cannot open last project: %s", e)
            return None
    pl_file = config.get("pl_file")
    en_file = config.get("en_file")
    if pl_file and en_file and Path(pl_file).is_file() and Path(en_file).is_file():
        return TranslationProject(pl_path=pl_file, en_path=en_file)
    return None


class DeepLUsageCache:
    value = (None, None, None)  # (remaining, used, limit)
    ts = 0.0


def get_deepl_usage(translator: deepl.Translator):
    """Return (used, limit) or (None, None) on error."""
    try:
        u = translator.get_usage()
        if u and u.character:
            return u.character.count or 0, u.character.limit or 0
    except Exception as e:
        logging.warning("Cannot fetch DeepL usage: %s", e)
    return None, None


def get_remaining_quota(translator: deepl.Translator):
    """Return (remaining, used, limit) or (None, None, None) if unknown."""
    used, limit = get_deepl_usage(translator)
    if used is None or limit is None:
        return None, None, None
    return max(limit - used, 0), used, limit


def refresh_usage_cache():
    """Update global cache synchronously; return (remaining, used, limit)."""
    rem, used, limit = get_remaining_quota(translator)
    DeepLUsageCache.value = (rem, used, limit)
    DeepLUsageCache.ts = time.time()
    return DeepLUsageCache.value


def estimate_char_cost(text: str) -> int:
    return len(text or "")


def load_json(path):
    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logging.warning(f"File not found: {path}")
        return {}
    except UnicodeDecodeError as e:
        logging.error(f"Encoding error reading file {path}: {e}")
        return {}
    except OSError as e:
        logging.error(f"Failed reading the file {path}: {e}")
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON format in file {path}: {e}")
        return {}


def save_json(data, path):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def translate_text(text, source_lang="PL", target_lang="EN-GB"):
    try:
        result = translator.translate_text(
            text, source_lang=source_lang, target_lang=target_lang
        )
        return result.text
    except deepl.DeepLException as e:
        logging.error("DeepL translation error: %s", e, exc_info=True)
        return ""


class AddDialog(ModernDialog):
    def __init__(
        self,
        parent,
        initial_key="",
        initial_pl="",
        initial_en="",
        auto_default=True,
        original_key=None,
        **kwargs,
    ):
        self.parent = parent
        self.initial_key = initial_key
        self.initial_pl = initial_pl
        self.initial_en = initial_en
        self.auto_default = auto_default
        self.original_key = original_key
        self.duplicate_key = None
        self.jump_button = None

        self._usage_update_job = None
        self.primary_text = "Save changes" if original_key else "Add key"

        super().__init__(parent, **kwargs)

    def build(self, master):
        fonts = getattr(self.parent, "fonts", {})
        heading = "Edit translation" if self.original_key else "New translation"
        ttk.Label(master, text=heading, style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 18)
        )

        field_label(master, "Key path (dot separated)", 1)
        self.key_entry = ttk.Entry(master, width=60, font=fonts.get("mono"))
        self.key_entry.grid(row=2, column=0, sticky="ew")
        if self.initial_key:
            self.key_entry.insert(0, self.initial_key)
        self.duplicate_label = ttk.Label(master, text="", style="Warning.TLabel")
        self.duplicate_label.grid(row=3, column=0, sticky="w", pady=(4, 10))
        self.key_entry.bind("<KeyRelease>", self.check_duplicate)

        field_label(master, "Polski (PL)", 4)
        self.pl_entry = ttk.Entry(master)
        self.pl_entry.grid(row=5, column=0, sticky="ew", pady=(0, 16))
        if self.initial_pl:
            self.pl_entry.insert(0, self.initial_pl)

        field_label(master, "English (EN)", 6)
        self.en_entry = ttk.Entry(master)
        self.en_entry.grid(row=7, column=0, sticky="ew", pady=(0, 10))
        if self.initial_en:
            self.en_entry.insert(0, self.initial_en)

        self.auto_var = tk.BooleanVar(master, self.auto_default)

        def toggle_en():
            if self.auto_var.get():
                self.en_entry.delete(0, tk.END)
                self.en_entry.config(state="disabled")
                self.usage_refresh_btn.pack(side="left", padx=(8, 0))
            else:
                self.en_entry.config(state="normal")
                self.usage_refresh_btn.pack_forget()

        chk = ttk.Checkbutton(
            master,
            text="Translate to English with DeepL",
            variable=self.auto_var,
            command=toggle_en,
        )
        chk.grid(row=8, column=0, sticky="w")

        wrap = ttk.Frame(master)
        wrap.grid(row=9, column=0, sticky="w", pady=(2, 0))
        self.usage_var = tk.StringVar(master, "")
        self.usage_label = ttk.Label(
            wrap, textvariable=self.usage_var, style="Small.TLabel"
        )
        self.usage_label.pack(side="left")
        self.usage_refresh_btn = ttk.Button(
            wrap,
            text="Refresh",
            style="Ghost.TButton",
            command=self._refresh_usage_async,
        )
        self.usage_refresh_btn.pack(side="left", padx=(8, 0))

        self.pl_entry.bind(
            "<KeyRelease>", lambda _e=None: self._schedule_update_usage_label()
        )
        self.auto_var.trace_add("write", lambda *_: self._update_usage_label())

        try:
            self._refresh_usage_async()
        except Exception:
            pass
        self._schedule_update_usage_label()
        toggle_en()

        return self.key_entry

    def _update_usage_label(self):
        if not self.auto_var.get():
            self.usage_var.set("")
            return
        text_pl = self.pl_entry.get().strip()
        needed = estimate_char_cost(text_pl)
        rem, used, limit = DeepLUsageCache.value
        if rem is None:
            self.usage_var.set(f"Will take ~{needed} characters (no limit info)")
        else:
            left_after = max(rem - needed, 0)
            self.usage_var.set(
                f"Will take ~{needed} • Remaining: {rem}/{limit} • After: {left_after}"
            )

    def _schedule_update_usage_label(self):
        if self._usage_update_job:
            try:
                self.after_cancel(self._usage_update_job)
            except Exception:
                pass
        self._usage_update_job = self.after(600, self._update_usage_label)

    def _refresh_usage_async(self):
        app = self.parent

        def work():
            refresh_usage_cache()

        def done():
            self._update_usage_label()

        app.executor.submit(lambda: (work(), self.after(0, done)))

    def validate(self):
        key = self.key_entry.get().strip()
        pl = self.pl_entry.get().strip()
        if key.endswith("."):
            messagebox.showerror("Error", f"Invalid key {key}")
            return False
        if not key:
            messagebox.showerror("Error", "Key is required")
            return False
        if not pl:
            messagebox.showerror("Error", "Polish text is required")
            return False
        if self.original_key and key == self.original_key:
            return True
        if hasattr(self.parent, "key_exists") and self.parent.key_exists(key):
            self.duplicate_key = key
            messagebox.showerror("Error", f"Key already exists: {key}")
            return False
        return True

    def on_jump(self):
        self.cancel()
        if self.duplicate_key:
            self.parent.select_key(self.duplicate_key)

    def apply(self):
        self.result = {
            "key": self.key_entry.get().strip(),
            "pl": self.pl_entry.get().strip(),
            "auto": self.auto_var.get(),
            "en": self.en_entry.get().strip(),
        }

    def add_extra_buttons(self, box):
        self.jump_button = ttk.Button(
            box, text="Jump to existing key", command=self.on_jump
        )

    def check_duplicate(self, event=None):
        key = self.key_entry.get().strip()
        if self.original_key and key == self.original_key:
            self.duplicate_key = None
            self.duplicate_label.config(text="")
            self.jump_button.pack_forget()
            return

        if hasattr(self.parent, "key_exists") and self.parent.key_exists(key):
            self.duplicate_key = key
            self.duplicate_label.config(text=f"Key “{key}” already exists.")
            self.jump_button.pack(side="left")
        else:
            self.duplicate_key = None
            self.duplicate_label.config(text="")
            self.jump_button.pack_forget()


def set_nested(d, keys, value):
    cur = d
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def get_nested(d, keys):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return ""
    return cur if not isinstance(cur, dict) else ""


def flatten_to_nested(d: dict) -> dict:
    result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            nested = flatten_to_nested(value)
            if key not in result or not isinstance(result[key], dict):
                result[key] = nested
            else:
                for subk, subv in nested.items():
                    result[key][subk] = subv
        else:
            parts = key.split(".")
            set_nested(result, parts, value)
    return result


class TranslationApp(tk.Tk):
    def __init__(self, pl_path, en_path, max_workers=5, project=None):
        super().__init__()
        self.fonts = apply_theme(self)
        config = load_json(CONFIG_PATH)
        self.pl_path = pl_path
        self.en_path = en_path
        self.project = project
        self._load_data()
        self.i18n = i18n
        self.ui_language = config.get("ui_language", "en")
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._status_job = None

        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        self._create_file_menu()
        self._create_edit_menu()
        self._create_settings_menu()
        self._create_help_menu()

        cfg_main_window_size = config.get("main_window_size")
        main_window_size = TypeUtils.is_null_or_empty(cfg_main_window_size, "1920x1080")
        self.geometry(main_window_size)
        self.minsize(820, 520)
        self.undo_stack = []
        self.redo_stack = []
        self._bind_shortcuts()

        self._build_header()
        self._build_toolbar()
        self._build_status_bar()
        self._build_body()

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy Key", command=self.copy_key)
        self.menu.add_command(label="Copy PL Value", command=self.copy_pl)
        self.menu.add_command(label="Copy EN Value", command=self.copy_en)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Button-2>", self.show_context_menu)
        self.tree.bind("<Control-Button-1>", self.show_context_menu)

        self.update_title()
        self.center_window()
        self.insert_all()
        self._show_default_status()
        self._refresh_global_usage()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_header(self):
        header = ttk.Frame(self, style="Header.TFrame", padding=(24, 16, 24, 16))
        header.pack(fill="x")

        titles = ttk.Frame(header, style="Header.TFrame")
        titles.pack(side="left", fill="x", expand=True)
        self.header_title = ttk.Label(titles, style="Header.Title.TLabel")
        self.header_title.pack(anchor="w")
        self.header_subtitle = ttk.Label(titles, style="Header.Small.TLabel")
        self.header_subtitle.pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(header, style="Header.TFrame")
        right.pack(side="right")

        self.lang_var = tk.StringVar(self, self.ui_language)
        self.lang_combo = ttk.Combobox(
            right,
            state="readonly",
            values=[f"{code} — {label}" for code, label in AVAILABLE_LANGS],
            width=14,
        )
        for code, label in AVAILABLE_LANGS:
            if code == self.ui_language:
                self.lang_combo.set(f"{code} — {label}")
                break
        self.lang_combo.pack(side="right")
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_language_changed)
        ttk.Label(right, text="Interface", style="Header.Small.TLabel").pack(
            side="right", padx=(16, 8)
        )

        self.missing_badge = ttk.Label(right, style="Badge.TLabel")
        self.count_badge = ttk.Label(right, style="Badge.TLabel")
        self.count_badge.pack(side="right", padx=(6, 0))

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(24, 16, 24, 12))
        bar.pack(fill="x")

        ttk.Button(bar, text="Save", command=self.save).pack(side="right")
        ttk.Separator(bar, orient="vertical").pack(side="right", fill="y", padx=12)
        ttk.Button(
            bar, text="Delete", style="Danger.TButton", command=self.delete_selected
        ).pack(side="right")
        ttk.Button(bar, text="Edit", command=self.edit_selected).pack(
            side="right", padx=(0, 8)
        )
        ttk.Button(
            bar, text="+  Add key", style="Accent.TButton", command=self.add_new
        ).pack(side="right", padx=(16, 8))

        search_box = ttk.Frame(bar, style="Card.TFrame", padding=(10, 0))
        search_box.pack(side="left", fill="x", expand=True)
        self.search_var = tk.StringVar(self)
        self.search_var.trace_add("write", self.on_search)
        self.search_entry = ttk.Entry(
            search_box, textvariable=self.search_var, style="Bare.TEntry"
        )
        self.search_entry.pack(fill="x", expand=True)
        shortcut = "⌘F" if sys.platform == "darwin" else "Ctrl+F"
        self.search_placeholder = ttk.Label(
            search_box,
            text=f"Search keys, Polish or English text…   {shortcut}",
            style="Placeholder.TLabel",
        )
        self.search_placeholder.bind(
            "<Button-1>", lambda _e: self.search_entry.focus_set()
        )
        self.search_entry.bind("<Escape>", lambda _e: self.search_var.set(""))
        self._update_search_placeholder()

    def _build_body(self):
        body = ttk.Frame(self, padding=(24, 0, 24, 16))
        body.pack(fill="both", expand=True)
        paned = ttk.PanedWindow(body, orient="horizontal")
        paned.pack(fill="both", expand=True)

        tree_card = ttk.Frame(paned, style="Card.TFrame", padding=(4, 4, 0, 4))
        tree_card.rowconfigure(0, weight=1)
        tree_card.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tree_card, selectmode="browse")
        self.tree["columns"] = ("full_key", "pl", "en")
        self.tree["displaycolumns"] = ("pl", "en")
        self.tree.heading("#0", text="KEY", anchor="w")
        self.tree.heading("pl", text="POLSKI", anchor="w")
        self.tree.heading("en", text="ENGLISH", anchor="w")
        self.tree.column("#0", width=340, minwidth=180, stretch=True)
        self.tree.column("pl", width=360, minwidth=120, stretch=True)
        self.tree.column("en", width=360, minwidth=120, stretch=True)
        self.tree.tag_configure("group", font=self.fonts["bold"])
        self.tree.tag_configure("missing", foreground=Palette.WARNING)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_card, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns", padx=(4, 4))
        self.tree.configure(yscrollcommand=vsb.set)

        self.empty_label = ttk.Label(
            tree_card, style="Card.Muted.TLabel", justify="center"
        )

        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Return>", lambda _e: self.edit_selected())
        self.tree.bind("<BackSpace>", lambda _e: self.delete_selected())
        self.tree.bind("<Delete>", lambda _e: self.delete_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_details())

        paned.add(tree_card, weight=3)
        paned.add(self._build_details(paned), weight=1)

    def _build_details(self, parent):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(22, 18, 22, 18))
        ttk.Label(card, text="DETAILS", style="Card.Caption.TLabel").pack(anchor="w")
        self.detail_empty = ttk.Label(
            card,
            text="Select a key to see its translations.",
            style="Card.Muted.TLabel",
        )
        self.detail_empty.pack(anchor="w", pady=(12, 0))

        self.detail_body = ttk.Frame(card, style="Card.TFrame")
        self._detail_values = {}
        self._detail_copy_buttons = {}
        for name, caption, style in (
            ("key", "KEY", "Card.Mono.TLabel"),
            ("pl", "POLSKI", "Card.TLabel"),
            ("en", "ENGLISH", "Card.TLabel"),
        ):
            row = ttk.Frame(self.detail_body, style="Card.TFrame")
            row.pack(fill="x", pady=(16, 4))
            ttk.Label(row, text=caption, style="Card.Caption.TLabel").pack(side="left")
            copy_btn = ttk.Button(
                row,
                text="Copy",
                style="Card.Ghost.TButton",
                command=lambda n=name: self._copy_detail(n),
            )
            copy_btn.pack(side="right")
            value = ttk.Label(self.detail_body, style=style, justify="left")
            value.pack(anchor="w", fill="x")
            self._detail_values[name] = value
            self._detail_copy_buttons[name] = copy_btn

        actions = ttk.Frame(self.detail_body, style="Card.TFrame")
        actions.pack(fill="x", pady=(24, 0))
        self.detail_edit_btn = ttk.Button(
            actions, text="Edit translation", command=self.edit_selected
        )
        self.detail_edit_btn.pack(side="left")

        def on_resize(event):
            wrap = max(event.width - 44, 120)
            for label in self._detail_values.values():
                label.configure(wraplength=wrap)
            self.detail_empty.configure(wraplength=wrap)

        card.bind("<Configure>", on_resize)
        return card

    def _build_status_bar(self):
        bar = ttk.Frame(self, style="Status.TFrame", padding=(24, 7))
        bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(self, "")
        self.status_label = ttk.Label(
            bar, textvariable=self.status_var, style="Status.Small.TLabel"
        )
        self.status_label.pack(side="left")
        self.usage_status_var = tk.StringVar(self, "DeepL: checking usage…")
        ttk.Label(
            bar, textvariable=self.usage_status_var, style="Status.Small.TLabel"
        ).pack(side="right")
        self.dirty_label = ttk.Label(bar, text="", style="Status.Small.TLabel")
        self.dirty_label.pack(side="right", padx=(0, 18))

    # ------------------------------------------------------------------
    # Status / notifications
    # ------------------------------------------------------------------
    def notify(self, message, kind="success"):
        """Show a short-lived message in the status bar instead of a popup."""
        colors = {
            "success": Palette.SUCCESS,
            "info": Palette.TEXT,
            "warning": Palette.WARNING,
            "error": Palette.DANGER,
        }
        self.status_var.set(message)
        self.status_label.configure(foreground=colors.get(kind, Palette.TEXT))
        if self._status_job:
            self.after_cancel(self._status_job)
        self._status_job = self.after(6000, self._show_default_status)

    def _show_default_status(self):
        self._status_job = None
        if self.project and self.project.path:
            text = f"Project file: {short_path(self.project.path)}"
        else:
            text = "No project file — use File › New Project… to open both files at once next time"
        self.status_var.set(text)
        self.status_label.configure(foreground=Palette.MUTED)

    def _update_usage_status(self):
        remaining, used, limit = DeepLUsageCache.value
        if remaining is None:
            self.usage_status_var.set("DeepL: usage unavailable")
        else:
            self.usage_status_var.set(
                f"DeepL: {remaining:,} of {limit:,} characters left"
            )

    def _run_async(self, work, on_done):
        """Run ``work`` on the executor and call ``on_done(result)`` on the UI thread."""
        future = self.executor.submit(work)

        def poll():
            if not future.done():
                self.after(150, poll)
            elif future.exception() is None:
                on_done(future.result())

        self.after(150, poll)

    # ------------------------------------------------------------------
    # Dirty tracking
    # ------------------------------------------------------------------
    def _snapshot_saved_state(self):
        self._saved_pl = copy.deepcopy(self.pl_data)
        self._saved_en = copy.deepcopy(self.en_data)

    def has_unsaved_changes(self):
        return self.pl_data != getattr(
            self, "_saved_pl", self.pl_data
        ) or self.en_data != getattr(self, "_saved_en", self.en_data)

    def _confirm_discard_changes(self, action):
        """Ask to save pending edits. Returns False if the user cancels."""
        if not self.has_unsaved_changes():
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            f"You have unsaved changes. Save them before you {action}?",
            parent=self,
        )
        if answer is None:
            return False
        if answer:
            return self.save()
        return True

    # ------------------------------------------------------------------
    # i18n / language
    # ------------------------------------------------------------------
    def _t(self, key: str, **params) -> str:
        """
        Instance-aware translator. Falls back to key if missing.
        """
        try:
            txt = self.i18n.t(key, locale=self.ui_language, **params)
            return txt if txt else key
        except Exception:
            return key

    def on_language_changed(self, _event=None):
        """Handle UI language change from the combobox and persist to config."""
        selected = self.lang_combo.get()  # np. "pl — Polski"
        new_code = selected.split(" — ", 1)[0].strip()
        if not new_code:
            return

        self.ui_language = new_code
        update_config_value("ui_language", new_code)
        self.notify(f"Saved UI language: {new_code}")

    def _refresh_global_usage(self, on_done=None):
        def done(_value):
            self._update_usage_status()
            if on_done:
                on_done()

        self._run_async(refresh_usage_cache, done)

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------
    def select_key(self, full_key: str):
        def _find(item):
            if self.tree.set(item, "full_key") == full_key:
                return item
            for child in self.tree.get_children(item):
                found = _find(child)
                if found:
                    self.tree.item(item, open=True)
                    return found
            return None

        target = None
        for root in self.tree.get_children(""):
            target = _find(root)
            if target:
                break

        if target:
            self.tree.selection_set(target)
            self.tree.see(target)
            self.tree.focus(target)

    def key_exists(self, full_key: str) -> bool:
        parts = full_key.split(".")
        return bool(get_nested(self.pl_data, parts) or get_nested(self.en_data, parts))

    def reorganize_all(self):
        if not messagebox.askyesno(
            "Reorganize JSON",
            "This operation will move all keys containing dots to a nested structure. Do you want to continue?",
        ):
            return

        self.pl_data = flatten_to_nested(self.pl_data)
        self.en_data = flatten_to_nested(self.en_data)

        self.insert_all()
        self.update_title()
        self.notify("Reorganized keys into a nested structure — save to keep it.")

    def reload(self):
        if not self._confirm_discard_changes("reload"):
            return
        try:
            self._load_data()
            self.insert_all()
            self.update_title()
            self.notify("Reloaded files from disk.")
        except Exception as e:
            logging.error("Error reloading files: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to reload files: {e}")

    # ------------------------------------------------------------------
    # Menus & shortcuts
    # ------------------------------------------------------------------
    @staticmethod
    def _accel(key, shift=False):
        if sys.platform == "darwin":
            return f"Command-{'Shift-' if shift else ''}{key}"
        return f"Ctrl+{'Shift+' if shift else ''}{key}"

    def _bind_shortcuts(self):
        def bind(sequence, handler):
            self.bind_all(sequence, lambda e: (handler(), "break")[1])

        bind("<Command-z>", self.undo_last)
        bind("<Command-y>", self.redo_last)
        bind("<Control-z>", self.undo_last)
        bind(f"<{MOD}-y>", self.redo_last)
        bind(f"<{MOD}-Shift-Z>", self.redo_last)
        bind(f"<{MOD}-s>", self.save)
        bind(f"<{MOD}-r>", self.reload)
        bind(f"<{MOD}-Shift-c>", self.change_files)
        bind(f"<{MOD}-Shift-C>", self.change_files)
        bind(f"<{MOD}-o>", self.open_project)
        bind(f"<{MOD}-n>", self.add_new)
        bind(f"<{MOD}-f>", self.focus_search)

    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, tk.END)

    def _create_settings_menu(self):
        settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        settings_menu.add_command(label="Show Config", command=self.show_config)
        self.menu_bar.add_cascade(label="Settings", menu=settings_menu)

    def show_config(self):
        config = load_json(CONFIG_PATH)
        text = json.dumps(config, ensure_ascii=False, indent=2)
        win = tk.Toplevel(self)
        win.title("Configuration File")
        style_toplevel(win)
        cfg_size = config.get("config_window_size")
        config_window_size = TypeUtils.is_null_or_empty(cfg_size, "800x500")
        win.geometry(config_window_size)

        frame = ttk.Frame(win, padding=(20, 18, 20, 0))
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        ttk.Label(frame, text="Configuration", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(frame, text=short_path(CONFIG_PATH), style="Small.TLabel").grid(
            row=0, column=0, sticky="e"
        )

        txt = tk.Text(frame, wrap="none", **text_widget_options(self))
        txt.insert("1.0", text)
        txt.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        def auto_indent(event):
            line = txt.get("insert linestart", "insert")
            indent = re.match(r"(\s*)", line).group(1)
            txt.insert("insert", "\n" + indent)
            return "break"

        txt.bind("<Return>", auto_indent)

        ysb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        ysb.grid(row=1, column=1, sticky="ns", pady=(12, 0))
        xsb = ttk.Scrollbar(frame, orient="horizontal", command=txt.xview)
        xsb.grid(row=2, column=0, sticky="ew")
        txt.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        btn_frame = ttk.Frame(win, padding=(20, 12, 20, 18))
        btn_frame.pack(fill="x")
        ttk.Button(
            btn_frame,
            text="Save",
            style="Accent.TButton",
            command=lambda: self.save_config(txt),
        ).pack(side="right")
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(
            side="right", padx=(0, 8)
        )

    def save_config(self, text_widget):
        content = text_widget.get("1.0", "end-1c")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON: {e}")
            return

        try:
            save_json(data, CONFIG_PATH)
        except OSError as e:
            logging.error("Error saving configuration: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

        new_pl = data.get("pl_file")
        new_en = data.get("en_file")
        if new_pl and new_pl != self.pl_path:
            self.pl_path = new_pl
        if new_en and new_en != self.en_path:
            self.en_path = new_en

        try:
            self._load_data()
            self.insert_all()
            self.update_title()
            self.notify(
                f"Configuration saved to {short_path(CONFIG_PATH)} and applied."
            )
        except Exception as e:
            logging.error("Error reloading after config save: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to reload data: {e}")

        try:
            cfg_win = text_widget.winfo_toplevel()
            cfg_win.destroy()
        except Exception:
            pass

    def _create_file_menu(self):
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(
            label="Open Project…",
            command=self.open_project,
            accelerator=self._accel("O"),
        )
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Open Recent", menu=self.recent_menu)
        file_menu.add_command(label="New Project…", command=self.new_project)
        file_menu.add_separator()
        file_menu.add_command(
            label="Change Files",
            command=self.change_files,
            accelerator=self._accel("C", shift=True),
        )
        file_menu.add_command(
            label="Save All", command=self.save, accelerator=self._accel("S")
        )
        file_menu.add_command(
            label="Reload", command=self.reload, accelerator=self._accel("R")
        )
        file_menu.add_separator()
        file_menu.add_command(label="Reorganize JSON", command=self.reorganize_all)
        self.menu_bar.add_cascade(label="Files", menu=file_menu)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.delete(0, tk.END)
        recent = load_json(CONFIG_PATH).get("recent_projects", [])
        for path in recent:
            self.recent_menu.add_command(
                label=short_path(path),
                command=lambda p=path: self._open_recent(p),
            )
        if not recent:
            self.recent_menu.add_command(label="No recent projects", state="disabled")

    def _create_edit_menu(self):
        edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        edit_menu.add_command(
            label="Add Key…", command=self.add_new, accelerator=self._accel("N")
        )
        edit_menu.add_command(label="Edit Selected…", command=self.edit_selected)
        edit_menu.add_command(label="Delete Selected", command=self.delete_selected)
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Undo", command=self.undo_last, accelerator=self._accel("Z")
        )
        edit_menu.add_command(
            label="Redo", command=self.redo_last, accelerator=self._accel("Y")
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Find", command=self.focus_search, accelerator=self._accel("F")
        )
        self.menu_bar.add_cascade(label="Edit", menu=edit_menu)

    def _create_help_menu(self):
        help_menu = tk.Menu(self.menu_bar, tearoff=0)
        help_menu.add_command(label="Overview", command=self.show_overview)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="FAQ", command=self.show_faq)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def open_project(self):
        if not self._confirm_discard_changes("open another project"):
            return
        project = open_project_interactive(self)
        if project:
            self._switch_to_project(project)

    def _open_recent(self, path):
        if not self._confirm_discard_changes("open another project"):
            return
        try:
            project = load_project(path)
        except ProjectError as e:
            messagebox.showerror("Cannot open project", str(e), parent=self)
            return
        self._switch_to_project(project)

    def new_project(self):
        if not self._confirm_discard_changes("switch projects"):
            return
        project = create_project_interactive(
            self, pl_path=self.pl_path, en_path=self.en_path
        )
        if project:
            self._switch_to_project(project)
            self.notify(f"Created project {short_path(project.path)}")

    def _switch_to_project(self, project):
        self.project = project
        self.pl_path, self.en_path = project.pl_path, project.en_path
        remember_project(project)
        self._rebuild_recent_menu()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._load_data()
        self.search_var.set("")
        self.insert_all()
        self.update_title()
        self.notify(f"Opened {project.display_name}")

    def _project_display_name(self):
        project = getattr(self, "project", None)
        if project:
            return project.display_name
        return f"{Path(self.pl_path).name} & {Path(self.en_path).name}"

    # ------------------------------------------------------------------
    # Data & stats
    # ------------------------------------------------------------------
    def count_translations(self):
        def _count_dict(d):
            count = 0
            for v in d.values():
                if isinstance(v, dict):
                    count += _count_dict(v)
                else:
                    count += 1
            return count

        return _count_dict(self.pl_data)

    def count_missing_en(self):
        def _count(d, prefix):
            missing = 0
            for k, v in d.items():
                parts = prefix + [k]
                if isinstance(v, dict):
                    missing += _count(v, parts)
                elif not get_nested(self.en_data, parts):
                    missing += 1
            return missing

        return _count(self.pl_data, [])

    def update_title(self):
        name = self._project_display_name()
        self.title(f"{name} — Translation Manager")
        if hasattr(self, "header_title"):
            self.header_title.configure(text=name)
            self.header_subtitle.configure(
                text=f"PL  {short_path(self.pl_path)}     EN  {short_path(self.en_path)}"
            )
            self._refresh_stats()

    def _refresh_stats(self):
        count = self.count_translations()
        self.count_badge.configure(text=f"{count:,} keys")
        missing = self.count_missing_en()
        if missing:
            self.missing_badge.configure(
                text=f"{missing:,} missing EN", foreground=Palette.WARNING
            )
            self.missing_badge.pack(side="right", padx=(6, 0), before=self.count_badge)
        else:
            self.missing_badge.pack_forget()
        unsaved = self.has_unsaved_changes()
        self.dirty_label.configure(
            text="● Unsaved changes" if unsaved else "",
            foreground=Palette.WARNING,
        )
        self.title(
            f"{'• ' if unsaved else ''}{self._project_display_name()} — Translation Manager"
        )

    @staticmethod
    def show_overview():
        text = (
            "This application allows you to browse, add, edit, and delete translation keys. "
            "Polish (PL) and English (EN) values are shown side by side. "
            "Use the toolbar to manage entries and the search box to filter keys.\n\n"
            "A project file (File › New Project…) stores the paths to both files, "
            "so you can open them together."
        )
        messagebox.showinfo("Overview", text)

    @staticmethod
    def show_shortcuts():
        mod = "Cmd" if sys.platform == "darwin" else "Ctrl"
        text = (
            "Keyboard Shortcuts:\n"
            f"- {mod}+O: Open project\n"
            f"- {mod}+N: Add new key\n"
            f"- {mod}+F: Search\n"
            f"- {mod}+Z: Undo last action\n"
            f"- {mod}+Y / {mod}+Shift+Z: Redo last action\n"
            f"- {mod}+S: Save changes\n"
            f"- {mod}+R: Reload data from files\n"
            "- Double-click or Enter on a key: Edit\n"
            "- Delete / Backspace on a key: Delete\n"
            "- Right-click on a key: Copy key or values\n"
        )
        messagebox.showinfo("Keyboard Shortcuts", text)

    @staticmethod
    def show_faq():
        text = (
            "FAQ:\n"
            "Q: How do I auto-translate?\n"
            "A: When adding or editing, check 'Translate to English with DeepL'.\n\n"
            "Q: What is a project file?\n"
            "A: A small JSON file with the paths to your PL and EN files "
            "(relative to the project file). Open it to load both at once.\n\n"
            "Q: Where are files saved?\n"
            f"A: Config path is {CONFIG_PATH}.\n"
        )
        messagebox.showinfo("FAQ", text)

    def _load_data(self):
        self.pl_data = load_json(self.pl_path)
        self.en_data = load_json(self.en_path)
        self._snapshot_saved_state()

    # ------------------------------------------------------------------
    # Tree interaction
    # ------------------------------------------------------------------
    def on_tree_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        else:
            self.tree.selection_remove(self.tree.selection())

    def _on_tree_double_click(self, event):
        row = self.tree.identify_row(event.y)
        if row and not self.tree.get_children(row):
            self.edit_selected()
            return "break"

    def show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        full = self.tree.set(row, "full_key")
        if not full:
            parent = self.tree.parent(row)
            full = self.tree.set(parent, "full_key")
        parts = full.split(".")
        pl_val = get_nested(self.pl_data, parts)
        en_val = get_nested(self.en_data, parts)
        self.menu.entryconfig(
            MenuOptionLabelEnum.LabelCopyPl.value,
            state="normal" if pl_val else "disabled",
        )
        self.menu.entryconfig(
            MenuOptionLabelEnum.LabelCopyEn.value,
            state="normal" if en_val else "disabled",
        )
        self._menu_parts = parts
        self.menu.post(event.x_root, event.y_root)
        self.menu.grab_release()

    def _copy_to_clipboard(self, value):
        if value:
            self.clipboard_clear()
            self.clipboard_append(value)
            self.notify("Copied to clipboard.", kind="info")

    def copy_key(self):
        key = ".".join(self._menu_parts)
        self.clipboard_clear()
        self.clipboard_append(key)

    def copy_pl(self):
        val = get_nested(self.pl_data, self._menu_parts)
        if val:
            self.clipboard_clear()
            self.clipboard_append(val)

    def copy_en(self):
        val = get_nested(self.en_data, self._menu_parts)
        if val:
            self.clipboard_clear()
            self.clipboard_append(val)

    def _copy_detail(self, name):
        full = self._get_selected_full_key()
        if not full:
            return
        parts = full.split(".")
        value = {
            "key": full,
            "pl": get_nested(self.pl_data, parts),
            "en": get_nested(self.en_data, parts),
        }[name]
        self._copy_to_clipboard(value)

    def _update_details(self):
        full = self._get_selected_full_key()
        if not full:
            self.detail_body.pack_forget()
            self.detail_empty.pack(anchor="w", pady=(12, 0))
            return
        parts = full.split(".")
        node = self.pl_data
        for part in parts:
            node = node.get(part, "") if isinstance(node, dict) else ""

        self.detail_empty.pack_forget()
        self.detail_body.pack(fill="x")
        self._detail_values["key"].configure(text=full)

        if isinstance(node, dict):
            count = sum(1 for _ in _iter_leaves(node))
            self._detail_values["pl"].configure(
                text=f"Group with {count} translation{'s' if count != 1 else ''}",
                foreground=Palette.MUTED,
            )
            self._detail_values["en"].configure(text="—", foreground=Palette.MUTED)
            for name in ("pl", "en"):
                self._detail_copy_buttons[name].state(["disabled"])
            self.detail_edit_btn.state(["disabled"])
            return

        en_val = get_nested(self.en_data, parts)
        self._detail_values["pl"].configure(text=str(node), foreground=Palette.TEXT)
        self._detail_values["en"].configure(
            text=en_val or "Missing translation",
            foreground=Palette.TEXT if en_val else Palette.WARNING,
        )
        self._detail_copy_buttons["pl"].state(["!disabled"])
        self._detail_copy_buttons["en"].state(["!disabled" if en_val else "disabled"])
        self.detail_edit_btn.state(["!disabled"])

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def on_close(self):
        if not self._confirm_discard_changes("quit"):
            return
        self.executor.shutdown(wait=True)  # Ensure all tasks complete before shutdown
        self.destroy()
        self.quit()

    def get_expanded_keys(self):
        expanded = set()
        for item in self.tree.get_children(""):
            self._collect_expanded(item, expanded)
        return expanded

    def _collect_expanded(self, item, expanded):
        if self.tree.item(item, "open"):
            key = self.tree.set(item, "full_key")
            if key:
                expanded.add(key)
        for child in self.tree.get_children(item):
            self._collect_expanded(child, expanded)

    def restore_expanded_keys(self, expanded):
        def _restore(value):
            key = self.tree.set(value, "full_key")
            if key in expanded:
                self.tree.item(value, open=True)
            for child in self.tree.get_children(value):
                _restore(child)

        for item in self.tree.get_children(""):
            _restore(item)

    def on_search(self, *args):
        self._update_search_placeholder()
        self.insert_all()

    def _update_search_placeholder(self):
        if self.search_var.get():
            self.search_placeholder.place_forget()
        else:
            self.search_placeholder.place(
                in_=self.search_entry, x=4, rely=0.5, anchor="w"
            )

    def insert_all(self):
        search = self.search_var.get().strip().lower()
        expanded = self.get_expanded_keys()
        # Search auto-expands matches; restore the user's own layout afterwards.
        was_searching = getattr(self, "_last_search", "")
        if search and not was_searching:
            self._expanded_before_search = expanded
        elif not search and was_searching:
            expanded = getattr(self, "_expanded_before_search", expanded)
        self._last_search = search
        selected = self._get_selected_full_key()
        self.tree.delete(*self.tree.get_children())

        def one_line(value):
            return str(value).replace("\n", " ⏎ ")

        def add_nodes(parent, data, prefix=""):
            for key, val in sorted(data.items()):
                full = f"{prefix}.{key}" if prefix else key
                en_val = str(get_nested(self.en_data, full.split(".")) or "")
                pl_val = str(val) if not isinstance(val, dict) else ""
                node_matches = (
                    search in full.lower()
                    or search in pl_val.lower()
                    or search in en_val.lower()
                    or not search
                )
                if isinstance(val, dict):
                    node_id = self.tree.insert(
                        parent,
                        "end",
                        text=key,
                        values=(full, "", ""),
                        open=(full in expanded or bool(search)),
                        tags=("group",),
                    )
                    add_nodes(node_id, val, full)
                    if not self.tree.get_children(node_id) and not node_matches:
                        self.tree.delete(node_id)
                elif node_matches:
                    self.tree.insert(
                        parent,
                        "end",
                        text=key,
                        values=(
                            full,
                            one_line(pl_val),
                            one_line(en_val) if en_val else "⚠  missing",
                        ),
                        tags=() if en_val else ("missing",),
                    )

        add_nodes("", self.pl_data)
        self.restore_expanded_keys(expanded)
        if selected:
            self.select_key(selected)

        if self.tree.get_children(""):
            self.empty_label.place_forget()
        else:
            self.empty_label.configure(
                text=(
                    f"No keys match “{search}”."
                    if search
                    else "No translations yet.\nClick “Add key” to create the first one."
                )
            )
            self.empty_label.place(relx=0.5, rely=0.4, anchor="center")
        self._update_details()
        self._refresh_stats()

    def add_new(self):
        self.redo_stack.clear()
        sel = self.tree.selection()
        initial = ""
        if sel:
            row = sel[0]
            while row:
                full = self.tree.set(row, "full_key")
                if full:
                    if self.tree.get_children(row):
                        initial = full + "."
                    elif "." in full:
                        initial = full.rsplit(".", 1)[0] + "."
                    break
                row = self.tree.parent(row)
        dlg = AddDialog(self, initial_key=initial, title="Add New Translation")
        if not getattr(dlg, "result", None):
            return

        parts = dlg.result["key"].split(".")
        pl_text = dlg.result["pl"]

        op = {"action": ActionEnum.Add.value, "parts": parts, "pl": pl_text, "en": ""}
        self.undo_stack.append(op)
        set_nested(self.pl_data, parts, pl_text)

        if dlg.result["auto"]:
            needed = estimate_char_cost(pl_text)
            remaining, used, limit = get_remaining_quota(translator)
            if remaining is not None and remaining < needed:
                messagebox.showerror(
                    "DeepL limit",
                    f"No limit to translate this key.\n"
                    f"Needed: {needed} characters\n"
                    f"Remaining: {remaining} / {limit} (used {used})",
                )
                self.insert_all()
                self.update_title()
                return
            self.insert_all()
            self.update_title()
            self.notify("Translating with DeepL…", kind="info")
            self.executor.submit(self.translate_and_insert, parts, pl_text)
        else:
            manual_en = dlg.result.get("en", "").strip()
            op["en"] = manual_en
            set_nested(self.en_data, parts, manual_en)
            self.insert_all()
            self.update_title()
        self.select_key(".".join(parts))

    def _get_selected_full_key(self):
        """
        Retrieve the full key of the currently selected item in the tree widget.
        If the selected item does not have a full key, the method attempts to retrieve
        the full key of its parent. If no selection is made or no full key is found,
        the method returns None.
        Returns:
            str or None: The full key of the selected item, or None if not available.
        """
        sel = self.tree.selection()
        if not sel:
            return None
        node = sel[0]
        full = self.tree.set(node, "full_key")
        if not full:
            parent = self.tree.parent(node)
            full = self.tree.set(parent, "full_key")
        return full or None

    def edit_selected(self):
        self.redo_stack.clear()
        full = self._get_selected_full_key()

        if not full:
            return

        parts = full.split(".")
        old_pl = get_nested(self.pl_data, parts)
        old_en = get_nested(self.en_data, parts)

        current_pl = old_pl or ""
        current_en = old_en or ""
        dlg = AddDialog(
            self,
            initial_key=full,
            initial_pl=current_pl,
            initial_en=current_en,
            auto_default=False,
            original_key=full,
            title="Edit Translation",
        )
        if not getattr(dlg, "result", None):
            return

        new_key = dlg.result["key"]
        new_parts = new_key.split(".")
        op = {
            "action": ActionEnum.Edit.value,
            "old_parts": parts,
            "new_parts": new_parts,
            "old_pl": old_pl,
            "old_en": old_en,
            "new_pl": dlg.result["pl"],
            "new_en": "",
        }
        self.undo_stack.append(op)
        # If key changed, move subtree
        if new_parts != parts:
            # extract pl subtree
            pl_val = get_nested(self.pl_data, parts)
            en_val = get_nested(self.en_data, parts)
            # remove old
            self.remove_nested(self.pl_data, parts)
            self.remove_nested(self.en_data, parts)
            parts = new_parts
            # set new subtree
            set_nested(self.pl_data, parts, pl_val)
            set_nested(self.en_data, parts, en_val)

        # Update texts
        set_nested(self.pl_data, parts, dlg.result["pl"])
        if dlg.result["auto"]:
            needed = estimate_char_cost(dlg.result["pl"])
            remaining, used, limit = get_remaining_quota(translator)
            if remaining is not None and remaining < needed:
                messagebox.showerror(
                    "DeepL limit",
                    f"No limit to translate this key.\n"
                    f"Needed: {needed} characters\n"
                    f"Remaining: {remaining} / {limit} (used {used})",
                )
                self.insert_all()
                return
            self.insert_all()
            self.notify("Translating with DeepL…", kind="info")
            self.executor.submit(self.translate_and_insert, parts, dlg.result["pl"])
        else:
            manual_en = dlg.result.get("en", "").strip()
            op["new_en"] = manual_en
            set_nested(self.en_data, parts, dlg.result.get("en", ""))
            self.insert_all()

    def translate_and_insert(self, parts, pl_text):
        en_text = translate_text(pl_text)
        self.after(0, lambda: self.finish_insert(parts, en_text))

    def finish_insert(self, parts, en_text):
        if not en_text:
            self.notify("DeepL translation failed.", kind="error")
            messagebox.showerror(
                "Translation failed",
                "Error while translating text. Check connection with DeepL and try again",
            )
            return
        set_nested(self.en_data, parts, en_text)

        for op in reversed(self.undo_stack):
            if op.get("parts") == parts or (
                op["action"] == ActionEnum.Edit.value
                and parts in (op.get("old_parts"), op.get("new_parts"))
            ):
                if op["action"] == ActionEnum.Add.value:
                    op["en"] = en_text
                elif op["action"] == ActionEnum.Edit.value:
                    op["new_en"] = en_text
                break

        self.notify(f"Translated “{'.'.join(parts)}” with DeepL.")
        self._refresh_global_usage()
        self.insert_all()

    def change_files(self):
        new_pl = filedialog.askopenfilename(
            title="Select Polish translation file",
            filetypes=[("JSON Files", "*.json")],
        )
        if not new_pl:
            return
        new_en = filedialog.askopenfilename(
            title="Select English translation file",
            filetypes=[("JSON Files", "*.json")],
        )
        if not new_en:
            return

        project = getattr(self, "project", None)
        if project and project.path:
            try:
                self.project = save_project(
                    project.path, new_pl, new_en, name=project.name
                )
            except OSError as e:
                messagebox.showerror("Cannot update project", str(e))
                return
        else:
            self.project = None

        config = load_json(CONFIG_PATH)

        config["pl_file"] = new_pl
        config["en_file"] = new_en

        save_json(config, CONFIG_PATH)

        self.pl_path, self.en_path = new_pl, new_en
        self._load_data()
        self.insert_all()
        self.update_title()

    def save(self):
        try:
            save_json(self.pl_data, self.pl_path)
            save_json(self.en_data, self.en_path)
        except OSError as e:
            logging.error("Error saving translations: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to save files: {e}")
            return False
        self._snapshot_saved_state()
        self._refresh_stats()
        self.notify(f"Updated {Path(self.pl_path).name} and {Path(self.en_path).name}.")
        return True

    @staticmethod
    def remove_nested(d, keys):
        if not keys:
            return
        cur = d
        parents = []
        for k in keys[:-1]:
            parents.append((cur, k))
            cur = cur.get(k, {})
            if not isinstance(cur, dict):
                return
        cur.pop(keys[-1], None)
        for parent, key in reversed(parents):
            if parent[key] == {}:
                parent.pop(key)

    def delete_selected(self):
        self.redo_stack.clear()
        full = self._get_selected_full_key()
        if not full:
            return

        if not messagebox.askyesno(
            "Confirm Delete", f"Are you sure to remove the key:\n{full}?"
        ):
            return

        parts = full.split(".")
        old_pl = get_nested(self.pl_data, parts)
        old_en = get_nested(self.en_data, parts)
        self.undo_stack.append(
            {"action": "delete", "parts": parts, "old_pl": old_pl, "old_en": old_en}
        )
        self.remove_nested(self.pl_data, parts)
        self.remove_nested(self.en_data, parts)
        self.insert_all()
        self.update_title()

    def undo_last(self):
        if not self.undo_stack:
            self.notify("Nothing to undo.", kind="info")
            return
        op = self.undo_stack.pop()
        self.redo_stack.append(op)
        action = op["action"]
        if action == ActionEnum.Add.value:
            self.remove_nested(self.pl_data, op["parts"])
            self.remove_nested(self.en_data, op["parts"])
            self.notify("Undid add.", kind="info")
        elif action == ActionEnum.Delete.value:
            set_nested(self.pl_data, op["parts"], op["old_pl"])
            set_nested(self.en_data, op["parts"], op["old_en"])
            self.notify("Undid delete.", kind="info")
        elif action == ActionEnum.Edit.value:
            self.remove_nested(self.pl_data, op["new_parts"])
            self.remove_nested(self.en_data, op["new_parts"])
            set_nested(self.pl_data, op["old_parts"], op["old_pl"])
            set_nested(self.en_data, op["old_parts"], op["old_en"])
            self.notify("Undid edit.", kind="info")
        self.insert_all()
        self.update_title()

    def redo_last(self):
        if not self.redo_stack:
            self.notify("Nothing to redo.", kind="info")
            return
        op = self.redo_stack.pop()
        self.undo_stack.append(op)
        action = op["action"]

        if action == ActionEnum.Add.value:
            set_nested(self.pl_data, op["parts"], op.get("pl") or "")
            set_nested(self.en_data, op["parts"], op.get("en") or "")
            self.notify("Redid add.", kind="info")
        elif action == ActionEnum.Delete.value:
            self.remove_nested(self.pl_data, op["parts"])
            self.remove_nested(self.en_data, op["parts"])
            self.notify("Redid delete.", kind="info")
        elif action == ActionEnum.Edit.value:
            self.remove_nested(self.pl_data, op["old_parts"])
            self.remove_nested(self.en_data, op["old_parts"])
            set_nested(self.pl_data, op["new_parts"], op["new_pl"])
            set_nested(self.en_data, op["new_parts"], op["new_en"])
            self.notify("Redid edit.", kind="info")

        self.insert_all()
        self.update_title()


def _iter_leaves(d):
    for v in d.values():
        if isinstance(v, dict):
            yield from _iter_leaves(v)
        else:
            yield v


def main():
    configure_logging(logging.INFO)
    config = load_json(CONFIG_PATH)
    project = startup_project(config)
    if project is None:
        project = run_welcome(config.get("recent_projects", []))
    if project is None:
        return
    remember_project(project)
    app = TranslationApp(project.pl_path, project.en_path, project=project)
    app.mainloop()


if __name__ == "__main__":
    main()
