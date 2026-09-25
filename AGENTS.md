# AGENTS.md

## Purpose

This repository is a hands-on exercise and doc stack for the AI Observability Lab.

## Required baseline files

Unless the task explicitly says otherwise, preserve or improve these files:

- `README.md`
- `LICENSE`
- `CODEOWNERS`
- `SUPPORT.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/dependabot.yml`
- `.github/workflows/`
- `.github/ISSUE_TEMPLATE/`
- `AGENTS.md`
- `.github/copilot-instructions.md`

## Documentation guidance

- Treat the markdown files in the `docs` folder as the documentation of this project.
- Prefer concrete, action-oriented instructions.
- Prefer policy-style wording where expectations are mandatory.
- Keep support and ownership language explicit.
- Keep examples short and easy to copy into generated repositories.
- Clearly mark placeholder values that must be replaced.

## Workflow guidance

Before proposing changes:
- check whether ownership, support, or publication expectations are affected
- preserve review-friendly workflows
- avoid unnecessary complexity
- avoid adding language-specific tooling unless it is broadly useful across most repositories created from this template

## Pull request guidance

When preparing a pull request:
- summarize what changed
- explain why the change improves the template
- call out any new maintainer actions required after repository creation
- keep the scope focused and easy to review

## Review checklist

When reviewing changes to this repository or repositories created from this template, verify that:

- `CODEOWNERS` is present
- support expectations are documented
- placeholder text is clearly marked
- no secrets or environment-specific values are included
- baseline automation is present and understandable
- maintainers can tell what must be updated before publication

## What to avoid

- Do not assume repositories created from this template are commercially supported.
- Do not add heavy automation unless it is broadly useful.
- Do not leave unclear placeholders that could accidentally ship to a public repository.
- Do not optimize for a single language or stack unless the template is intentionally stack-specific.
