"""
Tests for FormicOS DocklingParser — Topology-Preserving Document Chunking.

Covers:
1. convert_to_markdown (mocked docling)
2. chunk_markdown — table integrity (anti-Euclidean-shredding)
3. chunk_markdown — list integrity
4. parse end-to-end (mocked converter)
5. to_qdrant_payloads format
6. ChunkResult metadata
7. Empty document handling
8. Table integrity simulation (core anti-shredding assertion)

Mocking strategy:
  docling is NOT installed in CI.  All three lazy-imported modules
  (docling, docling_core) are injected via sys.modules before each
  test that exercises convert/chunk methods.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.ingestion.dockling_parser import ChunkResult, DocklingParser


# ── Helpers ───────────────────────────────────────────────────────────────


TABLE_MARKDOWN = """\
# Report

Some introductory prose before the table.

| Name    | Age | City      |
|---------|-----|-----------|
| Alice   | 30  | New York  |
| Bob     | 25  | London    |
| Charlie | 35  | Tokyo     |

Some concluding prose after the table.
"""

SAMPLE_MARKDOWN = """\
# Project Overview

This project demonstrates topology-preserving chunking.

## Data Summary

| Metric   | Q1   | Q2   |
|----------|------|------|
| Revenue  | 100  | 200  |
| Costs    | 50   | 80   |
| Profit   | 50   | 120  |

## Key Points

- First item in the list
- Second item in the list
- Third item with **bold** text

## Conclusion

The results are promising and warrant further investigation.
"""

LIST_MARKDOWN = """\
# Shopping List

Things to buy:

- Apples
- Bananas
- Cherries
- Dates
- Elderberries

End of list.
"""


def _count_table_rows(text: str) -> int:
    """Count lines that look like table rows (start and end with |)."""
    return sum(
        1
        for line in text.strip().splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    )


def _is_complete_table(text: str) -> bool:
    """Check if table rows in text form a complete table.

    Returns True if there are no table rows, or if they form a complete
    table (header + separator + data rows).
    """
    table_lines = [
        line.strip()
        for line in text.strip().splitlines()
        if line.strip().startswith("|") and line.strip().endswith("|")
    ]
    if not table_lines:
        return True

    if len(table_lines) < 3:
        return False

    separator = table_lines[1]
    if not re.match(r"^\|[\s\-:|]+\|$", separator):
        return False

    return True


@dataclass
class FakeChunkMeta:
    """Mock for docling chunk metadata."""

    data: dict[str, Any]

    def export_json_dict(self) -> dict[str, Any]:
        return self.data


@dataclass
class FakeChunk:
    """Mock for a docling chunk."""

    text: str
    meta: FakeChunkMeta | None = None


class FakeConvertResult:
    """Mock for docling DocumentConverter result."""

    def __init__(self, markdown: str):
        self.document = MagicMock()
        self.document.export_to_markdown.return_value = markdown


# ── Fixture: inject mock docling modules into sys.modules ─────────────────


@pytest.fixture()
def mock_docling():
    """Inject fake docling/docling_core modules into sys.modules.

    Returns a namespace with the mock objects for per-test configuration.
    Cleans up after the test so subsequent imports are unaffected.
    """
    # Top-level mock modules
    mod_docling = MagicMock()
    mod_docling_chunking = MagicMock()
    mod_docling_dc = MagicMock()
    mod_docling_core = MagicMock()
    mod_dc_transforms = MagicMock()
    mod_dc_transforms_chunker = MagicMock()
    mod_dc_transforms_chunker_tokenizer = MagicMock()
    mod_dc_types = MagicMock()
    mod_dc_types_doc = MagicMock()

    # Wire up the mock DocumentConverter
    mock_converter_cls = MagicMock()
    mod_docling_dc.DocumentConverter = mock_converter_cls

    # Wire up HybridChunker
    mock_chunker_cls = MagicMock()
    mod_docling_chunking.HybridChunker = mock_chunker_cls

    # Wire up HuggingFaceTokenizer
    mock_tokenizer_cls = MagicMock()
    mod_dc_transforms_chunker_tokenizer.HuggingFaceTokenizer = mock_tokenizer_cls

    # Wire up DoclingDocument
    mock_docling_doc = MagicMock()
    mod_dc_types_doc.DoclingDocument = mock_docling_doc

    injected = {
        "docling": mod_docling,
        "docling.chunking": mod_docling_chunking,
        "docling.document_converter": mod_docling_dc,
        "docling_core": mod_docling_core,
        "docling_core.transforms": mod_dc_transforms,
        "docling_core.transforms.chunker": mod_dc_transforms_chunker,
        "docling_core.transforms.chunker.tokenizer": mod_dc_transforms_chunker_tokenizer,
        "docling_core.types": mod_dc_types,
        "docling_core.types.doc": mod_dc_types_doc,
    }

    # Save originals
    saved = {k: sys.modules.get(k) for k in injected}

    # Inject
    sys.modules.update(injected)

    class _NS:
        converter_cls = mock_converter_cls
        chunker_cls = mock_chunker_cls
        tokenizer_cls = mock_tokenizer_cls
        docling_doc = mock_docling_doc

    try:
        yield _NS()
    finally:
        # Restore
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


# ── 1. Convert to Markdown ─────────────────────────────────────────────


def test_convert_to_markdown(mock_docling):
    """Mocked DocumentConverter returns expected Markdown."""
    parser = DocklingParser()

    mock_result = FakeConvertResult("# Hello\n\nWorld")
    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_result
    mock_docling.converter_cls.return_value = mock_converter

    md = parser.convert_to_markdown("/fake/document.pdf")

    assert md == "# Hello\n\nWorld"
    mock_converter.convert.assert_called_once_with("/fake/document.pdf")


# ── 2. Chunk Markdown — Table Integrity ──────────────────────────────────


def test_chunk_markdown_preserves_table(mock_docling):
    """A 3x3 table in Markdown survives chunking intact."""
    parser = DocklingParser()

    table_text = (
        "| Name    | Age | City      |\n"
        "|---------|-----|-----------|\n"
        "| Alice   | 30  | New York  |\n"
        "| Bob     | 25  | London    |\n"
        "| Charlie | 35  | Tokyo     |"
    )
    chunks = [
        FakeChunk("Some introductory prose before the table."),
        FakeChunk(table_text, FakeChunkMeta({"doc_item": "table"})),
        FakeChunk("Some concluding prose after the table."),
    ]

    mock_chunker = MagicMock()
    mock_chunker.chunk.return_value = chunks
    mock_docling.chunker_cls.return_value = mock_chunker
    mock_docling.docling_doc.from_markdown.return_value = MagicMock()

    results = parser.chunk_markdown(TABLE_MARKDOWN)

    assert len(results) == 3
    table_chunk = results[1]
    assert "Alice" in table_chunk.text
    assert "Bob" in table_chunk.text
    assert "Charlie" in table_chunk.text
    assert table_chunk.meta.get("doc_item") == "table"


# ── 3. Chunk Markdown — List Integrity ───────────────────────────────────


def test_chunk_markdown_preserves_list(mock_docling):
    """A bulleted list stays together in a single chunk."""
    parser = DocklingParser()

    list_text = "- Apples\n- Bananas\n- Cherries\n- Dates\n- Elderberries"
    chunks = [
        FakeChunk("Things to buy:"),
        FakeChunk(list_text, FakeChunkMeta({"doc_item": "list"})),
        FakeChunk("End of list."),
    ]

    mock_chunker = MagicMock()
    mock_chunker.chunk.return_value = chunks
    mock_docling.chunker_cls.return_value = mock_chunker
    mock_docling.docling_doc.from_markdown.return_value = MagicMock()

    results = parser.chunk_markdown(LIST_MARKDOWN)

    assert len(results) == 3
    list_chunk = results[1]
    assert "Apples" in list_chunk.text
    assert "Elderberries" in list_chunk.text


# ── 4. Parse End-to-End ──────────────────────────────────────────────────


def test_parse_end_to_end(mock_docling):
    """parse() = convert_to_markdown() + chunk_markdown()."""
    parser = DocklingParser()

    # Configure converter mock
    mock_result = FakeConvertResult(SAMPLE_MARKDOWN)
    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_result
    mock_docling.converter_cls.return_value = mock_converter

    # Configure chunker mock
    chunks = [
        FakeChunk("Project overview text"),
        FakeChunk("Table data", FakeChunkMeta({"heading": "Data Summary"})),
    ]
    mock_chunker = MagicMock()
    mock_chunker.chunk.return_value = chunks
    mock_docling.chunker_cls.return_value = mock_chunker
    mock_docling.docling_doc.from_markdown.return_value = MagicMock()

    results = parser.parse("/fake/report.pdf")

    assert len(results) == 2
    assert results[0].text == "Project overview text"
    assert results[1].meta.get("heading") == "Data Summary"
    assert results[0].chunk_index == 0
    assert results[1].chunk_index == 1


# ── 5. Qdrant Payload Format ────────────────────────────────────────────


def test_to_qdrant_payloads_format():
    """Payloads match Qdrant schema: content, source, doc_id, chunk_index."""
    chunks = [
        ChunkResult(text="First chunk", meta={"heading": "Intro"}, chunk_index=0),
        ChunkResult(text="Second chunk", meta={"heading": "Body"}, chunk_index=1),
    ]

    payloads = DocklingParser.to_qdrant_payloads(
        chunks, source="/docs/report.pdf", doc_id="report",
    )

    assert len(payloads) == 2

    p0 = payloads[0]
    assert p0["content"] == "First chunk"
    assert p0["source"] == "/docs/report.pdf"
    assert p0["doc_id"] == "report"
    assert p0["chunk_index"] == 0
    assert p0["heading"] == "Intro"

    p1 = payloads[1]
    assert p1["content"] == "Second chunk"
    assert p1["chunk_index"] == 1


def test_to_qdrant_payloads_with_extra():
    """Extra fields are merged into each payload."""
    chunks = [ChunkResult(text="Chunk", chunk_index=0)]

    payloads = DocklingParser.to_qdrant_payloads(
        chunks, source="a.pdf", doc_id="a",
        extra={"colony_id": "colony-1", "task_id": "t-42"},
    )

    assert payloads[0]["colony_id"] == "colony-1"
    assert payloads[0]["task_id"] == "t-42"


# ── 6. ChunkResult Metadata ─────────────────────────────────────────────


def test_chunk_result_has_metadata(mock_docling):
    """ChunkResult carries docling metadata from chunk.meta.export_json_dict()."""
    parser = DocklingParser()

    meta_data = {"heading": "Summary", "doc_item": "paragraph", "level": 2}
    chunks = [FakeChunk("Summary text", FakeChunkMeta(meta_data))]

    mock_chunker = MagicMock()
    mock_chunker.chunk.return_value = chunks
    mock_docling.chunker_cls.return_value = mock_chunker
    mock_docling.docling_doc.from_markdown.return_value = MagicMock()

    results = parser.chunk_markdown("# Summary\n\nSummary text")

    assert len(results) == 1
    assert results[0].meta["heading"] == "Summary"
    assert results[0].meta["doc_item"] == "paragraph"
    assert results[0].meta["level"] == 2


def test_chunk_result_missing_meta(mock_docling):
    """ChunkResult defaults to empty meta when chunk has no metadata."""
    parser = DocklingParser()

    chunks = [FakeChunk("Plain text", None)]

    mock_chunker = MagicMock()
    mock_chunker.chunk.return_value = chunks
    mock_docling.chunker_cls.return_value = mock_chunker
    mock_docling.docling_doc.from_markdown.return_value = MagicMock()

    results = parser.chunk_markdown("Plain text")

    assert results[0].meta == {}


# ── 7. Empty Document ───────────────────────────────────────────────────


def test_empty_document():
    """Empty markdown produces no chunks (no docling imports needed)."""
    parser = DocklingParser()
    assert parser.chunk_markdown("") == []
    assert parser.chunk_markdown("   ") == []
    assert parser.chunk_markdown("\n\n") == []


# ── 8. Table Integrity Simulation ────────────────────────────────────────


def test_table_integrity_simulation(mock_docling):
    """Core anti-Euclidean-shredding test.

    Creates a Markdown document with a 3x3 table surrounded by prose.
    Asserts that no chunk contains a partial table row — each chunk
    either contains the complete table or no table content at all.
    """
    parser = DocklingParser()

    table_block = (
        "| Name    | Age | City      |\n"
        "|---------|-----|-----------|\n"
        "| Alice   | 30  | New York  |\n"
        "| Bob     | 25  | London    |\n"
        "| Charlie | 35  | Tokyo     |"
    )

    test_scenarios = [
        # Scenario 1: Table in its own chunk (ideal)
        [
            FakeChunk("Introductory prose about the report."),
            FakeChunk(table_block, FakeChunkMeta({"doc_item": "table"})),
            FakeChunk("Concluding remarks about the data."),
        ],
        # Scenario 2: Table merged with surrounding prose
        [
            FakeChunk(
                f"Introductory prose.\n\n{table_block}\n\nConclusion.",
                FakeChunkMeta({"doc_item": "table"}),
            ),
        ],
        # Scenario 3: Multiple chunks, none with partial table
        [
            FakeChunk("Intro section with lots of detail."),
            FakeChunk("More context about the analysis."),
            FakeChunk(table_block, FakeChunkMeta({"doc_item": "table"})),
            FakeChunk("Final thoughts."),
        ],
    ]

    for scenario_idx, chunks in enumerate(test_scenarios):
        mock_chunker = MagicMock()
        mock_chunker.chunk.return_value = chunks
        mock_docling.chunker_cls.return_value = mock_chunker
        mock_docling.docling_doc.from_markdown.return_value = MagicMock()

        results = parser.chunk_markdown(TABLE_MARKDOWN)

        for chunk_idx, result in enumerate(results):
            row_count = _count_table_rows(result.text)
            if row_count > 0:
                assert _is_complete_table(result.text), (
                    f"Scenario {scenario_idx + 1}, chunk {chunk_idx}: "
                    f"partial table detected ({row_count} rows). "
                    f"Euclidean shredding NOT eradicated!\n"
                    f"Chunk text:\n{result.text}"
                )
                assert "Alice" in result.text, (
                    f"Scenario {scenario_idx + 1}: table missing row 'Alice'"
                )
                assert "Bob" in result.text, (
                    f"Scenario {scenario_idx + 1}: table missing row 'Bob'"
                )
                assert "Charlie" in result.text, (
                    f"Scenario {scenario_idx + 1}: table missing row 'Charlie'"
                )


# ── 9. Constructor Parameters ───────────────────────────────────────────


def test_custom_tokenizer_params():
    """DocklingParser accepts custom tokenizer model and max_tokens."""
    parser = DocklingParser(
        tokenizer_model="sentence-transformers/all-MiniLM-L6-v2",
        max_tokens=256,
        merge_peers=False,
    )
    assert parser._tokenizer_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert parser._max_tokens == 256
    assert parser._merge_peers is False


def test_default_params():
    """Default constructor uses BGE-M3 with 512 tokens and merge_peers=True."""
    parser = DocklingParser()
    assert parser._tokenizer_model == "BAAI/bge-m3"
    assert parser._max_tokens == 512
    assert parser._merge_peers is True


# ── 10. Module Imports ──────────────────────────────────────────────────


def test_core_ingestion_package_exports():
    """src.core.ingestion exports DocklingParser and ChunkResult."""
    from src.core.ingestion import ChunkResult as CR
    from src.core.ingestion import DocklingParser as DP

    assert CR is ChunkResult
    assert DP is DocklingParser
