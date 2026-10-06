# Security Policy

## Reporting a vulnerability
Please report privately through GitHub: **Security > Report a vulnerability** on this repository. Do not open a public issue. Expect an acknowledgement within a few days.

## Scope
The scripts, workflows and published datasets. Credentials (`KAGGLE_KEY`, optional `LLM_API_KEY`) live only in GitHub Actions secrets; if you find one exposed anywhere, report it immediately.

## Data concerns
If a dataset row exposes personal information about a victim or private individual, report it the same way and it will be removed from the next release.

Only the `main` branch is supported.
