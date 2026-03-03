"""
FormicOS v0.8.0 -- Textual TUI for Live REPL Telemetry

A terminal dashboard that surfaces ``formicos.repl`` log events so the
operator can watch the Root_Architect mapping the file system in real-time.

Launch::

    python -m src.tui.app                       # standalone
    python -m src.tui.app --session <id>        # tail a specific session

Architecture
------------
1. ``REPLLogHandler`` — A ``logging.Handler`` subclass attached to the
   ``formicos.repl`` logger.  On each ``emit()`` it posts a Textual
   ``REPLEvent`` message to the running app (thread-safe via
   ``call_from_thread``).

2. ``FormicOSTUI`` — A Textual ``App`` with two panels:
   - **Activity log**: scrolling ``RichLog`` showing every formic_read_bytes
     and formic_subcall invocation with timestamps and parameters.
   - **Stats footer**: live counters for total reads, total subcalls,
     and bytes scanned.

The TUI imports only ``logging`` and ``textual``; it has no dependency on
the rest of FormicOS and can run in a separate process.
"""

from __future__ import annotations

import argparse
import logging
import time
from typing import ClassVar

try:
    from textual.app import App, ComposeResult
    from textual.containers import Vertical
    from textual.message import Message
    from textual.widgets import Footer, Header, RichLog, Static
except ImportError as exc:
    raise SystemExit(
        "FormicOS TUI requires the 'textual' package.\n"
        "Install it with:  pip install textual>=1.0.0"
    ) from exc


# ── Textual Message ────────────────────────────────────────────────────


class REPLEvent(Message):
    """Posted by REPLLogHandler when a formicos.repl log record arrives."""

    def __init__(self, record: logging.LogRecord) -> None:
        super().__init__()
        self.record = record


# ── Logging Handler ────────────────────────────────────────────────────


class REPLLogHandler(logging.Handler):
    """Bridges Python logging → Textual message bus.

    Attach this handler to ``logging.getLogger("formicos.repl")`` and it
    will forward every record as a ``REPLEvent`` to the TUI app.
    """

    def __init__(self, app: FormicOSTUI) -> None:
        super().__init__(level=logging.DEBUG)
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._app.call_from_thread(self._app.post_message, REPLEvent(record))
        except Exception:
            # Textual may not be running yet / shutting down — silently drop
            pass


# ── TUI App ────────────────────────────────────────────────────────────


class FormicOSTUI(App):
    """Terminal dashboard for live Root_Architect REPL telemetry."""

    TITLE = "FormicOS — REPL Telemetry"

    CSS: ClassVar[str] = """
    #activity-log {
        height: 1fr;
        border: solid $accent;
    }
    #stats-bar {
        height: 3;
        padding: 0 2;
        background: $surface;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "clear_log", "Clear log"),
    ]

    def __init__(self, session_filter: str | None = None) -> None:
        super().__init__()
        self._session_filter = session_filter
        self._total_reads = 0
        self._total_subcalls = 0
        self._total_bytes = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield RichLog(id="activity-log", highlight=True, markup=True)
            yield Static(self._stats_text(), id="stats-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Attach the log handler to formicos.repl on app start."""
        repl_logger = logging.getLogger("formicos.repl")
        self._handler = REPLLogHandler(self)
        repl_logger.addHandler(self._handler)
        # Ensure the logger actually processes INFO events
        if repl_logger.level > logging.INFO or repl_logger.level == logging.NOTSET:
            repl_logger.setLevel(logging.INFO)
        self._log_widget = self.query_one("#activity-log", RichLog)
        self._stats_widget = self.query_one("#stats-bar", Static)
        self._log_widget.write("[bold cyan]FormicOS REPL Telemetry — waiting for events…[/]")

    def on_unmount(self) -> None:
        """Detach the handler on shutdown."""
        repl_logger = logging.getLogger("formicos.repl")
        repl_logger.removeHandler(self._handler)

    # ── Event Handling ─────────────────────────────────────────────

    def on_repl_event(self, event: REPLEvent) -> None:
        """Format and display a REPL telemetry record."""
        record = event.record
        repl_event = getattr(record, "repl_event", None)
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))

        if repl_event == "formic_read_bytes":
            offset = getattr(record, "offset", "?")
            length = getattr(record, "length", "?")
            actual = getattr(record, "actual_bytes", 0)
            self._total_reads += 1
            self._total_bytes += actual if isinstance(actual, int) else 0
            line = (
                f"[dim]{ts}[/]  [bold green]READ[/]  "
                f"offset=[cyan]{offset}[/]  length=[cyan]{length}[/]  "
                f"actual=[yellow]{actual}[/] bytes"
            )

        elif repl_event == "formic_subcall":
            caste = getattr(record, "target_caste", "?")
            preview = getattr(record, "task_preview", "")[:80]
            data_len = getattr(record, "data_slice_len", "?")
            num = getattr(record, "subcall_num", "?")
            self._total_subcalls += 1
            line = (
                f"[dim]{ts}[/]  [bold magenta]SUBCALL #{num}[/]  "
                f"caste=[cyan]{caste}[/]  data=[yellow]{data_len}[/]b  "
                f"task=\"[italic]{preview}[/]\""
            )

        elif repl_event == "formic_subcall_complete":
            caste = getattr(record, "target_caste", "?")
            result_len = getattr(record, "result_len", "?")
            line = (
                f"[dim]{ts}[/]  [bold green]SUBCALL DONE[/]  "
                f"caste=[cyan]{caste}[/]  result=[yellow]{result_len}[/] chars"
            )

        else:
            # Generic formicos.repl message (e.g. AST validation block)
            line = f"[dim]{ts}[/]  [bold white]REPL[/]  {record.getMessage()}"

        self._log_widget.write(line)
        self._stats_widget.update(self._stats_text())

    # ── Helpers ────────────────────────────────────────────────────

    def _stats_text(self) -> str:
        return (
            f"  Reads: [bold]{self._total_reads}[/]"
            f"  |  Subcalls: [bold]{self._total_subcalls}[/]"
            f"  |  Bytes scanned: [bold]{self._total_bytes:,}[/]"
        )

    def action_clear_log(self) -> None:
        self._log_widget.clear()
        self._total_reads = 0
        self._total_subcalls = 0
        self._total_bytes = 0
        self._stats_widget.update(self._stats_text())
        self._log_widget.write("[bold cyan]Log cleared — waiting for events…[/]")


# ── CLI Entry Point ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="FormicOS REPL Telemetry TUI")
    parser.add_argument("--session", help="Filter events to a specific session ID")
    args = parser.parse_args()

    app = FormicOSTUI(session_filter=args.session)
    app.run()


if __name__ == "__main__":
    main()
