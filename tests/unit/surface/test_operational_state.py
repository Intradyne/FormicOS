"""Wave 71.0 Team A: operational_state helper tests."""

from __future__ import annotations

from pathlib import Path

from formicos.surface.operational_state import (
    append_journal_entry,
    append_procedure_rule,
    get_journal_summary,
    get_procedures_summary,
    journal_path,
    load_procedures,
    parse_journal_entries,
    procedures_path,
    read_journal_tail,
    render_journal_for_queen,
    render_procedures_for_queen,
    save_procedures,
)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


class TestPaths:
    def test_journal_path(self, tmp_path: Path) -> None:
        p = journal_path(str(tmp_path), "ws1")
        assert p == tmp_path / ".formicos" / "operations" / "ws1" / "queen_journal.md"

    def test_procedures_path(self, tmp_path: Path) -> None:
        p = procedures_path(str(tmp_path), "ws1")
        assert p == tmp_path / ".formicos" / "operations" / "ws1" / "operating_procedures.md"


# ---------------------------------------------------------------------------
# Procedures
# ---------------------------------------------------------------------------


class TestProcedures:
    def test_load_absent(self, tmp_path: Path) -> None:
        assert load_procedures(str(tmp_path), "ws1") == ""

    def test_save_and_load(self, tmp_path: Path) -> None:
        save_procedures(str(tmp_path), "ws1", "## Rules\n- Do X\n")
        text = load_procedures(str(tmp_path), "ws1")
        assert "Do X" in text

    def test_append_rule_new_heading(self, tmp_path: Path) -> None:
        result = append_procedure_rule(
            str(tmp_path), "ws1", "Coding", "Always run tests",
        )
        assert "## Coding" in result
        assert "- Always run tests" in result

    def test_append_rule_existing_heading(self, tmp_path: Path) -> None:
        save_procedures(str(tmp_path), "ws1", "## Coding\n- Existing rule\n")
        result = append_procedure_rule(
            str(tmp_path), "ws1", "Coding", "New rule",
        )
        assert "- Existing rule" in result
        assert "- New rule" in result

    def test_get_summary_empty(self, tmp_path: Path) -> None:
        summary = get_procedures_summary(str(tmp_path), "ws1")
        assert summary["exists"] is False

    def test_get_summary_with_content(self, tmp_path: Path) -> None:
        save_procedures(str(tmp_path), "ws1", "## Rules\n- Be safe\n")
        summary = get_procedures_summary(str(tmp_path), "ws1")
        assert summary["exists"] is True
        assert "Be safe" in summary["content"]


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------


class TestJournal:
    def test_append_and_read(self, tmp_path: Path) -> None:
        append_journal_entry(str(tmp_path), "ws1", "session", "Started work")
        append_journal_entry(str(tmp_path), "ws1", "queen", "Spawned colony")
        tail = read_journal_tail(str(tmp_path), "ws1")
        assert "Started work" in tail
        assert "Spawned colony" in tail

    def test_tail_limit(self, tmp_path: Path) -> None:
        for i in range(50):
            append_journal_entry(str(tmp_path), "ws1", "test", f"Entry {i}")
        tail = read_journal_tail(str(tmp_path), "ws1", max_lines=5)
        lines = tail.strip().splitlines()
        assert len(lines) == 5
        assert "Entry 49" in lines[-1]

    def test_parse_entries(self) -> None:
        text = (
            "- [2026-03-26 10:00] [session] First entry\n"
            "- [2026-03-26 10:05] [queen] Second entry\n"
        )
        entries = parse_journal_entries(text)
        assert len(entries) == 2
        assert entries[0]["source"] == "session"
        assert entries[1]["message"] == "Second entry"

    def test_get_summary_empty(self, tmp_path: Path) -> None:
        summary = get_journal_summary(str(tmp_path), "ws1")
        assert summary["exists"] is False

    def test_get_summary_with_entries(self, tmp_path: Path) -> None:
        append_journal_entry(str(tmp_path), "ws1", "test", "Hello")
        summary = get_journal_summary(str(tmp_path), "ws1")
        assert summary["exists"] is True
        assert summary["totalEntries"] == 1
        assert summary["entries"][0]["body"] == "Hello"


# ---------------------------------------------------------------------------
# Queen rendering
# ---------------------------------------------------------------------------


class TestQueenRendering:
    def test_procedures_render_empty(self, tmp_path: Path) -> None:
        assert render_procedures_for_queen(str(tmp_path), "ws1") == ""

    def test_procedures_render(self, tmp_path: Path) -> None:
        save_procedures(str(tmp_path), "ws1", "## Rules\n- Be safe\n")
        text = render_procedures_for_queen(str(tmp_path), "ws1")
        assert text.startswith("# Operating Procedures")
        assert "Be safe" in text

    def test_journal_render_empty(self, tmp_path: Path) -> None:
        assert render_journal_for_queen(str(tmp_path), "ws1") == ""

    def test_journal_render(self, tmp_path: Path) -> None:
        append_journal_entry(str(tmp_path), "ws1", "session", "Did things")
        text = render_journal_for_queen(str(tmp_path), "ws1")
        assert text.startswith("# Queen Journal")
        assert "Did things" in text


# ---------------------------------------------------------------------------
# REST endpoint integration
# ---------------------------------------------------------------------------


class TestEndpoints:
    def _make_client(self, tmp_path: Path):  # noqa: ANN202
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from starlette.applications import Starlette
        from starlette.testclient import TestClient

        from formicos.surface.routes.api import routes

        settings_mock = MagicMock()
        settings_mock.system = SimpleNamespace(data_dir=str(tmp_path))

        route_list = routes(
            runtime=MagicMock(),
            settings=settings_mock,
            castes=None,
            castes_path="",
            config_path="",
            vector_store=None,
            kg_adapter=None,
            embed_client=None,
            skill_collection="",
            ws_manager=MagicMock(),
        )
        app = Starlette(routes=route_list)
        return TestClient(app)

    def test_get_journal_empty(self, tmp_path: Path) -> None:
        client = self._make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws1/queen-journal")
        assert resp.status_code == 200
        assert resp.json()["exists"] is False

    def test_get_journal_with_entries(self, tmp_path: Path) -> None:
        append_journal_entry(str(tmp_path), "ws1", "test", "Hello world")
        client = self._make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws1/queen-journal")
        data = resp.json()
        assert data["exists"] is True
        assert data["totalEntries"] == 1

    def test_get_procedures_empty(self, tmp_path: Path) -> None:
        client = self._make_client(tmp_path)
        resp = client.get("/api/v1/workspaces/ws1/operating-procedures")
        assert resp.status_code == 200
        assert resp.json()["exists"] is False

    def test_put_procedures(self, tmp_path: Path) -> None:
        client = self._make_client(tmp_path)
        resp = client.put(
            "/api/v1/workspaces/ws1/operating-procedures",
            json={"content": "## Rules\n- Always test\n"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

        # Verify it persisted
        resp2 = client.get("/api/v1/workspaces/ws1/operating-procedures")
        data = resp2.json()
        assert data["exists"] is True
        assert "Always test" in data["content"]
