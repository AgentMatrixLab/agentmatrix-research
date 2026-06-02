# Open Source Sanitization Checklist

Use this checklist before pushing changes to the public repository.

## Secrets

- No API keys, tokens, passwords, cookies, or private certificates are committed.
- `.env` files stay local and are never added to Git.
- Example code reads credentials from environment variables only.

## Local Paths

- CLI examples use relative paths, placeholders, or documented arguments.

## Data And Artifacts

- Real trading exports, account reports, and client datasets are not committed.
- Generated outputs stay under ignored directories such as `data/`, `runtime/`, or other local artifact folders.
- Example artifacts are synthetic or fully anonymized.

## Third-Party Materials

- PDFs, reports, screenshots, and sample documents are either created internally or cleared for redistribution.
- Remove any sample file with unclear ownership before merging.

## Account-Linked Identifiers

- Demo strategies do not include real account-bound IDs.
- Replace provider-specific IDs with placeholders or environment variables.

## Documentation

- Docs do not reveal personal usernames, machine names, or internal-only file locations.
- Setup instructions explain required environment variables clearly.

## Final Check

- Run `git diff --check` and review the final diff.
- Run repository searches for `C:\Users\`, `Desktop`, `token`, `secret`, and `key` before opening a PR.
- If unsure whether a file is safe to publish, remove it from the PR and ask for review.
