# Code Quality Setup

This project uses pre-commit hooks with ruff for code quality enforcement.

## Setup

Pre-commit hooks should be automatically installed, but if needed:

```bash
uv run pre-commit install
```

## Running Checks

### All checks
```bash
uv run pre-commit run --all-files
```

### Quick quality check
```bash
./scripts/check-quality.sh
```

### Specific checks
```bash
# Check for duplicate definitions
uv run ruff check --select F811 .

# Check function complexity
uv run ruff check --select C90 .

# Auto-fix formatting and simple issues
uv run ruff check --fix .
uv run ruff format .
```

## What Gets Checked

- **Duplicate definitions (F811)**: Catches duplicate function/method definitions
- **Complexity (C90)**: Functions with complexity > 15 are flagged
- **Code formatting**: Consistent style with ruff format
- **Import sorting**: Organized imports
- **Unused arguments (ARG)**: Identifies potentially unused parameters
- **Magic numbers (PLR2004)**: Encourages using named constants
- **Security issues**: Basic security anti-patterns
- **Performance**: Common performance improvements
- **File formatting**: Trailing whitespace, end-of-file newlines
- **YAML/TOML/JSON**: Syntax validation

## Configuration

See `pyproject.toml` `[tool.ruff.lint]` section for rule configuration.

## IDE Integration

Most editors support ruff integration:
- **VS Code**: Install the Ruff extension
- **PyCharm**: Ruff plugin available
- **Vim/Neovim**: Various ruff plugins

The pre-commit hooks will catch issues before commit, but IDE integration provides real-time feedback.
