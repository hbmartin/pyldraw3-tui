"""Typed physical-connection summaries and tables."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Static

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ldraw import ConnectionFeature, Diagnostic, PartGeometry
    from ldraw.connection_metadata import ConnectionMetadataReport
    from ldraw.pieces import Vector
    from textual.app import ComposeResult


def _coordinate(value: float) -> str:
    return f"{value:g}"


def _vector_label(vector: Vector) -> str:
    return (
        f"({_coordinate(vector.x)}, {_coordinate(vector.y)}, {_coordinate(vector.z)})"
    )


class ConnectionFeatureTable(DataTable[Text | str]):
    """Connection kind, placement, evidence, and occupancy for one part."""

    BINDINGS: ClassVar = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
    ]

    def on_mount(self) -> None:
        """Configure columns and row-based cursor navigation."""
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns(
            "Kind",
            "Role",
            "Position",
            "Axis",
            "Source",
            "Confidence",
            "Feature ID",
            "Occupancy",
            "Compatible parts",
        )

    def set_features(self, features: Sequence[ConnectionFeature]) -> None:
        """Replace rows with connection features in pyldraw3 order."""
        self.clear()
        for feature in features:
            occupancy = "free"
            if feature.occupied:
                occupancy = (
                    f"occupied by {feature.occupied_by}"
                    if feature.occupied_by is not None
                    else "occupied"
                )
            self.add_row(
                feature.kind.value,
                feature.role.value,
                _vector_label(feature.position),
                _vector_label(feature.axis),
                feature.source.value,
                f"{feature.confidence:.0%}",
                feature.feature_id or "—",
                occupancy,
                ", ".join(feature.compatible_parts) or "—",
            )


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
                str(getattr(diagnostic.code, "value", diagnostic.code)),
                Text("—" if diagnostic.path is None else str(diagnostic.path)),
                Text(diagnostic.message),
            )
        self.display = bool(diagnostics)


def _summary(report: ConnectionMetadataReport, feature_count: int) -> Text:
    text = Text()

    def line(label: str, value: str) -> None:
        if text:
            text.append("\n")
        text.append(f"{label:>12}  ", style="bold dim")
        text.append(value)

    line("coverage", report.coverage.value)
    line("features", str(feature_count))
    line("sources", str(report.source_count))
    line("recognized", str(report.recognized_record_count))
    line("unsupported", str(report.unsupported_record_count))
    line("invalid", str(report.invalid_record_count))
    return text


class PartConnections(Vertical):
    """Metadata summary, typed feature rows, and warnings for one part."""

    DEFAULT_CSS = """
    PartConnections > #connection-summary {
        height: auto;
        padding: 0 1 1 1;
    }
    PartConnections > #connection-features {
        height: 2fr;
    }
    PartConnections > #connection-diagnostics {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        """Lay out the coverage summary and connection tables."""
        yield Static("No part selected", id="connection-summary")
        yield ConnectionFeatureTable(id="connection-features")
        yield ConnectionDiagnosticsTable(id="connection-diagnostics")

    def _show_without_geometry(self, summary: Text | str) -> None:
        """Replace the summary and clear geometry-dependent table rows."""
        self.query_one("#connection-summary", expect_type=Static).update(summary)
        self.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        ).set_features(())
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
        report = geometry.connection_metadata
        if report is None:
            self.show_unavailable("Connection metadata report unavailable.")
            return
        self.query_one("#connection-summary", expect_type=Static).update(
            _summary(report, len(geometry.connections))
        )
        self.query_one(
            "#connection-features", expect_type=ConnectionFeatureTable
        ).set_features(geometry.connections)
        self.query_one(
            "#connection-diagnostics", expect_type=ConnectionDiagnosticsTable
        ).set_diagnostics(geometry.diagnostics)

    def show_unavailable(self, reason: str) -> None:
        """Render a nonfatal geometry/metadata loading failure."""
        summary = Text("Connections unavailable:", style="yellow")
        summary.append(f" {reason}")
        self._show_without_geometry(summary)
