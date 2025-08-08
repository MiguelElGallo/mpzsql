#!/usr/bin/env bash
# Code quality checker script for mpzsql project

echo "🔍 Running comprehensive code quality checks..."

echo ""
echo "1️⃣ Checking for duplicate function/method definitions..."
uv run ruff check --select F811 .
if [ $? -ne 0 ]; then
    echo "❌ Found duplicate definitions!"
    exit 1
fi
echo "✅ No duplicate definitions found"

echo ""
echo "2️⃣ Checking import issues and critical bugs..."
uv run ruff check --select F,B .
if [ $? -ne 0 ]; then
    echo "⚠️ Found import issues or potential bugs (many fixable)"
fi

echo ""
echo "3️⃣ Running minimal pre-commit checks..."
uv run pre-commit run --all-files
if [ $? -ne 0 ]; then
    echo "⚠️ Pre-commit found critical issues"
fi

echo ""
echo "4️⃣ Running full style check (optional)..."
echo "💡 Note: This may show many style issues but won't block commits"
uv run ruff check . | head -20
echo "   ... (use 'uv run ruff check .' for full output)"

echo ""
echo "✅ Code quality check complete!"
echo "💡 Pre-commit only blocks critical issues (duplicates, syntax errors, undefined vars)"
echo "💡 Full style checking available manually with 'uv run ruff check .'"
