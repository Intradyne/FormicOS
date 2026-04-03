"""Wave 87 Track C: polite-question colony gate tests."""

from __future__ import annotations

from formicos.surface.queen_runtime import _is_genuine_question


class TestGenuineQuestion:
    """Genuine informational questions should return True."""

    def test_what_question(self) -> None:
        assert _is_genuine_question("What is the status of the workspace?")

    def test_how_question(self) -> None:
        assert _is_genuine_question("How does the knowledge pipeline work?")

    def test_where_question(self) -> None:
        assert _is_genuine_question("Where is the config file?")

    def test_is_question(self) -> None:
        assert _is_genuine_question("Is the colony still running?")


class TestPoliteRequest:
    """Polite implementation requests should return False (not suppress colony)."""

    def test_can_you_fix(self) -> None:
        assert not _is_genuine_question("Can you fix the auth bug?")

    def test_could_you_audit(self) -> None:
        assert not _is_genuine_question("Could you audit this module?")

    def test_would_you_add(self) -> None:
        assert not _is_genuine_question("Would you add tests for the parser?")

    def test_will_you_implement(self) -> None:
        assert not _is_genuine_question("Will you implement the endpoint?")


class TestNoQuestionMark:
    """Messages without ? should never be genuine questions."""

    def test_imperative(self) -> None:
        assert not _is_genuine_question("fix the failing test")

    def test_statement(self) -> None:
        assert not _is_genuine_question("the build is broken")
