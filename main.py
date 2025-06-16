#!/usr/bin/env python3
import json
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
from pathlib import Path
import deepl
from dotenv import load_dotenv
import os
from ttkthemes import ThemedTk, ThemedStyle
from tkinter import ttk
from enums.menu_option_label_enum import MenuOptionLabelEnum
from enums.action_enum import ActionEnum
import logging
import concurrent.futures
from utils.logging_config import configure_logging
import sys

load_dotenv()
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
translator = deepl.Translator(DEEPL_API_KEY)

CONFIG_PATH = Path.home() / ".translation_app_config.json"


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


class AddDialog(simpledialog.Dialog):
    def __init__(
        self,
        parent,
        initial_key="",
        initial_pl="",
        initial_en="",
        auto_default=True,
        **kwargs,
    ):
        self.parent = parent
        self.initial_key = initial_key
        self.initial_pl = initial_pl
        self.initial_en = initial_en
        self.auto_default = auto_default
        self.duplicate_key = None
        self.jump_button = None
        super().__init__(parent, **kwargs)

    def body(self, master):
        toplevel = master.winfo_toplevel()
        style = ThemedStyle(toplevel)
        style.set_theme("equilux")
        bg = style.lookup("TFrame", "background")
        master.configure(background=bg)
        toplevel.configure(background=bg)
        ttk.Label(master, text="Key path (dot separated):").grid(
            row=0, column=0, sticky="w"
        )
        self.key_entry = ttk.Entry(master, width=50)
        self.key_entry.grid(row=0, column=1)
        if self.initial_key:
            self.key_entry.insert(0, self.initial_key)
        self.duplicate_label = ttk.Label(master, text="", foreground="orange")
        self.duplicate_label.grid(row=4, column=1, sticky="w", pady=(2, 0))
        self.key_entry.bind("<KeyRelease>", self.check_duplicate)

        ttk.Label(master, text="Polish text:").grid(row=1, column=0, sticky="w")
        self.pl_entry = ttk.Entry(master, width=50)
        self.pl_entry.grid(row=1, column=1)
        if self.initial_pl:
            self.pl_entry.insert(0, self.initial_pl)

        ttk.Label(master, text="English text:").grid(row=2, column=0, sticky="w")
        self.en_entry = ttk.Entry(master, width=50)
        self.en_entry.grid(row=2, column=1)
        if self.initial_en:
            self.en_entry.insert(0, self.initial_en)

        self.auto_var = tk.BooleanVar(master, self.auto_default)

        def toggle_en():
            if self.auto_var.get():
                self.en_entry.delete(0, tk.END)
                self.en_entry.config(state="disabled")
            else:
                self.en_entry.config(state="normal")

        chk = ttk.Checkbutton(
            master,
            text="Use DeepL to translate",
            variable=self.auto_var,
            command=toggle_en,
        )
        chk.grid(row=3, column=1, sticky="w")
        toggle_en()

        return self.key_entry

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

    def buttonbox(self):
        box = ttk.Frame(self)

        ok = ttk.Button(box, text="Submit", width=10, command=self.ok, default="active")
        ok.pack(side="left", padx=5, pady=5)
        cancel = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        cancel.pack(side="left", padx=5, pady=5)
        self.jump_button = ttk.Button(
            box, text="Jump to ID", width=10, command=self.on_jump
        )
        self.jump_button.pack(side="left", padx=5, pady=5)
        self.jump_button.pack_forget()

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def check_duplicate(self, event=None):
        key = self.key_entry.get().strip()
        if hasattr(self.parent, "key_exists") and self.parent.key_exists(key):
            self.duplicate_key = key
            self.duplicate_label.config(text=f"Key “{key}” already exists.")
            self.jump_button.pack(side="left", padx=5, pady=5)
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


class TranslationApp(ThemedTk):
    def __init__(self, pl_path, en_path, max_workers=5):
        super().__init__(theme="equilux")
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)
        self._create_file_menu()
        self._create_help_menu()
        self._create_settings_menu()
        self.pl_path = pl_path
        self.en_path = en_path
        self._load_data()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        style = ThemedStyle(self)
        style.configure("Custom.Treeview")
        style.map(
            "Custom.Treeview",
            background=[("selected", "#007acc")],
            foreground=[("selected", "white")],
        )
        style.map(
            "TEntry",
            fieldbackground=[("!disabled", "#222222")],
            foreground=[("!disabled", "white")],
            selectbackground=[("!disabled", "#007acc")],
            selectforeground=[("!disabled", "white")],
        )

        self.update_title()
        self.geometry("600x400")
        self.center_window()
        self.undo_stack = []
        self.redo_stack = []
        self.bind_all("<Command-z>", lambda e: self.undo_last())
        self.bind_all("<Command-y>", lambda e: self.redo_last())
        self.bind_all("<Control-z>", lambda e: self.undo_last())
        self.bind_all("<Command-s>", lambda e: self.save())
        self.bind_all("<Command-r>", lambda e: self.reload())
        self.bind_all("<Command-Shift-c>", lambda e: self.change_files())

        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x")
        ttk.Label(search_frame, text="Search:").pack(side="left")
        self.search_var = tk.StringVar(self)
        self.search_var.trace_add("write", self.on_search)
        self.search_entry = ttk.Entry(
            search_frame, textvariable=self.search_var, style="TEntry"
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))

        self.tree = ttk.Treeview(self, style="Custom.Treeview", selectmode="browse")
        self.tree["columns"] = ("full_key",)
        self.tree.column("full_key", width=0, stretch=False)
        self.tree.heading("#0", text="Translation Keys")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Button-1>", self.on_tree_click)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Copy Key", command=self.copy_key)
        self.menu.add_command(label="Copy PL Value", command=self.copy_pl)
        self.menu.add_command(label="Copy EN Value", command=self.copy_en)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Button-2>", self.show_context_menu)
        self.tree.bind("<Control-Button-1>", self.show_context_menu)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Add New", command=self.add_new).pack(
            side="left", padx=5, pady=5
        )
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Edit", command=self.edit_selected).pack(
            side="left", padx=5, pady=5
        )
        ttk.Button(btn_frame, text="Delete", command=self.delete_selected).pack(
            side="left", padx=5, pady=5
        )

        self.insert_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

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

        messagebox.showinfo(
            "Reorganization completed",
            "The reorganization of the JSON structure has been completed.",
        )

    def reload(self):
        try:
            self._load_data()
            self.insert_all()
            self.update_title()
            messagebox.showinfo("Reloaded", "Reloaded files")
        except Exception as e:
            logging.error("Error reloading files: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to reload files: {e}")

    def _create_settings_menu(self):
        settings_menu = tk.Menu(self.menu_bar, tearoff=0)
        settings_menu.add_command(label="Show Config", command=self.show_config)
        self.menu_bar.add_cascade(label="Settings", menu=settings_menu)

    def show_config(self):
        config = load_json(CONFIG_PATH)
        text = json.dumps(config, ensure_ascii=False, indent=2)
        win = tk.Toplevel(self)
        win.title("Configuration File")
        win.geometry("800x500")
        style = ThemedStyle(win)
        style.set_theme("equilux")
        bg = style.lookup("TFrame", "background")
        fg = style.lookup("TLabel", "foreground") or "white"
        win.configure(background=bg)

        style.configure(
            "Vertical.TScrollbar", troughcolor=bg, background=bg, arrowcolor=fg
        )
        style.configure(
            "Horizontal.TScrollbar", troughcolor=bg, background=bg, arrowcolor=fg
        )

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        txt = tk.Text(
            frame,
            wrap="none",
            bg=bg,
            fg=fg,
            insertbackground=fg,
            highlightthickness=0,
            bd=0,
        )
        txt.insert("1.0", text)
        txt.grid(row=0, column=0, sticky="nsew")

        ysb = ttk.Scrollbar(
            frame, style="Vertical.TScrollbar", orient="vertical", command=txt.yview
        )
        ysb.grid(row=0, column=1, sticky="ns")
        xsb = ttk.Scrollbar(
            frame, style="Horizontal.TScrollbar", orient="horizontal", command=txt.xview
        )
        xsb.grid(row=1, column=0, sticky="ew")
        txt.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Save", command=lambda: self.save_config(txt)).pack(
            side="left", padx=5, pady=5
        )
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(
            side="left", padx=5, pady=5
        )

    def save_config(self, text_widget):
        content = text_widget.get("1.0", "end-1c")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON: {e}")
            return

        save_json(data, CONFIG_PATH)
        messagebox.showinfo("Saved", f"Configuration saved to {CONFIG_PATH}")

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
            messagebox.showinfo("Reloaded", "Configuration applied and data reloaded.")
        except Exception as e:
            logging.error("Error reloading after config save: %s", e, exc_info=True)
            messagebox.showerror("Error", f"Failed to reload data: {e}")

        try:
            cfg_win = text_widget.winfo_toplevel()
            cfg_win.destroy()
        except Exception:
            pass

    def _create_file_menu(self):
        accel_text_change_files = (
            "Command-Shift-C" if sys.platform == "darwin" else "Ctrl-Shift-C"
        )
        accel_text_save = "Command-S" if sys.platform == "darwin" else "Ctrl+S"
        accel_text_refresh = "Command-R" if sys.platform == "darwin" else "Ctrl+R"
        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(
            label="Change Files",
            command=self.change_files,
            accelerator=accel_text_change_files,
        )
        file_menu.add_command(
            label="Save All", command=self.save, accelerator=accel_text_save
        )
        file_menu.add_command(
            label="Reload", command=self.reload, accelerator=accel_text_refresh
        )
        file_menu.add_command(label="Reorganize JSON", command=self.reorganize_all)
        self.menu_bar.add_cascade(label="Files", menu=file_menu)

    def _create_help_menu(self):
        help_menu = tk.Menu(self.menu_bar, tearoff=0)
        help_menu.add_command(label="Overview", command=self.show_overview)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts)
        help_menu.add_command(label="FAQ", command=self.show_faq)
        self.menu_bar.add_cascade(label="Help", menu=help_menu)

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

    def update_title(self):
        count = self.count_translations()
        self.title(
            f"Language Files - {Path(self.pl_path).name} & {Path(self.en_path).name} | Translations: {count}"
        )

    @staticmethod
    def show_overview():
        text = (
            "This application allows you to browse, add, edit, and delete translation keys. "
            "Polish (PL) and English (EN) values are displayed in a tree view. "
            "Use the buttons to manage entries and the search box to filter keys."
        )
        messagebox.showinfo("Overview", text)

    @staticmethod
    def show_shortcuts():
        text = (
            "Keyboard Shortcuts:\n"
            "- Ctrl+Z or Cmd+Z: Undo last action\n"
            "- Ctrl+Y or Cmd+Y: Redo last action\n"
            "- Ctrl+S or Cmd+S: Save changes\n"
            "- Ctrl+R or Cmd+R: Reload data from files\n"
            "- Right-click on a key: Copy key or values\n"
        )
        messagebox.showinfo("Keyboard Shortcuts", text)

    @staticmethod
    def show_faq():
        text = (
            "FAQ:\n"
            "Q: How do I auto-translate?\n"
            "A: When adding or editing, check 'Use DeepL to translate'.\n\n"
            "Q: Where are files saved?\n"
            f"A: Config path is {CONFIG_PATH}.\n"
        )
        messagebox.showinfo("FAQ", text)

    def _load_data(self):
        self.pl_data = load_json(self.pl_path)
        self.en_data = load_json(self.en_path)

    def on_tree_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        else:
            self.tree.selection_remove(self.tree.selection())

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

    def center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def on_close(self):
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
        self.insert_all()

    def insert_all(self):
        search = self.search_var.get().strip().lower()
        expanded = self.get_expanded_keys()
        self.tree.delete(*self.tree.get_children())

        def add_nodes(parent, data, prefix=""):
            for key, val in sorted(data.items()):
                full = f"{prefix}.{key}" if prefix else key
                en_val = get_nested(self.en_data, full.split(".")) or ""
                pl_val = val if not isinstance(val, dict) else ""
                node_matches = (
                    search in full.lower()
                    or search in pl_val.lower()
                    or search in en_val.lower()
                    or not search
                )
                if isinstance(val, dict):
                    for _, _ in val.items():
                        pass
                    node_id = self.tree.insert(
                        parent, "end", text=key, values=(full,), open=(full in expanded)
                    )
                    add_nodes(node_id, val, full)
                    if not self.tree.get_children(node_id) and not node_matches:
                        self.tree.delete(node_id)
                else:
                    if node_matches:
                        node = self.tree.insert(
                            parent, "end", text=key, values=(full,), open=False
                        )
                        self.tree.insert(node, "end", text=f"[PL] {pl_val}")
                        display_en = en_val or "(no translation)"
                        self.tree.insert(node, "end", text=f"[EN] {display_en}")

        add_nodes("", self.pl_data)
        self.restore_expanded_keys(expanded)

    def add_new(self):
        self.redo_stack.clear()
        sel = self.tree.selection()
        initial = ""
        if sel:
            row = sel[0]
            while row:
                full = self.tree.set(row, "full_key")
                if full:
                    initial = full + "."
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
            self.executor.submit(self.translate_and_insert, parts, pl_text)
        else:
            manual_en = dlg.result.get("en", "").strip()
            op["en"] = manual_en
            set_nested(self.en_data, parts, manual_en)
            self.insert_all()
            self.update_title()

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
            messagebox.showerror(
                "Translation failed",
                "Error while translating text. Check connection with DeepL and try again",
            )
            return
        set_nested(self.en_data, parts, en_text)

        for op in reversed(self.undo_stack):
            if op["parts"] == parts or (
                op["action"] == ActionEnum.Edit.value
                and parts in (op.get("old_parts"), op.get("new_parts"))
            ):
                if op["action"] == ActionEnum.Add.value:
                    op["en"] = en_text
                elif op["action"] == ActionEnum.Edit.value:
                    op["new_en"] = en_text
                break

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
        self.pl_path, self.en_path = new_pl, new_en
        save_json({"pl_file": self.pl_path, "en_file": self.en_path}, CONFIG_PATH)
        self._load_data()
        self.title(
            f"Language Files - {Path(self.pl_path).name} & {Path(self.en_path).name}"
        )
        self.insert_all()

    def save(self):
        save_json(self.pl_data, self.pl_path)
        save_json(self.en_data, self.en_path)
        messagebox.showinfo("Saved", f"Updated:\n{self.pl_path}\n{self.en_path}")

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
            messagebox.showinfo("Undo", "Nothing to undo.")
            return
        op = self.undo_stack.pop()
        self.redo_stack.append(op)
        action = op["action"]
        if action == ActionEnum.Add.value:
            self.remove_nested(self.pl_data, op["parts"])
            self.remove_nested(self.en_data, op["parts"])
            messagebox.showinfo("Undo", "Undo add operation.")
        elif action == ActionEnum.Delete.value:
            set_nested(self.pl_data, op["parts"], op["old_pl"])
            set_nested(self.en_data, op["parts"], op["old_en"])
            messagebox.showinfo("Undo", "Undo delete operation.")
        elif action == ActionEnum.Edit.value:
            self.remove_nested(self.pl_data, op["new_parts"])
            self.remove_nested(self.en_data, op["new_parts"])
            set_nested(self.pl_data, op["old_parts"], op["old_pl"])
            set_nested(self.en_data, op["old_parts"], op["old_en"])
            messagebox.showinfo("Undo", "Undo edit operation.")
        self.insert_all()
        self.update_title()

    def redo_last(self):
        if not self.redo_stack:
            messagebox.showinfo("Redo", "Nothing to redo.")
            return
        op = self.redo_stack.pop()
        self.undo_stack.append(op)
        action = op["action"]

        if action == ActionEnum.Add.value:
            set_nested(self.pl_data, op["parts"], op.get("pl") or "")
            set_nested(self.en_data, op["parts"], op.get("en") or "")
            messagebox.showinfo("Redo", "Redo add operation.")
        elif action == ActionEnum.Delete.value:
            self.remove_nested(self.pl_data, op["parts"])
            self.remove_nested(self.en_data, op["parts"])
            messagebox.showinfo("Redo", "Redo delete operation.")
        elif action == ActionEnum.Edit.value:
            self.remove_nested(self.pl_data, op["old_parts"])
            self.remove_nested(self.en_data, op["old_parts"])
            set_nested(self.pl_data, op["new_parts"], op["new_pl"])
            set_nested(self.en_data, op["new_parts"], op["new_en"])
            messagebox.showinfo("Redo", "Redo edit operation.")

        self.insert_all()
        self.update_title()


def main():
    configure_logging(logging.INFO)
    root = tk.Tk()
    root.withdraw()
    config = load_json(CONFIG_PATH)
    pl_file = config.get("pl_file")
    en_file = config.get("en_file")
    if not pl_file or not Path(pl_file).is_file():
        pl_file = filedialog.askopenfilename(
            title="Select Polish translation file",
            filetypes=[("JSON Files", "*.json")],
        )
    if not en_file or not Path(en_file).is_file():
        en_file = filedialog.askopenfilename(
            title="Select English translation file",
            filetypes=[("JSON Files", "*.json")],
        )
    if not pl_file or not en_file:
        return
    save_json({"pl_file": pl_file, "en_file": en_file}, CONFIG_PATH)
    app = TranslationApp(pl_file, en_file)
    app.mainloop()


if __name__ == "__main__":
    main()
