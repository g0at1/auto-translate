import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROJECT_FILE_SUFFIX = ".project.json"
DEFAULT_PROJECT_FILENAME = "translations" + PROJECT_FILE_SUFFIX


class ProjectError(Exception):
    """Raised when a project file cannot be read or points to missing files."""


@dataclass
class TranslationProject:
    pl_path: str
    en_path: str
    path: Optional[str] = None
    name: Optional[str] = None

    @property
    def display_name(self) -> str:
        if self.name:
            return self.name
        if self.path:
            filename = Path(self.path).name
            if filename.endswith(PROJECT_FILE_SUFFIX):
                return filename[: -len(PROJECT_FILE_SUFFIX)]
            return Path(self.path).stem
        return f"{Path(self.pl_path).name} & {Path(self.en_path).name}"


def _to_stored_path(target, project_dir: Path) -> str:
    """Store paths relative to the project file so it can live in a repo."""
    target = Path(target).resolve()
    try:
        return Path(os.path.relpath(target, project_dir.resolve())).as_posix()
    except ValueError:  # different drive on Windows
        return str(target)


def _resolve(stored: str, project_dir: Path) -> str:
    p = Path(stored).expanduser()
    if not p.is_absolute():
        p = project_dir / p
    return str(p.resolve())


def load_project(path) -> TranslationProject:
    path = Path(path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ProjectError(f"Project file not found:\n{path}")
    except (OSError, UnicodeDecodeError) as e:
        raise ProjectError(f"Cannot read project file {path}:\n{e}")
    except json.JSONDecodeError as e:
        raise ProjectError(f"Project file {path} is not valid JSON:\n{e}")

    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict) or not files.get("pl") or not files.get("en"):
        raise ProjectError(
            f'Project file {path} must contain "files": {{"pl": ..., "en": ...}}'
        )

    project_dir = path.resolve().parent
    pl_path = _resolve(files["pl"], project_dir)
    en_path = _resolve(files["en"], project_dir)
    missing = [p for p in (pl_path, en_path) if not Path(p).is_file()]
    if missing:
        raise ProjectError(
            "Translation file(s) referenced by the project do not exist:\n"
            + "\n".join(missing)
        )

    return TranslationProject(
        pl_path=pl_path,
        en_path=en_path,
        path=str(path.resolve()),
        name=data.get("name") or None,
    )


def save_project(path, pl_path, en_path, name=None) -> TranslationProject:
    path = Path(path).expanduser()
    project_dir = path.resolve().parent
    data = {}
    if name:
        data["name"] = name
    data["files"] = {
        "pl": _to_stored_path(pl_path, project_dir),
        "en": _to_stored_path(en_path, project_dir),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return TranslationProject(
        pl_path=str(Path(pl_path).resolve()),
        en_path=str(Path(en_path).resolve()),
        path=str(path.resolve()),
        name=name or None,
    )
