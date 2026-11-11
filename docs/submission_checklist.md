# EstateIQ final submission checklist

## GitHub repository readiness

- [x] Professional README with overview, architecture, setup, data, evaluation, and limitations.
- [x] `.env` and virtual environment ignored.
- [x] Raw Zillow CSVs and generated SQLite databases ignored.
- [x] Conversation WAL files, nested evaluation checkpoints, caches, logs, and `.DS_Store` ignored.
- [x] `.env.example` contains placeholders only.
- [x] Dependency files and Python version requirement documented.
- [x] Zillow Research attribution and non-redistribution guidance documented.
- [ ] Initialize or restore the Git repository; this workspace currently has no `.git` directory.
- [ ] Confirm `git status`, tracked files, remote URL, default branch, and commit history.
- [ ] Run a repository-aware secret scanner before the first push.
- [ ] Create the GitHub repository and push only after reviewing staged files.

## Documentation

- [x] `README.md`
- [x] `docs/project_documentation.md`
- [x] `docs/evaluation_summary.md`
- [x] `docs/demo_script.md`
- [x] `docs/submission_checklist.md`
- [x] Final evaluation, audit, failure, repair, and human-review artifacts linked.
- [ ] Add approved screenshots under `docs/images/`.
- [ ] Optionally add a sanitized development-prompts appendix; full coding prompts are not currently versioned.

## Validation and evaluation

- [x] Automated suite executed: 48 passed.
- [x] Original 15 scenarios represented in final results.
- [x] Numerical validation, multi-turn behavior, multi-metric behavior, geography, unsupported data, and transient recovery documented.
- [x] Human-review file prepared with blank human scores.
- [ ] Complete independent human review of the three flagged semantic cases.
- [ ] Run one clean atomic final evaluation after the Groq quota resets.
- [ ] Complete three live repetitions of the important LLM scenarios and report the denominator.
- [ ] Verify LangSmith trace upload from a network-enabled environment.

## Demo recording

- [x] Five-minute script prepared.
- [ ] Confirm Groq quota before recording.
- [ ] Record Market Overview and a supported comparison.
- [ ] Show actual agent/tool/validation metadata.
- [ ] Demonstrate an unsupported metric or property-scope guard.
- [ ] Present evaluation improvements and limitations accurately.
- [ ] Review the recording for exposed keys, personal information, or unsupported claims.
- [ ] Upload the final video and copy its shareable URL.

## Gen Academy submission

- [ ] GitHub repository URL: `____________________________`
- [ ] Demo video URL: `____________________________`
- [ ] Required submission form/page URL: `____________________________`
- [ ] Verify repository visibility and reviewer access.
- [ ] Verify README links and Mermaid rendering on GitHub.
- [ ] Submit before the required deadline.

## Outstanding blockers

1. The workspace is not currently a Git repository, so tracked-file and remote checks cannot be completed.
2. Portfolio screenshots and demo video do not yet exist.
3. The required Gen Academy submission link/form was not supplied.
4. Groq quota blocked a fresh atomic final evaluation and three-repeat reliability run.
5. Human review remains incomplete.

Do not push automatically. Review ignored and staged files locally before the first commit, especially `data/`, `.env`, and evaluation checkpoint databases.
