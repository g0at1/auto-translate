import sys
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont


class Palette:
    BG = "#17181c"
    SURFACE = "#1f2127"
    SURFACE_ALT = "#272a31"
    SURFACE_HOVER = "#30343c"
    BORDER = "#33363e"
    TEXT = "#e8e9ed"
    MUTED = "#8b909c"
    ACCENT = "#5b8cff"
    ACCENT_HOVER = "#4a7af0"
    ACCENT_PRESSED = "#3d69d6"
    SELECTION = "#2b3f6b"
    DANGER = "#f0605a"
    WARNING = "#e3a63b"
    SUCCESS = "#4cc38a"


def _mono_family(root):
    families = set(tkfont.families(root))
    for name in ("SF Mono", "Menlo", "JetBrains Mono", "Consolas", "DejaVu Sans Mono"):
        if name in families:
            return name
    return "TkFixedFont"


def _make_fonts(root):
    base = tkfont.Font(root=root, name="TkDefaultFont", exists=True)
    family = base.actual("family")
    size = 13 if sys.platform == "darwin" else 10
    base.configure(size=size)
    tkfont.Font(root=root, name="TkTextFont", exists=True).configure(
        family=family, size=size
    )
    mono = _mono_family(root)
    return {
        "body": base,
        "bold": tkfont.Font(root=root, family=family, size=size, weight="bold"),
        "small": tkfont.Font(root=root, family=family, size=size - 2),
        "caption": tkfont.Font(root=root, family=family, size=size - 3, weight="bold"),
        "title": tkfont.Font(root=root, family=family, size=size + 5, weight="bold"),
        "hero": tkfont.Font(root=root, family=family, size=size + 11, weight="bold"),
        "mono": tkfont.Font(root=root, family=mono, size=size - 1),
    }


def apply_theme(root):
    """Apply the app's flat dark theme to ``root`` and return its fonts."""
    p = Palette
    fonts = _make_fonts(root)
    root.fonts = fonts
    root.configure(background=p.BG)

    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure(
        ".",
        background=p.BG,
        foreground=p.TEXT,
        fieldbackground=p.SURFACE,
        bordercolor=p.BORDER,
        lightcolor=p.BORDER,
        darkcolor=p.BORDER,
        troughcolor=p.BG,
        focuscolor=p.ACCENT,
        selectbackground=p.SELECTION,
        selectforeground=p.TEXT,
        insertcolor=p.TEXT,
        font=fonts["body"],
    )

    # Containers
    style.configure("TFrame", background=p.BG)
    style.configure("Card.TFrame", background=p.SURFACE)
    style.configure("Header.TFrame", background=p.SURFACE)
    style.configure("Status.TFrame", background=p.SURFACE)
    style.configure("TPanedwindow", background=p.BG)
    style.configure("Sash", sashthickness=6, gripcount=0, background=p.BG)

    # Labels
    style.configure("TLabel", background=p.BG, foreground=p.TEXT)
    style.configure("Muted.TLabel", foreground=p.MUTED)
    style.configure("Small.TLabel", foreground=p.MUTED, font=fonts["small"])
    style.configure("Caption.TLabel", foreground=p.MUTED, font=fonts["caption"])
    style.configure("Title.TLabel", font=fonts["title"])
    style.configure("Hero.TLabel", font=fonts["hero"])
    style.configure("Warning.TLabel", foreground=p.WARNING, font=fonts["small"])
    for prefix in ("Card", "Header", "Status"):
        style.configure(f"{prefix}.TLabel", background=p.SURFACE, foreground=p.TEXT)
        style.configure(
            f"{prefix}.Muted.TLabel", background=p.SURFACE, foreground=p.MUTED
        )
        style.configure(
            f"{prefix}.Small.TLabel",
            background=p.SURFACE,
            foreground=p.MUTED,
            font=fonts["small"],
        )
    style.configure(
        "Card.Caption.TLabel",
        background=p.SURFACE,
        foreground=p.MUTED,
        font=fonts["caption"],
    )
    style.configure("Card.Mono.TLabel", background=p.SURFACE, font=fonts["mono"])
    style.configure("Header.Title.TLabel", background=p.SURFACE, font=fonts["title"])
    style.configure(
        "Badge.TLabel",
        background=p.SURFACE_ALT,
        foreground=p.MUTED,
        font=fonts["small"],
        padding=(8, 2),
    )
    style.configure(
        "Placeholder.TLabel",
        background=p.SURFACE,
        foreground=p.MUTED,
    )
    style.configure("Hover.TFrame", background=p.SURFACE_HOVER)
    style.configure("Hover.TLabel", background=p.SURFACE_HOVER, foreground=p.TEXT)
    style.configure(
        "Hover.Small.TLabel",
        background=p.SURFACE_HOVER,
        foreground=p.MUTED,
        font=fonts["small"],
    )

    # Buttons
    button_opts = dict(
        padding=(14, 7),
        borderwidth=0,
        relief="flat",
        focusthickness=0,
        anchor="center",
    )
    style.configure(
        "TButton",
        background=p.SURFACE_ALT,
        foreground=p.TEXT,
        bordercolor=p.SURFACE_ALT,
        lightcolor=p.SURFACE_ALT,
        darkcolor=p.SURFACE_ALT,
        **button_opts,
    )
    style.map(
        "TButton",
        background=[
            ("disabled", p.SURFACE),
            ("pressed", p.BORDER),
            ("active", p.SURFACE_HOVER),
        ],
        foreground=[("disabled", p.MUTED)],
        bordercolor=[("focus", p.ACCENT)],
    )
    style.configure(
        "Accent.TButton",
        background=p.ACCENT,
        foreground="#ffffff",
        bordercolor=p.ACCENT,
        lightcolor=p.ACCENT,
        darkcolor=p.ACCENT,
        font=fonts["bold"],
        **button_opts,
    )
    style.map(
        "Accent.TButton",
        background=[
            ("disabled", p.SURFACE_ALT),
            ("pressed", p.ACCENT_PRESSED),
            ("active", p.ACCENT_HOVER),
        ],
        bordercolor=[("pressed", p.ACCENT_PRESSED), ("active", p.ACCENT_HOVER)],
        lightcolor=[("pressed", p.ACCENT_PRESSED), ("active", p.ACCENT_HOVER)],
        darkcolor=[("pressed", p.ACCENT_PRESSED), ("active", p.ACCENT_HOVER)],
    )
    style.configure(
        "Danger.TButton",
        background=p.SURFACE_ALT,
        foreground=p.DANGER,
        bordercolor=p.SURFACE_ALT,
        lightcolor=p.SURFACE_ALT,
        darkcolor=p.SURFACE_ALT,
        **button_opts,
    )
    style.map(
        "Danger.TButton",
        background=[("pressed", "#b8423d"), ("active", p.DANGER)],
        foreground=[("active", "#ffffff"), ("disabled", p.MUTED)],
    )
    for name, bg in (("Ghost.TButton", p.BG), ("Card.Ghost.TButton", p.SURFACE)):
        style.configure(
            name,
            background=bg,
            foreground=p.MUTED,
            bordercolor=bg,
            lightcolor=bg,
            darkcolor=bg,
            padding=(8, 4),
            borderwidth=0,
            relief="flat",
            font=fonts["small"],
        )
        style.map(
            name,
            background=[("active", p.SURFACE_HOVER)],
            foreground=[("active", p.TEXT)],
        )

    # Inputs
    entry_opts = dict(
        fieldbackground=p.SURFACE,
        foreground=p.TEXT,
        bordercolor=p.BORDER,
        lightcolor=p.SURFACE,
        darkcolor=p.SURFACE,
        insertcolor=p.TEXT,
        padding=(10, 7),
    )
    style.configure("TEntry", **entry_opts)
    style.map(
        "TEntry",
        bordercolor=[("focus", p.ACCENT)],
        lightcolor=[("focus", p.ACCENT)],
        fieldbackground=[("disabled", p.BG)],
        foreground=[("disabled", p.MUTED)],
    )
    style.configure(
        "Bare.TEntry",
        fieldbackground=p.SURFACE,
        bordercolor=p.SURFACE,
        lightcolor=p.SURFACE,
        darkcolor=p.SURFACE,
        padding=(4, 7),
    )
    style.map(
        "Bare.TEntry",
        bordercolor=[("focus", p.SURFACE)],
        lightcolor=[("focus", p.SURFACE)],
    )
    style.configure(
        "TCombobox",
        arrowcolor=p.MUTED,
        background=p.SURFACE_ALT,
        **entry_opts,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", p.SURFACE)],
        foreground=[("readonly", p.TEXT)],
        selectbackground=[("readonly", p.SURFACE)],
        selectforeground=[("readonly", p.TEXT)],
        bordercolor=[("focus", p.ACCENT)],
        background=[("active", p.SURFACE_HOVER)],
        arrowcolor=[("active", p.TEXT)],
    )
    root.option_add("*TCombobox*Listbox.background", p.SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", p.TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", p.SELECTION)
    root.option_add("*TCombobox*Listbox.selectForeground", p.TEXT)
    root.option_add("*TCombobox*Listbox.font", fonts["body"])

    style.configure(
        "TCheckbutton",
        background=p.BG,
        foreground=p.TEXT,
        indicatorbackground=p.SURFACE,
        indicatorforeground="#ffffff",
        upperbordercolor=p.BORDER,
        lowerbordercolor=p.BORDER,
        indicatormargin=(0, 0, 8, 0),
        padding=(0, 4),
    )
    style.map(
        "TCheckbutton",
        background=[("active", p.BG)],
        indicatorbackground=[("selected", p.ACCENT), ("active", p.SURFACE_HOVER)],
        upperbordercolor=[("selected", p.ACCENT)],
        lowerbordercolor=[("selected", p.ACCENT)],
    )

    # Tree
    style.configure(
        "Treeview",
        background=p.SURFACE,
        fieldbackground=p.SURFACE,
        foreground=p.TEXT,
        bordercolor=p.SURFACE,
        lightcolor=p.SURFACE,
        darkcolor=p.SURFACE,
        borderwidth=0,
        rowheight=int(fonts["body"].metrics("linespace") * 2.1),
        indent=18,
    )
    style.map(
        "Treeview",
        background=[("selected", p.SELECTION)],
        foreground=[("selected", "#ffffff")],
    )
    style.configure(
        "Treeview.Heading",
        background=p.SURFACE,
        foreground=p.MUTED,
        bordercolor=p.BORDER,
        lightcolor=p.SURFACE,
        darkcolor=p.BORDER,
        relief="flat",
        padding=(10, 8),
        font=fonts["caption"],
    )
    style.map("Treeview.Heading", background=[("active", p.SURFACE_ALT)])
    style.configure("Treeitem.indicator", foreground=p.MUTED)
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # Slim, arrow-less scrollbars
    for orient, sticky in (("Vertical", "ns"), ("Horizontal", "ew")):
        style.layout(
            f"{orient}.TScrollbar",
            [
                (
                    f"{orient}.Scrollbar.trough",
                    {
                        "sticky": sticky,
                        "children": [
                            (
                                f"{orient}.Scrollbar.thumb",
                                {"expand": "1", "sticky": "nswe"},
                            )
                        ],
                    },
                )
            ],
        )
        style.configure(
            f"{orient}.TScrollbar",
            troughcolor=p.SURFACE,
            background=p.BORDER,
            bordercolor=p.SURFACE,
            lightcolor=p.BORDER,
            darkcolor=p.BORDER,
            gripcount=0,
            arrowsize=10,
            width=10,
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", p.MUTED)],
            lightcolor=[("active", p.MUTED)],
            darkcolor=[("active", p.MUTED)],
        )

    style.configure("TSeparator", background=p.BORDER)

    # Classic tk widgets (menus, text)
    root.option_add("*Menu.background", p.SURFACE_ALT)
    root.option_add("*Menu.foreground", p.TEXT)
    root.option_add("*Menu.activeBackground", p.ACCENT)
    root.option_add("*Menu.activeForeground", "#ffffff")
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.borderWidth", 0)
    return fonts


def style_toplevel(window):
    """Give a Toplevel (and simpledialog body frames) the theme background."""
    window.configure(background=Palette.BG)


def text_widget_options(root):
    p = Palette
    fonts = getattr(root, "fonts", None) or {}
    return dict(
        background=p.SURFACE,
        foreground=p.TEXT,
        insertbackground=p.TEXT,
        selectbackground=p.SELECTION,
        selectforeground=p.TEXT,
        highlightthickness=1,
        highlightbackground=p.BORDER,
        highlightcolor=p.ACCENT,
        relief="flat",
        borderwidth=0,
        padx=12,
        pady=10,
        font=fonts.get("mono", "TkFixedFont"),
    )
