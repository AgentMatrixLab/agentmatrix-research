# Summary

<!-- REQUIRED: Delete placeholder text and write your own answers. PRs with unfilled sections may be flagged by CI. -->

- **What problem does this PR solve?** (one sentence)
- **What changed?** (file list + one-line per file)
- **Why is this change correct?** (evidence, not opinion)
- **Main review targets:** files/modules reviewers should inspect first

# Change Type

- [ ] factor mining
- [ ] factor reproduction
- [ ] qlib workflow
- [ ] backtest adapter
- [ ] strategy engine
- [ ] API / contract change
- [ ] workflow / CI
- [ ] documentation
- [ ] repository hygiene

# AI Assistance Record

- [ ] This PR was primarily drafted by AI
- [ ] This PR was partially drafted by AI and partially edited manually
- [ ] I reviewed the final diff before submitting

AI-generated or AI-assisted areas (required):

```text
List files, functions, or code blocks that were primarily written or heavily modified by AI.
If none, write "none".
```

# Prompt / Instruction Record

- Main prompt or instruction used:
- What I asked the agent to implement:
- Files or functions I manually adjusted after AI output:

# Verification (Required)

- [ ] I ran the following command(s) and they passed
- [ ] I checked for secrets, API keys, and private paths: **no issues**
- [ ] I reviewed generated files and artifact locations
- [ ] I confirmed there are no local absolute paths / machine-specific references

Verification output:

```text
Paste the exact commands you ran and the key output.
Do not leave this block empty.
```

Areas not validated:

```text
List anything you did not run, did not check, or are not confident about.
If none, write "none".
```

# Research / Business Context

- Hypothesis:
- Universe / market:
- Time range:
- Main command(s) run:

# Key Metrics (for research PRs)

| Metric | Value |
|--------|-------|
| IC / Rank IC / ICIR | |
| Backtest return / Sharpe / Max DD | |
| Baseline comparison | |

# Artifacts

- Evaluation JSON path:
- Backtest JSON path:
- Proof artifact path:
- Screenshot or chart links:

# Risk Checklist

- [ ] This PR changes factor formula or factor spec
- [ ] This PR changes data loading / universe selection / point-in-time logic
- [ ] This PR changes backtest / target weights / execution assumptions
- [ ] This PR changes API response shape or contract fields
- [ ] This PR changes CI / workflow / deployment behavior

If any box above is checked, explain the regression risk and how you verified it:

```text
Describe the specific risk and the exact verification you ran.
```

# Hygiene Check

- [ ] No API keys, tokens, or `.env` files
- [ ] No absolute paths (`/home/`, `C:\Users\`)
- [ ] No downloaded data or large runtime artifacts
- [ ] No account-linked identifiers or private exports

# Self-Review

- **What's the riskiest part of this change?**
- **What did you test manually?**
- **What should reviewers focus on?**
