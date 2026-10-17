# Work Log

## 2026-10-17 — Runtime security and demo bundle verification

### Redis TLS correction

- Reviewed the runtime diff, Celery config, current backend tests, and project status/runbook before changing files.
- Changed managed Redis TLS certificate requirements from `ssl.CERT_NONE` to `ssl.CERT_REQUIRED`. The existing scheme check continues to apply TLS options only to `rediss://`; local `redis://` receives none.
- Added a regression assertion for required certificate verification alongside the existing plain-Redis/TLS-selection tests. Inspected the installed Celery/Kombu/redis-py SSL handling; the configuration uses Celery's supported `ssl_cert_reqs` option.
- Managed Redis TLS handshake/certificate-chain could not be exercised because no managed Redis endpoint or credentials were supplied. Local loopback Redis startup had already been verified.

### Verification commands and results

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **38 passed, 0 failed, 0 skipped, 0 blocked**, 11 warnings, exit code 0.
- `cd backend && .venv/bin/python -m pip check` — passed (`No broken requirements found`); pip cache was unavailable and disabled, which did not affect the check.
- `git diff --check` — passed.
- `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform android --output-dir /tmp/vitalyze-demo-android-export-final` — passed; emitted Android JS bundle, not APK/install/device verification.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform ios --output-dir /tmp/vitalyze-demo-ios-export-final` — passed; emitted iOS JS bundle, not simulator/device verification.
- Secret scan over staged project sources/docs and final staged diff — no credential values or private-key material found; templates use placeholders. Scan output was limited to file names/counts to avoid displaying matched content.
- `npm run lint` remains unavailable because no lint script is declared. No native simulator/device was available; actual screen flows remain unverified.

### Expo URL and LAN safety

- Documented target URLs: iOS Simulator uses `localhost`; Android Emulator uses host alias `10.0.2.2`; a physical device uses the Mac's current private Wi-Fi IP.
- Documented physical-device setup requires both devices on trusted private Wi-Fi, LAN-bound Uvicorn/Expo, firewall allowlisting for the private subnet, and no router port forwarding. The physical-device path was not tested; current local servers were loopback-only.
- Updated `docs/PROJECT_STATUS.md` and `docs/DEMO_RUNBOOK.md` with the results and remaining blockers. Feature outcomes remain separated as synthetic/mock checks vs live external integrations; no real WhatsApp message or external provider call was made.
- Created a new checkpoint commit after reviewing the complete staged diff. Checkpoint `634e5b1` was preserved; no amend, push, or deployment was performed.

## 2026-10-17 — Interview demo checkpoint

- Reviewed the full worktree, application diffs, new tests/docs, environment template, and ignore rules before staging.
- Confirmed the template contains only placeholders, local/default configuration, or empty optional values; detected test data is synthetic. Virtual environments, Python caches, and upload artifacts were excluded.
- Created checkpoint commit `634e5b1` (`Secure report access and harden backend validation`) with the reviewed Phase 3B/3C work and `docs/DEMO_RUNBOOK.md`.
- Runtime testing had not started at checkpoint time; no production configuration or external integrations were used.

### Runtime bootstrap milestone

- Confirmed local-only MongoDB 8.2.9 and Redis 8.6.2 startup; Redis persistence is disabled and MongoDB uses a fresh temporary data path.
- FastAPI startup and MongoDB connection succeeded with local synthetic settings; OpenAPI was reachable locally and declared 12 route paths.
- Celery worker startup is blocked by a confirmed TLS configuration mismatch for `redis://`: SSL options are applied unconditionally. No task was sent and no real reminder was loaded.
- Updated `backend/app/tasks/celery_app.py` to apply TLS options only for `rediss://`, and added `backend/tests/test_celery_config.py` covering plain and TLS Redis URLs. Focused tests: 2 passed. Full backend suite: 34 passed, 0 failed, 0 skipped, 0 blocked (11 warnings).
- Retried with temporary local services: the worker connected to loopback Redis and reached `ready`; Beat started using a `/tmp` schedule file. Both restoration hooks found zero daily reminders in the fresh local database. No tasks or messages were dispatched.
- Frontend manifest/lockfile match and `npm ls --depth=0` passed; Expo CLI is 54.0.23. Typecheck and Expo server verification are pending.
- The API service URL in frontend source is hard-coded to a different private IP than this machine's active interface; frontend connectivity has not yet been verified.
- Replaced the hard-coded private IP with `EXPO_PUBLIC_API_URL` and a `localhost` fallback; added `frontendv3/.env.example`. `npx tsc --noEmit` passed; Expo Metro started offline, and an iOS bundle contained the configured localhost URL and not the stale IP. No iOS simulator or Expo web runtime is available (missing simulator/Xcode and `react-native-web`/`react-dom`), so actual screen-generated requests remain blocked.
- Frontend package Axios made a real request to the configured local API URL; the protected report-history endpoint returned the expected 401. Frontend-to-backend network reachability is verified, but no authenticated native UI session was run.
- Synthetic report flow passed with local MongoDB, real digital-PDF text extraction, mocked AI functions, and stubbed Celery dispatch/status. Authentication, upload, save, status authorization, and report history endpoints were exercised. No Vertex/GCS calls or real patient data were used. Scanned-PDF OCR and actual asynchronous report-task completion remain unverified.
- First report harness attempt with Celery eager execution failed in the harness because the sync task tried to run an event loop inside the async TestClient request. This is not the normal worker execution mode; rerunning with dispatch stubs and direct task execution outside the request event loop passed. The eager-mode result and limitation are documented in the runbook.
- Daily/refill reminder API flow passed with synthetic credentials/user data and a dedicated local MongoDB database. Celery registration/queue functions were mocked; the authenticated profile reflected persisted reminders. No WhatsApp service or real Celery message was called. Actual WhatsApp integration remains blocked by missing credentials and explicit no-send policy.
- Pharmacy route checks passed using mocked Maps data: success (200), invalid coordinates (422), mocked provider failure (`200 []`), and missing key (503). No Google request was made. Device location permission and Google Maps link opening remain untested.
- Chatbot route checks passed with a synthetic response, blank input (422), and missing credential (generic 502 with no detail leakage). No Vertex call was made.
- Trends/history was checked via the report flow and returned the synthetic saved report/value for the authenticated user. The visual chart was not rendered due missing native simulator/web dependencies.
- Added safe local startup commands and limitations to `docs/DEMO_RUNBOOK.md`; no real service credentials were written.
- Removed logging/return of WhatsApp recipient, medicine, and provider response/error details; added a 10-second HTTP timeout. Mocked service success/failure tests and task payload/result privacy tests passed (4 tests). Automatic retries and duplicate-send idempotency remain unresolved. No WhatsApp request was made.

### Final runtime regression/check results

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — latest run after all runtime code fixes: **38 passed, 0 failed, 0 skipped, 0 blocked**, 11 warnings.
- `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform ios --output-dir /tmp/vitalyze-demo-ios-export` — passed; generated output stayed in `/tmp`.
- `cd frontendv3 && npm run lint` — failed because no `lint` script is declared (confirmed setup gap, not a source lint failure).
- `cd backend && .venv/bin/python -m pip check` — passed; no broken requirements.
- `git diff --check` — passed. Frontend `npm ls --depth=0` passed; lockfile package identity/version matches `package.json`.
- The local Axios request to protected report history returned the expected 401. API URL embedding and iOS bundle generation were verified; actual mobile screens were not run.
- Runtime code fixes after checkpoint `634e5b1` remain uncommitted: conditional Celery TLS config and configurable Expo API URL. No additional commit or push.
- The WhatsApp privacy/timeout fixes are also uncommitted. Remote Redis TLS still uses the existing `CERT_NONE` option; it was not changed or validated against a managed broker.
- Local OCR tool check: `tesseract`, `pdftoppm`, and `pdfinfo` are unavailable, so scanned-PDF OCR is blocked. Digital PDF text extraction passed.
- Restarted the local worker and Beat after reminder logging/timeout changes; the worker reached `ready`, Beat started, and restoration found zero reminders.

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
