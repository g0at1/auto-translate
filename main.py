#!/usr/bin/env python3
import json
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
from pathlib import Path
import deepl
from dotenv import load_dotenv
import os
from ttkthemes import ThemedTk, ThemedStyle
from tkinter import ttk

load_dotenv()
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
translator = deepl.Translator(DEEPL_API_KEY)

CONFIG_PATH = Path.home() / ".translation_app_config.json"


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
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
        print(f"DeepL translation error: {e}")
        return ""


class AddDialog(simpledialog.Dialog):
    def __init__(self, parent, initial_key="", **kwargs):
        self.initial_key = initial_key
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
            self.key_entry.insert(0, self.initial_key + ".")

        ttk.Label(master, text="Polish text:").grid(row=1, column=0, sticky="w")
        self.pl_entry = ttk.Entry(master, width=50)
        self.pl_entry.grid(row=1, column=1)

        ttk.Label(master, text="English text:").grid(row=2, column=0, sticky="w")
        self.en_entry = ttk.Entry(master, width=50)
        self.en_entry.grid(row=2, column=1)

        self.auto_var = tk.BooleanVar(master, True)

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

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()


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


class TranslationApp(ThemedTk):
    def __init__(self, pl_path, en_path):
        super().__init__(theme="equilux")
        self.pl_path = pl_path
        self.en_path = en_path
        self._load_data()

        self.title(f"Language Files - {Path(pl_path).name} & {Path(en_path).name}")
        self.geometry("600x400")
        self.center_window()

        self.tree = ttk.Treeview(self)
        self.tree["columns"] = ("full_key",)
        self.tree.column("full_key", width=0, stretch=False)
        self.tree.heading("#0", text="Translation Keys")
        self.tree.pack(fill="both", expand=True)

        self.tree.bind("<Button-1>", self.on_tree_click)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Add New", command=self.add_new).pack(
            side="left", padx=5, pady=5
        )
        ttk.Button(btn_frame, text="Change Files", command=self.change_files).pack(
            side="left", padx=5, pady=5
        )
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side="left", padx=5)

        self.insert_all()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _load_data(self):
        self.pl_data = load_json(self.pl_path)
        self.en_data = load_json(self.en_path)

    def on_tree_click(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            self.tree.selection_remove(self.tree.selection())

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
        self.destroy()
        self.quit()

    def insert_all(self):
        self.tree.delete(*self.tree.get_children())

        def add_nodes(parent, data, prefix=""):
            for key, val in sorted(data.items()):
                full = f"{prefix}.{key}" if prefix else key
                node = self.tree.insert(
                    parent, "end", text=key, values=(full,), open=False
                )
                if isinstance(val, dict):
                    add_nodes(node, val, full)
                else:
                    self.tree.insert(node, "end", text=f"[PL] {val}")
                    en_val = get_nested(self.en_data, full.split("."))
                    display_en = en_val or "(no translation)"
                    self.tree.insert(node, "end", text=f"[EN] {display_en}")

        add_nodes("", self.pl_data)

    def add_new(self):
        sel = self.tree.selection()
        initial = self.tree.set(sel[0], "full_key") if sel else ""
        dlg = AddDialog(self, initial_key=initial)
        if not getattr(dlg, "result", None):
            return

        if not dlg.result["key"] or not dlg.result["pl"]:
            messagebox.showerror("Error", "Key and Polish text are required")
            return

        parts = dlg.result["key"].split(".")
        pl_text = dlg.result["pl"]
        set_nested(self.pl_data, parts, pl_text)

        if dlg.result["auto"]:
            threading.Thread(
                target=self.translate_and_insert, args=(parts, pl_text), daemon=True
            ).start()
        else:
            manual_en = dlg.result.get("en", "").strip()
            set_nested(self.en_data, parts, manual_en)
            self.insert_all()

    def translate_and_insert(self, parts, pl_text):
        en_text = translate_text(pl_text)
        self.after(0, lambda: self.finish_insert(parts, en_text))

    def finish_insert(self, parts, en_text):
        if not en_text:
            en_text = (
                simpledialog.askstring("English translation", "Enter English text:")
                or ""
            )
        set_nested(self.en_data, parts, en_text)
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


def main():
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
