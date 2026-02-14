# README Restructuring Plan

## Style Guide — Borrowed from FastAPI Tutorial

The FastAPI docs are effective because they follow these principles:

1. **Action-first** — The reader does something immediately (install → run → see result) before learning theory.
2. **Progressive disclosure** — Start with the simplest happy path. Details, options, and edge cases come *after*.
3. **Copy-paste-run** — Every code block is a complete, runnable snippet. No pseudo-code.
4. **Short paragraphs** — One idea per paragraph. Liberal use of headings so readers can jump in.
5. **"Check it" moments** — After each action, show what the reader should see (output, browser, etc.).
6. **Tip / Info / Warning boxes** — Call out important notes without breaking the main flow.
7. **Tutorial vs Reference split** — The tutorial tells a story; the reference is a lookup table. They don't mix.

---

## Problem with the Current README

| Issue | Detail |
|-------|--------|
| **Two documents glued together** | Lines 1–230 are a generic "Lakehouse" README. Lines 231–382 are an Azure deployment guide. They have different audiences and different prereqs. |
| **Azure deploy is buried** | The most common use case (deploy to Azure, connect, query) doesn't start until halfway through. |
| **Wall of config** | A 30-row configuration table appears before the reader has even run anything. |
| **No clear "done" moment** | There's no point where the reader sees "you just queried DuckLake on Azure — congrats." |
| **JDBC/ADBC connection instructions are scattered** | ADBC is in Quick Start. JDBC Azure demo is at the very bottom. JDBC README is in a subfolder. |

---

## Proposed Structure

The new README follows a **tutorial flow**: Deploy → Connect → Query → (then everything else).

```
README.md
├─ Title + one-liner + badges
├─ What is Lakehouse? (3 sentences max)
│
├─ 🚀 Deploy to Azure            ← THE MAIN PATH
│   ├─ Prerequisites (az, azd, psql)
│   ├─ Step 1: Clone & configure
│   ├─ Step 2: azd up
│   ├─ Step 3: Verify it's running
│   └─ ✅ Check it — you should see ...
│
├─ 🔌 Connect to Your Server
│   ├─ Option A: JDBC (Java / DBeaver)
│   │   ├─ Get endpoint & password
│   │   ├─ JDBC connection string
│   │   └─ Run the Azure Demo
│   ├─ Option B: ADBC (Python)
│   │   ├─ pip install
│   │   ├─ Connect snippet
│   │   └─ Query snippet
│   └─ ✅ Check it — expected output
│
├─ 📖 What Just Happened? (brief architecture)
│
├─ ── REFERENCE SECTION ──────────────
│
├─ Local Development
│   ├─ Run locally (no Azure)
│   ├─ Tests
│   ├─ Lint & format
│   └─ Type check
│
├─ Configuration Reference
│   └─ Full env/CLI table (current table, moved here)
│
├─ Docker
│
├─ Architecture (diagram + module table)
│
├─ Flight SQL Protocol Support
│
├─ Azure Infrastructure Details
│   ├─ What gets provisioned
│   ├─ Required permissions
│   ├─ Validation commands
│   └─ Troubleshooting / Notes
│
└─ License
```

---

## Section-by-Section Plan

### 1. Title + Hero (5 lines)

Keep the existing title and one-liner. Add a short "why" sentence:

> Query DuckDB over the network using any Flight SQL or ADBC client.
> Deploy to Azure in one command. Connect with JDBC or Python.

### 2. 🚀 Deploy to Azure (~25 lines)

**Goal:** reader goes from zero to a running server on Azure.

```
Prerequisites: az, azd, psql, git

$ git clone … && cd lakehouse
$ azd env new lakehouse-dev
$ azd env set …   (6 env sets — compacted onto fewer lines where possible)
$ azd up
```

Then a "Check it" block:

```
$ az containerapp show … --query properties.configuration.ingress.fqdn
→ ca-lakehouse-xxxxx.centralus.azurecontainerapps.io
```

That's it. Done.

### 3. 🔌 Connect to Your Server (~40 lines)

Two tabs: **JDBC** and **ADBC (Python)**.

**JDBC path:**
1. Get endpoint + password (two `az` commands — keep it copy-paste).
2. Show the `mvn … exec:java` command.
3. Show expected output (catalogs, schemas, the 5 inserted rows).

**ADBC path:**
1. `pip install adbc-driver-flightsql`
2. 6-line Python snippet connecting with TLS to the Azure endpoint.
3. Show expected output.

### 4. 📖 What Just Happened? (~15 lines)

A condensed version of the architecture diagram — just the flow: Client → Flight SQL → DuckDB → DuckLake (PG catalog + Azure Storage). No module table here.

### 5. Local Development (moved from current Quick Start + Development)

- Install: `uv sync`
- Run locally: `uv run lakehouse serve`
- Connect locally (the existing ADBC snippet with `grpc://localhost:31337`)
- Tests, lint, format, type-check (keep as-is, just relocated)

### 6. Configuration Reference

Move the full 30-row table here. No changes to content.

### 7. Docker

Keep as-is — 3 code blocks.

### 8. Architecture (deep dive)

Keep the existing ASCII diagram and module table — moved here from its current position higher up.

### 9. Flight SQL Protocol Support

Keep the existing table.

### 10. Azure Infrastructure Details

Consolidate the "Lakehouse Azure Infrastructure" section:
- What gets provisioned (bullet list)
- Required permissions
- Validation commands
- Troubleshooting notes

This is the current bottom-half content, edited for brevity.

### 11. License

One line. MIT.

---

## Summary of Changes

| What | Action |
|------|--------|
| Azure deploy instructions | **Move to top**, simplify to 4 commands |
| JDBC + ADBC connect | **New section** right after deploy |
| Azure Demo | **Promoted** from bottom to "Connect" section |
| Configuration table | **Moved down** to Reference section |
| Architecture diagram | **Moved down** to Reference section |
| Local dev / Quick Start | **Moved down** below Azure path |
| Azure infra details & notes | **Consolidated** into one Reference section |
| Flight SQL table | **Kept**, moved to Reference section |
| Docker | **Kept**, moved to Reference section |
| Overall length | Roughly the same (~380 lines), but reordered |

---

## Writing Tone (FastAPI-inspired)

- Second person: "you", not "the user"  
- Imperative: "Run this command", not "You can run this command"
- Present tense: "This deploys…", not "This will deploy…"
- Celebrate small wins: "Done. Your server is live." / "You should see 5 rows."
- Keep paragraphs to 1–3 sentences
- Use `> **Tip:**` / `> **Note:**` blocks for optional info
