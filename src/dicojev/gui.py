"""Small native desktop interface for the direct DiCoJev runtime."""

from __future__ import annotations

import argparse
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
from .errors import GeneratorUnavailable
from .intent import IntentDraft, fallback_intent_draft
from .memory import LocalMemoryStore
from .multimedia import LocalMediaIngestor
from .routing import DirectAnswer, route_direct_answer
from .schemas import DecisionRequest, DecisionResponse, ImageRef, MultimodalState
from .secrets import SecretStore
from .workspace import ProjectWorkspace

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
    ) -> None:
        self.dpi_mode = enable_high_dpi()
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.client = client
        self.account = account.strip() or "default"
        self.memory = memory or LocalMemoryStore(data_dir)
        self.secret_store = secret_store or SecretStore(self.memory.data_dir)
        self.secret_name = f"api_key:{self.client.model_name}"
        self.memory.ensure_account(self.account)
        stored_key = self.secret_store.get(self.secret_name)
        if stored_key:
            self.client.configure_api_key(stored_key)
        chats = self.memory.list_chats(self.account)
        self.chat_id = chats[0].id if chats else self.memory.create_chat(self.account)
        self.ingestor = LocalMediaIngestor()
        self.attachment_paths: list[str] = []
        self._placeholder_active: set[Any] = set()
        self._placeholder_text: dict[Any, str] = {}
        self.raw_json = ""
        self.root = tk.Tk()
        self.root.title("DiCoJev — Decision Studio")
        dpi = self.root.winfo_fpixels("1i")
        self.root.tk.call("tk", "scaling", dpi / 72.0)
        self.root.geometry("1180x800")
        self.root.minsize(980, 680)
        self.root.configure(bg=COLORS["window"])
        self._set_window_icon()
        self._configure_styles()
        self._build()

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
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("Alt.TFrame", background=COLORS["panel_alt"])
        style.configure(
            "TLabel",
            background=COLORS["window"],
            foreground=COLORS["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=COLORS["window"],
            foreground=COLORS["muted"],
            font=("Segoe UI", 9),
        )
        style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("PanelMuted.TLabel", background=COLORS["panel"], foreground=COLORS["muted"])
        style.configure(
            "Title.TLabel",
            background=COLORS["window"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "Section.TLabel",
            background=COLORS["panel"],
            foreground=COLORS["text"],
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "Accent.TButton",
            background=COLORS["accent"],
            foreground="#17120a",
            borderwidth=0,
            padding=(18, 11),
            font=("Segoe UI Semibold", 10),
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
            padding=(12, 8),
        )
        style.map("Quiet.TButton", background=[("active", COLORS["border"])])

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
            pady=9,
            font=("Segoe UI", 10),
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
            font=("Segoe UI", 10),
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
        widget.bind("<FocusIn>", lambda _event, target=widget: self._hide_placeholder(target))
        widget.bind("<FocusOut>", lambda _event, target=widget: self._restore_placeholder(target))

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
        self.ttk.Label(parent, text=text, style="PanelMuted.TLabel").pack(anchor="w", pady=(10, 5))

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
        status = self.ttk.Frame(header)
        status.pack(side="right")
        self.status_dot = self.tk.Label(
            status, text="●", bg=COLORS["window"], fg=COLORS["good"], font=("Segoe UI", 9)
        )
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_var = self.tk.StringVar(value="Ready")
        self.ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")

        body = self.ttk.Frame(self.root, padding=(28, 0, 28, 24))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, minsize=260)
        body.columnconfigure(1, weight=5, uniform="column")
        body.columnconfigure(2, weight=6, uniform="column")
        body.rowconfigure(0, weight=1)

        sidebar = self.ttk.Frame(body, style="Panel.TFrame", padding=14)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        inputs = self.ttk.Frame(body, style="Panel.TFrame", padding=20)
        inputs.grid(row=0, column=1, sticky="nsew", padx=8)
        outputs = self.ttk.Frame(body, style="Panel.TFrame", padding=20)
        outputs.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        self._build_sidebar(sidebar)
        self._build_inputs(inputs)
        self._build_outputs(outputs)

    def _build_sidebar(self, parent) -> None:
        self.ttk.Label(parent, text="Chats", style="Section.TLabel").pack(anchor="w")
        self.ttk.Label(
            parent, text=f"Local profile · {self.account}", style="PanelMuted.TLabel"
        ).pack(anchor="w", pady=(2, 10))
        chat_actions = self.ttk.Frame(parent, style="Panel.TFrame")
        chat_actions.pack(fill="x", pady=(0, 8))
        self.ttk.Button(
            chat_actions, text="＋ New", style="Quiet.TButton", command=self._new_chat
        ).pack(side="left", fill="x", expand=True)
        self.ttk.Button(
            chat_actions, text="Rename", style="Quiet.TButton", command=self._rename_chat
        ).pack(side="left", padx=(4, 0))
        self.ttk.Button(
            chat_actions, text="Delete", style="Quiet.TButton", command=self._delete_chat
        ).pack(side="left", padx=(4, 0))
        self.chat_list = self.tk.Listbox(
            parent,
            bg=COLORS["field"],
            fg=COLORS["text"],
            selectbackground="#49606b",
            selectforeground=COLORS["text"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
        )
        self.chat_list.pack(fill="both", expand=True)
        self.chat_list.bind("<<ListboxSelect>>", self._select_chat)
        self.ttk.Label(parent, text="Project", style="Section.TLabel").pack(
            anchor="w", pady=(12, 5)
        )
        self.project_var = self.tk.StringVar(value="No project")
        self.project_box = self.ttk.Combobox(
            parent, textvariable=self.project_var, state="readonly", height=6
        )
        self.project_box.pack(fill="x")
        self.project_box.bind("<<ComboboxSelected>>", self._select_project)
        self.ttk.Button(
            parent, text="Add project folder", style="Quiet.TButton", command=self._add_project
        ).pack(fill="x", pady=(5, 0))
        self.ttk.Button(
            parent, text="Browse project files", style="Quiet.TButton", command=self._browse_project
        ).pack(fill="x", pady=(5, 0))
        self.ttk.Button(
            parent, text="Open data folder", style="Quiet.TButton", command=self._open_data_folder
        ).pack(fill="x", pady=(8, 0))
        self.ttk.Button(
            parent, text="Settings", style="Quiet.TButton", command=self._open_settings
        ).pack(fill="x", pady=(5, 0))
        self._refresh_chats(select_id=self.chat_id)
        self._refresh_projects()
        self._refresh_history()

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
        self.context = self._text(parent, height=5)
        self.context.pack(fill="x")
        self._add_placeholder(
            self.context,
            "Describe the situation, evidence, and uncertainty.\n"
            "Example: A customer reports two similar card charges; identity is verified.",
        )
        self._field_label(parent, "GOAL")
        self.goal = self._text(parent, height=2)
        self.goal.pack(fill="x")
        self._add_placeholder(
            self.goal,
            "State the desired outcome, or leave blank for intent drafting.\n"
            "Example: Choose the safest next support action.",
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
        self._field_label(advanced, "STRUCTURED STATE  ·  optional JSON object")
        self.structured = self._text(advanced, height=2)
        self.structured.pack(fill="x")
        self._add_placeholder(
            self.structured,
            "Add optional machine-readable facts as one JSON object.\n"
            'Example: {"identity_verified": true, "charge_count": 2}',
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
            buttons, text="Understand for me", style="Quiet.TButton", command=self._infer_intent
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
            pady=5,
            font=("Segoe UI Semibold", 9),
        )
        self.action_badge.pack(side="right")

        self.conversation_text = self.tk.Text(
            parent,
            height=17,
            wrap="word",
            bg=COLORS["field"],
            fg=COLORS["text"],
            relief="flat",
            borderwidth=0,
            padx=13,
            pady=11,
            font=("Segoe UI", 9),
            state="disabled",
        )
        self.conversation_text.tag_configure(
            "request_label", justify="right", foreground=COLORS["accent"], spacing1=8
        )
        self.conversation_text.tag_configure(
            "request", justify="right", foreground=COLORS["text"], lmargin1=65, lmargin2=65
        )
        self.conversation_text.tag_configure(
            "decision_label", justify="left", foreground=COLORS["info"], spacing1=8
        )
        self.conversation_text.tag_configure(
            "decision", justify="left", foreground=COLORS["text"], rmargin=65
        )
        self.conversation_text.pack(fill="both", expand=True, pady=(10, 10))
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
            font=("Segoe UI Semibold", 15),
        ).pack(fill="x", pady=(7, 10))

        metrics = self.ttk.Frame(parent, style="Panel.TFrame")
        metrics.pack(fill="x")
        self.coverage_var = self._metric(metrics, "COVERAGE", "—", 0)
        self.confidence_var = self._metric(metrics, "CONFIDENCE", "—", 1)
        self.feedback_var = self._metric(metrics, "FEEDBACK", "—", 2)

        self.ttk.Label(parent, text="Candidates", style="Section.TLabel").pack(
            anchor="w", pady=(12, 5)
        )
        self.candidate_text = self._output_box(parent, height=4)
        self.candidate_text.pack(fill="x")
        self.ttk.Label(parent, text="Controller trace", style="Section.TLabel").pack(
            anchor="w", pady=(10, 5)
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
            font=("Segoe UI Semibold", 8),
        ).pack(anchor="w")
        variable = self.tk.StringVar(value=value)
        self.tk.Label(
            card,
            textvariable=variable,
            bg=COLORS["panel_alt"],
            fg=COLORS["text"],
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(4, 0))
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

        if not self._field_value(self.goal):
            self._infer_intent()
            return
        try:
            request = self._request()
        except (ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Check the request", str(error), parent=self.root)
            return
        self.decide_button.configure(state="disabled")
        self.status_var.set("Thinking…")
        self.status_dot.configure(fg=COLORS["accent"])
        attachments = tuple(self.attachment_paths)
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
            target=self._run_decision, args=(request, attachments, chat_id), daemon=True
        ).start()

    def _run_decision(
        self, request: DecisionRequest, attachments: tuple[str, ...], chat_id: str
    ) -> None:
        try:
            request = self.ingestor.enrich_request(request, attachments)
            response = self.client.decide_sync(request)
            presentation = present_response(response)
        except Exception as error:  # noqa: BLE001 - GUI boundary presents normalized failure
            self.root.after(0, self._show_error, type(error).__name__, str(error))
            return
        self.root.after(0, self._show_result, presentation, response, chat_id)

    def _show_result(
        self, result: DecisionPresentation, response: DecisionResponse, chat_id: str
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
            self.account, chat_id, self.client.model_name, "decision", self.client.usage_snapshot()
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
        threading.Thread(
            target=self._run_intent_inference,
            args=(context, history, self.chat_id),
            daemon=True,
        ).start()

    def _run_intent_inference(self, context: str, history: tuple[str, ...], chat_id: str) -> None:
        direct = route_direct_answer(context)
        if direct is not None:
            self.root.after(0, self._show_direct_answer, direct, context, chat_id)
            return
        used_fallback = False
        try:
            draft = self.client.infer_intent_sync(context, history)
        except GeneratorUnavailable:
            draft = fallback_intent_draft(context)
            used_fallback = True
        except Exception as error:  # noqa: BLE001 - GUI boundary
            self.root.after(0, self._show_error, type(error).__name__, str(error))
            return
        self.root.after(0, self._show_intent, draft, chat_id, used_fallback)

    def _show_intent(self, draft: IntentDraft, chat_id: str, used_fallback: bool = False) -> None:
        from tkinter import messagebox

        self._set_field(self.goal, draft.goal)
        if draft.constraints:
            self._set_field(self.constraints, "\n".join(draft.constraints))
        if draft.suggested_tools:
            self._set_field(self.tools, "\n".join(draft.suggested_tools))
        status = "Offline draft" if used_fallback else "Intent drafted"
        self.status_var.set(f"{status} · {draft.confidence:.0%} confidence")
        self.status_dot.configure(fg=COLORS["warn"] if used_fallback else COLORS["info"])
        self.decide_button.configure(state="normal")
        self.memory.record_usage(
            self.account,
            chat_id,
            self.client.model_name,
            "intent",
            self.client.intent_inferer.last_usage if self.client.intent_inferer else {},
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
                    "summary": f"Drafted goal: {draft.goal}",
                },
            )
            self._refresh_chats(select_id=chat_id)
            self._refresh_history()
        note = draft.instruction
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
        self._chat_rows = self.memory.list_chats(self.account)
        self.chat_list.delete(0, "end")
        for index, chat in enumerate(self._chat_rows):
            self.chat_list.insert("end", chat.title)
            if chat.id == select_id:
                self.chat_list.selection_set(index)

    def _new_chat(self) -> None:
        self.chat_id = self.memory.create_chat(self.account)
        for widget in (self.context, self.goal, self.tools, self.constraints, self.structured):
            self._show_placeholder(widget)
        self._clear_attachments()
        self.action_var.set("WAITING")
        self.selected_var.set("Submit a decision to begin.")
        self.project_var.set("No project")
        self._refresh_chats(select_id=self.chat_id)
        self._refresh_history()

    def _rename_chat(self) -> None:
        from tkinter import simpledialog

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

        current = next((chat for chat in self._chat_rows if chat.id == self.chat_id), None)
        if not current or not messagebox.askyesno(
            "Delete chat",
            f"Permanently delete '{current.title}' and its local history?",
            parent=self.root,
        ):
            return
        self.memory.delete_chat(self.chat_id)
        chats = self.memory.list_chats(self.account)
        self.chat_id = chats[0].id if chats else self.memory.create_chat(self.account)
        self._refresh_chats(select_id=self.chat_id)
        selected = next(chat for chat in self._chat_rows if chat.id == self.chat_id)
        self._load_chat(selected)

    def _select_chat(self, _event=None) -> None:
        selection = self.chat_list.curselection()
        if not selection:
            return
        chat = self._chat_rows[selection[0]]
        if chat.id == self.chat_id:
            return
        self.chat_id = chat.id
        self._load_chat(chat)

    def _load_chat(self, chat) -> None:
        latest = self.memory.latest_turn(chat.id, "user") or {}
        self._set_field(self.context, latest.get("context", ""))
        self._set_field(self.goal, latest.get("goal", ""))
        self._set_field(self.tools, "\n".join(latest.get("tools", ())))
        self._set_field(self.constraints, "\n".join(latest.get("constraints", ())))
        result = self.memory.latest_turn(chat.id, "assistant")
        self.selected_var.set(
            result.get("summary", "No decision yet.") if result else "No decision yet."
        )
        project = self.memory.get_chat_project(chat.id)
        self.project_var.set(project.name if project else "No project")
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

    def _refresh_projects(self) -> None:
        self._project_rows = self.memory.list_projects(self.account)
        values = ("No project", *(item.name for item in self._project_rows))
        self.project_box.configure(values=values)

    def _add_project(self) -> None:
        from tkinter import filedialog

        selected = filedialog.askdirectory(title="Choose an agent project folder")
        if not selected:
            return
        path = Path(selected).resolve()
        project_id = self.memory.create_project(self.account, path.name, str(path))
        self.memory.set_chat_project(self.chat_id, project_id)
        self._refresh_projects()
        self.project_var.set(path.name)

    def _select_project(self, _event=None) -> None:
        index = self.project_box.current()
        project_id = None if index <= 0 else self._project_rows[index - 1].id
        self.memory.set_chat_project(self.chat_id, project_id)

    def _browse_project(self) -> None:
        from tkinter import messagebox

        project = self.memory.get_chat_project(self.chat_id)
        if project is None:
            messagebox.showinfo(
                "Choose a project", "Add or select a project folder first.", parent=self.root
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
        window = self.tk.Toplevel(self.root)
        window.title("DiCoJev Settings")
        window.geometry("820x560")
        window.configure(bg=COLORS["window"])
        frame = self.ttk.Frame(window, padding=22)
        frame.pack(fill="both", expand=True)
        self.ttk.Label(frame, text="Settings", style="Title.TLabel").pack(anchor="w")
        self.ttk.Label(frame, text=f"Model · {self.client.model_name}", style="Muted.TLabel").pack(
            anchor="w", pady=(0, 16)
        )
        self.ttk.Label(frame, text="MODEL API KEY", style="Muted.TLabel").pack(anchor="w")
        key_var = self.tk.StringVar()
        key_entry = self.tk.Entry(
            frame,
            textvariable=key_var,
            show="•",
            bg=COLORS["field"],
            fg=COLORS["text"],
            insertbackground=COLORS["accent"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        key_entry.pack(fill="x", ipady=8, pady=(5, 5))
        key_status = (
            "A key is stored." if self.secret_store.has(self.secret_name) else "No key stored."
        )
        self.ttk.Label(
            frame,
            text=(
                f"{key_status} Protected for this Windows user with DPAPI. "
                "Blank keeps it; enter REMOVE to delete it."
            ),
            style="Muted.TLabel",
        ).pack(anchor="w")

        def save_key() -> None:
            value = key_var.get().strip()
            if value == "REMOVE":
                self.secret_store.set(self.secret_name, "")
                self.client.configure_api_key(None)
                self.status_var.set("API key removed")
            elif value:
                self.secret_store.set(self.secret_name, value)
                self.client.configure_api_key(value)
                self.status_var.set("API key saved securely")
            key_var.set("")

        self.ttk.Button(frame, text="Save key", style="Accent.TButton", command=save_key).pack(
            anchor="e", pady=(8, 18)
        )
        self.ttk.Label(frame, text="Token usage by model and chat", style="Section.TLabel").pack(
            anchor="w", pady=(0, 7)
        )
        columns = ("model", "chat", "input", "output", "total", "calls")
        usage_table = self.ttk.Treeview(frame, columns=columns, show="headings", height=12)
        headings = {
            "model": "Model",
            "chat": "Chat",
            "input": "Input",
            "output": "Output",
            "total": "Total",
            "calls": "Calls",
        }
        for column in columns:
            usage_table.heading(column, text=headings[column])
            usage_table.column(column, width=190 if column == "model" else 85, anchor="w")
        chat_names = {chat.id: chat.title for chat in self.memory.list_chats(self.account)}
        for usage in self.memory.usage_summary(self.account):
            usage_table.insert(
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
        usage_table.pack(fill="both", expand=True)

    def _open_data_folder(self) -> None:
        if sys.platform == "win32":
            os.startfile(self.memory.data_dir)
        else:
            self.status_var.set(str(self.memory.data_dir))

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
    ).run()


if __name__ == "__main__":
    main()
