"""Explicitly scoped project folders for future agent capabilities."""

from __future__ import annotations

from pathlib import Path


class ProjectWorkspace:
    """Confine file access to one user-selected project root."""

    def __init__(self, root: str | Path, *, allow_write: bool = False) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Project root must be a directory.")
        self.allow_write = allow_write

    def resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Path escapes the selected project root.")
        return candidate

    def list_files(self, *, limit: int = 500) -> tuple[str, ...]:
        values = []
        for path in self.root.rglob("*"):
            if path.is_file():
                values.append(path.relative_to(self.root).as_posix())
                if len(values) >= limit:
                    break
        return tuple(values)

    def read_text(self, relative_path: str | Path, *, max_chars: int = 200_000) -> str:
        path = self.resolve(relative_path)
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]

    def write_text(self, relative_path: str | Path, content: str) -> None:
        if not self.allow_write:
            raise PermissionError("Project write access was not granted.")
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
