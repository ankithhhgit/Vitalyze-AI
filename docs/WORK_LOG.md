# Work Log

## 2026-10-18 — Geoapify pharmacy provider migration

### Changes

- `backend/app/services/maps_service.py`: replaced the Google Places (`googlemaps`) provider with the Geoapify Places API (`GET https://api.geoapify.com/v2/places`). Search uses `categories=healthcare.pharmacy,commercial.health_and_beauty.pharmacy`, `filter=circle:LON,LAT,RADIUS`, `bias=proximity:LON,LAT`, `limit=40`, and an 8-second timeout via `requests`. Results map to the unchanged shape (`name`, `vicinity`, `rating`, `user_ratings_total`, `geometry.lat/lng`, `place_id`); Geoapify exposes no ratings, so `rating`/`user_ratings_total` are always `null`. Features without coordinates are skipped, and `place_id` falls back to a `geoapify:LAT,LON` identifier only when absent. Provider exceptions log the exception type only.
- `backend/app/api/v1/endpoints/maps.py`: missing configuration returns **503** (message names `GEOAPIFY_API_KEY`), provider failure **502**, timeout **504**, and empty results **200 `[]`**. Endpoint path, `Pharmacy` model, and auth dependency are unchanged.
- `backend/app/core/config.py`: removed `GOOGLE_MAPS_API_KEY` and added `GEOAPIFY_API_KEY` (optional). `backend/requirements.txt`: removed the now-unused `googlemaps` dependency. `backend/.env.example` and the local `backend/.env`: documented `GEOAPIFY_API_KEY` and dropped the obsolete `GOOGLE_MAPS_API_KEY` entry.
- `frontendv3/screens/MedicalLocatorScreen.tsx`: locator error copy reflects the provider, and the external Google Maps handoff now links by coordinates (Geoapify place IDs are not Google place IDs). Distance sorting is unchanged. `frontendv3/.env` and `frontendv3/.env.example`: API base URL moved to backend port **8001**.
- Tests: new `backend/tests/test_maps_service.py` (10 mocked cases — success, geometry/place-id fallbacks, empty, missing key, HTTP error, connection error, timeout, malformed payload); `backend/tests/test_api_baseline.py` updated for the Geoapify provider plus success/empty/timeout endpoint cases; `backend/tests/conftest.py` sets `GEOAPIFY_API_KEY=""`.
- Docs: `docs/DEMO_RUNBOOK.md` (export line, provider references, and example API URLs/firewall ports updated to 8001), `docs/PROJECT_STATUS.md`, and `docs/WORK_LOG.md` updated from the Google Maps provider to Geoapify. References to the separate external Google Maps handoff are retained.

### Commands and results

- `cd backend && .venv/bin/python -m pytest tests/ -q` — **126 passed, 9 warnings**.
- `cd frontendv3 && ./node_modules/.bin/tsc --noEmit` — passed.
- `cd frontendv3 && npm test` — **7 passed**.
- All provider boundaries are mocked; no live provider call was made. Restart FastAPI on port 8001 before reconnecting the iPhone.

## 2026-10-17 — Medicine reminders: WhatsApp delivery, local fallback, and profile

### Changes

- `backend/app/core/config.py`: added `WHATSAPP_MEDICATION_TEMPLATE_NAME`, `WHATSAPP_REFILL_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANGUAGE`, `WHATSAPP_APP_SECRET` (all defaulted; templates blank until Meta approves them).
- `backend/app/services/whatsapp_service.py`: rewrote the sender — E.164 recipient validation before any send, per-purpose approved-template check via `is_configured(template)`, provider message-id extraction, bounded retries (`MAX_SEND_ATTEMPTS=3` for `Timeout`/`ConnectionError` only), terminal handling for provider HTTP errors, and no logging of recipients/content.
- `backend/app/tasks/reminder_tasks.py`: dispatcher now creates one durable delivery per due occurrence and marks it `queued` **before** publishing the worker task (race fix), marks `failed` if publishing raises, indexes `provider_message_id`, and records `blocked`/`blocked_reason` for unverified or unconfigured states. Delivery task claims atomically (`queued`→`sending`) and stores the provider receipt id.
- `backend/app/api/v1/endpoints/webhooks.py`: `POST /whatsapp` maps provider delivery statuses onto `reminder_deliveries`; optional `X-Hub-Signature-256` HMAC verification via `WHATSAPP_APP_SECRET`.
- `backend/app/api/v1/api.py`: mounted the webhooks router at `/api/v1/webhooks`.
- `backend/app/api/v1/endpoints/reminders.py`: added `local_notifications_enabled` to reminder payloads and expanded `GET /reminders/status` to report medication/refill template readiness and `phone_verified` without secrets.
- `backend/tests/conftest.py`, `test_whatsapp_service.py`, `test_reminder_dispatch.py` (new), `test_whatsapp_webhook.py` (new): fake `reminder_deliveries` collection, sender return-type/template/retry tests, dispatcher/delivery tests (including the queue-before-publish regression and publish-failure path), and webhook status/signature tests. All provider/broker/database boundaries are mocked.
- `frontendv3/services/localReminderNotifications.mjs` (+`.d.mts`, `.test.mjs`): permission helper with an explanation and idempotent reconciliation of app-owned daily/refill notifications.
- `frontendv3/services/profile.mjs` (+`.d.mts`, `.test.mjs`): pure `buildProfileFields` helper extracted for Node testing.
- `frontendv3/screens/ProfileScreen.tsx` (new): loads the authenticated user and renders real fields.
- `frontendv3/screens/RemindersScreen.tsx`: `local_notifications_enabled`/`whatsapp_opt_in` toggles, permission messaging, and reconciled local scheduling.
- `frontendv3/App.tsx`: profile icon in the Home header (top-left) navigating to the `Profile` stack screen.
- `frontendv3/package.json`: added `test` (`node --test services/*.test.mjs`) and `typecheck` (`tsc --noEmit`) scripts.
- `backend/.env.example`: documented the new WhatsApp template/secret placeholders.

### Commands and results

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **97 passed, 0 failed, 9 warnings**, exit 0.
- `cd frontendv3 && npm test` — **7 passed, 0 failed**; `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && npx expo export --platform ios --output-dir /tmp/vitalyze-feature-ios` and the `--platform android` equivalent — passed (JS bundles only).
- `cd backend && .venv/bin/python -m pip check` — passed; `git diff --check` — passed.
- `WHATSAPP_SEND_ENABLED=false` throughout; all provider calls mocked; no real message sent, and no `.env` values were read or changed.

### Remaining setup / limitations

- Real delivery requires Meta-approved templates (`medication_reminder_v3`, `refill_reminder_v1`), live Cloud API credentials, `WHATSAPP_APP_SECRET`, and an operator-set `phone_verified`. There is no OTP self-service flow.
- Dispatcher favors no-duplicate over no-loss on crash; refill reminders stay Celery-`eta`-based (not Beat-driven); local notifications fire on device-local time.

## 2026-10-17 — iPhone demo recheck and focused fixes

### Audit observations

- Branch is `demo/try-expo-57`. Existing modified and untracked files were preserved; no reset, checkout, clean, commit, or push was run. The existing SDK 57 `package-lock.json` and `pnpm-lock.yaml.sdk52.backup` remain in place.
- `lsof` showed MongoDB PID 31700 on loopback `27017`, Redis PID 31713 on loopback `6379`, and initially Python PID 31767 bound to `127.0.0.1:8000`; I did not stop or change these processes. Later read-only HTTP checks could not connect to either port 8000 or 8001. Port 8001 was free at listener inspection. The current Wi-Fi IPv4 address was `192.168.0.100` on `en0` from `ifconfig` (the `ipconfig getifaddr` command failed in this shell).
- FastAPI's report route requires multipart field `file`. The client used `FormData` correctly but the shared Axios client set JSON content type, which Axios 1.13 converts to JSON. Replaced that header for FormData; inspected the installed React Native 0.86 native networking code: iOS applies its generated multipart boundary and Android builds the multipart body. Added a backend regression that rejects an incorrectly named multipart field.
- Registration's backend call was inside `try/finally`, but Axios had no timeout; an unreachable/hung API could keep the spinner active. Added a 20-second timeout and readable timeout text, duplicate-submit guard, whitespace-name validation, and age validation for the backend's positive integer schema.
- Existing locator 503 handling and the external Google Maps fallback were present; no blank-error root cause was reproducible from this source. Added helper text for the radius control during loading/unavailable states. The Chatbot already showed explicit unavailable status and cleared loading in `finally`; no behavior change/provider call was needed. Home descriptions were adjusted to avoid promising configured AI/live pharmacy results.
- Reminder code persists and reloads records; WhatsApp remains disabled. UI copy now avoids equating persistence with delivery. A daily reminder added after Celery Beat has already started may not enter that separate Beat process's schedule until restart; live refresh was not verified and remains a limitation.

### Changes

- `frontendv3/services/api.ts`: default local API fallback moved to port 8001, request timeout added, multipart content-type handling fixed for React Native FormData, and timeout errors made actionable.
- `frontendv3/screens/RegisterScreen.tsx`: duplicate-submit, required text and positive-integer age validation; network request remains protected by `finally`.
- `frontendv3/screens/ReportAnalyserScreen.tsx`: validate selected URI/name/type and enforce size using picker metadata and legacy filesystem metadata; preserve the expected `file` multipart key and auth interceptor.
- `frontendv3/screens/MedicalLocatorScreen.tsx`: explain radius behavior during loading or provider unavailability.
- `frontendv3/screens/RemindersScreen.tsx`: state explicitly that save, Celery processing, and WhatsApp delivery are separate.
- `frontendv3/screens/HomeScreen.tsx`: clarify that AI and live pharmacy results need backend provider configuration.
- `backend/tests/test_api_baseline.py`: reject a mismatched upload multipart field and assert no task is queued.
- `docs/PROJECT_STATUS.md`, `docs/WORK_LOG.md`, `docs/DEMO_RUNBOOK.md`: record current findings and commands/results.

### Commands and results

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_api_baseline.py -k 'report_upload' --tb=short` — **5 passed, 39 deselected**, exit 0 (9 warnings).
- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **63 passed, 0 failed, 0 skipped, 0 blocked**, 9 warnings, exit 0.
- `cd backend && .venv/bin/python -m pip check` — passed; no broken requirements.
- `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && npm ls --depth=0` — passed; installed Expo is 57.0.30 and dependencies are present.
- `cd frontendv3 && EXPO_OFFLINE=1 npx expo install --check` — dependencies up to date; Expo notes offline validation is less reliable.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://192.168.0.100:8001/api/v1 npx expo export --platform ios --output-dir /tmp/vitalyze-iphone-demo-ios-export` — passed; JavaScript bundle only.
- Same Expo export command with `--platform android --output-dir /tmp/vitalyze-iphone-demo-android-export` — passed; JavaScript bundle only.
- Axios local adapter check with a synthetic Node `FormData` — payload remained FormData and content type was multipart; no request was sent. Native boundary generation was inspected in installed RN source, not verified on a physical device.
- `curl --connect-timeout 2 --max-time 4 -fsS http://127.0.0.1:8001/` and the same request to port 8000 — both failed to connect at final check. No live FastAPI integration or iPhone request was performed.
- `git diff --check` — passed before the final documentation edits; rerun after them before handoff. No secret values were read or printed.
- Final rerun after the UI/docs edits: backend **63 passed**, TypeScript passed, `pip check` passed, `npm ls --depth=0` passed, iOS export `/tmp/vitalyze-final-ios` passed, Android export `/tmp/vitalyze-final-android` passed, and `git diff --check` passed.
- `gitleaks`/`detect-secrets` are not installed. A high-confidence `rg -l` scan (key/token/private-key patterns, values never displayed; `.env` files explicitly excluded) returned no matches. `backend/.env.example` was inspected as a placeholder file; real `.env` values were not read.

### Remaining manual checks

- Start updated FastAPI on trusted LAN interface port 8001 using local-only MongoDB/Redis config; verify `/` and OpenAPI locally, then verify iPhone connectivity at `http://192.168.0.100:8001/` (after rechecking the IP).
- On iPhone: test registration and login, request timeout/error copy, small synthetic text PDF upload and extracted text, saved reminder reload, locator permission and the external Google Maps link, chatbot unavailable/retry, and Trend/Home empty states.
- Do not treat Beat task registration as verified when Beat is already running; restart Beat after adding a daily reminder if validating scheduling. Do not enable WhatsApp.
- No live provider or database readback was run during this recheck. Previous isolated integration results remain historical evidence, not a current live-service check.

## 2026-10-17 — Credential-free project stabilization

### Audit and changes

- Preserved branch `demo/try-expo-57` and all prior uncommitted work. Registration and login screens are correctly registered in the signed-out stack; Sign In has a bound `useNavigation()` for the Register link. Added an authenticated `/auth/me` profile check to restore stored sessions and clear invalid tokens through the existing 401 handler.
- Found an import-time Vertex AI initialization in the unused medicine route that crashed FastAPI when project credentials were absent. Initialization is now lazy and returns a generic 503 when not configured; provider errors are generic and safely logged.
- Report workers previously always called Gemini and converted provider failures to empty findings/placeholder summaries that could be saved as successful results. Added default local extraction mode, explicit `REPORT_ANALYSIS_MODE=ai` opt-in, direct PyMuPDF text extraction, specific invalid/empty/scanned-PDF errors, a 15 MB upload limit, and removed GCS calls from this local upload path. Reports persist only after successful extraction/analysis; local previews include no generated medical values. Status polling returns safe failure text.
- Added authenticated reminders history, duplicate request checks, saved reminder UI, and explicit unconfirmed-delivery copy. Celery's reminder restore hook previously tried to run a nested event loop during FastAPI requests; it now runs only in a process marked `CELERY_ROLE=beat`. WhatsApp sending has a second explicit opt-in (`WHATSAPP_SEND_ENABLED=true`); default false, with tests proving a disabled worker does not call the provider.
- Protected chatbot and pharmacy endpoints with the existing bearer-token dependency. Added query bounds and a clearly-labelled external Google Maps search handoff. Chat UI validates provider responses and explains that no offline AI answers are generated. Trends handles empty history separately from request errors, sorts chronologically without mutating API data, skips invalid dates, and reads the actual structured report fields.

### Commands and results

- `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **62 passed, 0 failed, 0 skipped, 0 blocked**, 9 warnings.
- `cd backend && .venv/bin/python -m pip check` — passed; no broken requirements.
- `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && npm ls --depth=0` — passed; installed Expo remains 57.0.30 with the existing lockfile strategy.
- `cd frontendv3 && EXPO_OFFLINE=1 npx expo install --check` — dependencies reported up to date; CLI notes offline compatibility validation is less reliable.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform android --output-dir /tmp/vitalyze-stable-android-export` — passed.
- `cd frontendv3 && EXPO_OFFLINE=1 EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo export --platform ios --output-dir /tmp/vitalyze-stable-ios-export` — passed. These are JS exports, not native-device tests.
- `git diff --check` — passed.
- Isolated local integration used MongoDB on loopback port 27018 with fresh `/tmp/vitalyze-demo-safe-mongo`, Redis on 6380 with persistence disabled, FastAPI on 8011, and a Celery worker. Synthetic register/login/profile, saved-reminder GET/POST, digital PDF upload, real worker extraction, local preview persistence, task ownership/status, and same-user history passed. Chat and pharmacy search returned 503 for missing configuration. No Beat was started, WhatsApp was disabled, and no external provider was contacted.
- `command -v tesseract` and `command -v pdftoppm` — both unavailable; scanned PDF OCR remains blocked with an actionable API failure.

Native iPhone checks remain manual: Expo Go login/session restoration and Register navigation, PDF picker and upload on device, permission allow/deny, external Google Maps link, and chart rendering. Do not enable WhatsApp delivery or provider APIs for the credential-free demo.

## 2026-10-17 — iPhone registration, session, upload, and SDK 57 fixes

### Audit findings

- Confirmed the backend `UserCreate` schema requires an E.164 phone (`+` and 2–15 digits), name, and password length 8–72. `RegisterScreen` sent the raw phone and rendered FastAPI's array of validation objects as a React Native child.
- The backend registration response model was `UserInDB`, exposing `hashed_password`; changed it to `UserPublic` and added a regression test.
- `App.tsx` mounted protected tabs while logged out. API requests already used SecureStore bearer tokens, but no 401 session reset existed.
- Report upload called `getInfoAsync` through the SDK 57 default module; switched to `expo-file-system/legacy` and preserved URI/name/MIME/multipart/polling behavior.
- Confirmed the pharmacy provider key was unset and the Vertex credential path is configured but its file does not exist. The old pharmacy service hid provider failures as `200 []`; Chat collapsed missing credentials and upstream errors into 502.
- `expo-file-system/legacy` exists in the installed SDK 57 package. `expo install --check` and `npm ls --depth=0` report the local dependency set is aligned. TypeScript 6 rejected an unused `baseUrl` alias; no imports used `@/`, so the alias was removed.
- Expo Doctor's first run found `.expo/` not ignored and both npm/pnpm lockfiles. Added `.expo/` and `.env` ignore rules. Confirmed `package-lock.json` and installed modules correspond to SDK 57, while `pnpm-lock.yaml` was stale SDK 52; preserved it as `pnpm-lock.yaml.sdk52.backup`. A final Doctor retry could not reach registry.npmjs.org (`ENOTFOUND`).

### Changes and verification

- Added E.164 formatting normalization/validation in registration and login and a safe FastAPI detail formatter that only renders text (`msg` plus field location), never raw objects.
- Protected navigation now depends on authenticated context; protected-request 401 responses clear stored credentials and return to sign-in.
- Registration API response excludes password fields. Pharmacy missing configuration/provider failure and Chat missing configuration/provider failure now have separate, generic status responses; provider exception details are not logged or returned.
- Backend suite: `cd backend && PYTHONPATH=. .venv/bin/pytest -q --tb=short` — **42 passed, 0 failed, 0 skipped, 0 blocked**, 11 warnings.
- `cd frontendv3 && npx tsc --noEmit` — passed after final changes.
- `cd frontendv3 && EXPO_OFFLINE=1 npx expo export --platform android --output-dir /tmp/vitalyze-sdk57-android-verified` — passed after the final auth-session change.
- `cd frontendv3 && EXPO_OFFLINE=1 npx expo export --platform ios --output-dir /tmp/vitalyze-sdk57-ios-verified` — passed after the final auth-session change.
- `cd frontendv3 && EXPO_OFFLINE=1 npx expo install --check` — dependencies up to date using Expo's local SDK metadata; online version validation unavailable.
- `cd frontendv3 && npm ls --depth=0` — passed. `cd backend && .venv/bin/python -m pip check` — passed. `git diff --check` — passed.
- Synthetic local API verification on updated loopback port 8001: invalid phone 422; valid registration 201 with no password field; login 200, token kept in memory/not printed; authenticated history 200. Actual local provider config checks returned pharmacy 503 and Chat 503. No external API was contacted.
- Authenticated reminder route returned 201 in TestClient using the live synthetic account/token and real local MongoDB lookup, with Celery scheduling and reminder persistence mocked. No WhatsApp message or queued reminder was sent.
- Existing listener on port 8000 was an older process, so it was left untouched. The updated checkout was stopped after testing; restart FastAPI from this branch before reconnecting the iPhone.
- No iPhone UI, native file picker/upload, pharmacy results, Vertex response, or WhatsApp delivery was live-tested. At that time the pharmacy provider key (`GOOGLE_MAPS_API_KEY`, later replaced by `GEOAPIFY_API_KEY`) was unset; a valid file must be supplied at `GOOGLE_APPLICATION_CREDENTIALS` (the path currently configured does not exist). `GCP_PROJECT_ID` is configured.

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
- Pharmacy route checks passed using mocked provider data: success (200), invalid coordinates (422), mocked provider failure (`200 []`), and missing key (503). No provider request was made. Device location permission and the external Google Maps link opening remain untested.
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
# 2026-10-17 — Report text preview and Trend selector

## Investigation

- The local PDF extraction task uses PyMuPDF and persists the extracted string in the report document's `raw_text` field. Its Celery success result contains `analysis_mode`, `report_id`, and `simple_summary`, but does not include `raw_text`.
- Authenticated `GET /api/v1/reports/history` returns the user's saved reports, including `raw_text`; task status is owner-checked. The prior UI fetched history only for exact `local_extraction_preview` results and only rendered text for that mode, so successful responses with a different/legacy mode could show an AI-summary fallback while hiding already-extracted text.
- The Trend selector had a valid `bp` selected value and valid options, but the shared picker styling constrained the native iOS wheel to 50 pixels. Set an explicit iOS picker height and visible item text color, and guard invalid selected values with the first valid metric.

## Changes and verification

- Report Analyser now resolves text from the status payload when present, otherwise reads the owned report from history by `report_id`, with a recent matching-filename fallback for legacy task results. It renders extracted text independently from the AI summary and distinguishes history retrieval failures from task/extraction failures.
- Added a regression proving successful local task results expose a report ID that resolves to the saved report's `raw_text`; the worker test also verifies the persisted ID is returned.
- `cd backend && ./.venv/bin/python -m pytest -q tests/test_report_tasks.py tests/test_api_baseline.py` — **53 passed, 0 failed**, 9 warnings.
- `cd backend && ./.venv/bin/python -m pytest -q` — **64 passed, 0 failed, 0 skipped, 0 blocked**, 9 warnings.
- `cd frontendv3 && npx tsc --noEmit` — passed.
- `cd frontendv3 && npx expo export --platform ios --output-dir /tmp/vitalyze-ios-report-trend-check` — passed; iOS JavaScript bundle exported. This does not verify the native UI on a physical iPhone.
- `git diff --check` — passed.

No AI provider or real patient data was used. The live device's prior response was not available in this workspace; the current backend implementation supports successful local extraction without AI credentials.
