"""Typed physical-connection summaries and tables."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw import ConnectionFeature, Diagnostic, PartGeometry
    from ldraw.pieces import Vector
    from textual.app import ComposeResult


def _coordinate(value: float) -> str:
    return f"{value:g}"


def _vector_label(vector: Vector) -> str:
    return (
        f"({_coordinate(vector.x)}, {_coordinate(vector.y)}, {_coordinate(vector.z)})"
    )


class ConnectionFeatureTable(DataTable[Text | str]):
    """Compact connection rows for the narrow part-detail pane."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def on_mount(self) -> None:
        """Configure columns and row-based cursor navigation."""
        self._features: tuple[ConnectionFeature, ...] = ()
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Kind", "Role", "Source", "Confidence")

    def set_features(self, features: Sequence[ConnectionFeature]) -> None:
        """Replace rows with connection features in pyldraw3 order."""
        self.clear()
        self._features = tuple(features)
        for index, feature in enumerate(self._features):
            self.add_row(
                feature.kind.value,
                feature.role.value,
                feature.source.value,
                f"{feature.confidence:.1%}",
                key=str(index),
            )

    def feature_at(self, row: int) -> ConnectionFeature | None:
        """Return the feature at a visible row, if one exists."""
        if 0 <= row < len(self._features):
            return self._features[row]
        return None


class ConnectionDiagnosticsTable(DataTable[Text | str]):
    """Geometry and connection-metadata warnings for one part."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def on_mount(self) -> None:
        """Configure diagnostic columns and row-based cursor navigation."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Line", "Code", "Path", "Message")

    def set_diagnostics(self, diagnostics: Sequence[Diagnostic]) -> None:
        """Replace rows with structured geometry and metadata diagnostics."""
        self.clear()
        for diagnostic in diagnostics:
            self.add_row(
                "—" if diagnostic.line_number is None else str(diagnostic.line_number),
                str(diagnostic.code),
                Text("—" if diagnostic.path is None else str(diagnostic.path)),
                Text(diagnostic.message),
            )
        self.display = bool(diagnostics)


def _summary(geometry: PartGeometry) -> Text:
    """Render metadata statistics without requiring a metadata report."""
    text = Text()

    def line(label: str, value: str) -> None:
        if text:
            text.append("\n")
        text.append(f"{label:>12}  ", style="bold dim")
        text.append(value)

    report = geometry.connection_metadata
    line("coverage", "unavailable" if report is None else report.coverage.value)
    line("features", str(len(geometry.connections)))
    if report is not None:
        line("sources", str(report.source_count))
        line("recognized", str(report.recognized_record_count))
        line("unsupported", str(report.unsupported_record_count))
        line("invalid", str(report.invalid_record_count))
    return text


def _feature_details(feature: ConnectionFeature | None) -> Text:
    """Render the selected feature's wide fields without Rich markup parsing."""
    if feature is None:
        return Text("No connection features.")
    text = Text()

    def line(label: str, value: str) -> None:
        if text:
            text.append("\n")
        text.append(f"{label:>10}  ", style="bold dim")
        text.append(value)

    occupancy = "free"
    if feature.occupied:
        occupancy = (
            f"occupied by {feature.occupied_by}"
            if feature.occupied_by is not None
            else "occupied"
        )
    line("position", _vector_label(feature.position))
    line("axis", _vector_label(feature.axis))
    line("feature ID", feature.feature_id or "—")
    line("occupancy", occupancy)
    line("compatible", ", ".join(feature.compatible_parts) or "—")
    return text


class PartConnections(Vertical):
    """Metadata summary, typed feature rows, and warnings for one part."""

    DEFAULT_CSS = """
    PartConnections > #connection-summary {
        height: auto;
        padding: 0 1 1 1;
    }
    PartConnections > #connection-features {
        height: auto;
        max-height: 12;
    }
    PartConnections > #connection-feature-detail {
        height: auto;
        max-height: 6;
        padding: 0 1 1 1;
    }
    PartConnections > #connection-diagnostics {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        """Lay out the coverage summary and connection tables."""
        yield Static("No part selected", id="connection-summary")
        yield ConnectionFeatureTable(id="connection-features")
        yield Static("No connection features.", id="connection-feature-detail")
        yield ConnectionDiagnosticsTable(id="connection-diagnostics")

    def _show_without_geometry(self, summary: Text | str) -> None:
        """Replace the summary and clear geometry-dependent table rows."""
        self.query_one("#connection-summary", expect_type=Static).update(summary)
        self.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        ).set_features(())
        self.query_one("#connection-feature-detail", expect_type=Static).update(
            "No connection features."
        )
        self.query_one(
            "#connection-diagnostics", expect_type=ConnectionDiagnosticsTable
        ).set_diagnostics(())

    def show_empty(self) -> None:
        """Clear the panel when no catalog part is selected."""
        self._show_without_geometry("No part selected")

    def show_loading(self, code: str) -> None:
        """Show a loading state while a part's geometry resolves."""
        summary = Text("Loading connections for ")
        summary.append(code)
        summary.append("…")
        self._show_without_geometry(summary)

    def show_geometry(self, geometry: PartGeometry) -> None:
        """Render connection metadata from one resolved part geometry."""
        self.query_one("#connection-summary", expect_type=Static).update(
            _summary(geometry)
        )
        features = self.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        )
        features.set_features(geometry.connections)
        self._show_feature_detail(features.feature_at(0))
        self.query_one(
            "#connection-diagnostics", expect_type=ConnectionDiagnosticsTable
        ).set_diagnostics(geometry.diagnostics)

    @on(DataTable.RowHighlighted, "#connection-features")
    def _feature_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show wide fields for the selected compact feature row."""
        table = self.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        )
        self._show_feature_detail(table.feature_at(event.cursor_row))

    def _show_feature_detail(self, feature: ConnectionFeature | None) -> None:
        self.query_one("#connection-feature-detail", expect_type=Static).update(
            _feature_details(feature)
        )

    def show_unavailable(self, reason: str) -> None:
        """Render a nonfatal geometry/metadata loading failure."""
        summary = Text("Connections unavailable:", style="yellow")
        summary.append(f" {reason}")
        self._show_without_geometry(summary)
