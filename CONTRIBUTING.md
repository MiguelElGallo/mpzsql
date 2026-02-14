# Contributing to Lakehouse

Thanks for your interest in improving Lakehouse.

## Development Setup

```bash
git clone https://github.com/MiguelElGallo/lakehouse.git
cd lakehouse
uv sync --group dev
```

## Local Checks (required before PR)

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run ty check src/lakehouse/
uv run pytest
```

## Coding Guidelines

- Follow existing style and structure in `src/lakehouse/`.
- Add tests for behavior changes and bug fixes.
- Keep changes focused; avoid unrelated refactors.
- Update docs when behavior, config, or deployment steps change.

## Commit and PR Guidelines

- Use clear, descriptive commit messages.
- In your PR description, include:
  - what changed
  - why it changed
  - how it was tested
- Link related issues where relevant.

## Security

This software is experimental, no commitment to fix security vulnerabilities.
