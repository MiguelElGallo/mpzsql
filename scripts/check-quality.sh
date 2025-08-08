#!/usr/bin/env bash
# Code quality checker script for mpzsql project

echo "🔍 Running code quality checks..."

echo ""
echo "1️⃣ Checking for duplicate function/method definitions..."
uv run ruff check --select F811 .
if [ $? -ne 0 ]; then
    echo "❌ Found duplicate definitions!"
    exit 1
fi
echo "✅ No duplicate definitions found"

echo ""
echo "2️⃣ Checking function complexity (max 15)..."
uv run ruff check --select C90 .
if [ $? -ne 0 ]; then
    echo "❌ Found overly complex functions!"
    exit 1
fi
echo "✅ All functions within complexity limits"

echo ""
echo "3️⃣ Checking for unused arguments..."
uv run ruff check --select ARG .
if [ $? -ne 0 ]; then
    echo "⚠️ Found unused arguments (consider fixing)"
fi

echo ""
echo "4️⃣ Checking for magic numbers..."
uv run ruff check --select PLR2004 .
if [ $? -ne 0 ]; then
    echo "⚠️ Found magic numbers (consider using constants)"
fi

echo ""
echo "5️⃣ Running full pre-commit checks..."
uv run pre-commit run --all-files
if [ $? -ne 0 ]; then
    echo "⚠️ Pre-commit found issues (some may be auto-fixed)"
fi

echo ""
echo "✅ Code quality check complete!"
