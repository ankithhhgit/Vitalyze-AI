# Project Status

## Geoapify pharmacy provider migration — 2026-10-18 (latest)

- Pharmacy lookup now uses the Geoapify Places API instead of Google Places. The backend key is read from `GEOAPIFY_API_KEY`; the obsolete `GOOGLE_MAPS_API_KEY` setting was removed. The `GET /api/v1/maps/pharmacies` response shape is unchanged, but Geoapify exposes no ratings, so `rating`/`user_ratings_total` are always `null` and the UI shows "No ratings yet".
- Status mapping: missing configuration **503**, provider failure **502**, timeout **504**, empty results **200 `[]`**. Provider errors are logged by exception type only. Distance sorting is unchanged; the separate external Google Maps handoff links by coordinates.
- Frontend `EXPO_PUBLIC_API_URL` (and the `frontendv3/services/api.ts` fallback) target backend port **8001**.
- Verified: backend suite **126 passed**; `tsc --noEmit` passed; frontend `npm test` **7 passed**. Provider calls are mocked in tests; a live iPhone check remains manual.

## Medicine reminders: WhatsApp + local notifications + profile — 2026-10-17 (latest)

- Added per-purpose WhatsApp template configuration. The sender accepts a template name only when it appears in `WHATSAPP_APPROVED_TEMPLATE_NAME`, `WHATSAPP_MEDICATION_TEMPLATE_NAME`, or `WHATSAPP_REFILL_TEMPLATE_NAME` (all blank in `.env.example` until Meta approves real templates). Daily reminders use `medication_reminder_v3`; refill reminders use `refill_reminder_v1`. Blanks make `is_configured(template)` return `False`, so nothing is sent.
- `send_template_message` now returns the provider message id on success (`""` when the provider accepted the message but returned no id, `None` on any no-send/failure), so callers never mistake a skipped send for a delivery. Network failures (`Timeout`/`ConnectionError`) retry up to `MAX_SEND_ATTEMPTS=3`; provider HTTP errors are terminal. Recipient numbers must be valid E.164 before any configuration check.
- Dispatcher hardening: `dispatch_due_daily_reminders` writes one durable `reminder_deliveries` record per due occurrence (unique `delivery_key`), marks the record `queued` **before** publishing the worker task (fixing a race where a fast worker could claim nothing and silently drop the reminder), and marks it `failed` if publishing raises. `reminder_deliveries.provider_message_id` is indexed for webhook correlation. Deliveries are only recorded for opted-in users; unverified phones/disabled/unconfigured WhatsApp are stored as `blocked` with a `blocked_reason`.
- Webhook router is mounted at `/api/v1/webhooks`. `POST /whatsapp` maps provider delivery statuses (`sent`, `delivered`/`read` → `delivered`, `failed`) onto the matching `reminder_deliveries` record via `provider_message_id`. A configured `WHATSAPP_APP_SECRET` enables `X-Hub-Signature-256` HMAC verification; when blank (local dev) signatures are skipped as a documented prerequisite.
- `GET /api/v1/reminders/status` reports readiness without secrets: `whatsapp_enabled`, `provider_ready`, `medication_template_configured`, `refill_template_configured`, `phone_verified`, and overall `status` (`ready` only when enabled + provider ready + phone verified, otherwise `not_configured`).
- Frontend local fallback: `services/localReminderNotifications.mjs` requests notification permission with an explanation and reconciles the device's scheduled daily/refill notifications on every load/preference change (cancels only app-owned entries, then reschedules active ones). `RemindersScreen` surfaces local-notification permission state and labels success copy so local scheduling is never confused with WhatsApp delivery.
- Profile: a `person-circle-outline` icon in the Home tab header (top-left) opens a `Profile` stack screen that reads the authenticated user via `authService.getCurrentUser()` and renders real fields (`name`, `phone_number`, `email`, `phone_verified`, `age`, `gender`, `created_at`) through the pure, Node-testable `services/profile.mjs` helper.
- Verification: backend **97 passed, 9 warnings** (`PYTHONPATH=. .venv/bin/pytest -q --tb=short`); frontend `npm test` **7 passed**; `npx tsc --noEmit` passed; iOS and Android `expo export` passed; `git diff --check` and `pip check` clean.
- `WHATSAPP_SEND_ENABLED=false` throughout. No real WhatsApp message was sent; all provider calls are mocked. Remaining setup: Meta-approved templates, real Cloud API credentials, `phone_verified` (operator-set; no OTP self-service), and `WHATSAPP_APP_SECRET`. Known accepted limitations: the dispatcher prioritizes no-duplicate over no-loss on crash; refill reminders still use a Celery `eta` (not Beat-driven); local notifications use device-local time.

## Report preview and Trend selector — 2026-10-17

- The current local extraction worker returns `analysis_mode`, `report_id`, summary, and empty structured findings; extracted PDF text is persisted in the owner-scoped `/api/v1/reports/history` response as `raw_text`. Therefore AI summary availability is independent of whether PDF text extraction succeeded.
- Report Analyser now loads the saved text by report ID (or, for older successful task results lacking an ID, a recent matching filename) and displays it in a separate text panel for every successful task result. It no longer hides text when the task is not tagged `local_extraction_preview`. A history lookup failure is shown as a text-preview retrieval issue, not a PDF extraction failure.
- Trend selector now uses a validated Blood Pressure default and adequate iOS picker height/item text color; this avoids clipping the native iOS wheel to its prior 50-pixel container.
- Backend regression results: **64 passed, 0 failed, 0 skipped, 0 blocked**. TypeScript check and offline iOS Expo export passed. No live device upload was run in this check, so text extraction on the user's iPhone still needs manual confirmation.

## iPhone demo recheck — 2026-10-17 (latest)

- Confirmed report upload defect: shared Axios `Content-Type: application/json` caused Axios 1.13 to JSON-serialize React Native `FormData`; FastAPI requires the multipart field `file`. The request interceptor now sets multipart for FormData, preserving the descriptor and allowing React Native's native networking layer to generate the boundary. Added a regression test for a wrong field name; targeted upload tests pass **5/5**.
- Registration now prevents duplicate submit callbacks, validates trimmed names and positive whole-number ages against the backend schema, and uses a 20-second request timeout. Existing `finally` handling releases loading on success and failures; FastAPI validation arrays continue to display as readable text.
- API fallback now targets local port 8001; physical iPhone builds must explicitly use the verified current LAN IP `192.168.0.100` (en0) and port 8001. Timeout errors now give an actionable message. Home copy no longer promises configured AI or live pharmacy results. Locator radius state is explained during loading/provider outages; its external Maps handoff remains separate from Vitalyze results.
- Reminder success messages distinguish persistence from Celery processing and WhatsApp delivery. Celery Beat runtime refresh for reminders created after Beat starts remains unverified; WhatsApp sending remains disabled.
- Verified results: backend **63 passed, 0 failed, 0 skipped, 0 blocked** (9 warnings); report upload focus **5 passed, 39 deselected**; TypeScript passed; `pip check`, `npm ls --depth=0`, offline Expo dependency check, and `git diff --check` passed; Android and iOS offline exports passed. These bundles do not verify native screen behavior.
- Runtime limitation: MongoDB PID 31700 and Redis PID 31713 were listening on loopback ports 27017/6379. Port 8001 had no listener; port 8000 also failed its final HTTP reachability check. Earlier `lsof` showed PID 31767 on 127.0.0.1:8000, but I did not stop or modify it. No live backend/device requests were made in this recheck.
- No Gemini, Geoapify, WhatsApp, production API, or real patient data was used. Native iPhone registration/upload, device permission, external Google Maps handoff, reminder persistence against the live local database, and visual chart rendering remain manual checks. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).

## Credential-free stabilization — 2026-10-17 (latest)

- Authentication navigation is correct: the signed-out stack contains `SignIn` and `Register`; both screens use React Navigation. Login persists the token, logout clears it, and startup validates a stored token through authenticated `GET /api/v1/auth/me`. A 401 clears the session and returns to the signed-out stack. Registration validation details remain converted to readable text.
- Report upload accepts bounded (15 MB maximum) PDF multipart uploads, rejects invalid headers, and no longer attempts GCS. The worker extracts text with PyMuPDF. Default `REPORT_ANALYSIS_MODE=local` persists an explicitly labelled local extraction preview with no inferred findings. AI interpretation requires explicit mode `ai` plus configured backend credentials. Required persistence failure and AI failure cannot produce `COMPLETED`. Scanned PDFs report that local Tesseract/Poppler are missing in this environment; no OCR binaries were found.
- Chatbot and pharmacy endpoints now require authentication. Missing Vertex credentials and the pharmacy provider key produce clear 503 responses; the UI distinguishes those states. The locator offers an external Google Maps search link, clearly labelled as separate from Vitalyze results.
- Reminders expose the authenticated user's saved list, validate and trim inputs, reject duplicate active reminder requests, and show that scheduling does not confirm WhatsApp delivery. Celery schedule restoration is restricted to Beat, preventing an event-loop error in FastAPI. WhatsApp sends require explicit `WHATSAPP_SEND_ENABLED=true`; the default is false and tests prove no provider call occurs while disabled.
- Trends now sorts without mutating response data, skips invalid dates/missing values, parses values from the backend's `Indicator`/`Value` fields, and shows a true empty-history state. Local preview reports contain no structured findings, so they do not create chart values.
- Real local isolated API integration passed using synthetic credentials/data and dedicated MongoDB/Redis ports: registration/login/profile validation, reminder persistence/read, text-PDF upload, Celery extraction, report save, owned status, and same-user history. Chatbot and pharmacy search returned missing-configuration responses. No external provider, Vertex, GCS, WhatsApp, or production service was contacted.
- Latest checks: backend suite **62 passed, 0 failed, 0 skipped, 0 blocked** (9 warnings); `pip check`, `git diff --check`, TypeScript, npm dependency tree, and Expo offline dependency validation passed. SDK 57 Android and iOS offline exports passed. Expo install validation warns that offline validation is less reliable. No native iPhone screen or PDF picker interaction was available for direct verification.
- WhatsApp, Geoapify live pharmacy results, Vertex AI, visual chart rendering, device permissions, external Google Maps link opening, and iPhone native PDF selection/upload still require manual/device verification. Scanned-PDF OCR requires local Tesseract and Poppler.

## iPhone demo fixes — 2026-10-17

- Registration now trims/normalizes formatting separators in phone input and checks the backend's existing E.164 rule before sending. FastAPI validation arrays are formatted into text; registration returns `UserPublic` and no longer serializes the password hash.
- Navigation only exposes the protected feature tabs after login. The Axios client reads the SecureStore bearer token and clears the session on protected-request 401s.
- Report upload imports `expo-file-system/legacy` for `getInfoAsync` and keeps the selected file URI, name, MIME type, multipart request, and status polling.
- Pharmacy search distinguishes missing `GEOAPIFY_API_KEY` (503) from a provider failure (502); a provider error no longer looks like a successful empty result. Chat distinguishes unavailable backend credentials/configuration (503) from an upstream provider failure (502). Logs and API responses omit provider exception details.
- Current local config uses loopback MongoDB/Redis. The pharmacy provider key is read from `GEOAPIFY_API_KEY`; `GOOGLE_APPLICATION_CREDENTIALS` points to a missing file. Set a valid service-account file path on the backend for live Vertex services. No external provider or Vertex request was made.
- Synthetic registration/login against the updated local API returned 201/200; authenticated history returned 200. A reminder route call used the synthetic account with scheduling and persistence mocked (201); no message was sent.
- Backend regression suite: **42 passed, 0 failed, 0 skipped, 0 blocked** (11 warnings). TypeScript and offline Android/iOS bundles passed after fixes. Expo SDK 57 dependencies are locally aligned; TypeScript 6 compatibility was fixed by removing an unused `baseUrl` alias.
- Expo Doctor initially reported only `.expo/` not ignored and multiple lockfiles. `.expo/` and local `.env` are now ignored. npm is the active package manager (`package-lock.json`, `npm ls` clean); the tracked pnpm lock was a stale SDK 52 lock and has been retained as `pnpm-lock.yaml.sdk52.backup`. A final Expo Doctor rerun was blocked by npm registry DNS (`ENOTFOUND`).
- An older FastAPI process still listened on port 8000 during review; the updated checkout was tested on loopback port 8001. Restart FastAPI before reconnecting the iPhone so it uses these changes. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) for the LAN start commands and remaining verification limits.

## Earlier local runtime milestone — 2026-10-17 (before iPhone fixes)

Checkpoint `634e5b1` contains the reviewed Phase 3B/3C changes. The second checkpoint contains the following runtime fixes and verification updates:

- Celery TLS options are now applied only to `rediss://` brokers, with `ssl.CERT_REQUIRED` certificate verification. Plain local `redis://` continues to receive no TLS options. The focused tests assert both behaviors. Local loopback Redis worker startup was verified; no managed Redis TLS endpoint was available, so certificate-chain validation against a managed service remains unverified.
- Frontend API configuration now uses `EXPO_PUBLIC_API_URL` with a `localhost` fallback rather than a hard-coded private IP. TypeScript passed, Metro started offline, and a generated iOS JS bundle included the local API URL without the stale IP. A real Axios request from the frontend package reached FastAPI and received the expected 401 for protected report history.
- Synthetic report flow passed through registration, upload, real digital-PDF text extraction, mocked AI analysis, local MongoDB persistence, authenticated status, and history. Celery dispatch/status were stubbed for this flow; the worker itself was independently verified. Vertex AI, GCS, scanned-PDF OCR, and actual async result polling remain unverified.
- Synthetic daily/refill reminder API checks passed with scheduling mocked and data persisted only in a dedicated local test DB. No WhatsApp call or queued message was made.
- Pharmacy route checks passed with mocked provider data, including success, malformed query, provider failure, and missing-key responses. Provider credentials are absent and no external request was made.
- Chat route passed with a mocked response; blank input and missing-credential behavior returned 422 and generic 502. Vertex AI was not contacted. Trends/history returned the saved synthetic report through the authenticated API.
- WhatsApp service/task logs and Celery result strings were found to expose recipient/medication values and provider response details. They now log generic status plus exception class only, return generic task statuses, and enforce a 10-second provider request timeout. Four mocked privacy/payload tests pass; no WhatsApp request was sent. Retry and duplicate-send idempotency are unresolved.
- Native UI verification is incomplete: no iOS simulator/Xcode or Android emulator/device was available, and Expo web dependencies (`react-native-web`, `react-dom`) are absent. Location permission, external Google Maps link opening, and rendered chart behavior were not exercised.

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

Remaining limitations include the warnings emitted by existing framework/model dependencies and the absence of real Geoapify pharmacy, WhatsApp, MongoDB, Redis, and Vertex AI integration verification.

## Phase 3B: Backend authorization and report processing

Implemented the reviewed authorization and persistence fixes:

- Report upload records `{ task id, user id, filename, created_at }` in MongoDB's `report_jobs` collection before returning a task ID. Status lookup requires authentication and queries by both task ID and owner. Unknown tasks and other users' tasks return 404; ownership-store errors fail closed with 503.
- User profile lookup is authenticated and self-only. Its `UserPublic` response model explicitly excludes password fields, including `hashed_password`.
- Report processing raises on empty extracted text and on database persistence failure. Persistence errors are logged internally and surfaced as a generic task failure; status responses do not expose Celery exception details.

The backend test suite uses synthetic records and mocked database, Celery, pharmacy-provider, and chatbot boundaries. Last complete run:

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
- Medicine-reminder dispatcher: on a crash between marking `queued` and publishing, a `queued` record can be left with no worker task (favoring no-duplicate over no-loss). `reminder_deliveries` and its indexes are created on first use; there is no migration framework.
- `phone_verified` is operator-set only — there is no OTP/self-service verification flow, so real WhatsApp delivery requires an operator to set it and approved templates plus credentials.
- Refill reminders are scheduled with a Celery `eta` at creation time (not Beat-driven), so editing quantity/frequency does not reschedule the existing task; changing `is_active` best-effort revokes it.
- Local notifications are a device-only fallback and fire on device-local time, independent of the reminder `timezone` field.
