# Project Status

## Interview demo runtime milestone — 2026-10-17 (verified update)

Checkpoint `634e5b1` contains the reviewed Phase 3B/3C changes. The second checkpoint contains the following runtime fixes and verification updates:

- Celery TLS options are now applied only to `rediss://` brokers, with `ssl.CERT_REQUIRED` certificate verification. Plain local `redis://` continues to receive no TLS options. The focused tests assert both behaviors. Local loopback Redis worker startup was verified; no managed Redis TLS endpoint was available, so certificate-chain validation against a managed service remains unverified.
- Frontend API configuration now uses `EXPO_PUBLIC_API_URL` with a `localhost` fallback rather than a hard-coded private IP. TypeScript passed, Metro started offline, and a generated iOS JS bundle included the local API URL without the stale IP. A real Axios request from the frontend package reached FastAPI and received the expected 401 for protected report history.
- Synthetic report flow passed through registration, upload, real digital-PDF text extraction, mocked AI analysis, local MongoDB persistence, authenticated status, and history. Celery dispatch/status were stubbed for this flow; the worker itself was independently verified. Vertex AI, GCS, scanned-PDF OCR, and actual async result polling remain unverified.
- Synthetic daily/refill reminder API checks passed with scheduling mocked and data persisted only in a dedicated local test DB. No WhatsApp call or queued message was made.
- Pharmacy route checks passed with mocked Maps data, including success, malformed query, provider failure, and missing-key responses. Google Maps credentials are absent and no external request was made.
- Chat route passed with a mocked response; blank input and missing-credential behavior returned 422 and generic 502. Vertex AI was not contacted. Trends/history returned the saved synthetic report through the authenticated API.
- WhatsApp service/task logs and Celery result strings were found to expose recipient/medication values and provider response details. They now log generic status plus exception class only, return generic task statuses, and enforce a 10-second provider request timeout. Four mocked privacy/payload tests pass; no WhatsApp request was sent. Retry and duplicate-send idempotency are unresolved.
- Native UI verification is incomplete: no iOS simulator/Xcode or Android emulator/device was available, and Expo web dependencies (`react-native-web`, `react-dom`) are absent. Location permission, Google Maps link opening, and rendered chart behavior were not exercised.

Local services used a fresh temporary MongoDB data path and Redis with persistence disabled. All patient-like records were synthetic and stored in dedicated local databases. No production configuration or external integration was used. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) for commands and remaining limits.

Managed Redis TLS now requires trusted certificate verification with `ssl.CERT_REQUIRED`. The setting was validated by regression test and inspection of the installed Celery/redis-py handling, but no live managed Redis service was available for a TLS handshake test.

Final regression/check commands after the runtime fixes and Redis TLS security correction:

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **38 passed, 0 failed, 0 skipped, 0 blocked**, 11 warnings.
- `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform android --output-dir /tmp/vitalyze-demo-android-export-final` — passed; Android JS bundle exported to `/tmp` (not an APK or device launch).
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform ios --output-dir /tmp/vitalyze-demo-ios-export-final` — passed; iOS JS bundle exported to `/tmp` (not a simulator launch).
- `cd frontendv3 && npm run lint` — unavailable; `package.json` has no `lint` script.
- `cd backend && .venv/bin/python -m pip check` — passed; no broken requirements.
- `git diff --check` — passed.
- Redis TLS regression confirms `CERT_REQUIRED` for `rediss://` and no TLS options for local `redis://`; managed Redis certificate verification was not live-tested.

The second checkpoint contains the post-checkpoint runtime fixes and frontend API configuration. It is separate from checkpoint `634e5b1`; no push or deployment was performed.

## Phase 3C: Reminder validation and chatbot error handling

Completed the three reviewed backend fixes:

- Daily and refill reminder request models reject empty or whitespace-only medicine names with FastAPI/Pydantic 422 validation responses.
- Chat requests reject empty or whitespace-only messages before provider initialization. Valid requests retain their existing response contract.
- Chat provider and configuration exceptions now produce a generic 502 response. Internal logs contain only the exception class, not exception text or traceback.

Backend suite result from `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short`: **32 passed, 0 failed, 0 skipped, 0 blocked**, 11 warnings, exit code 0. `pip check` found no broken requirements; `git diff --check` passed. Secret scan found only the intentional synthetic test hash fixture (`backend/tests/conftest.py`); no real credentials were found. No external integrations were called.

Remaining limitations include the warnings emitted by existing framework/model dependencies and the absence of real Google Maps, WhatsApp, MongoDB, Redis, and Vertex AI integration verification.

## Phase 3B: Backend authorization and report processing

Implemented the reviewed authorization and persistence fixes:

- Report upload records `{ task id, user id, filename, created_at }` in MongoDB's `report_jobs` collection before returning a task ID. Status lookup requires authentication and queries by both task ID and owner. Unknown tasks and other users' tasks return 404; ownership-store errors fail closed with 503.
- User profile lookup is authenticated and self-only. Its `UserPublic` response model explicitly excludes password fields, including `hashed_password`.
- Report processing raises on empty extracted text and on database persistence failure. Persistence errors are logged internally and surfaced as a generic task failure; status responses do not expose Celery exception details.

The backend test suite uses synthetic records and mocked database, Celery, Maps, and chatbot boundaries. Last complete run:

```text
Command: cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short
Result: 23 passed, 3 failed, 0 skipped, 0 blocked; 11 warnings; exit code 1
```

At the end of Phase 3B, three tests still failed: empty medicine name validation, empty chatbot message validation, and chatbot upstream error-detail exposure. All three were fixed and verified in Phase 3C above.

## Remaining risks

- Tasks created before the `report_jobs` ownership record was introduced have no reliable owner mapping and now fail closed as not found. Do not infer ownership from a Celery task ID.
- If the ownership record cannot be saved after Celery accepts a task, upload returns 503 and attempts to revoke that task. Revocation is best-effort; this path requires operational monitoring.
- The new `report_jobs` collection is created by MongoDB on first insert; there is no migration framework in this repository.
- No real MongoDB, Redis, Google, or WhatsApp integration was exercised by these tests.
