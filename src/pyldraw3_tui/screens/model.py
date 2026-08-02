"""Read-only model browser: pieces, stats, bill of materials, and issues."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ldraw import iter_instruction_issues
from ldraw.bom import bill_of_materials
from ldraw.errors import UnknownSubmodelError
from ldraw.validation import ValidationIssue, iter_ldr_issues
from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Select, Static, TabbedContent, TabPane

from pyldraw3_tui.errors import ModelLoadError
from pyldraw3_tui.widgets.bom_table import BomTable
from pyldraw3_tui.widgets.directives_table import DirectivesTable
from pyldraw3_tui.widgets.instruction_details import InstructionDetails
from pyldraw3_tui.widgets.issues_table import IssuesTable
from pyldraw3_tui.widgets.piece_table import PieceTable
from pyldraw3_tui.widgets.stats_panel import StatsPanel

if TYPE_CHECKING:
    from ldraw.bom import BomRow
    from ldraw.instructions import (
        InstructionDocument,
        InstructionSection,
        InstructionStep,
    )
    from ldraw.model import Model
    from ldraw.parts import Parts
    from textual.app import ComposeResult

    from pyldraw3_tui.data.source import CatalogSource

ROOT_KEY = "__root__"
MODEL_MODE = "model"
INSTRUCTIONS_MODE = "instructions"
_INSTRUCTION_ONLY_TABS = ("tab-pli", "tab-directives")


class ModelView(Vertical):
    """Whole-model and semantic instruction views of one LDraw document."""

    BINDINGS: ClassVar = [
        Binding("i", "toggle_instructions", "Toggle instructions", show=False),
        Binding(
            "left_square_bracket",
            "previous_instruction_step",
            "Previous instruction step",
            key_display="[",
            show=False,
        ),
        Binding(
            "right_square_bracket",
            "next_instruction_step",
            "Next instruction step",
            key_display="]",
            show=False,
        ),
    ]

    DEFAULT_CSS = """
    ModelView > #model-topbar {
        height: 3;
        padding: 0 1;
    }
    ModelView #model-title {
        width: 1fr;
        content-align: left middle;
        height: 3;
    }
    ModelView #view-mode-select {
        width: 20;
    }
    ModelView #submodel-select {
        width: 32;
    }
    ModelView #instruction-section-select {
        display: none;
        width: 28;
    }
    ModelView #instruction-step-select {
        display: none;
        width: 14;
    }
    ModelView.instructions #submodel-select {
        display: none;
    }
    ModelView.instructions #instruction-section-select,
    ModelView.instructions #instruction-step-select {
        display: block;
    }
    ModelView #instruction-details {
        display: none;
        border-top: solid $primary-muted;
        margin-top: 1;
        padding-top: 1;
        height: auto;
    }
    ModelView.instructions #instruction-details {
        display: block;
    }
    ModelView #model-error {
        display: none;
        border: round $error;
        margin: 1 2;
        padding: 1 2;
        height: auto;
    }
    ModelView.errored #model-error {
        display: block;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:  # noqa: A002 - Textual idiom
        super().__init__(id=id)
        self._source: CatalogSource | None = None
        self._parts: Parts | None = None
        self._model: Model | None = None
        self._path: Path | None = None
        self._selected_key = ROOT_KEY
        self._view_mode = MODEL_MODE
        self._instruction_document: InstructionDocument | None = None
        self._selected_instruction_section: str | None = None
        self._selected_instruction_step = 1
        self._step_occurrence_counts: tuple[int, ...] | None = None
        self._step_counts_section: str | None = None

    def compose(self) -> ComposeResult:
        """Lay out the top bar and the three tabs."""
        with Horizontal(id="model-topbar"):
            yield Static("No model open — try :Open model…", id="model-title")
            yield Select[str](
                [("Whole model", MODEL_MODE), ("Instructions", INSTRUCTIONS_MODE)],
                value=MODEL_MODE,
                allow_blank=False,
                id="view-mode-select",
            )
            yield Select[str](
                [],
                prompt="Submodel",
                allow_blank=True,
                id="submodel-select",
            )
            yield Select[str](
                [],
                prompt="Section",
                allow_blank=True,
                id="instruction-section-select",
            )
            yield Select[int](
                [],
                prompt="Step",
                allow_blank=True,
                id="instruction-step-select",
            )
        yield Static("", id="model-error")
        with TabbedContent(id="model-tabs"):
            with TabPane("Pieces", id="tab-pieces"):
                yield PieceTable(id="piece-table")
            with TabPane("Summary", id="tab-summary"), VerticalScroll():
                yield StatsPanel(id="stats-panel")
                yield InstructionDetails(id="instruction-details")
            with TabPane("PLI", id="tab-pli"):
                yield BomTable(id="pli-table")
            with TabPane("BOM", id="tab-bom"):
                yield BomTable(id="bom-table")
            with TabPane("Directives", id="tab-directives"):
                yield DirectivesTable(id="directives-table")
            with TabPane("Issues", id="tab-issues"):
                yield IssuesTable(id="issues-table")

    def on_mount(self) -> None:
        """Apply the initial whole-model control and tab visibility."""
        self._sync_mode_ui()

    def set_source(self, source: CatalogSource) -> None:
        """Provide the source used to open model files."""
        self._source = source

    def set_parts(self, parts: Parts) -> None:
        """Provide the catalog for descriptions and colour names."""
        self._parts = parts
        if self._model is not None:
            self._build_instruction_document(reset=False)
            self._render_model()
        if self._path is not None:
            self._render_issues()

    @property
    def bom_rows(self) -> list[BomRow]:
        """The currently displayed bill-of-materials rows."""
        return self.query_one("#bom-table", BomTable).rows_data

    def load_model(self, path: Path | str) -> None:
        """Open a model file and show its root model."""
        if self._source is None:
            return
        self._path = Path(path)
        try:
            model = self._source.open_model(self._path)
        except ModelLoadError as error:
            self._show_error(str(error))
            self._render_issues()
            return
        self.remove_class("errored")
        self._model = model
        self._selected_key = ROOT_KEY
        self._view_mode = MODEL_MODE
        self._build_instruction_document(reset=True)
        title = Path(path).name
        if (description := model.description) is not None:
            title = f"{title} — {description}"
        self.query_one("#model-title", Static).update(title)
        select = self.query_one("#submodel-select", Select)
        root_label = model.name or Path(path).name
        options = [(f"(root) {root_label}", ROOT_KEY)]
        options += [(name, name) for name in model.submodels]
        with select.prevent(Select.Changed):
            select.set_options(options)
            select.value = ROOT_KEY
        mode_select = self.query_one("#view-mode-select", Select)
        with mode_select.prevent(Select.Changed):
            mode_select.value = MODEL_MODE
        self._sync_mode_ui()
        self._render_model()
        self._render_issues()
        self.query_one("#piece-table", PieceTable).focus()

    @on(Select.Changed, "#view-mode-select")
    def _view_mode_changed(self, event: Select.Changed) -> None:
        event.stop()
        if isinstance(event.value, str):
            self._view_mode = event.value
            self._sync_mode_ui()
            self._render_model()

    @on(Select.Changed, "#submodel-select")
    def _submodel_changed(self, event: Select.Changed) -> None:
        event.stop()
        if isinstance(event.value, str):
            self._selected_key = event.value
            self._render_model()

    @on(Select.Changed, "#instruction-section-select")
    def _instruction_section_changed(self, event: Select.Changed) -> None:
        event.stop()
        if isinstance(event.value, str):
            self._selected_instruction_section = event.value
            self._set_step_options(reset=True)
            self._render_model()

    @on(Select.Changed, "#instruction-step-select")
    def _instruction_step_changed(self, event: Select.Changed) -> None:
        event.stop()
        if isinstance(event.value, int):
            self._selected_instruction_step = event.value
            self._render_model()

    def _show_error(self, message: str) -> None:
        self._model = None
        self._instruction_document = None
        self._selected_instruction_section = None
        self._selected_instruction_step = 1
        self._step_occurrence_counts = None
        self._step_counts_section = None
        self._view_mode = MODEL_MODE
        mode_select = self.query_one("#view-mode-select", Select)
        with mode_select.prevent(Select.Changed):
            mode_select.value = MODEL_MODE
        self._sync_mode_ui()
        self.add_class("errored")
        self.query_one("#model-error", Static).update(f"[bold red]Error:[/] {message}")
        self.query_one("#model-title", Static).update("No model open")
        self.query_one("#piece-table", PieceTable).set_occurrences([], self._parts)
        self.query_one("#stats-panel", StatsPanel).update("Model has no pieces.")
        self.query_one("#instruction-details", InstructionDetails).update("")
        self.query_one("#pli-table", BomTable).set_rows([], self._parts)
        self.query_one("#bom-table", BomTable).set_rows([], self._parts)
        self.query_one("#directives-table", DirectivesTable).set_directives([])
        self._clear_instruction_selectors()

    def _selected_model(self) -> Model | None:
        if self._model is None:
            return None
        if self._selected_key == ROOT_KEY:
            return self._model
        try:
            return self._model.submodel_view(self._selected_key)
        except UnknownSubmodelError:
            self._selected_key = ROOT_KEY
            select = self.query_one("#submodel-select", Select)
            with select.prevent(Select.Changed):
                select.value = ROOT_KEY
            return self._model

    def _render_model(self) -> None:
        if self._view_mode == INSTRUCTIONS_MODE:
            self._render_instruction_step()
            return
        self._render_whole_model()

    def _render_whole_model(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        steps = model.steps
        occurrences = list(
            model.iter_occurrences(include_steps=len(steps) > 1),
        )
        self.query_one("#piece-table", PieceTable).set_occurrences(
            occurrences,
            self._parts,
        )
        self.query_one("#stats-panel", StatsPanel).show_occurrences(
            occurrences,
            self._parts,
            steps=len(steps),
        )
        self.query_one("#bom-table", BomTable).set_rows(
            bill_of_materials(model, parts=self._parts),
            self._parts,
        )

    def _render_instruction_step(self) -> None:
        selection = self._instruction_selection()
        if selection is None:
            return
        section, step = selection
        occurrences = step.cumulative_occurrences(expand_submodels=True)
        counts = self._section_step_counts(section)
        labels = tuple(
            source_step.number
            for source_step, count in zip(
                section.steps[: step.number],
                counts[: step.number],
                strict=True,
            )
            for _ in range(count)
        )
        # pyldraw3 guarantees the cumulative expansion is the ordered
        # concatenation of each step's added occurrences; if that ever
        # drifts, blank step labels beat crashing the render.
        step_numbers = labels if len(labels) == len(occurrences) else None
        self.query_one("#piece-table", PieceTable).set_occurrences(
            occurrences,
            self._parts,
            step_numbers=step_numbers,
        )
        self.query_one("#stats-panel", StatsPanel).show_occurrences(
            occurrences,
            self._parts,
            steps=len(section.steps),
        )
        self.query_one("#instruction-details", InstructionDetails).show_step(
            step,
            total_steps=len(section.steps),
            added_count=counts[step.number - 1],
            cumulative_count=len(occurrences),
        )
        self.query_one("#pli-table", BomTable).set_rows(
            step.added_bill_of_materials(
                parts=self._parts,
                expand_submodels=True,
                respect_lpub=True,
            ),
            self._parts,
            title="Parts list",
        )
        self.query_one("#bom-table", BomTable).set_rows(
            step.cumulative_bill_of_materials(
                parts=self._parts,
                expand_submodels=True,
                respect_lpub=True,
            ),
            self._parts,
        )
        self.query_one("#directives-table", DirectivesTable).set_directives(
            step.directives,
        )

    def _section_step_counts(self, section: InstructionSection) -> tuple[int, ...]:
        """Occurrence counts added per step, computed once per section."""
        if (
            self._step_occurrence_counts is None
            or self._step_counts_section != section.name
        ):
            self._step_occurrence_counts = tuple(
                len(step.added_occurrences(expand_submodels=True))
                for step in section.steps
            )
            self._step_counts_section = section.name
        return self._step_occurrence_counts

    def _build_instruction_document(self, *, reset: bool) -> None:
        self._step_occurrence_counts = None
        self._step_counts_section = None
        if self._model is None:
            self._instruction_document = None
            self._clear_instruction_selectors()
            return
        self._instruction_document = self._model.instruction_document(
            parts=self._parts,
        )
        document = self._instruction_document
        section_names = {section.name for section in document.sections}
        if reset or self._selected_instruction_section not in section_names:
            self._selected_instruction_section = document.root.name
            self._selected_instruction_step = 1
        section_select = self.query_one("#instruction-section-select", Select)
        options = [
            (
                f"(root) {section.name}" if section.is_root else section.name,
                section.name,
            )
            for section in document.sections
        ]
        with section_select.prevent(Select.Changed):
            section_select.set_options(options)
            section_select.value = self._selected_instruction_section
        self._set_step_options(reset=reset)

    def _set_step_options(self, *, reset: bool) -> None:
        section = self._instruction_section()
        if section is None:
            self._clear_step_selector()
            return
        numbers = {step.number for step in section.steps}
        if reset or self._selected_instruction_step not in numbers:
            self._selected_instruction_step = section.steps[0].number
        step_select = self.query_one("#instruction-step-select", Select)
        with step_select.prevent(Select.Changed):
            step_select.set_options(
                [(f"Step {step.number}", step.number) for step in section.steps],
            )
            step_select.value = self._selected_instruction_step

    def _instruction_section(self) -> InstructionSection | None:
        document = self._instruction_document
        if document is None:
            return None
        for section in document.sections:
            if section.name == self._selected_instruction_section:
                return section
        return document.root

    def _instruction_selection(
        self,
    ) -> tuple[InstructionSection, InstructionStep] | None:
        section = self._instruction_section()
        if section is None:
            return None
        for step in section.steps:
            if step.number == self._selected_instruction_step:
                return section, step
        fallback = section.steps[0]
        self._selected_instruction_step = fallback.number
        return section, fallback

    def _clear_instruction_selectors(self) -> None:
        section_select = self.query_one("#instruction-section-select", Select)
        with section_select.prevent(Select.Changed):
            section_select.set_options([])
        self._clear_step_selector()

    def _clear_step_selector(self) -> None:
        step_select = self.query_one("#instruction-step-select", Select)
        with step_select.prevent(Select.Changed):
            step_select.set_options([])

    def _sync_mode_ui(self) -> None:
        instructions = self._view_mode == INSTRUCTIONS_MODE
        self.set_class(instructions, "instructions")
        tabs = self.query_one("#model-tabs", TabbedContent)
        if not instructions and tabs.active in _INSTRUCTION_ONLY_TABS:
            tabs.active = "tab-pieces"
        for pane_id in _INSTRUCTION_ONLY_TABS:
            tabs.get_tab(pane_id).display = instructions

    def action_toggle_instructions(self) -> None:
        """Switch between whole-model and instruction modes."""
        next_mode = (
            MODEL_MODE if self._view_mode == INSTRUCTIONS_MODE else INSTRUCTIONS_MODE
        )
        self.query_one("#view-mode-select", Select).value = next_mode

    def action_previous_instruction_step(self) -> None:
        """Select the preceding step in the current instruction section."""
        self._move_instruction_step(-1)

    def action_next_instruction_step(self) -> None:
        """Select the following step in the current instruction section."""
        self._move_instruction_step(1)

    def _move_instruction_step(self, offset: int) -> None:
        if self._view_mode != INSTRUCTIONS_MODE:
            return
        section = self._instruction_section()
        if section is None:
            return
        target = min(
            max(self._selected_instruction_step + offset, section.steps[0].number),
            section.steps[-1].number,
        )
        self.query_one("#instruction-step-select", Select).value = target

    def _render_issues(self) -> None:
        """Validate the open file and show the issues, whole file at once.

        Validation covers the file (all submodels), not the selected
        submodel, so this runs on load — and also for files that failed
        to parse, where the issue list explains what is wrong.
        """
        if self._path is None:
            return
        try:
            issues = list(iter_ldr_issues(self._path, self._parts))
        except (OSError, UnicodeDecodeError) as error:
            issues = [
                ValidationIssue(
                    line_number=0,
                    message=f"could not re-read file: {error}",
                ),
            ]
        instruction_issues = (
            list(iter_instruction_issues(self._instruction_document))
            if self._instruction_document is not None
            else []
        )
        combined_issues = [*issues, *instruction_issues]
        self.query_one("#issues-table", IssuesTable).set_issues(combined_issues)
        tabs = self.query_one("#model-tabs", TabbedContent)
        tabs.get_tab("tab-issues").label = f"Issues ({len(combined_issues)})"
