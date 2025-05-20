import json
import pytest
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import main as app
from tkinter import filedialog, messagebox, Tk


# Helper to create a temporary JSON file
@pytest.fixture
def temp_json_file(tmp_path):
    data = {"a": {"b": "value"}}
    file_path = tmp_path / "test.json"
    file_path.write_text(json.dumps(data, ensure_ascii=False))
    return file_path, data


# -----------------------------
# Basic function tests
# -----------------------------
def test_load_json_valid(temp_json_file):
    path, data = temp_json_file
    loaded = app.load_json(path)
    assert loaded == data


def test_load_json_invalid(tmp_path):
    path = tmp_path / "nope.json"
    loaded = app.load_json(path)
    assert loaded == {}


def test_save_json_and_load(tmp_path):
    out = tmp_path / "out.json"
    data = {"x": 1, "y": {"z": 2}}
    app.save_json(data, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == data


# -----------------------------
# Nested dict helpers
# -----------------------------
def test_set_and_get_nested():
    d = {}
    app.set_nested(d, ["level1", "level2", "key"], "val")
    assert d == {"level1": {"level2": {"key": "val"}}}
    assert app.get_nested(d, ["level1", "level2", "key"]) == "val"
    assert app.get_nested(d, ["level1", "nope"]) == ""


def test_set_nested_overwrite():
    d = {"a": 1}
    app.set_nested(d, ["a", "b"], "v")
    assert isinstance(d["a"], dict)
    assert d["a"]["b"] == "v"


def test_get_nested_dict_case():
    d = {"a": {"b": {}}}
    assert app.get_nested(d, ["a", "b"]) == ""


# -----------------------------
# Translation tests
# -----------------------------
class DummyTranslator:
    def translate_text(self, text, source_lang=None, target_lang=None):
        class Result:
            def __init__(self, text):
                self.text = text

        if text == "error":
            raise app.deepl.DeepLException("fail")
        return Result(text + "_translated")


@pytest.fixture(autouse=True)
def patch_translator(monkeypatch):
    monkeypatch.setattr(app, "translator", DummyTranslator())


def test_translate_text_success():
    assert (
        app.translate_text("hello", source_lang="PL", target_lang="EN-GB")
        == "hello_translated"
    )


def test_translate_text_failure():
    assert app.translate_text("error") == ""


# -----------------------------
# Integration: change_files
# -----------------------------
def test_change_files_persists_config(tmp_path, monkeypatch):
    orig_pl = tmp_path / "orig_pl.json"
    orig_en = tmp_path / "orig_en.json"
    orig_pl.write_text(json.dumps({}), encoding="utf-8")
    orig_en.write_text(json.dumps({}), encoding="utf-8")
    new_pl = tmp_path / "new_pl.json"
    new_en = tmp_path / "new_en.json"
    new_pl.write_text(json.dumps({}), encoding="utf-8")
    new_en.write_text(json.dumps({}), encoding="utf-8")
    config = tmp_path / "config.json"
    monkeypatch.setattr(app, "CONFIG_PATH", config)
    ta = app.TranslationApp(str(orig_pl), str(orig_en))
    seq = [str(new_pl), str(new_en)]
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: seq.pop(0))
    ta.change_files()
    assert ta.pl_path.endswith("new_pl.json")
    assert ta.en_path.endswith("new_en.json")
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["pl_file"].endswith("new_pl.json")
    assert saved["en_file"].endswith("new_en.json")


def test_change_files_cancelled(tmp_path, monkeypatch):
    orig_pl = tmp_path / "orig_pl.json"
    orig_en = tmp_path / "orig_en.json"
    orig_pl.write_text(json.dumps({}), encoding="utf-8")
    orig_en.write_text(json.dumps({}), encoding="utf-8")
    ta = app.TranslationApp(str(orig_pl), str(orig_en))
    # pl dialog returns path, en returns empty -> should cancel
    seq = [str(orig_pl), ""]
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: seq.pop(0))
    ta.change_files()
    assert ta.pl_path == str(orig_pl)
    assert ta.en_path == str(orig_en)


# -----------------------------
# Test save() behavior
# -----------------------------
def test_save_updates_files_and_message(tmp_path, monkeypatch):
    pl = tmp_path / "p.json"
    en = tmp_path / "e.json"
    pl.write_text(json.dumps({}), encoding="utf-8")
    en.write_text(json.dumps({}), encoding="utf-8")
    ta = app.TranslationApp(str(pl), str(en))
    ta.pl_data["foo"] = "bar"
    ta.en_data["baz"] = "qux"
    info_called = {}
    monkeypatch.setattr(
        messagebox,
        "showinfo",
        lambda title, msg: info_called.update({"title": title, "msg": msg}),
    )
    ta.save()
    assert json.loads(pl.read_text())["foo"] == "bar"
    assert json.loads(en.read_text())["baz"] == "qux"
    assert "Updated" in info_called["title"] or "Updated" in info_called["msg"]


# -----------------------------
# Test on_tree_click
# -----------------------------
def test_on_tree_click_clears_selection(monkeypatch):
    # Create dummy app with fake tree
    ta = app.TranslationApp.__new__(app.TranslationApp)

    class FakeTree:
        def __init__(self):
            self.removed = False

        def identify_row(self, y):
            return ""

        def selection(self):
            return ["item"]

        def selection_remove(self, sel):
            self.removed = True

    ta.tree = FakeTree()

    # Simulate event
    class E:
        y = 10

    ta.on_tree_click(E())
    assert ta.tree.removed is True


# -----------------------------
# Test AddDialog logic
# -----------------------------
def test_adddialog_toggle_behavior(monkeypatch):
    root = Tk()
    dlg = app.AddDialog.__new__(app.AddDialog)
    dlg.initial_key = ""
    # Create fake widgets
    dlg.auto_var = app.tk.BooleanVar(root, True)

    class FakeEntry:
        def __init__(self):
            self.state = None

        def config(self, state):
            self.state = state

        def delete(self, a, b):
            pass

    dlg.en_entry = FakeEntry()

    # Recreate toggle function
    def toggle_en():
        if dlg.auto_var.get():
            dlg.en_entry.config(state="disabled")
        else:
            dlg.en_entry.config(state="normal")

    # Initially auto_var true -> disabled
    toggle_en()
    assert dlg.en_entry.state == "disabled"
    # Now switch
    dlg.auto_var.set(False)
    toggle_en()
    assert dlg.en_entry.state == "normal"
    root.destroy()


# -----------------------------
# Tests for finish_insert and main()
# -----------------------------
def test_finish_insert_updates_data(tmp_path):
    pl = tmp_path / "p.json"
    en = tmp_path / "e.json"
    pl.write_text(json.dumps({}))
    en.write_text(json.dumps({}))
    ta = app.TranslationApp(str(pl), str(en))
    parts = ["a", "b"]
    ta.finish_insert(parts, "hello")
    assert app.get_nested(ta.en_data, parts) == "hello"


def test_main_saves_config(monkeypatch, tmp_path):
    # No config
    monkeypatch.setenv("HOME", str(tmp_path))
    config = tmp_path / ".translation_app_config.json"
    monkeypatch.setattr(app, "CONFIG_PATH", config)
    # Dialog returns files
    p = tmp_path / "p.json"
    e = tmp_path / "e.json"
    p.write_text(json.dumps({}))
    e.write_text(json.dumps({}))
    seq = [str(p), str(e)]
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: seq.pop(0))
    saved = []
    monkeypatch.setattr(app, "save_json", lambda data, path: saved.append((data, path)))

    class DummyApp:
        def __init__(self, x, y):
            self.x, self.y = x, y

        def mainloop(self):
            pass

    monkeypatch.setattr(app, "TranslationApp", DummyApp)
    app.main()
    assert saved and saved[0][1] == config


def test_load_json_malformed(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not: valid json", encoding="utf-8")
    loaded = app.load_json(path)
    assert loaded == {}


def make_translation_app_with_tree(pl_data, en_data, full_key):
    ta = app.TranslationApp.__new__(app.TranslationApp)
    ta.pl_data = pl_data
    ta.en_data = en_data

    ta.insert_all = lambda: None

    class FakeTree:
        def __init__(self):
            self._selection = ["n1"]

        def selection(self):
            return self._selection

        def identify_row(self, y):
            return "n1"

        def set(self, row, col):
            return full_key

        def parent(self, row):
            return None

    ta.tree = FakeTree()
    return ta


def test_delete_selected_removes_key(monkeypatch):
    pl = {"foo": {"bar": "PL"}}
    en = {"foo": {"bar": "EN"}}
    full_key = "foo.bar"
    ta = make_translation_app_with_tree(pl, en, full_key)

    monkeypatch.setattr(messagebox, "askyesno", lambda title, msg: True)

    ta.delete_selected()

    assert ta.pl_data == {}
    assert ta.en_data == {}


def test_delete_selected_cancelled(monkeypatch):
    pl = {"x": {"y": "val"}}
    en = {"x": {"y": "val"}}
    full_key = "x.y"
    ta = make_translation_app_with_tree(pl.copy(), en.copy(), full_key)

    monkeypatch.setattr(messagebox, "askyesno", lambda title, msg: False)

    ta.delete_selected()

    assert ta.pl_data == {"x": {"y": "val"}}
    assert ta.en_data == {"x": {"y": "val"}}


def test_edit_selected_changes_key_and_translations(monkeypatch):
    pl = {"foo": {"bar": "PL_old"}}
    en = {"foo": {"bar": "EN_old"}}
    full_key = "foo.bar"

    ta = app.TranslationApp.__new__(app.TranslationApp)
    ta.pl_data = pl
    ta.en_data = en

    ta.insert_all = lambda: None

    class FakeTree:
        def selection(self):
            return ["n1"]

        def identify_row(self, y):
            return "n1"

        def set(self, row, col):
            return full_key

        def parent(self, row):
            return None

    ta.tree = FakeTree()

    fake_result = {"key": "alpha.beta", "pl": "PL_new", "auto": False, "en": "EN_new"}

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            self.result = fake_result

    monkeypatch.setattr(app, "AddDialog", FakeDialog)

    ta.edit_selected()

    assert "foo" not in ta.pl_data
    assert "foo" not in ta.en_data
    assert ta.pl_data["alpha"]["beta"] == "PL_new"
    assert ta.en_data["alpha"]["beta"] == "EN_new"
