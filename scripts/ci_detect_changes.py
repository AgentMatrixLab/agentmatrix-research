#!/usr/bin/env python3
"""Detect which factors and submissions have changed in this PR.

Outputs a JSON file with changed factor names and submission directories.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_git_diff(base_ref: str) -> list[str]:
    """Get list of changed files vs base ref."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Fallback: diff against HEAD~1
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1...HEAD"],
            capture_output=True, text=True,
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def detect_factor_lab_changes(files: list[str]) -> list[str]:
    """Detect which alpha101 factors were added/modified.

    Heuristic: if factor_lab/libraries/alpha101/factors.py or specs.py changed,
    check git diff for function-level changes to identify specific factors.
    """
    factor_files = [f for f in files if 'factor_lab' in f]
    if not factor_files:
        return []

    # If factors.py or specs.py changed, find specific function changes
    factors_py_changed = any('factors.py' in f for f in factor_files)
    specs_py_changed = any('specs.py' in f for f in factor_files)
    operators_py_changed = any('operators.py' in f for f in factor_files)

    if operators_py_changed:
        # Operator changes affect all factors
        return ["__ALL__"]

    if factors_py_changed or specs_py_changed:
        # Try to detect specific factor function changes
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD~1...HEAD", "--",
                 "research_core/factor_lab/libraries/alpha101/factors.py",
                 "research_core/factor_lab/libraries/alpha101/specs.py"],
                capture_output=True, text=True,
            )
            diff_text = result.stdout
            factors = set()
            for line in diff_text.splitlines():
                if line.startswith('+def compute_alpha'):
                    # Extract alphaN from compute_alphaN
                    name = line.split('def compute_')[1].split('(')[0]
                    factors.add(name)
                elif line.startswith('+') and 'alpha' in line.lower():
                    # Check for alpha references in specs
                    import re
                    found = re.findall(r'alpha\d+', line)
                    factors.update(found)
            if factors:
                return sorted(factors)
        except Exception:
            pass

        return ["__ALL__"]  # Can't determine, validate all

    # Check for submission-level changes
    if any('cli.py' in f or 'validation.py' in f for f in factor_files):
        return ["__ALL__"]

    return []


def detect_submission_changes(files: list[str]) -> list[str]:
    """Detect changed factor submission directories."""
    submissions = set()
    for f in files:
        if f.startswith('submissions/') and f != 'submissions/README.md':
            parts = Path(f).parts
            if len(parts) >= 2:
                submissions.add(str(Path('submissions') / parts[1]))
    return sorted(submissions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-ref', default='origin/main')
    parser.add_argument('--output-json', default='/tmp/changed_factors.json')
    args = parser.parse_args()

    files = run_git_diff(args.base_ref)

    factor_changes = detect_factor_lab_changes(files)
    submission_changes = detect_submission_changes(files)

    output = {
        "files_changed": len(files),
        "factor_lab_changed": bool(factor_changes),
        "changed_factors": factor_changes,
        "submission_changed": bool(submission_changes),
        "changed_submissions": submission_changes,
    }

    Path(args.output_json).write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))

    # Write submissions list to a separate file for shell usage
    if submission_changes:
        Path('/tmp/changed_submissions.txt').write_text('\n'.join(submission_changes))


if __name__ == '__main__':
    main()
