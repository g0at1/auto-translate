import json
from types import SimpleNamespace

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
    assert ta.has_unsaved_changes()
    notified = []
    monkeypatch.setattr(ta, "notify", lambda msg, kind="success": notified.append(msg))
    assert ta.save() is True
    assert json.loads(pl.read_text())["foo"] == "bar"
    assert json.loads(en.read_text())["baz"] == "qux"
    assert "Updated" in notified[-1]
    assert not ta.has_unsaved_changes()


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


class DummyMainApp:
    instances = []

    def __init__(self, pl_path, en_path, **kwargs):
        self.pl_path, self.en_path = pl_path, en_path
        self.project = kwargs.get("project")
        DummyMainApp.instances.append(self)

    def mainloop(self):
        pass


@pytest.fixture
def main_env(monkeypatch, tmp_path):
    config = tmp_path / ".translation_app_config.json"
    monkeypatch.setattr(app, "CONFIG_PATH", config)
    DummyMainApp.instances = []
    monkeypatch.setattr(app, "TranslationApp", DummyMainApp)
    pl = tmp_path / "i18n" / "pl.json"
    en = tmp_path / "i18n" / "en.json"
    pl.parent.mkdir()
    pl.write_text(json.dumps({}))
    en.write_text(json.dumps({}))
    return SimpleNamespace(config=config, pl=pl, en=en, tmp=tmp_path)


def test_main_uses_project_chosen_on_welcome_screen(monkeypatch, main_env):
    project = app.save_project(
        main_env.tmp / "translations.project.json", main_env.pl, main_env.en
    )
    monkeypatch.setattr(app, "run_welcome", lambda recent: project)
    app.main()
    started = DummyMainApp.instances[-1]
    assert started.pl_path == str(main_env.pl.resolve())
    assert started.en_path == str(main_env.en.resolve())
    saved = json.loads(main_env.config.read_text(encoding="utf-8"))
    assert saved["project_file"] == project.path
    assert saved["recent_projects"] == [project.path]


def test_main_reopens_last_project_without_asking(monkeypatch, main_env):
    project = app.save_project(
        main_env.tmp / "translations.project.json", main_env.pl, main_env.en
    )
    app.save_json({"project_file": project.path}, main_env.config)
    monkeypatch.setattr(
        app, "run_welcome", lambda recent: pytest.fail("should not ask")
    )
    app.main()
    assert DummyMainApp.instances[-1].project.path == project.path


def test_main_falls_back_to_legacy_file_pair(monkeypatch, main_env):
    app.save_json(
        {"pl_file": str(main_env.pl), "en_file": str(main_env.en)}, main_env.config
    )
    monkeypatch.setattr(
        app, "run_welcome", lambda recent: pytest.fail("should not ask")
    )
    app.main()
    assert DummyMainApp.instances[-1].pl_path == str(main_env.pl)


def test_main_exits_when_welcome_cancelled(monkeypatch, main_env):
    monkeypatch.setattr(app, "run_welcome", lambda recent: None)
    app.main()
    assert DummyMainApp.instances == []


def test_main_shows_welcome_when_last_project_is_broken(monkeypatch, main_env):
    app.save_json(
        {
            "project_file": str(main_env.tmp / "gone.project.json"),
            "pl_file": str(main_env.pl),
            "en_file": str(main_env.en),
        },
        main_env.config,
    )
    asked = []
    monkeypatch.setattr(app, "run_welcome", lambda recent: asked.append(1))
    app.main()
    assert asked


# -----------------------------
# Project files
# -----------------------------
def test_project_roundtrip_stores_relative_paths(tmp_path):
    from utils.project import load_project, save_project

    files = tmp_path / "src" / "i18n"
    files.mkdir(parents=True)
    (files / "pl.json").write_text("{}")
    (files / "en.json").write_text("{}")
    project_path = tmp_path / "app.project.json"

    save_project(project_path, files / "pl.json", files / "en.json", name="My app")
    stored = json.loads(project_path.read_text(encoding="utf-8"))
    assert stored == {
        "name": "My app",
        "files": {"pl": "src/i18n/pl.json", "en": "src/i18n/en.json"},
    }

    project = load_project(project_path)
    assert project.pl_path == str((files / "pl.json").resolve())
    assert project.en_path == str((files / "en.json").resolve())
    assert project.display_name == "My app"


def test_project_display_name_from_filename(tmp_path):
    from utils.project import TranslationProject

    p = TranslationProject(
        "a/pl.json", "a/en.json", path=str(tmp_path / "shop.project.json")
    )
    assert p.display_name == "shop"
    assert (
        TranslationProject("a/pl.json", "a/en.json").display_name == "pl.json & en.json"
    )


@pytest.mark.parametrize(
    "content, message",
    [
        ("{oops", "not valid JSON"),
        (json.dumps({"files": {"pl": "pl.json"}}), '"files"'),
        (
            json.dumps({"files": {"pl": "pl.json", "en": "missing.json"}}),
            "do not exist",
        ),
    ],
)
def test_load_project_errors(tmp_path, content, message):
    from utils.project import ProjectError, load_project

    (tmp_path / "pl.json").write_text("{}")
    project_path = tmp_path / "x.project.json"
    project_path.write_text(content, encoding="utf-8")
    with pytest.raises(ProjectError, match=message):
        load_project(project_path)


def test_change_files_updates_open_project(tmp_path, monkeypatch):
    for name in ("pl", "en", "pl2", "en2"):
        (tmp_path / f"{name}.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app, "CONFIG_PATH", tmp_path / "config.json")
    project = app.save_project(
        tmp_path / "t.project.json", tmp_path / "pl.json", tmp_path / "en.json"
    )
    ta = app.TranslationApp(project.pl_path, project.en_path, project=project)
    seq = [str(tmp_path / "pl2.json"), str(tmp_path / "en2.json")]
    monkeypatch.setattr(filedialog, "askopenfilename", lambda **k: seq.pop(0))
    ta.change_files()
    stored = json.loads((tmp_path / "t.project.json").read_text(encoding="utf-8"))
    assert stored["files"] == {"pl": "pl2.json", "en": "en2.json"}
    ta.destroy()


def test_tree_shows_pl_and_en_columns(tmp_path, monkeypatch):
    pl = tmp_path / "pl.json"
    en = tmp_path / "en.json"
    pl.write_text(json.dumps({"a": {"b": "Cześć", "c": "Pa"}}), encoding="utf-8")
    en.write_text(json.dumps({"a": {"b": "Hi"}}), encoding="utf-8")
    monkeypatch.setattr(app, "CONFIG_PATH", tmp_path / "config.json")
    ta = app.TranslationApp(str(pl), str(en))
    (group,) = ta.tree.get_children("")
    rows = {ta.tree.set(i, "full_key"): i for i in ta.tree.get_children(group)}
    assert ta.tree.set(rows["a.b"], "pl") == "Cześć"
    assert ta.tree.set(rows["a.b"], "en") == "Hi"
    assert "missing" in ta.tree.item(rows["a.c"], "tags")
    assert ta.count_missing_en() == 1

    ta.search_var.set("hi")
    (group,) = ta.tree.get_children("")
    assert [ta.tree.set(i, "full_key") for i in ta.tree.get_children(group)] == ["a.b"]
    ta.destroy()


def test_load_json_malformed(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not: valid json", encoding="utf-8")
    loaded = app.load_json(path)
    assert loaded == {}


def make_translation_app_with_tree(pl_data, en_data, full_key):
    ta = app.TranslationApp.__new__(app.TranslationApp)
    ta.pl_data = pl_data
    ta.en_data = en_data
    ta.undo_stack = []
    ta.redo_stack = []

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
    ta.update_title = lambda: None

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
    ta.redo_stack = []
    ta.undo_stack = []

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


# -----------------------------
# Tests for preserving & restoring expanded nodes in the Treeview
# -----------------------------
class FakeTree:
    def __init__(self, structure, open_keys):
        self.structure = structure
        self._open = {node: (node in open_keys) for node in structure}
        self._full_key = {node: node for node in structure}

    def get_children(self, item=""):
        return self.structure.get(item, [])

    def item(self, item, option=None, **kwargs):
        if "open" in kwargs:
            self._open[item] = kwargs["open"]
        if option == "open":
            return self._open[item]
        return None

    def set(self, item, column):
        if column == "full_key":
            return self._full_key[item]
        return None


class DummyApp(app.TranslationApp):
    def __init__(self):
        pass


def test_get_expanded_keys_simple():
    structure = {"": ["A", "B"], "A": ["A1"], "A1": [], "B": ["B1"], "B1": []}
    open_keys = {"A", "B1"}
    fake = FakeTree(structure, open_keys)
    ta = DummyApp()
    ta.tree = fake

    got = app.TranslationApp.get_expanded_keys(ta)
    assert got == open_keys


def test_restore_expanded_keys_simple():
    structure = {"": ["X", "Y"], "X": [], "Y": []}
    fake = FakeTree(structure, {"X"})
    ta = DummyApp()
    ta.tree = fake

    for node in ["X", "Y"]:
        fake._open[node] = False

    app.TranslationApp.restore_expanded_keys(ta, {"X"})

    assert fake._open["X"] is True
    assert fake._open["Y"] is False


def test_roundtrip_expand_and_restore():
    structure = {"": ["N1", "N2"], "N1": ["N1a", "N1b"], "N1a": [], "N1b": [], "N2": []}
    initial_open = {"N1", "N1b"}
    fake = FakeTree(structure, initial_open)
    ta = DummyApp()
    ta.tree = fake

    saved = app.TranslationApp.get_expanded_keys(ta)
    assert saved == initial_open

    for n in initial_open:
        fake._open[n] = False

    app.TranslationApp.restore_expanded_keys(ta, saved)

    for n in ["N1", "N1b"]:
        assert fake._open[n] is True
    assert fake._open["N2"] is False


# -----------------------------
# Tests for AddDialog.validate()
# -----------------------------
import pytest
from tkinter import Tk
from tkinter import messagebox
import main as app


class FakeEntry:
    def __init__(self, text):
        self._text = text

    def get(self):
        return self._text

    def delete(self, a=None, b=None):
        pass

    def config(self, **kwargs):
        pass


@pytest.fixture(autouse=True)
def suppress_tk(monkeypatch):
    monkeypatch.setattr(
        app.simpledialog.Dialog, "__init__", lambda *args, **kwargs: None
    )
    yield


@pytest.fixture
def dlg(monkeypatch):
    root = Tk()
    dlg = app.AddDialog.__new__(app.AddDialog)
    dlg.key_entry = FakeEntry("")
    dlg.pl_entry = FakeEntry("")
    dlg.en_entry = FakeEntry("")
    dlg.auto_var = app.tk.BooleanVar(root, False)
    return dlg


def test_validate_empty_key_and_pl(monkeypatch, dlg):
    calls = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda title, msg: calls.append((title, msg))
    )
    dlg.key_entry = FakeEntry("")  # empty key
    dlg.pl_entry = FakeEntry("")  # empty pl
    assert dlg.validate() is False
    assert calls[-1][1] in ("Polish text is required", "Key is required")


def test_validate_empty_key(monkeypatch, dlg):
    calls = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda title, msg: calls.append((title, msg))
    )
    dlg.key_entry = FakeEntry("")  # empty key
    dlg.pl_entry = FakeEntry("tekst")
    assert dlg.validate() is False
    assert calls[-1] == ("Error", "Key is required")


def test_validate_empty_pl(monkeypatch, dlg):
    calls = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda title, msg: calls.append((title, msg))
    )
    dlg.key_entry = FakeEntry("foo")
    dlg.pl_entry = FakeEntry("")  # empty pl
    assert dlg.validate() is False
    assert calls[-1] == ("Error", "Polish text is required")


def test_validate_key_endswith_dot(monkeypatch, dlg):
    calls = []
    monkeypatch.setattr(
        messagebox, "showerror", lambda title, msg: calls.append((title, msg))
    )
    dlg.key_entry = FakeEntry("foo.bar.")
    dlg.pl_entry = FakeEntry("tekst")
    assert dlg.validate() is False
    assert calls[-1] == ("Error", "Invalid key foo.bar.")


def test_validate_success(monkeypatch, dlg):
    monkeypatch.setattr(
        messagebox, "showerror", lambda title, msg: pytest.skip("should not be called")
    )
    dlg.key_entry = FakeEntry("valid.key")
    dlg.pl_entry = FakeEntry("tekst")
    dlg.parent = SimpleNamespace(key_exists=lambda key: False)
    dlg.original_key = FakeEntry("valid.key")
    assert dlg.validate() is True


# -----------------------------
# Tests for copy functions
# -----------------------------


def make_app_for_copy():
    """
    Helper to create a TranslationApp instance with clipboard methods patched
    and sample data for testing copy_key, copy_pl, and copy_en.
    """
    ta = app.TranslationApp.__new__(app.TranslationApp)
    calls = []

    def clear():
        calls.append("clear")

    def append(val):
        calls.append(val)

    ta.clipboard_clear = clear
    ta.clipboard_append = append
    ta._menu_parts = ["foo", "bar"]
    ta.pl_data = {"foo": {"bar": "PL_val"}}
    ta.en_data = {"foo": {"bar": "EN_val"}}
    return ta, calls


def test_copy_key():
    ta, calls = make_app_for_copy()
    ta.copy_key()
    assert calls == ["clear", "foo.bar"]


def test_copy_pl():
    ta, calls = make_app_for_copy()
    ta.copy_pl()
    assert calls == ["clear", "PL_val"]


def test_copy_en():
    ta, calls = make_app_for_copy()
    ta.copy_en()
    assert calls == ["clear", "EN_val"]


def test_copy_pl_no_value():
    ta, calls = make_app_for_copy()
    # Simulate no Polish translation
    ta.pl_data = {"foo": {"bar": ""}}
    calls.clear()
    ta.copy_pl()
    assert calls == []


def test_copy_en_no_value():
    ta, calls = make_app_for_copy()
    # Simulate no English translation
    ta.en_data = {"foo": {"bar": ""}}
    calls.clear()
    ta.copy_en()
    assert calls == []
