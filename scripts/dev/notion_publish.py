"""Publish a markdown file as a Notion page under the project's tracking page.

Why this exists: the project already delivered to Notion this way once (see
docs/superpowers/reports/2026-10-03-ds-notion-submission.md). There is no Notion CLI, no
plugin and no MCP server -- the submission used the REST API directly with a token that
was provided at runtime and deliberately never written to disk. This is the same method,
rebuilt as a script so the next submission is one command.

Method recorded in that report and followed here:
  * parent page 「2026-10执行情况」 = 3ece9a01-c0bb-8017-87c1-c8c86dd1dc92
  * the renderer must handle inline bold, inline code, and BOLD CONTAINING CODE -- the
    first batch of pages was rebuilt because a simpler renderer left literal `**` and
    backticks in the text
  * a page created by the API is appended at the END of a parent that already has 100+
    blocks, so verifying requires paging through with start_cursor rather than reading
    the first page

Usage:
    export NOTION_TOKEN=...
    python -X utf8 scripts/dev/notion_publish.py --dry-run          # render only, no network
    python -X utf8 scripts/dev/notion_publish.py --verify-only      # list recent children
    python -X utf8 scripts/dev/notion_publish.py                    # publish
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
PARENT_PAGE_ID = "3ece9a01-c0bb-8017-87c1-c8c86dd1dc92"
MAX_CHILDREN_PER_REQUEST = 100


class NotionError(RuntimeError):
    pass


# ── markdown → rich text ─────────────────────────────────────────────────────

_TOKEN = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")


def rich_text(text: str) -> list[dict]:
    """Split a line into Notion rich_text runs, honouring **bold** and `code`, nested.

    The nesting is why this is a small parser rather than a regex split. A regex
    alternation matches `**bold with `code` nested**` as ONE bold token, strips the outer
    `**`, and leaves the inner backticks in the published text -- which is precisely the
    leftover-markup failure that forced the earlier submission to be redone. Here the
    inner content of a matched span is parsed again, so annotations accumulate (bold AND
    code) and no marker character survives.
    """
    runs: list[dict] = []

    def emit(content: str, bold: bool, code: bool) -> None:
        if not content:
            return
        runs.append(
            {
                "type": "text",
                "text": {"content": content},
                "annotations": {"bold": bold, "code": code},
            }
        )

    def parse(segment: str, bold: bool, code: bool) -> None:
        buffer = ""
        index = 0
        while index < len(segment):
            if segment.startswith("**", index):
                close = segment.find("**", index + 2)
                if close != -1:
                    emit(buffer, bold, code)
                    buffer = ""
                    parse(segment[index + 2:close], True, code)
                    index = close + 2
                    continue
            if segment[index] == "`":
                close = segment.find("`", index + 1)
                if close != -1:
                    emit(buffer, bold, code)
                    buffer = ""
                    parse(segment[index + 1:close], bold, True)
                    index = close + 1
                    continue
            buffer += segment[index]
            index += 1
        emit(buffer, bold, code)

    parse(text, False, False)
    return runs or [{"type": "text", "text": {"content": ""}}]


def text_block(kind: str, line: str, **extra) -> dict:
    payload = {"type": kind, kind: {"rich_text": rich_text(line)}}
    payload[kind].update(extra)
    return payload


def table_block(rows: list[list[str]]) -> dict:
    width = max(len(r) for r in rows)
    children = []
    for row in rows:
        cells = [rich_text(cell) for cell in row] + [[{"type": "text", "text": {"content": ""}}]] * (width - len(row))
        children.append({"type": "table_row", "table_row": {"cells": cells}})
    return {
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": children,
        },
    }


def markdown_to_blocks(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        # fenced code
        if stripped.startswith("```"):
            index += 1
            body: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            index += 1
            blocks.append(
                {
                    "type": "code",
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": "\n".join(body)[:2000]}}],
                        "language": "plain text",
                    },
                }
            )
            continue

        # tables: a header row followed by a separator row
        if stripped.startswith("|") and index + 1 < len(lines) and set(lines[index + 1].strip()) <= set("|-: "):
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [c.strip() for c in lines[index].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append(cells)
                index += 1
            if rows:
                blocks.append(table_block(rows))
            continue

        if not stripped:
            index += 1
            continue
        if stripped.startswith("<!--") or stripped.startswith("# 交接正文"):
            index += 1
            continue
        if set(stripped) <= set("-—") and len(stripped) >= 3:
            blocks.append({"type": "divider", "divider": {}})
            index += 1
            continue
        if stripped.startswith(">"):
            blocks.append(text_block("quote", stripped.lstrip("> ").strip()))
            index += 1
            continue

        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(text_block(f"heading_{level}", heading.group(2)))
            index += 1
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", stripped)
        if bullet:
            blocks.append(text_block("bulleted_list_item", bullet.group(1)))
            index += 1
            continue

        numbered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if numbered:
            blocks.append(text_block("numbered_list_item", numbered.group(1)))
            index += 1
            continue

        blocks.append(text_block("paragraph", stripped))
        index += 1
    return blocks


def check_no_leftover_markup(blocks: list[dict]) -> list[str]:
    """The failure that forced a rebuild last time: literal markers surviving into Notion."""
    problems: list[str] = []

    def walk(node: dict) -> None:
        kind = node.get("type")
        if kind:
            for run in (node.get(kind) or {}).get("rich_text", []) or []:
                content = run.get("text", {}).get("content", "")
                if "**" in content or (content.count("`") % 2):
                    problems.append(content[:80])
        for child in (node.get(kind) or {}).get("children", []) if kind else []:
            walk(child)

    for block in blocks:
        walk(block)
    return problems


# ── Notion REST ──────────────────────────────────────────────────────────────

def request(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise NotionError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise NotionError(f"{method} {path} -> {exc.reason}") from exc


def list_children(token: str, page_id: str) -> list[dict]:
    """Page through EVERY child: API-created pages are appended at the end of a long parent."""
    out: list[dict] = []
    cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if cursor:
            path += f"&start_cursor={cursor}"
        payload = request("GET", path, token)
        out.extend(payload.get("results", []))
        if not payload.get("has_more"):
            return out
        cursor = payload.get("next_cursor")


def publish(token: str, title: str, blocks: list[dict], parent: str) -> str:
    first, rest = blocks[:MAX_CHILDREN_PER_REQUEST], blocks[MAX_CHILDREN_PER_REQUEST:]
    page = request(
        "POST",
        "/pages",
        token,
        {
            "parent": {"page_id": parent},
            "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
            "children": first,
        },
    )
    page_id = page["id"]
    for offset in range(0, len(rest), MAX_CHILDREN_PER_REQUEST):
        request(
            "PATCH",
            f"/blocks/{page_id}/children",
            token,
            {"children": rest[offset:offset + MAX_CHILDREN_PER_REQUEST]},
        )
    return page_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--markdown", default="docs/delivery/HANDOFF-PROMPT.md")
    parser.add_argument("--title", default="DS回报｜10-06 22:10｜晨星 300 因子交付完成（332 个 / 23 项验收全过）")
    parser.add_argument("--parent", default=PARENT_PAGE_ID)
    parser.add_argument("--dry-run", action="store_true", help="render and validate, no network")
    parser.add_argument("--verify-only", action="store_true", help="list the parent's children and exit")
    parser.add_argument("--list-blocks", type=int, default=0, help="print the first N rendered blocks")
    args = parser.parse_args(argv)

    token = os.environ.get("NOTION_TOKEN", "").strip()
    if not token and not args.dry_run:
        print("NOTION_TOKEN is not set. It was never persisted to disk by design -- provide it")
        print("in the environment for this command, then re-run.")
        return 2

    if args.verify_only:
        children = list_children(token, args.parent)
        print(f"parent {args.parent}: {len(children)} child block(s)")
        for child in children:
            kind = child.get("type")
            title = ""
            if kind == "child_page":
                title = (child.get("child_page") or {}).get("title", "")
            print(f"  {child['id']}  {kind:14s} {title}")
        return 0

    text = Path(args.markdown).read_text(encoding="utf-8")
    # Drop the copy markers so they do not become content in Notion.
    text = text.split("# 交接正文（从这里开始复制）")[-1]
    text = re.sub(r"^#\s*交接正文（复制到此结束）\s*$", "", text, flags=re.MULTILINE)
    blocks = markdown_to_blocks(text)
    problems = check_no_leftover_markup(blocks)

    print(f"markdown : {args.markdown}")
    print(f"blocks   : {len(blocks)}")
    kinds: dict[str, int] = {}
    for block in blocks:
        kinds[block["type"]] = kinds.get(block["type"], 0) + 1
    print(f"kinds    : {kinds}")
    print(f"leftover markup runs: {len(problems)}")
    for problem in problems[:5]:
        print(f"  !! {problem}")

    if args.list_blocks:
        for block in blocks[: args.list_blocks]:
            print(json.dumps(block, ensure_ascii=False)[:200])

    if args.dry_run:
        if problems:
            print("\nDRY RUN: leftover markup found -- fix the renderer before publishing")
            return 1
        print("\nDRY RUN ok: no network calls made")
        return 0

    if problems:
        print("\nrefusing to publish with leftover markup")
        return 1

    before = {c["id"] for c in list_children(token, args.parent)}
    page_id = publish(token, args.title, blocks, args.parent)
    print(f"\npublished page: {page_id}")

    after = list_children(token, args.parent)
    found = [c for c in after if c["id"] == page_id]
    print(f"verified by paging back: {'YES' if found else 'NO'} "
          f"(parent now has {len(after)} children, was {len(before)})")
    print(f"url: https://www.notion.so/{page_id.replace('-', '')}")
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
