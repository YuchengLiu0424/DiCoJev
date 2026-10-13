"""Capability boundaries for project agents and optional computer-use adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from .schemas import MultimodalState
from .workspace import ProjectWorkspace


class ComputerUseAdapter(Protocol):
    """Optional external desktop adapter; DiCoJev provides no unrestricted default."""

    @property
    def capabilities(self) -> tuple[str, ...]: ...

    def act(self, action: str, arguments: Mapping[str, Any]) -> Awaitable[dict[str, Any]]: ...


class ProjectAgentTools:
    """Allowlist-ready handlers confined to one selected project folder."""

    def __init__(self, workspace: ProjectWorkspace) -> None:
        self.workspace = workspace

    def handlers(self) -> dict[str, Callable[..., Any]]:
        return {
            "list_project_files": self.list_project_files,
            "read_project_file": self.read_project_file,
            "write_project_file": self.write_project_file,
        }

    def list_project_files(
        self, state: MultimodalState, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], MultimodalState]:
        limit = min(500, max(1, int(arguments.get("limit", 200))))
        return {"files": list(self.workspace.list_files(limit=limit))}, state

    def read_project_file(
        self, state: MultimodalState, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], MultimodalState]:
        relative_path = str(arguments.get("path", ""))
        if not relative_path:
            raise ValueError("read_project_file requires path")
        return {
            "path": relative_path,
            "content": self.workspace.read_text(relative_path),
        }, state

    def write_project_file(
        self, state: MultimodalState, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], MultimodalState]:
        relative_path = str(arguments.get("path", ""))
        content = arguments.get("content")
        if not relative_path or not isinstance(content, str):
            raise ValueError("write_project_file requires path and string content")
        self.workspace.write_text(relative_path, content)
        return {"path": relative_path, "bytes_written": len(content.encode("utf-8"))}, state
