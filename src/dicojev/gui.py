"""Small native desktop interface for the direct DiCoJev runtime."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from .cli import PACKAGED_DEFAULT_CONFIG
from .config import load_config
from .direct import DirectClient
from .intent import IntentDraft
from .memory import LocalMemoryStore
from .model_discovery import (
    ADAPTER_STANDARDS,
    discover_local_model,
    validate_cloud_model,
    validate_model_standard,
)
from .multimedia import IMAGE_SUFFIXES, VIDEO_SUFFIXES, LocalMediaIngestor, LocalVisionBridge
from .routing import DirectAnswer
from .schemas import DecisionRequest, DecisionResponse, ImageRef, MultimodalState
from .secrets import SecretStore
from .workspace import ProjectWorkspace

NO_PROJECT_ID = "__no_project__"

COLORS = {
    "window": "#0d1113",
    "panel": "#151b1e",
    "panel_alt": "#1b2327",
    "field": "#222b30",
    "border": "#303b40",
    "text": "#edf2f0",
    "muted": "#93a09e",
    "accent": "#d9a441",
    "accent_hover": "#efb64a",
    "good": "#68b486",
    "warn": "#d9a441",
    "danger": "#d66b62",
    "info": "#6e9fc1",
}


class RoundedNavList:
    """Compact canvas-backed navigation rows with rounded selection surfaces."""

    def __init__(self, tk, parent, *, on_select, on_context, height: int) -> None:
        self.tk = tk
        self.on_select = on_select
        self.on_context = on_context
        self.items: list[tuple[str, str]] = []
        self.selected_id: str | None = None
        self.canvas = tk.Canvas(
            parent,
            height=height,
            bg=COLORS["panel"],
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Button-3>", self._context)
        self.canvas.bind(
            "<MouseWheel>", lambda event: self.canvas.yview_scroll(-int(event.delta / 120), "units")
        )

    def pack(self, **kwargs) -> None:
        self.canvas.pack(**kwargs)

    def set_items(self, items, *, selected_id: str | None = None) -> None:
        self.items = [
            (item.id, item.name if hasattr(item, "name") else item.title) for item in items
        ]
        self.selected_id = selected_id
        self._draw()

    def _item_at(self, y: int) -> str | None:
        index = (y - 5) // 46
        if index < 0 or index >= len(self.items) or (y - 5) % 46 >= 38:
            return None
        return self.items[index][0]

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs) -> None:
        points = (
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        )
        self.canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(80, self.canvas.winfo_width())
        for index, (item_id, label) in enumerate(self.items):
            top = 5 + index * 46
            selected = item_id == self.selected_id
            self._rounded_rect(
                4,
                top,
                width - 4,
                top + 38,
                10,
                fill=COLORS["field"] if selected else COLORS["panel_alt"],
                outline=COLORS["accent"] if selected else COLORS["border"],
                width=1,
            )
            self.canvas.create_text(
                17,
                top + 19,
                anchor="w",
                text=label,
                fill=COLORS["text"],
                font=("Segoe UI Semibold" if selected else "Segoe UI", 10),
            )
        requested = max(48, 10 + len(self.items) * 46)
        self.canvas.configure(scrollregion=(0, 0, width, requested))

    def _click(self, event) -> None:
        item_id = self._item_at(int(self.canvas.canvasy(event.y)))
        if item_id:
            self.selected_id = item_id
            self._draw()
            self.on_select(item_id)

    def _context(self, event) -> None:
        item_id = self._item_at(int(self.canvas.canvasy(event.y)))
        if item_id:
            self.on_context(item_id, event.x_root, event.y_root)


def enable_high_dpi() -> str:
    """Enable the sharpest Windows DPI mode available before creating a Tk root."""
    if sys.platform != "win32":
        return "platform_default"
    import ctypes

    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per_monitor_v2"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per_monitor"
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"


@dataclass(frozen=True)
class DecisionPresentation:
    action: str
    action_color: str
    selected: str
    coverage: str
    confidence: str
    feedback: str
    candidates: str
    trace: str
    raw_json: str


def split_items(value: str) -> tuple[str, ...]:
    return tuple(
        item
        for line in value.splitlines()
        for item in (part.strip() for part in line.split(","))
        if item
    )


def build_request(
    *,
    context: str,
    goal: str,
    tools: str = "",
    constraints: str = "",
    structured_json: str = "",
    image_path: str = "",
) -> DecisionRequest:
    structured: dict[str, Any] = {}
    if structured_json.strip():
        value = json.loads(structured_json)
        if not isinstance(value, dict):
            raise ValueError("Structured state must be a JSON object.")
        structured = value
    images = ()
    if image_path.strip():
        path = Path(image_path).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Image does not exist: {path}")
        images = (ImageRef(uri=str(path)),)
    return DecisionRequest(
        state=MultimodalState(text=context.strip(), images=images, structured=structured),
        goal=goal.strip(),
        available_tools=split_items(tools),
        constraints=split_items(constraints),
    )


def present_response(response: DecisionResponse) -> DecisionPresentation:
    coverage_score = response.backend_result.coverage
    selection = response.backend_result.selection
    coverage = "—"
    if coverage_score is not None:
        value = coverage_score.calibrated
        coverage = f"{value if value is not None else coverage_score.raw:.1%}"
    confidence = "—"
    if selection is not None:
        value = selection.confidence_calibrated
        raw_value = value if value is not None else selection.confidence_raw
        if raw_value is not None:
            confidence = f"{raw_value:.1%}"
    selected = (
        response.selected_candidate.action if response.selected_candidate else "No action selected"
    )
    reason_code = response.controller.reason_code
    component_failure = reason_code.startswith("component_failure:")
    action = "UNAVAILABLE" if component_failure else response.action.value
    if component_failure:
        error_type = response.backend_result.diagnostics.get("error_type", "model service")
        selected = f"{error_type}: the configured model service could not complete this request"
    candidates = "\n".join(
        f"{candidate.id or '?'}  {candidate.action}"
        + (f"  ·  {candidate.tool}" if candidate.tool else "")
        for candidate in response.candidates
    )
    trace = "\n".join(
        f"Round {event.round_index + 1}  ·  {event.controller_action.value}  ·  "
        f"{event.controller_reason_code}"
        for event in response.trace
    )
    colors = {
        "ACT": COLORS["good"],
        "EXPAND": COLORS["info"],
        "ABSTAIN": COLORS["warn"],
        "ESCALATE": COLORS["danger"],
        "UNAVAILABLE": COLORS["danger"],
    }
    return DecisionPresentation(
        action=action,
        action_color=colors[action],
        selected=selected,
        coverage=coverage,
        confidence=confidence,
        feedback=(
            f"SERVICE · {response.backend_result.diagnostics.get('error_type', 'UNAVAILABLE')}"
            if component_failure
            else response.feedback.primary.code.value
        ),
        candidates=candidates or "No candidates",
        trace=trace or "No trace",
        raw_json=json.dumps(response.model_dump(mode="json"), indent=2),
    )


class DiCoJevDesktop:
    """Native Tk interface that calls :class:`DirectClient` in-process."""

    def __init__(
        self,
        client: DirectClient,
        *,
        account: str = "default",
        data_dir: str | Path | None = None,
        memory: LocalMemoryStore | None = None,
        secret_store: SecretStore | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.dpi_mode = enable_high_dpi()
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.client = client
        self.base_config = copy.deepcopy(config or load_config(PACKAGED_DEFAULT_CONFIG))
        self.account = account.strip() or "default"
        self.memory = memory or LocalMemoryStore(data_dir)
        self.secret_store = secret_store or SecretStore(self.memory.data_dir)
        self.memory.ensure_account(self.account)
        projects = self.memory.list_projects(self.account)
        self.project_id: str | None = projects[0].id if projects else None
        chats = self._chats_in_active_container()
        if not chats and self.project_id is not None:
            unassigned = self.memory.list_unassigned_chats(self.account)
            if unassigned:
                self.project_id = None
                chats = unassigned
        created_chat = not chats
        self.chat_id = (
            chats[0].id
            if chats
            else self.memory.create_chat(self.account, project_id=self.project_id)
        )
        self._ensure_chat_model_defaults(self.chat_id, prefer_executable=created_chat)
        self._activate_chat_models(self.chat_id)
        self.ingestor = LocalMediaIngestor()
        self.vision_bridge = LocalVisionBridge()
        self.attachment_paths: list[str] = []
        self._scroll_regions: list[tuple[Any, Any]] = []
        self._placeholder_active: set[Any] = set()
        self._placeholder_text: dict[Any, str] = {}
        self.raw_json = ""
        self.root = tk.Tk()
        self.root.title("DiCoJev — Decision Studio")
        dpi = self.root.winfo_fpixels("1i")
        self.root.tk.call("tk", "scaling", dpi / 72.0)
        self.root.geometry("1280x860")
        self.root.minsize(1080, 720)
        self.root.configure(bg=COLORS["window"])
        self._set_window_icon()
        self._configure_styles()
        self._build()
        self.root.bind_all("<Button-1>", self._release_text_focus, add="+")
        self.root.bind_all("<MouseWheel>", self._route_mousewheel, add="+")

    def _ensure_chat_model_defaults(self, chat_id: str, *, prefer_executable: bool = False) -> None:
        selection = self.memory.get_chat_models(chat_id)
        language = self.memory.list_models(self.account, "language")
        decision = self.memory.list_models(self.account, "decision")
        mercury = next((item for item in language if item.adapter == "mercury"), None)
        jev = next((item for item in decision if item.adapter == "jev_cloud"), None)
        cloud_ready = (
            mercury is not None
            and jev is not None
            and self.secret_store.has(f"api_key:{mercury.id}")
            and self.secret_store.has(f"api_key:{jev.id}")
        )
        if prefer_executable and cloud_ready:
            self.memory.set_chat_models(chat_id, mercury.id, jev.id)
            return
        language_id = selection.language_model_id or next(
            (item.id for item in language if item.name == "LLaDA Local"),
            language[0].id if language else None,
        )
        decision_id = selection.decision_model_id or next(
            (item.id for item in decision if item.adapter == "native_dlm"),
            decision[0].id if decision else None,
        )
        self.memory.set_chat_models(chat_id, language_id, decision_id)

    def _activate_chat_models(self, chat_id: str) -> None:
        selection = self.memory.get_chat_models(chat_id)
        models = {item.id: item for item in self.memory.list_models(self.account)}
        language = models.get(selection.language_model_id)
        decision = models.get(selection.decision_model_id)
        if language is None or decision is None:
            return
        generator_models = {
            "diffusiongemma": "dicojev-diffusiongemma",
            "llada": "llada-v-local",
            "mercury": "mercury-2.5",
        }
        decision_models = {
            "native_dlm": "llada-v-local",
            "laya_local": "english",
            "djev_local": "dgemma",
            "jev_cloud": "jev-latest",
        }
        config = copy.deepcopy(self.base_config)
        config["model"] = {
            "generator_kind": language.adapter,
            "generator_model": language.model_identifier
            or generator_models.get(language.adapter, language.name),
            "deployment": "separate_models",
            "base_url": language.location,
            "timeout_seconds": 600,
        }
        config["decision_backend"] = {
            "kind": decision.adapter,
            "model": decision.model_identifier
            or decision_models.get(decision.adapter, decision.name),
            "base_url": decision.location,
            "timeout_seconds": 600,
        }
        if decision.adapter == "native_dlm":
            config["decision_backend"]["runtime_kind"] = "llada_http"
        bridge = next((item for item in models.values() if item.name == "Qwen2 Local"), None)
        if language.adapter == "llada" and bridge is not None:
            config["intent"] = {
                "base_url": bridge.location,
                "model": bridge.model_identifier or "qwen2:7b",
                "timeout_seconds": 180,
            }
        else:
            config["intent"] = {
                "base_url": language.location,
                "model": language.model_identifier
                or generator_models.get(language.adapter, language.name),
                "timeout_seconds": 600,
            }
        language_key = self.secret_store.get(f"api_key:{language.id}")
        decision_key = self.secret_store.get(f"api_key:{decision.id}")
        self.client = DirectClient.from_config(
            config,
            generator_api_key=language_key,
            decision_api_key=decision_key,
            use_environment=False,
        )
        self.language_model = language
        self.decision_model = decision

    def _set_window_icon(self) -> None:
        self._icon_images = [self._make_icon(size) for size in (16, 32, 64)]
        self.root.iconphoto(True, *self._icon_images)

    def _make_icon(self, size: int):
        image = self.tk.PhotoImage(width=size, height=size)
        scale = size / 64

        def point(x: float, y: float, color: str, radius: float = 1.5) -> None:
            cx, cy, r = round(x * scale), round(y * scale), max(1, round(radius * scale))
            for px in range(max(0, cx - r), min(size, cx + r + 1)):
                for py in range(max(0, cy - r), min(size, cy + r + 1)):
                    if (px - cx) ** 2 + (py - cy) ** 2 <= r**2:
                        image.put(color, (px, py))

        def line(a: tuple[float, float], b: tuple[float, float], color: str) -> None:
            steps = max(abs(round((b[0] - a[0]) * scale)), abs(round((b[1] - a[1]) * scale)), 1)
            for index in range(steps + 1):
                ratio = index / steps
                point(
                    a[0] + (b[0] - a[0]) * ratio,
                    a[1] + (b[1] - a[1]) * ratio,
                    color,
                    1.0,
                )

        for particle in ((8, 13, 2.3), (5, 31, 1.6), (11, 50, 2.0), (20, 8, 1.3)):
            point(*particle[:2], COLORS["info"], particle[2])
        for start in ((10, 13), (7, 31), (13, 50), (21, 9)):
            line(start, (29, 32), COLORS["border"])
        diamond = ((39, 15), (56, 32), (39, 49), (22, 32), (39, 15))
        for first, second in pairwise(diamond):
            line(first, second, COLORS["accent"])
        line((31, 32), (47, 32), COLORS["accent"])
        line((39, 24), (39, 40), COLORS["accent"])
        point(39, 32, COLORS["text"], 2.0)
        return image

    def _configure_styles(self) -> None:
        style = self.ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["window"])
        for name in ("TNotebook", "TNotebook.Tab", "TRadiobutton", "Treeview.Heading"):
            style.configure(name, background=COLORS["window"], foreground=COLORS["text"])
            style.map(
                name,
                background=[("selected", COLORS["panel_alt"]), ("active", COLORS["panel_alt"])],
            )
        for name in ("TEntry", "TCombobox", "Treeview"):
            style.configure(
                name,
                fieldbackground=COLORS["field"],
                background=COLORS["field"],
                foreground=COLORS["text"],
                insertcolor=COLORS["text"],
            )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["field"])],
            foreground=[("readonly", COLORS["text"])],
        )
        self.root.option_add("*TCombobox*Listbox.background", COLORS["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Alt.TFrame", background=COLORS["panel_alt"])
        style.configure(
            "TLabel",
            background=COLORS["window"],
            foreground=COLORS["text"],
            font=("Segoe UI", 11),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["window"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Panel.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Segoe UI", 11),
        )
        style.configure(
            "PanelMuted.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Title.TLabel",
            background=COLORS["window"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 13),
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="#17120a",
            borderwidth=0,
            padding=(18, 11),
            font=("Segoe UI Semibold", 11),
        )
        style.map(
            "Accent.TButton",
            background=[("active", COLORS["accent_hover"]), ("disabled", COLORS["border"])],
        )
        style.configure(
            "Quiet.TButton",
            background=COLORS["field"],
            foreground=COLORS["text"],
            borderwidth=0,
            padding=(13, 10),
            font=("Segoe UI", 10),
        )
        style.map("Quiet.TButton", background=[("active", COLORS["border"])])
        style.configure("TEntry", font=("Segoe UI", 11), padding=6)
        style.configure("TCombobox", font=("Segoe UI", 11), padding=5)
        style.configure("TRadiobutton", font=("Segoe UI", 11), padding=(2, 5))
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(14, 9))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=31)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _text(self, parent, *, height: int = 4):
        return self.tk.Text(
            parent,
            height=height,
            wrap="word",
            bg=COLORS["field"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            selectbackground="#49606b",
            relief="flat",
            borderwidth=0,
            padx=11,
            pady=11,
            font=("Segoe UI", 11),
            spacing1=3,
            spacing2=2,
            spacing3=7,
        )

    def _entry(self, parent):
        return self.tk.Entry(
            parent,
            bg=COLORS["field"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            selectbackground="#49606b",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 11),
        )

    def _draw_brand_mark(self, canvas) -> None:
        particles = ((4, 8, 2), (7, 20, 1), (3, 33, 2), (15, 4, 1))
        for x, y, radius in particles:
            canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=COLORS["info"],
                outline="",
            )
            canvas.create_line(x + radius, y, 22, 20, fill=COLORS["border"], width=1)
        canvas.create_polygon(
            32,
            5,
            46,
            20,
            32,
            35,
            18,
            20,
            outline=COLORS["accent"],
            fill="",
            width=2,
        )
        canvas.create_line(24, 20, 40, 20, fill=COLORS["accent"], width=2)
        canvas.create_line(32, 12, 32, 28, fill=COLORS["accent"], width=2)
        canvas.create_oval(29, 17, 35, 23, fill=COLORS["text"], outline="")

    def _field_is_text(self, widget) -> bool:
        return isinstance(widget, self.tk.Text)

    def _clear_field(self, widget) -> None:
        if self._field_is_text(widget):
            widget.delete("1.0", "end")
        else:
            widget.delete(0, "end")

    def _insert_field(self, widget, value: str) -> None:
        if self._field_is_text(widget):
            widget.insert("1.0", value)
        else:
            widget.insert(0, value)

    def _add_placeholder(self, widget, text: str) -> None:
        self._placeholder_text[widget] = text
        self._show_placeholder(widget)
        widget.bind(
            "<KeyPress>", lambda event, target=widget: self._placeholder_keypress(event, target)
        )
        widget.bind("<<Paste>>", lambda _event, target=widget: self._hide_placeholder(target))
        widget.bind("<FocusOut>", lambda _event, target=widget: self._restore_placeholder(target))

    def _placeholder_keypress(self, event, widget) -> None:
        if event.keysym not in {
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
            "Alt_L",
            "Alt_R",
            "Tab",
            "ISO_Left_Tab",
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
        }:
            self._hide_placeholder(widget)

    def _release_text_focus(self, event) -> None:
        """Hide the insertion cursor when the user clicks outside an input control."""
        if event.widget.winfo_class() not in {
            "Text",
            "Entry",
            "TEntry",
            "TCombobox",
            "Spinbox",
            "TSpinbox",
        }:
            self.root.after_idle(self.root.focus_set)

    def _show_placeholder(self, widget) -> None:
        self._clear_field(widget)
        self._insert_field(widget, self._placeholder_text[widget])
        widget.configure(fg=COLORS["muted"])
        self._placeholder_active.add(widget)

    def _hide_placeholder(self, widget) -> None:
        if widget not in self._placeholder_active:
            return
        self._clear_field(widget)
        widget.configure(fg=COLORS["text"])
        self._placeholder_active.discard(widget)

    def _restore_placeholder(self, widget) -> None:
        if self._field_value(widget):
            return
        self._show_placeholder(widget)

    def _set_field(self, widget, value: str) -> None:
        self._placeholder_active.discard(widget)
        self._clear_field(widget)
        self._insert_field(widget, value)
        widget.configure(fg=COLORS["text"])

    def _field_value(self, widget) -> str:
        if widget in self._placeholder_active:
            return ""
        if self._field_is_text(widget):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    def _field_label(self, parent, text: str) -> None:
        self.ttk.Label(parent, text=text, style="PanelMuted.TLabel").pack(anchor="w", pady=(14, 7))

    def _build(self) -> None:
        header = self.ttk.Frame(self.root, padding=(28, 22, 28, 14))
        header.pack(fill="x")
        brand = self.ttk.Frame(header)
        brand.pack(side="left")
        mark = self.tk.Canvas(brand, width=48, height=40, bg=COLORS["window"], highlightthickness=0)
        mark.pack(side="left", padx=(0, 11))
        self._draw_brand_mark(mark)
        title_stack = self.ttk.Frame(brand)
        title_stack.pack(side="left")
        self.ttk.Label(title_stack, text="DiCoJev", style="Title.TLabel").pack(anchor="w")
        self.ttk.Label(
            title_stack,
            text="DECISION STUDIO  ·  DIRECT PYTHON RUNTIME",
            style="Muted.TLabel",
        ).pack(anchor="w")
        scene_nav = self.ttk.Frame(header)
        scene_nav.pack(side="left", padx=(42, 0))
        self.ttk.Button(
            scene_nav,
            text="Workspace",
            style="Quiet.TButton",
            command=lambda: self._show_scene("workspace"),
        ).pack(side="left")
        self.ttk.Button(
            scene_nav,
            text="Settings",
            style="Quiet.TButton",
            command=lambda: self._show_scene("settings"),
        ).pack(side="left", padx=(6, 0))
        status = self.ttk.Frame(header)
        status.pack(side="right")
        self.status_dot = self.tk.Label(
            status, text="●", bg=COLORS["window"], fg=COLORS["good"], font=("Segoe UI", 9)
        )
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_var = self.tk.StringVar(value="Ready")
        self.ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")

        self.scene_host = self.ttk.Frame(self.root, padding=(28, 0, 28, 24))
        self.scene_host.pack(fill="both", expand=True)
        self.workspace_scene = self.tk.PanedWindow(
            self.scene_host,
            orient="horizontal",
            bg=COLORS["window"],
            borderwidth=0,
            relief="flat",
            sashwidth=7,
            sashpad=5,
            sashrelief="flat",
            opaqueresize=True,
        )
        self.workspace_scene.pack(fill="both", expand=True)

        sidebar = self.ttk.Frame(self.workspace_scene, style="Panel.TFrame", padding=14)
        inputs = self.ttk.Frame(self.workspace_scene, style="Panel.TFrame", padding=20)
        outputs = self.ttk.Frame(self.workspace_scene, style="Panel.TFrame", padding=20)
        self.workspace_scene.add(sidebar, minsize=220, width=250, stretch="always")
        self.workspace_scene.add(inputs, minsize=330, width=430, stretch="always")
        self.workspace_scene.add(outputs, minsize=380, width=520, stretch="always")
        self._build_sidebar(sidebar)
        self._build_inputs(self._scrolling_panel(inputs))
        self._build_outputs(outputs)
        self.settings_scene = self.ttk.Frame(self.scene_host, style="Panel.TFrame", padding=22)
        self._build_settings_scene(self.settings_scene)

    def _scrolling_panel(self, parent):
        canvas = self.tk.Canvas(parent, bg=COLORS["panel"], highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        inner = self.ttk.Frame(canvas, style="Panel.TFrame")
        window_id = canvas.create_window(0, 0, window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        self._scroll_regions.append((canvas, inner))
        return inner

    def _route_mousewheel(self, event):
        """Route wheel input to a hidden-scrollbar canvas under the pointer."""
        if event.widget.winfo_class() in {"Text", "Listbox", "Treeview", "TCombobox"}:
            return None
        widget_path = str(event.widget)
        for canvas, inner in self._scroll_regions:
            if event.widget is canvas or widget_path.startswith(f"{inner}."):
                steps = -int(event.delta / 120) if event.delta else 0
                if steps:
                    canvas.yview_scroll(steps, "units")
                    return "break"
        return None

    def _show_scene(self, name: str) -> None:
        if self._request_in_progress():
            return
        self.workspace_scene.pack_forget()
        self.settings_scene.pack_forget()
        if name == "settings":
            self._refresh_settings_scene()
            self.settings_scene.pack(fill="both", expand=True)
        else:
            self.workspace_scene.pack(fill="both", expand=True)

    def _build_sidebar(self, parent) -> None:
        self.ttk.Label(
            parent, text=f"Local profile · {self.account}", style="PanelMuted.TLabel"
        ).pack(anchor="w", pady=(2, 12))
        self.ttk.Button(
            parent, text="Projects  ＋", style="Quiet.TButton", command=self._new_project
        ).pack(fill="x", pady=(4, 6))
        self.project_nav = RoundedNavList(
            self.tk,
            parent,
            on_select=self._select_project_id,
            on_context=self._project_context_menu,
            height=140,
        )
        self.project_nav.pack(fill="x", pady=(0, 6))
        self.chat_group_var = self.tk.StringVar()
        self.ttk.Label(parent, textvariable=self.chat_group_var, style="PanelMuted.TLabel").pack(
            anchor="w", padx=(14, 0), pady=(2, 2)
        )
        self.ttk.Button(
            parent, text="New child chat  ＋", style="Quiet.TButton", command=self._new_chat
        ).pack(fill="x", padx=(12, 0), pady=(2, 4))
        self.chat_nav = RoundedNavList(
            self.tk,
            parent,
            on_select=self._select_chat_id,
            on_context=self._chat_context_menu,
            height=280,
        )
        self.chat_nav.pack(fill="both", expand=True, padx=(12, 0), pady=(0, 12))
        self.active_models_var = self.tk.StringVar()
        self.ttk.Button(
            parent, text="Browse project files", style="Quiet.TButton", command=self._browse_project
        ).pack(fill="x", pady=4)
        self.ttk.Button(
            parent, text="Open data folder", style="Quiet.TButton", command=self._open_data_folder
        ).pack(fill="x", pady=4)
        self._refresh_project_nav()
        self._refresh_chats(select_id=self.chat_id)
        self._update_active_model_label()

    def _refresh_project_nav(self) -> None:
        from types import SimpleNamespace

        items = [SimpleNamespace(id=NO_PROJECT_ID, name="No project")]
        items.extend(self.memory.list_projects(self.account))
        self.project_nav.set_items(items, selected_id=self.project_id or NO_PROJECT_ID)

    def _chats_in_active_container(self):
        if self.project_id is None:
            return self.memory.list_unassigned_chats(self.account)
        return self.memory.list_chats(self.account, self.project_id)

    def _active_container_name(self) -> str:
        if self.project_id is None:
            return "No project"
        return next(
            (
                item.name
                for item in self.memory.list_projects(self.account)
                if item.id == self.project_id
            ),
            "Project",
        )

    def _update_active_model_label(self) -> None:
        self.active_models_var.set(
            f"Language · {self.language_model.name}\nDecision · {self.decision_model.name}"
        )
        if hasattr(self, "quick_language_var"):
            self._refresh_quick_model_choices()
            language_label = next(
                (
                    label
                    for label, model_id in self._quick_language_map.items()
                    if model_id == self.language_model.id
                ),
                self.language_model.name,
            )
            decision_label = next(
                (
                    label
                    for label, model_id in self._quick_decision_map.items()
                    if model_id == self.decision_model.id
                ),
                self.decision_model.name,
            )
            self.quick_language_var.set(language_label)
            self.quick_decision_var.set(decision_label)

    def _build_quick_model_switchers(self, parent) -> None:
        bar = self.ttk.Frame(parent, style="Panel.TFrame")
        bar.pack(fill="x", pady=(8, 0))
        self.quick_language_var = self.tk.StringVar()
        self.quick_decision_var = self.tk.StringVar()
        self.quick_language = self.ttk.Combobox(
            bar, textvariable=self.quick_language_var, state="readonly", width=8
        )
        self.quick_decision = self.ttk.Combobox(
            bar, textvariable=self.quick_decision_var, state="readonly", width=8
        )
        for column, (label, widget) in enumerate(
            (("Language model", self.quick_language), ("Decision model", self.quick_decision))
        ):
            self.ttk.Label(bar, text=label, style="PanelMuted.TLabel").grid(
                row=0, column=column, sticky="w", padx=(0 if column == 0 else 10, 0)
            )
            widget.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(0 if column == 0 else 10, 0),
                pady=(2, 0),
            )
            bar.columnconfigure(column, weight=1, uniform="quick-model")
        self.quick_language.bind("<<ComboboxSelected>>", self._quick_models_changed)
        self.quick_decision.bind("<<ComboboxSelected>>", self._quick_models_changed)
        self._refresh_quick_model_choices()
        self._update_active_model_label()

    def _model_choice_map(self, role: str) -> dict[str, str]:
        models = self.memory.list_models(self.account, role)
        counts = {item.name: sum(model.name == item.name for model in models) for item in models}
        return {
            (
                item.name
                if counts[item.name] == 1
                else f"{item.name} · {item.deployment.title()} · {item.adapter}"
            ): item.id
            for item in models
        }

    def _refresh_quick_model_choices(self) -> None:
        if not hasattr(self, "quick_language"):
            return
        self._quick_language_map = self._model_choice_map("language")
        self._quick_decision_map = self._model_choice_map("decision")
        self.quick_language.configure(values=list(self._quick_language_map))
        self.quick_decision.configure(values=list(self._quick_decision_map))

    def _quick_models_changed(self, _event=None) -> None:
        if self._request_in_progress():
            self._update_active_model_label()
            return
        language_id = self._quick_language_map.get(self.quick_language_var.get())
        decision_id = self._quick_decision_map.get(self.quick_decision_var.get())
        if language_id is None or decision_id is None:
            return
        previous = self.memory.get_chat_models(self.chat_id)
        try:
            self.memory.set_chat_models(self.chat_id, language_id, decision_id)
            self._activate_chat_models(self.chat_id)
            self._update_active_model_label()
            self.status_var.set("Models changed for this chat")
        except Exception as error:  # noqa: BLE001 - GUI boundary restores prior selection
            from tkinter import messagebox

            self.memory.set_chat_models(
                self.chat_id, previous.language_model_id, previous.decision_model_id
            )
            self._activate_chat_models(self.chat_id)
            self._update_active_model_label()
            messagebox.showerror("Change models", str(error), parent=self.root)

    def _new_project(self) -> None:
        if self._request_in_progress():
            return
        from tkinter import filedialog, simpledialog

        name = simpledialog.askstring("Create project", "Project name", parent=self.root)
        if not name or not name.strip():
            return
        folder = filedialog.askdirectory(title="Project folder (Cancel for a chat-only project)")
        self.project_id = self.memory.create_project(self.account, name, folder or "")
        self._new_chat()
        self._refresh_project_nav()

    def _select_project_id(self, project_id: str) -> None:
        if self._request_in_progress():
            return
        self.project_id = None if project_id == NO_PROJECT_ID else project_id
        chats = self._chats_in_active_container()
        if not chats:
            self._new_chat()
        else:
            self._select_chat_id(chats[0].id)
        self._refresh_project_nav()
        self._refresh_chats(select_id=self.chat_id)

    def _select_chat_id(self, chat_id: str) -> None:
        if self._request_in_progress():
            return
        self.chat_id = chat_id
        self._ensure_chat_model_defaults(chat_id)
        self._activate_chat_models(chat_id)
        chat = next(item for item in self.memory.list_chats(self.account) if item.id == chat_id)
        self._load_chat(chat)
        self._refresh_chats(select_id=chat_id)
        self._update_active_model_label()

    def _chat_context_menu(self, chat_id: str, x: int, y: int) -> None:
        self._select_chat_id(chat_id)
        menu = self.tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Rename", command=self._rename_chat)
        move_menu = self.tk.Menu(menu, tearoff=False)
        move_menu.add_command(label="No project", command=lambda: self._move_chat(chat_id, None))
        for project in self.memory.list_projects(self.account):
            move_menu.add_command(
                label=project.name,
                command=lambda target=project.id: self._move_chat(chat_id, target),
            )
        menu.add_cascade(label="Move to", menu=move_menu)
        menu.add_command(label="Delete", command=self._delete_chat)
        menu.tk_popup(x, y)

    def _move_chat(self, chat_id: str, project_id: str | None) -> None:
        if self._request_in_progress():
            return
        self.memory.set_chat_project(chat_id, project_id)
        self.project_id = project_id
        self._refresh_project_nav()
        self._refresh_chats(select_id=chat_id)
        self.status_var.set(f"Chat moved to {self._active_container_name()}")

    def _project_context_menu(self, project_id: str, x: int, y: int) -> None:
        from tkinter import filedialog, messagebox, simpledialog

        if project_id == NO_PROJECT_ID:
            return
        project = next(
            item for item in self.memory.list_projects(self.account) if item.id == project_id
        )

        def rename():
            value = simpledialog.askstring(
                "Rename project", "Project name", initialvalue=project.name, parent=self.root
            )
            if value and value.strip():
                self.memory.rename_project(project_id, value)
                self._refresh_project_nav()

        def delete():
            if not messagebox.askyesno(
                "Delete project",
                f"Delete '{project.name}' and its chats? Files in the project folder are preserved.",
                parent=self.root,
            ):
                return
            self.memory.delete_project(project_id)
            projects = self.memory.list_projects(self.account)
            self.project_id = projects[0].id if projects else None
            self._select_project_id(self.project_id)

        menu = self.tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Rename", command=rename)

        def choose_folder():
            value = filedialog.askdirectory(title="Project folder", parent=self.root)
            if value:
                self.memory.set_project_folder(project_id, str(Path(value).resolve()))

        menu.add_command(label="Choose project folder", command=choose_folder)
        menu.add_command(label="Delete", command=delete)
        menu.tk_popup(x, y)

    def _build_inputs(self, parent) -> None:
        self.ttk.Label(parent, text="Describe the decision", style="Section.TLabel").pack(
            anchor="w"
        )
        self.ttk.Label(
            parent,
            text="Give the model the situation, desired outcome, and boundaries.",
            style="PanelMuted.TLabel",
        ).pack(anchor="w", pady=(3, 4))

        self._field_label(parent, "CONTEXT")
        self.context = self._text(parent, height=3)
        self.context.pack(fill="x")
        self._add_placeholder(
            self.context,
            "Enter context only and let the language model complete the missing fields.\n"
            "Or use this as a general text box for your complete request.\n"
            "Example: I have two plans, a $50 budget, and need the better choice.",
        )
        self._field_label(parent, "GOAL")
        self.goal = self._text(parent, height=2)
        self.goal.pack(fill="x")
        self._add_placeholder(
            self.goal,
            "State the desired outcome, or leave blank for intent drafting.\n"
            "Example: Compare the plans and explain the best fit.",
        )
        self._field_label(parent, "AVAILABLE TOOLS  ·  comma or new line")
        self.tools = self._text(parent, height=2)
        self.tools.pack(fill="x")
        self._add_placeholder(
            self.tools,
            "List only tools the agent is permitted to use.\n"
            "Example: inspect_transactions, issue_refund, escalate_to_human",
        )
        self._field_label(parent, "CONSTRAINTS  ·  comma or new line")
        self.constraints = self._text(parent, height=3)
        self.constraints.pack(fill="x")
        self._add_placeholder(
            self.constraints,
            "Describe rules that every acceptable action must obey.\n"
            "Example: Confirm both transactions before issuing a refund.",
        )

        advanced = self.ttk.Frame(parent, style="Panel.TFrame")
        advanced.pack(fill="x", pady=(8, 0))
        self._field_label(
            advanced,
            "STRUCTURED STATE  ·  optional JSON combined with context and generated candidates",
        )
        self.structured = self._text(advanced, height=6)
        self.structured.pack(fill="x")
        self._add_placeholder(
            self.structured,
            "Optional machine-readable state. Full example:\n"
            '{"facts":{"identity_verified":true,"charge_count":2},\n'
            ' "entities":["Plan A","Plan B"],\n'
            ' "preferences":{"budget":50,"currency":"USD"},\n'
            ' "uncertainties":["delivery date"],\n'
            ' "intent_instruction":"Compare against budget",\n'
            ' "draft_options":["Choose Plan A","Choose Plan B"]}',
        )
        self._field_label(advanced, "ATTACHMENTS  ·  image, text, document, audio, or video")
        image_row = self.ttk.Frame(advanced, style="Panel.TFrame")
        image_row.pack(fill="x")
        self.attachment_var = self.tk.StringVar(value="No files selected")
        self.tk.Label(
            image_row,
            textvariable=self.attachment_var,
            bg=COLORS["field"],
            fg=COLORS["muted"],
            anchor="w",
            padx=10,
            font=("Segoe UI", 9),
        ).pack(side="left", fill="both", expand=True, ipady=8)
        self.ttk.Button(
            image_row, text="Add files", style="Quiet.TButton", command=self._choose_attachments
        ).pack(side="left", padx=(8, 0))
        self.ttk.Button(
            image_row, text="Clear", style="Quiet.TButton", command=self._clear_attachments
        ).pack(side="left", padx=(5, 0))

        buttons = self.ttk.Frame(parent, style="Panel.TFrame")
        buttons.pack(fill="x", pady=(18, 0))
        self.ttk.Button(
            buttons, text="Load sample", style="Quiet.TButton", command=self._load_sample
        ).pack(side="left")
        self.ttk.Button(
            buttons,
            text="Complete missing fields",
            style="Quiet.TButton",
            command=self._infer_intent,
        ).pack(side="left", padx=(6, 0))
        self.decide_button = self.ttk.Button(
            buttons, text="Make decision  →", style="Accent.TButton", command=self._submit
        )
        self.decide_button.pack(side="right")

    def _build_outputs(self, parent) -> None:
        top = self.ttk.Frame(parent, style="Panel.TFrame")
        top.pack(fill="x")
        self.ttk.Label(top, text="Conversation", style="Section.TLabel").pack(side="left")
        self.action_var = self.tk.StringVar(value="WAITING")
        self.action_badge = self.tk.Label(
            top,
            textvariable=self.action_var,
            bg=COLORS["field"],
            fg=COLORS["muted"],
            padx=12,
            pady=7,
            font=("Segoe UI Semibold", 10),
        )
        self.action_badge.pack(side="right")
        self._build_quick_model_switchers(parent)

        self.conversation_text = self.tk.Text(
            parent,
            height=10,
            wrap="word",
            bg=COLORS["field"],
            fg=COLORS["text"],
            relief="flat",
            borderwidth=0,
            padx=13,
            pady=14,
            font=("Segoe UI", 11),
            spacing1=4,
            spacing2=2,
            spacing3=10,
            state="disabled",
        )
        self.conversation_text.tag_configure(
            "request_label",
            justify="right",
            foreground=COLORS["accent"],
            font=("Segoe UI Semibold", 10),
            spacing1=12,
            spacing3=4,
        )
        self.conversation_text.tag_configure(
            "request",
            justify="right",
            foreground=COLORS["text"],
            lmargin1=65,
            lmargin2=65,
            spacing1=4,
            spacing2=3,
            spacing3=14,
        )
        self.conversation_text.tag_configure(
            "decision_label",
            justify="left",
            foreground=COLORS["info"],
            font=("Segoe UI Semibold", 10),
            spacing1=12,
            spacing3=4,
        )
        self.conversation_text.tag_configure(
            "decision",
            justify="left",
            foreground=COLORS["text"],
            rmargin=65,
            spacing1=4,
            spacing2=3,
            spacing3=14,
        )
        self.conversation_text.pack(fill="both", expand=True, pady=(14, 14))
        self._refresh_history()

        self.selected_var = self.tk.StringVar(value="Submit a decision to begin.")
        self.tk.Label(
            parent,
            textvariable=self.selected_var,
            bg=COLORS["panel"],
            fg=COLORS["text"],
            justify="left",
            anchor="w",
            wraplength=490,
            font=("Segoe UI Semibold", 16),
        ).pack(fill="x", pady=(10, 14))

        metrics = self.ttk.Frame(parent, style="Panel.TFrame")
        metrics.pack(fill="x")
        self.coverage_var = self._metric(metrics, "COVERAGE", "—", 0)
        self.confidence_var = self._metric(metrics, "CONFIDENCE", "—", 1)
        self.feedback_var = self._metric(metrics, "FEEDBACK", "—", 2)

        self.ttk.Label(parent, text="Candidates", style="Section.TLabel").pack(
            anchor="w", pady=(16, 7)
        )
        self.candidate_text = self._output_box(parent, height=4)
        self.candidate_text.pack(fill="x")
        self.ttk.Label(parent, text="Controller trace", style="Section.TLabel").pack(
            anchor="w", pady=(14, 7)
        )
        self.trace_text = self._output_box(parent, height=3)
        self.trace_text.pack(fill="x")
        self.ttk.Button(
            parent, text="Copy full JSON", style="Quiet.TButton", command=self._copy_json
        ).pack(anchor="e", pady=(12, 0))

    def _metric(self, parent, label: str, value: str, column: int):
        card = self.ttk.Frame(parent, style="Alt.TFrame", padding=(12, 10))
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))
        parent.columnconfigure(column, weight=1)
        self.tk.Label(
            card,
            text=label,
            bg=COLORS["panel_alt"],
            fg=COLORS["muted"],
            font=("Segoe UI Semibold", 9),
        ).pack(anchor="w")
        variable = self.tk.StringVar(value=value)
        self.tk.Label(
            card,
            textvariable=variable,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w", pady=(6, 0))
        return variable

    def _output_box(self, parent, *, height: int):
        widget = self._text(parent, height=height)
        widget.configure(state="disabled")
        return widget

    def _set_output(self, widget, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _choose_attachments(self) -> None:
        from tkinter import filedialog

        paths = filedialog.askopenfilenames(
            title="Add multimodal attachments",
            filetypes=[
                (
                    "Supported media",
                    "*.png *.jpg *.jpeg *.webp *.txt *.md *.csv *.json *.pdf *.docx *.wav *.mp3 *.m4a *.flac *.mp4 *.mov *.mkv *.webm",
                ),
                ("All files", "*.*"),
            ],
        )
        if paths:
            self.attachment_paths = list(paths)
            names = [Path(path).name for path in paths]
            label = ", ".join(names[:3])
            if len(names) > 3:
                label += f"  +{len(names) - 3} more"
            self.attachment_var.set(label)

    def _clear_attachments(self) -> None:
        self.attachment_paths = []
        self.attachment_var.set("No files selected")

    def _load_sample(self) -> None:
        self._set_field(
            self.context, "A customer reports two similar card charges. Their identity is verified."
        )
        self._set_field(self.goal, "Choose the safest next support action")
        self._set_field(self.tools, "inspect_transactions, issue_refund, escalate_to_human")
        self._set_field(
            self.constraints,
            "Do not issue a refund before confirming that both transactions settled",
        )
        self._set_field(self.structured, '{"identity_verified": true, "charge_count": 2}')

    def _request(self) -> DecisionRequest:
        request = build_request(
            context=self._field_value(self.context),
            goal=self._field_value(self.goal),
            tools=self._field_value(self.tools),
            constraints=self._field_value(self.constraints),
            structured_json=self._field_value(self.structured),
        )
        project = self.memory.get_chat_project(self.chat_id)
        if project:
            structured = dict(request.state.structured)
            structured["project"] = {
                "name": project.name,
                "root_path": project.root_path,
                "access": "selected_folder",
            }
            request = request.model_copy(
                update={"state": request.state.model_copy(update={"structured": structured})}
            )
        return request.model_copy(update={"history": self.memory.decision_history(self.chat_id)})

    def _submit(self) -> None:
        from tkinter import messagebox

        signature = tuple(
            self._field_value(widget)
            for widget in (self.context, self.goal, self.tools, self.constraints, self.structured)
        )
        if not all(signature[1:4]) and signature != getattr(self, "_completion_signature", None):
            self._infer_intent()
            return
        try:
            request = self._request()
        except (ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Check the request", str(error), parent=self.root)
            return
        attachments = tuple(self.attachment_paths)
        visual_attachments = any(
            Path(path).suffix.lower() in IMAGE_SUFFIXES | VIDEO_SUFFIXES for path in attachments
        )
        cloud_pair = any(
            model.deployment == "online" for model in (self.language_model, self.decision_model)
        )
        if (
            visual_attachments
            and cloud_pair
            and not messagebox.askyesno(
                "Send local vision analysis to cloud models?",
                "The original image or video frames will stay on this computer and be analyzed "
                "by local Qwen3.5. The resulting text description will be sent to the selected "
                "cloud language and decision models. Continue?",
                parent=self.root,
            )
        ):
            self.status_var.set("Attachment request cancelled")
            return
        self.decide_button.configure(state="disabled")
        self.status_var.set("Thinking…")
        self.status_dot.configure(fg=COLORS["accent"])
        latest = self.memory.latest_turn(self.chat_id, "user") or {}
        matches_draft = (
            latest.get("kind") == "intent_draft"
            and latest.get("context") == request.state.text
            and latest.get("goal") == request.goal
        )
        if not matches_draft:
            self.memory.append_turn(
                self.chat_id,
                "user",
                {
                    "context": request.state.text,
                    "goal": request.goal,
                    "tools": list(request.available_tools),
                    "constraints": list(request.constraints),
                    "summary": f"{request.goal}: {request.state.text[:500]}",
                },
            )
        self._refresh_chats(select_id=self.chat_id)
        self._refresh_history()
        chat_id = self.chat_id
        threading.Thread(
            target=self._run_decision,
            args=(request, attachments, chat_id, self.client),
            daemon=True,
        ).start()

    def _run_decision(
        self,
        request: DecisionRequest,
        attachments: tuple[str, ...],
        chat_id: str,
        client: DirectClient,
    ) -> None:
        try:
            request = self.ingestor.enrich_request(request, attachments)
            orchestrator = getattr(client.runtime, "orchestrator", None)
            generator = getattr(orchestrator, "generator", None)
            backend = getattr(orchestrator, "backend", None)
            generator_capabilities = getattr(generator, "capabilities", None)
            backend_capabilities = getattr(backend, "capabilities", None)
            native_pair = bool(
                generator_capabilities
                and generator_capabilities.supports_images
                and generator_capabilities.supports_native_multimodal
                and backend_capabilities
                and backend_capabilities.supports_images
                and backend_capabilities.supports_native_multimodal
            )
            if request.state.images and not native_pair:
                request = self.vision_bridge.enrich_request(request)
            response = client.decide_sync(request)
            presentation = present_response(response)
        except Exception as error:  # noqa: BLE001 - GUI boundary presents normalized failure
            self.root.after(0, self._show_error, type(error).__name__, str(error))
            return
        self.root.after(0, self._show_result, presentation, response, chat_id, client)

    def _show_result(
        self,
        result: DecisionPresentation,
        response: DecisionResponse,
        chat_id: str,
        client: DirectClient,
    ) -> None:
        self.raw_json = result.raw_json
        self.action_var.set(result.action)
        self.action_badge.configure(fg=result.action_color)
        self.selected_var.set(result.selected)
        self.coverage_var.set(result.coverage)
        self.confidence_var.set(result.confidence)
        self.feedback_var.set(result.feedback)
        self._set_output(self.candidate_text, result.candidates)
        self._set_output(self.trace_text, result.trace)
        self.status_var.set("Ready")
        self.status_dot.configure(fg=COLORS["good"])
        self.decide_button.configure(state="normal")
        self.memory.append_turn(
            chat_id,
            "assistant",
            {
                "action": result.action,
                "selected": result.selected,
                "summary": f"{result.action}: {result.selected}",
                "response": response.model_dump(mode="json"),
            },
        )
        self.memory.record_usage(
            self.account, chat_id, client.model_name, "generation", client.usage_snapshot()
        )
        backend_usage = response.backend_result.diagnostics.get("usage", {})
        self.memory.record_usage(
            self.account,
            chat_id,
            client.decision_model_name,
            "decision",
            backend_usage if isinstance(backend_usage, dict) else {},
        )
        self._refresh_chats(select_id=self.chat_id)
        if chat_id == self.chat_id:
            self._refresh_history()

    def _infer_intent(self) -> None:
        from tkinter import messagebox

        context = self._field_value(self.context)
        if not context:
            messagebox.showinfo(
                "Add some context",
                "Write or paste the situation first. DiCoJev will draft the goal and boundaries.",
                parent=self.root,
            )
            return
        self.decide_button.configure(state="disabled")
        self.status_var.set("Understanding…")
        self.status_dot.configure(fg=COLORS["accent"])
        history = self.memory.decision_history(self.chat_id)
        partial = {
            "goal": self._field_value(self.goal),
            "constraints": split_items(self._field_value(self.constraints)),
            "suggested_tools": split_items(self._field_value(self.tools)),
            "attachments": [
                {"name": Path(path).name, "kind": Path(path).suffix.lower()}
                for path in self.attachment_paths
            ],
        }
        threading.Thread(
            target=self._run_intent_inference,
            args=(context, history, self.chat_id, self.client, partial),
            daemon=True,
        ).start()

    def _run_intent_inference(
        self,
        context: str,
        history: tuple[str, ...],
        chat_id: str,
        client: DirectClient,
        partial_fields: dict | None = None,
    ) -> None:
        try:
            draft = client.infer_intent_sync(context, history, partial_fields)
        except Exception as error:  # noqa: BLE001 - GUI boundary
            self.root.after(0, self._show_error, type(error).__name__, str(error))
            return
        self.root.after(0, self._show_intent, draft, chat_id, False, client)

    def _show_intent(
        self,
        draft: IntentDraft,
        chat_id: str,
        used_fallback: bool = False,
        client: DirectClient | None = None,
    ) -> None:
        from tkinter import messagebox

        if not self._field_value(self.goal):
            self._set_field(self.goal, draft.goal)
        if draft.constraints and not self._field_value(self.constraints):
            self._set_field(self.constraints, "\n".join(draft.constraints))
        if draft.suggested_tools and not self._field_value(self.tools):
            self._set_field(self.tools, "\n".join(draft.suggested_tools))
        try:
            structured = json.loads(self._field_value(self.structured) or "{}")
            if not isinstance(structured, dict):
                raise TypeError("Structured state must be a JSON object.")
        except (ValueError, TypeError) as error:
            self._show_error("Invalid structured state", str(error))
            return
        structured["intent_instruction"] = draft.instruction
        structured["draft_options"] = list(draft.options)
        self._set_field(self.structured, json.dumps(structured, ensure_ascii=False))
        self._completion_signature = tuple(
            self._field_value(widget)
            for widget in (self.context, self.goal, self.tools, self.constraints, self.structured)
        )
        status = "Offline draft" if used_fallback else "Intent drafted"
        self.status_var.set(f"{status} · {draft.confidence:.0%} confidence")
        self.status_dot.configure(fg=COLORS["warn"] if used_fallback else COLORS["info"])
        self.decide_button.configure(state="normal")
        client = client or self.client
        self.memory.record_usage(
            self.account,
            chat_id,
            client.model_name,
            "intent",
            client.intent_inferer.last_usage if client.intent_inferer and not used_fallback else {},
        )
        if chat_id == self.chat_id:
            self.memory.append_turn(
                chat_id,
                "user",
                {
                    "kind": "intent_draft",
                    "context": self._field_value(self.context),
                    "goal": draft.goal,
                    "tools": list(draft.suggested_tools),
                    "constraints": list(draft.constraints),
                    "instruction": draft.instruction,
                    "options": list(draft.options),
                    "summary": f"Drafted goal: {draft.goal}",
                },
            )
            self._refresh_chats(select_id=chat_id)
            self._refresh_history()
        note = draft.instruction
        if draft.options:
            note += "\n\nGenerated options:\n• " + "\n• ".join(draft.options)
        if draft.assumptions:
            note += "\n\nAssumptions to review:\n• " + "\n• ".join(draft.assumptions)
        if draft.needs_clarification and draft.clarifying_question:
            note += f"\n\nQuestion: {draft.clarifying_question}"
        if used_fallback:
            note += (
                "\n\nThe configured model service is not running. This conservative draft "
                "was created locally without model inference."
            )
        note += "\n\nReview the draft, especially suggested tools, then click Make decision."
        messagebox.showinfo("Intent draft", note, parent=self.root)

    def _show_direct_answer(self, answer: DirectAnswer, context: str, chat_id: str) -> None:
        self._set_field(self.goal, answer.goal)
        self.action_var.set("ANSWER")
        self.action_badge.configure(fg=COLORS["good"])
        self.selected_var.set(answer.answer)
        self.coverage_var.set("N/A")
        self.confidence_var.set(f"{answer.confidence:.0%}")
        self.feedback_var.set("DIRECT")
        self._set_output(self.candidate_text, f"calculator_result  {answer.answer}")
        self._set_output(self.trace_text, "Direct deterministic route · decision loop not invoked")
        self.raw_json = json.dumps(
            {
                "route": "direct_answer",
                "goal": answer.goal,
                "answer": answer.answer,
                "method": answer.method,
                "confidence": answer.confidence,
            },
            indent=2,
        )
        self.memory.append_turn(
            chat_id,
            "user",
            {
                "kind": "direct_request",
                "context": context,
                "goal": answer.goal,
                "tools": ["calculator"],
                "constraints": [],
                "summary": answer.goal,
            },
        )
        self.memory.append_turn(
            chat_id,
            "assistant",
            {
                "kind": "direct_answer",
                "action": "ANSWER",
                "selected": answer.answer,
                "answer": answer.answer,
                "method": answer.method,
                "confidence": answer.confidence,
                "summary": f"ANSWER: {answer.answer}",
            },
        )
        self.memory.record_usage(
            self.account, chat_id, "deterministic-calculator", "direct_answer", {}
        )
        self.status_var.set("Answered directly")
        self.status_dot.configure(fg=COLORS["good"])
        self.decide_button.configure(state="normal")
        self._refresh_chats(select_id=chat_id)
        if chat_id == self.chat_id:
            self._refresh_history()

    def _refresh_chats(self, *, select_id: str | None = None) -> None:
        self._chat_rows = self._chats_in_active_container()
        if hasattr(self, "chat_group_var"):
            self.chat_group_var.set(f"└  Chats · {self._active_container_name()}")
        self.chat_nav.set_items(self._chat_rows, selected_id=select_id)

    def _new_chat(self) -> None:
        if self._request_in_progress():
            return
        self.chat_id = self.memory.create_chat(self.account, project_id=self.project_id)
        self._ensure_chat_model_defaults(self.chat_id, prefer_executable=True)
        self._activate_chat_models(self.chat_id)
        for widget in (self.context, self.goal, self.tools, self.constraints, self.structured):
            self._show_placeholder(widget)
        self._clear_attachments()
        self.action_var.set("WAITING")
        self.selected_var.set("Submit a decision to begin.")
        self._refresh_chats(select_id=self.chat_id)
        self._refresh_history()
        self._update_active_model_label()

    def _rename_chat(self) -> None:
        from tkinter import simpledialog

        if self._request_in_progress():
            return

        current = next((chat for chat in self._chat_rows if chat.id == self.chat_id), None)
        value = simpledialog.askstring(
            "Rename chat",
            "Chat name",
            initialvalue=current.title if current else "",
            parent=self.root,
        )
        if value and value.strip():
            self.memory.rename_chat(self.chat_id, value)
            self._refresh_chats(select_id=self.chat_id)

    def _delete_chat(self) -> None:
        from tkinter import messagebox

        if self._request_in_progress():
            return

        current = next((chat for chat in self._chat_rows if chat.id == self.chat_id), None)
        if not current or not messagebox.askyesno(
            "Delete chat",
            f"Permanently delete '{current.title}' and its local history?",
            parent=self.root,
        ):
            return
        self.memory.delete_chat(self.chat_id)
        chats = self._chats_in_active_container()
        created_chat = not chats
        self.chat_id = (
            chats[0].id
            if chats
            else self.memory.create_chat(self.account, project_id=self.project_id)
        )
        self._ensure_chat_model_defaults(self.chat_id, prefer_executable=created_chat)
        self._activate_chat_models(self.chat_id)
        self._refresh_chats(select_id=self.chat_id)
        selected = next(chat for chat in self._chat_rows if chat.id == self.chat_id)
        self._load_chat(selected)

    def _load_chat(self, chat) -> None:
        latest = self.memory.latest_turn(chat.id, "user") or {}
        self._set_field(self.context, latest.get("context", ""))
        self._set_field(self.goal, latest.get("goal", ""))
        self._set_field(self.tools, "\n".join(latest.get("tools", ())))
        self._set_field(self.constraints, "\n".join(latest.get("constraints", ())))
        self._set_field(self.structured, "")
        self._clear_attachments()
        self.raw_json = ""
        self.action_var.set("WAITING")
        self.selected_var.set("Submit a decision to begin.")
        self._set_output(self.candidate_text, "")
        self._set_output(self.trace_text, "")
        self._refresh_history()

    def _refresh_history(self) -> None:
        if not hasattr(self, "conversation_text"):
            return
        widget = self.conversation_text
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for turn in self.memory.list_turns(self.chat_id):
            if turn.role == "user":
                label = "YOU · STRUCTURED REQUEST"
                if turn.content.get("kind") == "intent_draft":
                    label = "YOU · REVIEW THIS INTENT DRAFT"
                widget.insert("end", f"{label}\n", "request_label")
                fields = [
                    ("Goal", turn.content.get("goal")),
                    ("Context", turn.content.get("context")),
                    ("Tools", ", ".join(turn.content.get("tools", ()))),
                    ("Constraints", "; ".join(turn.content.get("constraints", ()))),
                    ("Instruction", turn.content.get("instruction")),
                    ("Generated options", "; ".join(turn.content.get("options", ()))),
                ]
                body = "\n".join(f"{name}: {value}" for name, value in fields if value)
                widget.insert("end", f"{body}\n\n", "request")
                continue
            if turn.content.get("kind") == "direct_answer":
                widget.insert("end", "DICOJEV · DIRECT ANSWER\n", "decision_label")
                widget.insert(
                    "end",
                    (
                        f"Result: {turn.content.get('answer', '—')}\n"
                        f"Method: {turn.content.get('method', 'deterministic')}\n"
                        f"Confidence: {turn.content.get('confidence', 1.0):.0%}\n\n"
                    ),
                    "decision",
                )
                continue
            response = turn.content.get("response", {})
            backend = response.get("backend_result", {}) if isinstance(response, dict) else {}
            coverage = backend.get("coverage") or {}
            selection = backend.get("selection") or {}
            coverage_value = coverage.get("calibrated")
            if coverage_value is None:
                coverage_value = coverage.get("raw")
            confidence = selection.get("confidence_calibrated")
            if confidence is None:
                confidence = selection.get("confidence_raw")
            selected = turn.content.get("selected") or "No choice"
            lines = [f"Action: {turn.content.get('action', '—')}"]
            if isinstance(coverage_value, int | float):
                lines.append(
                    f"Adequate (Y/N): {'Y' if coverage_value >= 0.5 else 'N'}  ·  "
                    f"coverage {coverage_value:.1%}"
                )
            lines.append(f"Choice: {selected}")
            if isinstance(confidence, int | float):
                lines.append(f"Choice score: {confidence:.1%}")
            probabilities = selection.get("probabilities", {})
            candidates = response.get("candidates", ()) if isinstance(response, dict) else ()
            actions = {
                item.get("id"): item.get("action") for item in candidates if isinstance(item, dict)
            }
            if isinstance(probabilities, dict) and probabilities:
                options = [
                    f"{actions.get(candidate_id, candidate_id)} = {score:.1%}"
                    for candidate_id, score in probabilities.items()
                    if isinstance(score, int | float)
                ]
                lines.append("Options: " + "  ·  ".join(options))
            widget.insert("end", "DICOJEV · DECISION\n", "decision_label")
            widget.insert("end", "\n".join(lines) + "\n\n", "decision")
        if not self.memory.list_turns(self.chat_id):
            widget.insert("end", "Your structured request and DiCoJev's decision will appear here.")
        widget.configure(state="disabled")
        widget.see("end")

    def _browse_project(self) -> None:
        from tkinter import messagebox

        project = self.memory.get_chat_project(self.chat_id)
        if project is None or not project.root_path:
            messagebox.showinfo(
                "Choose a project folder",
                "This project has no folder. Create a project with a folder to browse files.",
                parent=self.root,
            )
            return
        workspace = ProjectWorkspace(project.root_path)
        window = self.tk.Toplevel(self.root)
        window.title(f"Project files — {project.name}")
        window.geometry("620x520")
        frame = self.ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        self.ttk.Label(
            frame,
            text="Select files to add as decision context",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        files = workspace.list_files()
        file_list = self.tk.Listbox(
            frame,
            selectmode="extended",
            bg=COLORS["field"],
            fg=COLORS["text"],
            selectbackground="#49606b",
            relief="flat",
            borderwidth=0,
            font=("Consolas", 9),
        )
        for value in files:
            file_list.insert("end", value)
        file_list.pack(fill="both", expand=True)

        def attach() -> None:
            selected = [files[index] for index in file_list.curselection()]
            if not selected:
                return
            self.attachment_paths.extend(str(workspace.resolve(item)) for item in selected)
            self.attachment_var.set(f"{len(self.attachment_paths)} file(s) selected")
            window.destroy()

        self.ttk.Button(frame, text="Add selected", style="Accent.TButton", command=attach).pack(
            anchor="e", pady=(10, 0)
        )

    def _open_settings(self) -> None:
        self._show_scene("settings")

    def _build_settings_scene(self, frame) -> None:
        self.ttk.Label(frame, text="Settings", style="Section.TLabel").pack(anchor="w")
        self.settings_tabs = self.ttk.Notebook(frame)
        self.settings_tabs.pack(fill="both", expand=True, pady=(12, 0))
        self.models_page = self.ttk.Frame(self.settings_tabs, padding=18)
        self.chats_page = self.ttk.Frame(self.settings_tabs, padding=18)
        self.usage_page = self.ttk.Frame(self.settings_tabs, padding=18)
        for page, label in (
            (self.models_page, "Model registry"),
            (self.chats_page, "Chats & models"),
            (self.usage_page, "Token usage"),
        ):
            self.settings_tabs.add(page, text=label)
        self.models_page = self._scrolling_panel(self.models_page)
        self.chats_page = self._scrolling_panel(self.chats_page)
        columns = ("name", "role", "deployment", "adapter", "source")
        self.model_table = self.ttk.Treeview(
            self.models_page, columns=columns, show="headings", height=7
        )
        for column in columns:
            self.model_table.heading(column, text=column.title())
            self.model_table.column(column, width=140 if column != "source" else 280)
        self.model_table.pack(fill="x", pady=(0, 14))
        self.model_table.bind("<Button-3>", self._model_context_menu)
        self.editing_model_id = None
        form = self.ttk.Frame(self.models_page)
        form.pack(fill="x")
        self.local_model_path = self.tk.StringVar()
        self.discovered_model = None
        self.model_form = {}
        self.model_widgets = {}
        self.model_labels = {}
        fields = (
            ("Name", None),
            ("Role", ("language", "decision")),
            ("Deployment", ("local", "online")),
            (
                "Adapter",
                (
                    "diffusiongemma",
                    "llada",
                    "openai_compatible",
                    "mercury",
                    "laya_local",
                    "djev_local",
                    "jev_cloud",
                    "native_dlm",
                ),
            ),
            ("Location", None),
            ("Model identifier", None),
            ("API key", None),
        )
        for index, (label, choices) in enumerate(fields):
            display_label = {
                "Location": "API URL",
                "Model identifier": "Model name",
            }.get(label, label)
            title = self.ttk.Label(form, text=display_label)
            title.grid(row=index, column=0, sticky="w", pady=5)
            self.model_labels[label] = title
            variable = self.tk.StringVar()
            self.model_form[label] = variable
            if label in {"Role", "Deployment"}:
                widget = self.ttk.Frame(form)
                labels = (
                    ("Language model", "Decision model") if label == "Role" else ("Local", "Cloud")
                )
                for value, caption in zip(choices, labels, strict=True):
                    self.ttk.Radiobutton(
                        widget,
                        text=caption,
                        value=value,
                        variable=variable,
                        command=self._update_model_controls,
                    ).pack(side="left", padx=(0, 18))
                variable.set(choices[0])
            elif choices:
                widget = self.ttk.Combobox(
                    form, textvariable=variable, values=choices, state="readonly"
                )
                variable.set(choices[0])
            else:
                widget = self.ttk.Entry(
                    form, textvariable=variable, show="•" if label == "API key" else ""
                )
            widget.grid(row=index, column=1, sticky="ew", pady=5)
            self.model_widgets[label] = widget
            if label == "Adapter":
                widget.bind("<<ComboboxSelected>>", lambda _event: self._update_model_controls())
        form.columnconfigure(1, weight=1)
        for row in range(4, 8):
            form.grid_rowconfigure(row, minsize=46)
        self.local_path_label = self.ttk.Label(form, text="Model folder")
        self.local_path_label.grid(row=4, column=0, sticky="w", pady=5)
        self.local_path_row = self.ttk.Frame(form)
        self.local_path_row.grid(row=4, column=1, sticky="ew", pady=5)
        self.ttk.Entry(
            self.local_path_row, textvariable=self.local_model_path, state="readonly"
        ).pack(side="left", fill="x", expand=True)
        self.ttk.Button(
            self.local_path_row, text="Choose model folder…", command=self._choose_model_folder
        ).pack(side="left", padx=8)
        self.model_hint = self.ttk.Label(
            form,
            text="Use exactly one source: a local model folder or cloud API credentials.",
            style="Muted.TLabel",
        )
        self.model_hint.grid(row=8, column=1, sticky="w")
        self.ttk.Button(
            form, text="Save model", command=self._add_registered_model, style="Accent.TButton"
        ).grid(row=9, column=1, sticky="e", pady=10)
        self.ttk.Button(form, text="New model", command=self._reset_model_form).grid(
            row=9, column=0, sticky="w", pady=10
        )
        self._update_model_controls()
        self.settings_chat_rows = self.ttk.Frame(self.chats_page)
        self.settings_chat_rows.pack(fill="both", expand=True)
        columns = ("model", "chat", "input", "output", "total", "calls")
        self.usage_table = self.ttk.Treeview(self.usage_page, columns=columns, show="headings")
        for column in columns:
            self.usage_table.heading(column, text=column.title())
            self.usage_table.column(column, width=140)
        self.usage_table.pack(fill="both", expand=True)
        self._refresh_settings_scene()

    def _add_registered_model(self, validated_values: dict | None = None) -> None:
        from tkinter import messagebox

        values = validated_values or {
            key: var.get().strip() for key, var in self.model_form.items()
        }
        try:
            if not values["Name"]:
                raise ValueError("Enter a model name.")
            validate_model_standard(values["Adapter"], values["Role"], values["Deployment"])
            if values["Deployment"] == "online" and not values["Model identifier"]:
                raise ValueError("Enter the provider model identifier to validate its capability.")
            if values["Deployment"] == "local":
                if not self.local_model_path.get():
                    raise ValueError("Choose the local model folder.")
                discovered = discover_local_model(self.local_model_path.get(), values["Role"])
                if discovered["adapter"] != values["Adapter"]:
                    raise ValueError("Selected folder does not match the chosen model adapter.")
                values["Model identifier"] = discovered["model_identifier"]
                values["Location"] = discovered["endpoint"] or {
                    "diffusiongemma": "http://127.0.0.1:11434",
                    "llada": "http://127.0.0.1:8002",
                    "openai_compatible": "http://127.0.0.1:8002",
                    "laya_local": "http://127.0.0.1:8000",
                    "djev_local": "http://127.0.0.1:8000",
                    "native_dlm": "http://127.0.0.1:8002",
                }.get(values["Adapter"], "http://127.0.0.1:8000")
                values["API key"] = ""
            elif not values["Location"]:
                raise ValueError("Enter the cloud API endpoint.")
            from urllib.parse import urlparse

            endpoint = urlparse(values["Location"])
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
                raise ValueError("Enter a valid API URL, such as https://provider.example/v1.")
            if values["Deployment"] == "local" and endpoint.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                raise ValueError("Local models must use a loopback server endpoint.")
            if values["Deployment"] == "online" and validated_values is None:
                from tkinter import messagebox

                if not messagebox.askyesno(
                    "Validate cloud model",
                    "Send a small capability test before saving? This may consume API tokens.",
                    parent=self.root,
                ):
                    return
                model_id = self.editing_model_id
                key = values["API key"] or (
                    self.secret_store.get(f"api_key:{model_id}") if model_id else ""
                )
                self.status_var.set("Validating cloud model…")
                threading.Thread(
                    target=self._validate_cloud_registration,
                    args=(values, key, model_id),
                    daemon=True,
                ).start()
                return
            parameters = {
                "name": values["Name"],
                "role": values["Role"],
                "deployment": values["Deployment"],
                "adapter": values["Adapter"],
                "location": values["Location"],
                "model_identifier": values["Model identifier"],
                "local_path": self.local_model_path.get()
                if values["Deployment"] == "local"
                else "",
            }
            if self.editing_model_id:
                model_id = self.editing_model_id
                self.memory.update_model(model_id, **parameters)
            else:
                model_id = self.memory.add_model(self.account, **parameters)
            if values["API key"]:
                self.secret_store.set(
                    f"api_key:{model_id}",
                    "" if values["API key"] == "REMOVE" else values["API key"],
                )
            self.model_form["API key"].set("")
            self._refresh_settings_scene()
            self._refresh_quick_model_choices()
            self._activate_chat_models(self.chat_id)
            self._update_active_model_label()
            self.status_var.set("Model registered")
        except Exception as error:  # noqa: BLE001 - GUI boundary
            messagebox.showerror("Model registration", str(error), parent=self.root)

    def _validate_cloud_registration(self, values: dict, key: str, model_id: str | None) -> None:
        try:
            asyncio.run(
                validate_cloud_model(
                    values["Location"], key, values["Model identifier"], values["Role"]
                )
            )
        except Exception as error:  # noqa: BLE001 - normalize service failure without printing keys
            detail = (
                str(error)
                if isinstance(error, ValueError)
                else "Service unreachable; model type could not be verified."
            )
            self.root.after(0, self._show_error, "Model validation", detail)
            return

        def save():
            current = {key: var.get().strip() for key, var in self.model_form.items()}
            if self.editing_model_id != model_id or current != values:
                self.status_var.set("Model selection changed; please validate again")
                return
            self._add_registered_model(values)

        self.root.after(0, save)

    def _reset_model_form(self) -> None:
        self.editing_model_id = None
        self.local_model_path.set("")
        self.discovered_model = None
        for field in ("Name", "Location", "Model identifier", "API key"):
            self.model_form[field].set("")

    def _update_model_controls(self) -> None:
        local = self.model_form["Deployment"].get() == "local"
        standards = ADAPTER_STANDARDS.get(
            (self.model_form["Role"].get(), self.model_form["Deployment"].get()), ()
        )
        self.model_widgets["Adapter"].configure(values=standards)
        if self.model_form["Adapter"].get() not in standards and standards:
            self.model_form["Adapter"].set(standards[0])
        if local:
            self.local_path_row.grid()
            self.local_path_label.grid()
            self.model_widgets["Location"].grid_remove()
            self.model_labels["Location"].grid_remove()
            self.model_widgets["API key"].grid_remove()
            self.model_labels["API key"].grid_remove()
            self.model_widgets["Model identifier"].grid_remove()
            self.model_labels["Model identifier"].grid_remove()
        else:
            self.local_path_row.grid_remove()
            self.local_path_label.grid_remove()
            self.model_widgets["Location"].grid()
            self.model_labels["Location"].grid()
            self.model_widgets["API key"].grid()
            self.model_labels["API key"].grid()
            self.model_widgets["Model identifier"].grid()
            self.model_labels["Model identifier"].grid()
            defaults = {
                "mercury": ("https://api.inceptionlabs.ai/v1", "mercury-2.5"),
                "jev_cloud": ("https://api.typesafe.ai", "jev-latest"),
            }
            default = defaults.get(self.model_form["Adapter"].get())
            if default:
                if not self.model_form["Location"].get().strip():
                    self.model_form["Location"].set(default[0])
                if not self.model_form["Model identifier"].get().strip():
                    self.model_form["Model identifier"].set(default[1])
        self.model_hint.configure(
            text=(
                "Choose the folder containing model metadata and weights. No API key is used."
                if local
                else (
                    "API URL = provider address; Model name = model served there; API key = access. "
                    "Mercury and Jev defaults are filled automatically."
                )
            )
        )

    def _choose_model_folder(self) -> None:
        from tkinter import filedialog, messagebox

        folder = filedialog.askdirectory(title="Select local model folder", parent=self.root)
        if not folder:
            return
        try:
            model = discover_local_model(folder, self.model_form["Role"].get())
            self.local_model_path.set(model["path"])
            self.discovered_model = model
            self.model_form["Adapter"].set(model["adapter"])
            self.model_form["Model identifier"].set(model["model_identifier"])
            if model["endpoint"]:
                self.model_form["Location"].set(model["endpoint"])
            self.status_var.set("Model found · configure its running local runtime")
        except (ValueError, OSError) as error:
            messagebox.showerror("Local model", str(error), parent=self.root)

    def _model_context_menu(self, event) -> None:
        from tkinter import messagebox

        model_id = self.model_table.identify_row(event.y)
        if not model_id:
            return
        model = next(item for item in self.memory.list_models(self.account) if item.id == model_id)

        def edit():
            self.local_model_path.set("")
            self.editing_model_id = model_id
            for field, value in (
                ("Name", model.name),
                ("Role", model.role),
                ("Deployment", model.deployment),
                ("Adapter", model.adapter),
                ("Location", model.location),
                ("Model identifier", model.model_identifier),
            ):
                self.model_form[field].set(value)
            self.local_model_path.set(model.local_path)
            self.model_form["API key"].set("")
            self._update_model_controls()

        def delete():
            if any(
                model_id in (selection.language_model_id, selection.decision_model_id)
                for selection in (
                    self.memory.get_chat_models(chat.id)
                    for chat in self.memory.list_chats(self.account)
                )
            ):
                messagebox.showinfo(
                    "Model in use",
                    "Change the chats using this model before deleting it.",
                    parent=self.root,
                )
                return
            if messagebox.askyesno(
                "Delete model", f"Delete '{model.name}' from the registry?", parent=self.root
            ):
                self.secret_store.set(f"api_key:{model_id}", "")
                self.memory.delete_model(model_id)
                self._refresh_settings_scene()

        menu = self.tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Edit model / API key", command=edit)
        menu.add_command(label="Delete", command=delete)
        menu.tk_popup(event.x_root, event.y_root)

    def _refresh_settings_scene(self) -> None:
        if not hasattr(self, "model_table"):
            return
        self.model_table.delete(*self.model_table.get_children())
        models = self.memory.list_models(self.account)
        for model in models:
            source = (
                model.local_path or f"Built-in runtime · {model.location}"
                if model.deployment == "local"
                else model.location
            )
            self.model_table.insert(
                "",
                "end",
                iid=model.id,
                values=(model.name, model.role, model.deployment, model.adapter, source),
            )
        for child in self.settings_chat_rows.winfo_children():
            child.destroy()
        self._refresh_quick_model_choices()
        language_map = self._model_choice_map("language")
        decision_map = self._model_choice_map("decision")
        language_by_id = {model_id: label for label, model_id in language_map.items()}
        decision_by_id = {model_id: label for label, model_id in decision_map.items()}
        self.ttk.Label(
            self.settings_chat_rows,
            text="All chats · base models are saved independently for every chat",
            style="Section.TLabel",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        self.ttk.Label(self.settings_chat_rows, text="Chat name").grid(row=1, column=0, sticky="w")
        self.ttk.Label(self.settings_chat_rows, text="Language model · DLM / LLM").grid(
            row=1, column=1
        )
        self.ttk.Label(self.settings_chat_rows, text="Decision model · Jev / Laya").grid(
            row=1, column=2
        )
        groups = [("No project", self.memory.list_unassigned_chats(self.account))]
        groups.extend(
            (project.name, self.memory.list_chats(self.account, project.id))
            for project in self.memory.list_projects(self.account)
        )
        row = 2
        for group_name, chats in groups:
            self.ttk.Label(
                self.settings_chat_rows,
                text=f"▾  {group_name}  ·  {len(chats)} chat{'s' if len(chats) != 1 else ''}",
                style="PanelMuted.TLabel",
            ).grid(row=row, column=0, columnspan=4, sticky="ew", pady=(14, 4))
            row += 1
            for chat in chats:
                self._ensure_chat_model_defaults(chat.id)
                selection = self.memory.get_chat_models(chat.id)
                name = self.tk.StringVar(value=chat.title)
                language = self.tk.StringVar(
                    value=language_by_id.get(selection.language_model_id, "")
                )
                decision = self.tk.StringVar(
                    value=decision_by_id.get(selection.decision_model_id, "")
                )
                self.ttk.Entry(self.settings_chat_rows, textvariable=name).grid(
                    row=row, column=0, padx=6, pady=8, sticky="ew"
                )
                self.ttk.Combobox(
                    self.settings_chat_rows,
                    textvariable=language,
                    values=list(language_map),
                    state="readonly",
                ).grid(row=row, column=1, padx=6, pady=8, sticky="ew")
                self.ttk.Combobox(
                    self.settings_chat_rows,
                    textvariable=decision,
                    values=list(decision_map),
                    state="readonly",
                ).grid(row=row, column=2, padx=6, pady=8, sticky="ew")

                def save(cid=chat.id, nv=name, lv=language, dv=decision):
                    from tkinter import messagebox

                    previous = self.memory.get_chat_models(cid)
                    try:
                        self.memory.set_chat_models(
                            cid, language_map[lv.get()], decision_map[dv.get()]
                        )
                        self.memory.rename_chat(cid, nv.get())
                        if cid == self.chat_id:
                            self._activate_chat_models(cid)
                            self._update_active_model_label()
                        self._refresh_project_nav()
                        self._refresh_chats(select_id=self.chat_id)
                        self.status_var.set("Chat settings saved")
                    except Exception as error:  # noqa: BLE001 - GUI boundary
                        self.memory.set_chat_models(
                            cid, previous.language_model_id, previous.decision_model_id
                        )
                        if cid == self.chat_id:
                            self._activate_chat_models(cid)
                            self._update_active_model_label()
                        messagebox.showerror("Chat settings", str(error), parent=self.root)

                self.ttk.Button(self.settings_chat_rows, text="Save", command=save).grid(
                    row=row, column=3, padx=6, pady=8
                )
                row += 1
        for column in range(3):
            self.settings_chat_rows.columnconfigure(column, weight=1)
        self.usage_table.delete(*self.usage_table.get_children())
        chat_names = {item.id: item.title for item in self.memory.list_chats(self.account)}
        for usage in self.memory.usage_summary(self.account):
            self.usage_table.insert(
                "",
                "end",
                values=(
                    usage.model,
                    chat_names.get(usage.chat_id, "Deleted chat"),
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    usage.calls,
                ),
            )

    def _open_data_folder(self) -> None:
        if sys.platform == "win32":
            os.startfile(self.memory.data_dir)
        else:
            self.status_var.set(str(self.memory.data_dir))

    def _request_in_progress(self) -> bool:
        busy = hasattr(self, "decide_button") and "disabled" in self.decide_button.state()
        if busy:
            self.status_var.set("Finishing the current request…")
        return busy

    def _show_error(self, title: str, detail: str) -> None:
        from tkinter import messagebox

        self.status_var.set("Unavailable")
        self.status_dot.configure(fg=COLORS["danger"])
        self.decide_button.configure(state="normal")
        messagebox.showerror(
            "Decision failed",
            f"{title}: {detail}\n\nCheck that the configured model runtime is running.",
            parent=self.root,
        )

    def _copy_json(self) -> None:
        if not self.raw_json:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.raw_json)
        self.status_var.set("JSON copied")
        self.root.after(1500, lambda: self.status_var.set("Ready"))

    def run(self) -> None:
        self.root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dicojev-gui", description="Open the native DiCoJev Decision Studio."
    )
    parser.add_argument("--config", default=str(PACKAGED_DEFAULT_CONFIG))
    parser.add_argument("--account", default="default", help="Local profile name")
    parser.add_argument("--data-dir", help="Override the private local data folder")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    memory = LocalMemoryStore(args.data_dir)
    secret_store = SecretStore(memory.data_dir)
    config = load_config(args.config)
    model_name = config.get("model", {}).get("generator_model", "llada-v-local")
    api_key = secret_store.get(f"api_key:{model_name}")
    DiCoJevDesktop(
        DirectClient.from_config(config, api_key=api_key),
        account=args.account,
        memory=memory,
        secret_store=secret_store,
        config=config,
    ).run()


if __name__ == "__main__":
    main()
