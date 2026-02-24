# AI Work Rules (Repo Collaboration + Prompt Templates)

This document is for AI/Codex/automation assistants working in this repository, and for humans who want a clear collaboration standard.

Goals:

- Reduce accidental changes
- Keep docs aligned with implementation
- Prevent secret and sensitive-data leakage
- Improve repeatability for complex tasks via reusable templates

## Part 1: Repository Collaboration Rules (for AI/Codex)

## 1. Default Workflow

1. Read before editing: verify real behavior in `cli.py`, `config.py`, and `pipeline.py`
2. Define scope: decide whether the task is docs-only or behavior-changing
3. Make the smallest change that solves the request
4. Self-check consistency: commands, config keys, paths, and statuses must match the code
5. Report changes clearly: what changed, why, and how it was validated

## 2. Editing Principles (Must Follow)

- Preserve existing CLI behavior unless the user explicitly requests behavior changes
- Treat the codebase as the source of truth for documentation
- Do not expand scope on your own (for example, adding config keys or commands)
- Fix inconsistencies first (wrong file names, commands, paths), then improve wording
- For high-risk areas (schema, state flow, AI prompt semantics), state the impact explicitly before changing them

## 3. Key Repository Invariants (Protect These)

### CLI and Parameters

- Command names are defined in `medaudit_diff_watcher/cli.py`:
  - `doctor`
  - `run`
  - `scan-once`
  - `compare`
  - `rebuild-report`
- `--config` is a top-level CLI argument (examples should place it before the subcommand)

### Configuration Model

- Config keys are defined by `medaudit_diff_watcher/config.py` dataclasses and `_build_config()`
- If a config key is added or renamed, update all of:
  - `config.example.yaml`
  - `doc/CONFIGURATION.md`
  - `README.md` (if quick-start behavior changes)

### Report Layout

- Batch directory format is `results-YYYYMMDDHHMMSS`
- Common file-level report files:
  - `detailed_report.html`
  - `row_diffs.csv`
  - `ai_summary.md` (optional)
- Common batch-level files:
  - `index.html`
  - `summary.csv`
  - `batch_ai_summary.md` (optional)

### Storage and Compatibility

- SQLite tables and state flow are defined in `repository.py` and `pipeline.py`
- Do not remove compatibility notes (such as `job_<id>` legacy report paths or schema backfill behavior) unless the code has removed that compatibility

### AI Summary Semantics

- `ai_client.py` contains both file-level and batch-level prompts with explicit output structure requirements
- If prompt text is changed, explain:
  - What problem it addresses (quality, redundancy, factuality, etc.)
  - Output-format compatibility impact
  - Whether tests should be updated (especially fixed-template behavior)

## 4. Security Rules (Must Follow)

- Never copy real API keys from `config.yaml` into docs, logs, or commit messages
- Use `config.example.yaml` for shared examples
- Use placeholder or generic paths in examples; do not expose real business directories
- Do not paste real report data into public contexts without redaction

## 5. Validation Rules (By Change Type)

### Docs-only Changes

At minimum, check:

1. Referenced file paths exist
2. CLI commands match `cli.py`
3. Config keys match `config.py`
4. No sensitive data is exposed

### Config-related Code Changes (`config.py` / template)

At minimum, check:

1. `config.example.yaml` is updated
2. `doc/CONFIGURATION.md` is updated
3. `README.md` quick start still works
4. Multi-watch path isolation docs are still accurate

### Report/Storage-related Changes (`pipeline.py` / `reporting.py` / `repository.py`)

At minimum, check:

1. `doc/REPORTS_AND_STORAGE.md` is updated
2. Report paths/file names are still documented correctly
3. `rebuild-report` docs still match behavior
4. Status names and compatibility notes are still accurate

## 6. Default Prohibitions

- Do not change database schema behavior and remove compatibility logic without confirmation
- Do not rename CLI parameters or subcommands without confirmation
- Do not replace examples with real secrets or real data
- Do not trust IDE tabs or memory for file existence; verify against the repo
- Do not treat non-existent `bc_launcher.py` as the real entry point (the current file is `compare_tool_launcher.py`)

## 7. Pre-Submit Checklist (Recommended)

1. Scope is respected (no unrequested behavior changes)
2. File changes are minimal and focused
3. Doc examples are executable enough (syntax and parameter names are correct)
4. Paths, commands, config keys, and statuses match the code
5. No secrets (for example, API keys) appear in changes

## Part 2: Prompt Templates (Reusable)

Use these templates when asking an AI assistant to work on this repository. Replace bracketed placeholders with your task details.

## Template A: Documentation Update Task

```text
You are maintaining documentation for the MedAudit-Diff-Watcher repository.

Task goal:
- [Describe the documentation change goal]

Constraints:
- Use medaudit_diff_watcher/cli.py, config.py, pipeline.py, and reporting.py as the source of truth
- Do not change Python business logic unless I explicitly ask for it
- Keep documentation aligned with the existing language/style of the repo
- Do not expose real secrets or local business paths from config.yaml

Please do a read-only repo scan first, then provide:
1) Inconsistencies found
2) Files to change
3) Actual edits
4) Self-check results (commands/config keys/paths consistency)
```

## Template B: Bug Fix Task

```text
You are fixing a problem in MedAudit-Diff-Watcher.

Observed issue:
- [Error message / reproduction steps]

Requirements:
- Identify the root cause first (with file/function references)
- Propose the smallest safe fix
- State whether it affects CLI / config / reports / DB schema
- Update docs if the user-facing behavior changes

Output format:
1) Root cause
2) Fix
3) Risk and compatibility impact
4) Validation steps
```

## Template C: Configuration Troubleshooting

```text
Help me troubleshoot a MedAudit-Diff-Watcher configuration issue.

Context:
- Symptom: [doctor fail / compare tool not found / no matching csv / etc.]
- Command used: [command]

Requirements:
- Check actual supported keys and values from config.py first
- Respond as: symptom -> likely causes -> how to verify -> recommended fix
- If sensitive fields are involved (api_key), provide only redacted guidance
```

## Template D: Report Result Interpretation

```text
Help me interpret a MedAudit-Diff-Watcher report result.

I will provide:
- summary.csv (partial)
- key information from index.html
- row_diffs.csv (partial)

Requirements:
- Separate schema changes, row additions/deletions, and suspected modifications
- Do not invent numbers
- If suspected_modified is mentioned, explain it is heuristic matching (not strict primary-key alignment)
- Provide human review suggestions
```

## Template E: AI Summary Quality / Prompt Optimization

```text
Help me improve the AI summary prompt in medaudit_diff_watcher/ai_client.py.

Goal:
- [For example: reduce filler, enforce fixed structure, emphasize field change patterns]

Constraints:
- Keep the current payload structure unless I explicitly approve changing it
- Explain output-format compatibility impact
- If prompt text changes, show before/after differences and reasons
- Evaluate whether tests should be updated (for example, fixed-template behavior)
```

## Template F: Plan First, Implement Later (Complex Task)

```text
Do not change code yet. First do a read-only scan of MedAudit-Diff-Watcher and produce an implementation plan.

Task:
- [Complex goal]

Requirements:
- Identify the real implementation first (entry points, config, data flow, reports/storage)
- List exact files to change
- Provide test/validation strategy
- Call out risks, compatibility impact, and non-goals
- Wait for confirmation before implementing
```

## When to Use Which Template

- Docs tasks: Template A or F
- Bug fixes: Template B
- Configuration issues: Template C
- Report interpretation / review support: Template D
- Prompt-quality tuning: Template E

