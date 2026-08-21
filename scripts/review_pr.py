#!/usr/bin/env python3
"""
PR Structured Review — AI-powered review that outputs JSON, not prose.

Usage:
  python scripts/review_pr.py <pr_number>
  python scripts/review_pr.py --diff <path/to/diff.patch>

Output: JSON object with structured verdict + per-criterion checks.

Requires: DEEPSEEK_API_KEY env var (or set in the script).
"""
from __future__ import annotations
import json, os, sys, subprocess, argparse
from typing import Dict, Any, Optional

# ── Config ──────────────────────────────────────────────────────────────────
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = "https://api.deepseek.com/v1"
REVIEW_MODEL = "deepseek-chat"

REVIEW_PROMPT = """You are a code reviewer for the AgentMatrixLab research repository.
Review the following PR diff and return a STRUCTURED JSON verdict.

Focus on:
1. CORRECTNESS: Is the logic right? Are there obvious bugs?
2. SECURITY: Any secrets, tokens, private paths?
3. COMPLETENESS: Does the PR description match the code changes?
4. REPRODUCIBILITY: Can someone else run this and get the same result?
5. FACTOR-SPECIFIC: If this is a factor PR, is there a backtest/proof?

Return ONLY a JSON object (no markdown, no prose):
{
  "verdict": "approve|comment|needs_changes|reject",
  "summary": "<one sentence in Chinese>",
  "checks": {
    "correctness": {"status": "ok|warn|fail", "detail": "<specific issue if any>"},
    "security": {"status": "ok|warn|fail", "detail": "<specific issue if any>"},
    "completeness": {"status": "ok|warn|fail", "detail": "<missing field if any>"},
    "reproducibility": {"status": "ok|warn|fail", "detail": "<can't reproduce because...>"},
    "factor_specific": {"status": "ok|warn|fail|n/a", "detail": "<metrics present or missing>"}
  },
  "recommended_action": "<what the PR author should do next>",
  "risk_level": "low|medium|high"
}"""


def get_pr_diff(pr_number: int) -> Optional[str]:
    """Get PR diff via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number)],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if result.returncode == 0:
            return result.stdout
        print(f"gh error: {result.stderr}", file=sys.stderr)
        return None
    except FileNotFoundError:
        print("gh CLI not found", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def get_pr_body(pr_number: int) -> Optional[str]:
    """Get PR description via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "body", "-q", ".body"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except Exception:
        return None


def review_diff(diff_text: str, pr_body: str = "") -> Dict[str, Any]:
    """Call DeepSeek API to review the diff and return structured verdict."""
    if not DEEPSEEK_KEY:
        return {
            "verdict": "error",
            "summary": "DEEPSEEK_API_KEY not set",
            "checks": {},
            "recommended_action": "Set DEEPSEEK_API_KEY env var",
            "risk_level": "unknown",
        }

    # Truncate diff to avoid token limits
    max_diff_chars = 15000
    if len(diff_text) > max_diff_chars:
        diff_text = diff_text[:max_diff_chars] + "\n... [truncated]\n"

    prompt = REVIEW_PROMPT + f"\n\n# PR Description\n{pr_body[:2000]}\n\n# Diff\n{diff_text}"

    try:
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE)
        resp = client.chat.completions.create(
            model=REVIEW_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.1,
        )
        content = resp.choices[0].message.content or "{}"

        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))

        return {
            "verdict": "error",
            "summary": f"Failed to parse JSON from AI response: {content[:200]}",
            "checks": {},
            "recommended_action": "Retry review",
            "risk_level": "unknown",
        }
    except Exception as e:
        return {
            "verdict": "error",
            "summary": f"API error: {str(e)[:200]}",
            "checks": {},
            "recommended_action": "Check DeepSeek API connectivity",
            "risk_level": "unknown",
        }


def main():
    parser = argparse.ArgumentParser(description="AI-powered PR structured review")
    parser.add_argument("pr_number", nargs="?", type=int, help="PR number to review")
    parser.add_argument("--diff", type=str, help="Path to diff file")
    parser.add_argument("--pr-body", type=str, help="Path to PR body file")
    args = parser.parse_args()

    diff_text = ""
    pr_body = ""

    if args.diff:
        with open(args.diff) as f:
            diff_text = f.read()
    elif args.pr_number:
        diff_text = get_pr_diff(args.pr_number) or ""
        pr_body = get_pr_body(args.pr_number) or ""
    else:
        print(json.dumps({"verdict": "error", "summary": "No PR number or diff provided"}, ensure_ascii=False))
        sys.exit(1)

    if not diff_text.strip():
        print(json.dumps({"verdict": "error", "summary": "Empty diff"}, ensure_ascii=False))
        sys.exit(1)

    if args.pr_body:
        with open(args.pr_body) as f:
            pr_body = f.read()

    result = review_diff(diff_text, pr_body)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
