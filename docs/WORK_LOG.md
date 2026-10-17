# Work Log

## 2026-10-17 — Interview demo checkpoint

- Reviewed the full worktree, application diffs, new tests/docs, environment template, and ignore rules before staging.
- Confirmed the template contains only placeholders, local/default configuration, or empty optional values; detected test data is synthetic. Virtual environments, Python caches, and upload artifacts were excluded.
- Created checkpoint commit `1b2977d` (`Secure report access and harden backend validation`) with the reviewed Phase 3B/3C work and `docs/DEMO_RUNBOOK.md`.
- Runtime testing had not started at checkpoint time; no production configuration or external integrations were used.

## 2026-10-17 — Phase 3C reminder and chatbot fixes

### Changes

- Added Pydantic field validation to both daily and refill reminder inputs so blank or whitespace-only medicine names return 422 before task scheduling or persistence.
- Added chatbot message validation so blank or whitespace-only input returns 422 before model initialization/provider invocation.
- Replaced chatbot exception detail exposure with a generic 502 response. Internal logging records only exception class, avoiding provider exception text, URLs, and credentials.
- Extended regression coverage for blank and whitespace-only reminder names, blank chatbot inputs, valid chatbot requests, and upstream failure detail/log redaction.

### Commands and results

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **32 passed, 0 failed, 0 skipped, 0 blocked**, 11 warnings, exit code 0.
- `cd backend && .venv/bin/python -m pip check` — passed; no broken requirements. Pip noted its user cache is unavailable and disabled caching.
- `git diff --check` — passed.
- Secret-pattern scan over `backend/app`, `backend/tests`, and `docs` — only matched the synthetic test hash in `backend/tests/conftest.py`; no real secrets identified.
- Final diff/status inspection — changes limited to the reminder/chat fixes, regression tests, and phase documentation, alongside previously reviewed Phase 3B changes. No commit or push.

No production service, external provider, WhatsApp API, or real patient data was used.

## 2026-10-17 — Phase 3B backend security and report persistence

### Inspection and decisions

- Inspected report upload, Celery chain results, task processing, status polling, authentication dependencies, MongoDB access, user route, and user/report Pydantic models.
- The current result model had no persistent task-to-user association while a report was pending. Added a minimal `report_jobs` owner record at upload time; status access now fails closed when the record is missing or belongs to another user.
- Made `/api/v1/users/{user_id}` self-only and added a public response model that does not include password-related data.
- Changed report processing to raise on empty extracted text or a required report save failure. Internal errors are logged; callers receive generic task failure information.

### Files changed

- `backend/app/api/v1/endpoints/reports.py`
- `backend/app/api/v1/endpoints/users.py`
- `backend/app/models/user.py`
- `backend/app/tasks/report_processing.py`
- `backend/tests/conftest.py`
- `backend/tests/test_api_baseline.py`
- `backend/tests/test_report_tasks.py`
- `docs/PROJECT_STATUS.md`
- `docs/WORK_LOG.md`

### Commands and results

- `PYTHONPATH=. .venv/bin/pytest -q --tb=short` (from `backend/`) — **23 passed, 3 failed, 0 skipped, 0 blocked**, 11 warnings, exit code 1.
- `.venv/bin/python -m pip check` (from `backend/`) — passed; no broken requirements.
- `git status --short` — no commit or push performed.

Those three Phase 3B baseline failures were resolved and verified in Phase 3C. No test contacted real services or used real patient data.
