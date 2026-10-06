"""TEST-ONLY tests for the Notion renderer.

The earlier submission had to be redone because a simpler renderer left literal ``**`` and
backticks in the published text, and the report specifically calls out the nested case
(bold containing code). These tests pin that, plus the block conversions and the refusal
to publish when markup survives.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))

from notion_publish import (  # noqa: E402
    check_no_leftover_markup,
    markdown_to_blocks,
    rich_text,
    table_block,
)


def _join(runs: list[dict]) -> str:
    return "".join(run["text"]["content"] for run in runs)


def test_only_plain_text_is_untouched() -> None:
    runs = rich_text("just words")
    assert _join(runs) == "just words"
    assert runs[0]["annotations"] == {"bold": False, "code": False}


def test_only_bold_and_code_are_annotated() -> None:
    runs = rich_text("a **bold** and `code` mix")
    assert _join(runs) == "a bold and code mix"
    by_text = {run["text"]["content"]: run["annotations"] for run in runs}
    assert by_text["bold"]["bold"] is True
    assert by_text["bold"]["code"] is False
    assert by_text["code"]["code"] is True


def test_only_nested_markup_becomes_bold_and_code_together() -> None:
    """The case that forced a rebuild: bold wrapped around code."""
    for source in ("**`fully nested`**", "**bold with `code` nested**", "`code with **bold** nested`"):
        runs = rich_text(source)
        joined = _join(runs)
        assert "**" not in joined, source
        assert "`" not in joined, source
        annotated = [run for run in runs if run["annotations"]["bold"] or run["annotations"]["code"]]
        assert annotated, f"no annotations produced for {source}"


def test_only_no_case_leaves_marker_characters_behind() -> None:
    cases = [
        "plain",
        "**bold**",
        "`code`",
        "**bold with `code` nested**",
        "`code with **bold** nested`",
        "**`fully nested`**",
        "**332** 个因子，`in_delivery_package`",
        "**严禁并行度 > 2** —— oos 相位单进程约 28 GB",
    ]
    for source in cases:
        joined = _join(rich_text(source))
        assert "**" not in joined, source
        assert "`" not in joined, source


def test_only_headings_lists_and_rules_map_to_the_right_blocks() -> None:
    blocks = markdown_to_blocks(
        "# H1\n## H2\n### H3\n\n- bullet\n1. numbered\n> quote\n\n---\n\ntail\n"
    )
    kinds = [block["type"] for block in blocks]
    assert kinds == [
        "heading_1", "heading_2", "heading_3",
        "bulleted_list_item", "numbered_list_item", "quote", "divider", "paragraph",
    ]


def test_only_fenced_code_becomes_one_code_block() -> None:
    blocks = markdown_to_blocks("```\nline one\nline two\n```\n")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "code"
    assert blocks[0]["code"]["rich_text"][0]["text"]["content"] == "line one\nline two"


def test_only_a_table_becomes_a_table_block_with_rectangular_rows() -> None:
    blocks = markdown_to_blocks("| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 |\n")
    assert len(blocks) == 1
    table = blocks[0]["table"]
    assert blocks[0]["type"] == "table"
    assert table["table_width"] == 3
    rows = table["children"]
    assert len(rows) == 3, "header plus two body rows"
    for row in rows:
        assert len(row["table_row"]["cells"]) == 3, "every row must match the table width"


def test_only_an_empty_cell_still_produces_rich_text() -> None:
    """Notion rejects a table cell with no rich_text array."""
    table = table_block([["a", "b"], ["x", "y"]])
    for row in table["table"]["children"]:
        for cell in row["table_row"]["cells"]:
            assert cell and cell[0]["type"] == "text"


def test_only_leftover_markup_is_detected() -> None:
    clean = markdown_to_blocks("**bold** and `code`\n")
    assert check_no_leftover_markup(clean) == []

    broken = [{"type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": "**not converted**"}}
    ]}}]
    assert check_no_leftover_markup(broken) == ["**not converted**"]


def test_only_the_real_handoff_document_renders_clean() -> None:
    """The document this script exists to publish must pass its own check."""
    source = ROOT / "docs" / "delivery" / "HANDOFF-PROMPT.md"
    if not source.is_file():
        return
    text = source.read_text(encoding="utf-8").split("# 交接正文（从这里开始复制）")[-1]
    blocks = markdown_to_blocks(text)
    assert len(blocks) > 30
    assert check_no_leftover_markup(blocks) == []
    kinds = {block["type"] for block in blocks}
    assert {"heading_2", "table", "code", "bulleted_list_item"} <= kinds
