# Vitalyze.ai Interview Demo Runbook

## Current credential-free iPhone demo setup — 2026-10-17 (rechecked)

Use these commands for the current verified local implementation. They use a fresh isolated MongoDB path and database, loopback Redis, blank provider settings, local PDF extraction mode, and disabled WhatsApp sends. They do not read backend `.env` values or overwrite either `.env` file. Keep the old SDK 52 pnpm lock backup untouched; install with the existing npm lockfile only.

### 1. MongoDB and Redis

At this review, MongoDB (PID 31700) and Redis (PID 31713) are already listening on loopback ports 27017 and 6379. Recheck before starting anything; do not start a duplicate service if a listener is present:

```sh
lsof -nP -iTCP:27017 -iTCP:6379 -sTCP:LISTEN
```

Only start a service if its port is free. For an isolated fresh MongoDB test data path and a loopback Redis without persistence:

```sh
mkdir -p /tmp/vitalyze-demo-isolated-mongo
mongod --dbpath /tmp/vitalyze-demo-isolated-mongo --bind_ip 127.0.0.1 --port 27017 --nounixsocket
```

```sh
redis-server --bind 127.0.0.1 --port 6379 --save '' --appendonly no
```

### 2. Backend environment

Repeat these exports in each backend terminal. The signing key below is a synthetic local-only value; do not use it outside this isolated demo.

```sh
export MONGO_URI=mongodb://127.0.0.1:27017
export MONGO_DB_NAME=vitalyze_demo_local
export REDIS_URL=redis://127.0.0.1:6379/0
export SECRET_KEY=synthetic-local-demo-signing-key
export ALGORITHM=HS256
export ACCESS_TOKEN_EXPIRE_MINUTES=30
export WHATSAPP_API_VERSION=vXX.X
export WHATSAPP_ACCESS_TOKEN=
export WHATSAPP_PHONE_NUMBER_ID=
export WHATSAPP_VERIFY_TOKEN=
export WHATSAPP_APPROVED_TEMPLATE_NAME=
export WHATSAPP_MEDICATION_TEMPLATE_NAME=
export WHATSAPP_REFILL_TEMPLATE_NAME=
export WHATSAPP_TEMPLATE_LANGUAGE=en_US
export WHATSAPP_APP_SECRET=
export WHATSAPP_SEND_ENABLED=false
export GEOAPIFY_API_KEY=
export GCP_PROJECT_ID=
export GCP_LOCATION=us-central1
export GOOGLE_APPLICATION_CREDENTIALS=
export REPORT_ANALYSIS_MODE=local
```

FastAPI (for the phone, on trusted private Wi-Fi only):

```sh
cd backend
PYTHONPATH=. .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001
```

Port 8001 was free during this review. Do not stop the older listener on port 8000; it is not the updated demo backend. Verify the new process with `lsof -nP -iTCP:8001 -sTCP:LISTEN` and `curl http://127.0.0.1:8001/` before connecting the phone.

Celery worker (required for report extraction; WhatsApp remains disabled):

```sh
cd backend
PYTHONPATH=. .venv/bin/celery -A app.tasks.celery_app:celery worker --loglevel=INFO --pool=solo
```

Celery Beat is optional for daily schedule timing. If used, repeat the exports above and set `CELERY_ROLE=beat`; do not use a database containing real reminders.

```sh
cd backend
CELERY_ROLE=beat PYTHONPATH=. .venv/bin/celery -A app.tasks.celery_app:celery beat --loglevel=INFO --schedule=/tmp/vitalyze-demo-celerybeat
```

With the default `WHATSAPP_SEND_ENABLED=false`, reminder tasks stay pending and make no WhatsApp request. Do not change this for the demo.

### 3. Expo on the iPhone

The current Wi-Fi address was verified as `192.168.0.100` on `en0` with `ifconfig`; `ipconfig getifaddr` was unavailable in this shell. Recheck the active Wi-Fi address before each demo. Keep the phone and Mac on the same trusted private network. The command-line variable overrides any existing Expo `.env` value; do not edit or replace `.env`:

```sh
cd frontendv3
EXPO_PUBLIC_API_URL=http://192.168.0.100:8001/api/v1 npx expo start --lan --port 8081 --clear
```

If the address changes, substitute the address shown for the active Wi-Fi interface. Restart Expo after changing it. Restrict inbound ports 8001 and 8081 to the trusted private subnet in the Mac firewall; do not use public Wi-Fi, router port forwarding, or public tunnels.

### Verified readiness

- Recheck on 2026-10-17: backend suite **63 passed, 0 failed, 0 skipped, 0 blocked** (9 warnings); targeted report upload tests **5 passed**; `pip check`, `git diff --check`, TypeScript, `npm ls --depth=0`, Expo dependency check, and SDK 57 offline Android/iOS exports passed. The Expo dependency check ran offline and notes its validation is less reliable in that mode.
- A fresh isolated local integration verified synthetic registration/login, authenticated reminders, text-PDF upload and extraction by a real local Celery worker, task ownership/status, MongoDB persistence, and same-user report history. External provider credentials were blank. Chatbot and pharmacy search correctly reported configuration unavailable.
- Local text PDF preview is real extracted text and is labelled as a local preview; it does not invent medical values or diagnoses. AI interpretation is disabled by default. Scanned PDF OCR is not available here because Tesseract and Poppler are absent.
- Native iPhone screen flows were not directly exercised. Expo exports verify JS bundling only. No FastAPI process was reachable on ports 8000 or 8001 at the final reachability check, so live registration, login, reminder readback, and phone-to-backend connectivity still need a local/device run.
- Medicine-reminder feature (WhatsApp + local notifications + profile): backend suite **97 passed, 0 failed** (9 warnings); frontend `npm test` **7 passed**; `npx tsc --noEmit` passed; iOS/Android `expo export` passed. `WHATSAPP_SEND_ENABLED=false`; all provider calls mocked; no real message sent.

## Medicine reminders: WhatsApp, local notifications, and profile — 2026-10-17

### How it works

- Saving a daily reminder stores it under the authenticated user and reconciles **local** notifications on the device via `expo-notifications` (a daily trigger per selected time). Times default to `10:00`, `14:00`, `21:00` (`Asia/Kolkata`). Local notifications are the demo-visible fallback and never depend on WhatsApp.
- WhatsApp delivery is a separate, disabled-by-default path. A dispatcher records one durable `reminder_deliveries` entry per due occurrence and only queues a send when the user opted in, the phone is verified, and the template is approved/configured. Otherwise the entry is stored as `blocked` with a reason.
- `GET /api/v1/reminders/status` (authenticated) tells the app why WhatsApp is not sending. In the default demo it returns `whatsapp_enabled: false`, blank/`false` template flags, and `status: "not_configured"`.

### Why WhatsApp shows "not configured"

All of these must be true before any real message is sent; in the demo they are intentionally not met:

1. `WHATSAPP_SEND_ENABLED=true` (kept `false`).
2. Valid `WHATSAPP_API_VERSION`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` (not placeholders).
3. The matching template name populated in `WHATSAPP_MEDICATION_TEMPLATE_NAME`/`WHATSAPP_REFILL_TEMPLATE_NAME` **and** approved by Meta (`medication_reminder_v3`, `refill_reminder_v1`).
4. The user's `phone_verified` flag set to true (operator-set; there is no OTP self-service flow).

Until then, reminders are saved and local notifications still fire. Do **not** enable `WHATSAPP_SEND_ENABLED` for the demo.

### Safe local testing of the WhatsApp path

Sending stays disabled, so exercise it only through mocks/tests:

```sh
cd backend
PYTHONPATH=. .venv/bin/pytest -q tests/test_whatsapp_service.py tests/test_reminder_dispatch.py tests/test_whatsapp_webhook.py --tb=short
```

To inspect the readiness response with a live local backend, log in and call the authenticated endpoint:

```sh
curl -s http://127.0.0.1:8001/api/v1/reminders/status -H "Authorization: Bearer <LOCAL_TOKEN>"
```

The webhook receiver is mounted at `POST /api/v1/webhooks/whatsapp`; with `WHATSAPP_APP_SECRET` blank it accepts callbacks without a signature (local only). Set the secret to require `X-Hub-Signature-256` verification.

### iPhone: profile and local-reminder test steps

1. Sign in, then tap the person icon at the top-left of the Home header. Confirm "My Profile" shows the account's real name, phone, email, verification state, age, gender, and created date; missing fields read "Not provided".
2. Open the Reminders tab. Accept the notification-permission prompt when asked (the prompt text explains it schedules on-device reminders). Reject once to confirm the "enable them in iPhone Settings" fallback message, then re-enable in Settings.
3. Create a daily reminder for a medicine with a time a few minutes ahead. Confirm it appears under Saved reminders and that the local-notification status updates.
4. Background the app and confirm the local notification fires at the scheduled time. Delivery to WhatsApp is intentionally not expected.
5. Toggle "Disable local alerts"/"Enable local alerts" and confirm the scheduled local notifications are reconciled (no duplicates) on reload.
6. Tap "Opt in to WhatsApp" then "Revoke WhatsApp consent" to confirm consent is stored; the status line should still report WhatsApp as not configured.

## Current verification notes — 2026-10-17

- Confirmed report upload root cause: the Axios instance's JSON default caused Axios 1.13 to serialize the React Native `FormData` payload. FastAPI expects multipart field `file`. The request interceptor now marks FormData as multipart; React Native 0.86's native iOS networking adds/overrides the generated boundary and Android's OkHttp multipart builder generates the boundary. The backend contract test accepts `file` and rejects a mismatched `report` field.
- Registration now has a 20-second API timeout, readable timeout/validation feedback, and input checks for trimmed name, E.164 phone, password length, and positive integer age. Network paths always clear loading in `finally`; no live registration was attempted in this review.
- The locator UI maps the backend's missing-key 503 to a readable message and the external Google Maps handoff uses the current coordinates when available. Radius state explains when search is loading or unavailable. Pharmacy results are served by Geoapify through the backend's `GEOAPIFY_API_KEY` setting.
- Chatbot keeps the explicit provider-unavailable message and restores its send state in `finally`. No Gemini/Vertex request was made.
- Reminder saves/readback and ownership have backend regression coverage. UI success copy now distinguishes database save from Celery processing and disabled WhatsApp delivery. Celery Beat's active-runtime schedule refresh was not verified; start Beat only for scheduled processing and do not infer message delivery from persistence.
- `WHATSAPP_SEND_ENABLED=false`; no WhatsApp request was made. Synthetic/mock regression tests are not live provider verification.

## Previous milestone readiness (superseded by the verified readiness above)

- At that earlier checkpoint, the backend suite had 42 passing tests (11 warnings). Later credential-free stabilization results are listed above and in `PROJECT_STATUS.md`.
- Checkpoint `634e5b1` contains reviewed Phase 3B/3C changes. The separate runtime/security checkpoint is recorded in the work log and Git history.
- Do not use real patient records or real WhatsApp recipients for the demo. Current demo instructions keep WhatsApp sending disabled.

## Verification sequence

1. Start local/test MongoDB and Redis and verify connectivity without touching production data.
2. Start the Celery worker and, if the configured schedules require it, Beat against the local Redis broker.
3. Start FastAPI using local/test configuration and synthetic test data.
4. Start `frontendv3` Expo and verify the app's API base URL and frontend-to-backend requests.
5. Verify the report analyzer first with a synthetic PDF, then reminders with mocked/no-send messaging, pharmacy locator, chatbot, and trends/history.
6. Run backend regression tests and available frontend checks after any approved fixes.

## Results

### Local runtime bootstrap

- MongoDB 8.2.9 started with a fresh `/tmp/vitalyze-demo-mongo` database, loopback only; no pre-existing database was opened.
- Redis 8.6.2 started on loopback with persistence disabled; `redis-cli ... ping` returned `PONG`.
- FastAPI imported and startup connected to local MongoDB. Local OpenAPI returned 12 route paths, including reports and reminders. The Google service-account file was intentionally absent; startup logged that GCS credential initialization is unavailable and the pharmacy provider was unconfigured.
- Celery worker reached the reminder restore hook and found zero local daily reminders, then exited before worker startup: `broker_use_ssl`/`redis_backend_use_ssl` are configured even for a plain `redis://` local URL. Celery requires `rediss://` when those SSL options are present. This is a confirmed runtime configuration bug.
- Fixed the Celery startup blocker by applying the existing SSL options only when `REDIS_URL` uses `rediss://`. Added two focused configuration tests; targeted tests passed 2/2 and the full backend suite passed 34/34 (11 warnings). Worker then connected to local Redis and reached `ready`; Beat started with its schedule in `/tmp` and found zero local reminders.
- `frontendv3/node_modules` exists, and `package-lock.json` agrees with the package name/version. `npm ls --depth=0` passed and Expo CLI reports 54.0.23.
- Frontend API code currently hard-codes `http://10.209.40.99:8000/api/v1`; this host's active interface address is `192.168.0.100`. The configured URL therefore does not match this demo host; actual frontend requests remain to be verified after addressing the configuration blocker.
- Replaced the hard-coded frontend address with `EXPO_PUBLIC_API_URL` and a local `localhost` fallback; added `frontendv3/.env.example`. Expo's official environment-variable guidance confirms static `process.env.EXPO_PUBLIC_*` references are inlined by CLI builds ([Expo docs](https://docs.expo.dev/guides/environment-variables/)). TypeScript passed, Metro started in offline mode, and the generated iOS bundle contained the local URL and no longer contained the old IP.
- A real Axios request from the frontend package's Node runtime to the configured local API URL received the expected 401 from protected report history. This verifies the frontend HTTP client can reach FastAPI; no authenticated screen flow was run.
- A synthetic API flow registered/logged in a synthetic user, uploaded a generated PDF, extracted its text with PyMuPDF, ran the analysis task with mocked AI results, saved the synthetic report to a dedicated local MongoDB database, and read it through authenticated report status/history endpoints. Celery dispatch and status result were stubbed for this run; worker startup was separately verified. Vertex AI, GCS, scanned-PDF OCR, and a real asynchronous task result remain unverified due missing credentials/configuration.
- Scanned-PDF OCR is blocked locally: neither `tesseract` nor `pdftoppm` is installed.
- An initial harness enabled Celery eager execution inside the async TestClient request. It returned an expected task failure because the synchronous report task tried to start an event loop while the test event loop was active (`Cannot run the event loop while another loop is running`). The harness was rerun without eager mode and passed via isolated dispatch stubs; eager-task mode is not used by the app's local worker configuration.
- Synthetic daily and refill reminder requests passed through FastAPI using a dedicated local MongoDB database. Celery periodic registration and refill task dispatch were mocked; the authenticated profile returned both stored reminders. No WhatsApp API request or Celery message was sent. Real WhatsApp credentials/delivery remain unavailable and unverified.
- Mocked pharmacy-provider flow passed: valid synthetic result returned 200, malformed coordinates returned 422, a mocked provider exception collapsed to `200 []`, and missing provider configuration returned 503. No pharmacy provider was contacted; the missing API key blocks real location results. Device location permission and the external Google Maps link were not verified without a mobile runtime.
- Mocked chatbot flow passed with a synthetic valid response; whitespace-only input returned 422 and missing credentials returned a generic 502 without leaking the synthetic path/URL. Vertex AI was not contacted.
- Trends/history was exercised as part of the synthetic report flow: the authenticated history endpoint returned the newly saved structured value. The chart component itself was not rendered because there is no simulator/web runtime.
- WhatsApp service/task logging was hardened after inspection found phone numbers, medicine names, and provider error/response content were logged or returned in task results. They now log generic status plus exception class only and return generic task statuses. Four mocked success/failure/privacy tests passed; no WhatsApp API request was made.
- WhatsApp HTTP calls use a 10-second timeout, covered by the mocked request test. Automatic retries and duplicate-send idempotency are not implemented; review those semantics before production delivery.
- After the WhatsApp privacy/timeout changes, the worker was restarted and again reached `ready`; Beat restarted successfully against the empty local demo database.

Actual mobile UI requests remain unverified: no iOS simulator/Xcode output is available, and `react-native-web`/`react-dom` are absent for Expo web. No live integration is considered verified until exercised safely against the intended controlled service. Further runtime commands, per-feature outcomes, and fixes will be logged here as milestones complete.

## API URL setup by target

`frontendv3/services/api.ts` reads `EXPO_PUBLIC_API_URL` at bundle time. Set it before starting Expo; restart Metro after changing it. The fallback is `http://localhost:8001/api/v1`.

```sh
# iOS Simulator on this Mac
EXPO_PUBLIC_API_URL=http://localhost:8001/api/v1 npx expo start --localhost

# Android Studio emulator (host machine is 10.0.2.2 from the emulator)
EXPO_PUBLIC_API_URL=http://10.0.2.2:8001/api/v1 npx expo start --localhost

# Physical device: replace with this Mac's current private Wi-Fi IPv4 address.
# Find it with: ipconfig getifaddr en0 (or check the active Wi-Fi interface).
EXPO_PUBLIC_API_URL=http://<MAC-LAN-IP>:8001/api/v1 npx expo start --lan
```

For a physical-device demo, start Uvicorn bound to the LAN interface (`--host 0.0.0.0`) and Expo in LAN mode. Keep both devices on a trusted private Wi-Fi network; set the host firewall to allow ports 8001 and 8081 only from that trusted subnet, and ensure the router has no port forwarding for either port. Do not use public Wi-Fi, a public tunnel, or expose these development servers to the internet. This LAN device route has not been exercised in this verification; the currently running local services are loopback-only. The API URL is embedded into the app bundle, so rebuild/restart Expo after changing it.

## Earlier pre-SDK 57 runtime checks

- Backend regression suite: 38 passed, 0 failed, 0 skipped, 0 blocked; 11 warnings.
- Frontend TypeScript: passed. Offline Android and iOS JavaScript exports: passed. These exports do not verify native launch or user-facing screens.
- Frontend lint: unavailable because no `lint` script is declared. No component or mobile E2E test script is declared either.
- Backend `pip check`: passed. `git diff --check`: passed.
- Post-checkpoint code changes include Celery Redis TLS selection with `ssl.CERT_REQUIRED` for managed `rediss://`, configurable frontend API URL, WhatsApp log/result redaction, and a bounded WhatsApp request timeout. They are captured in the second checkpoint commit; managed Redis TLS was not live-tested.

## Previous startup commands (superseded by the credential-free commands at the top)

The commands below are retained as historical notes from an earlier milestone. Use the credential-free startup section at the top for this demo; it avoids loading values from backend `.env`.

```sh
# MongoDB (fresh temporary database, loopback only)
mkdir -p /tmp/vitalyze-demo-mongo
mongod --dbpath /tmp/vitalyze-demo-mongo --bind_ip 127.0.0.1 --port 27017 --nounixsocket

# Redis (loopback only, persistence disabled)
redis-server --bind 127.0.0.1 --port 6379 --save '' --appendonly no

# Backend terminal: work from backend/; create .env only if absent
cd backend
test -f .env || cp .env.example .env
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000

# Worker terminal: work from backend/
cd backend
.venv/bin/celery -A app.tasks.celery_app:celery worker --loglevel=INFO --pool=solo

# Beat terminal: work from backend/
cd backend
.venv/bin/celery -A app.tasks.celery_app:celery beat --loglevel=INFO --schedule=/tmp/vitalyze-demo-celerybeat

# Expo terminal: work from frontendv3/
cd frontendv3
EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 EXPO_OFFLINE=1 npx expo start --localhost --port 8081
```

For a physical phone, `localhost` refers to the phone itself. Follow “API URL setup by target” and restrict LAN access to your trusted private subnet. Expo Go or an iOS/Android simulator is required for actual native-screen testing. The web target also needs Expo-compatible `react-native-web` and `react-dom` packages, which are not currently installed.

## Manual iPhone checks still required

- Launch Expo Go and tap Sign In → Create an Account → Sign In; submit an invalid phone once and confirm the validation message is readable. Login with the synthetic demo account, close/reopen the app to check session restoration, then log out and confirm the protected tabs are gone.
- Upload a small synthetic text-based PDF. Confirm the local extraction preview label, extracted text, status completion, and saved report in Trends/history. Scanned PDFs should show the OCR dependency message; local Tesseract and Poppler are absent.
- Create a daily reminder and confirm it appears under Saved reminders. Do not expect a WhatsApp message; delivery stays disabled unless separately and explicitly enabled after stabilization.
- Tap the top-left profile icon and confirm "My Profile" reads the signed-in account's real fields (phone, email, verification state, age, gender, created date); accept/deny the local-notification permission prompt and confirm a scheduled local reminder fires on-device.
- Open Medical Locator, test location permission allow/deny, and use the Google Maps handoff. The link opens a separate Google Maps search; it is not a Vitalyze pharmacy result. Backend pharmacy data requires the `GEOAPIFY_API_KEY` credential.
- Open Chatbot and confirm the backend-configuration message appears without a fabricated answer. Vertex AI is not configured.
- Open Trends with no reports (clean empty state), then after a local preview report (no chart metrics are fabricated). Verify chart appearance on the phone; only the JavaScript bundle and API/history data were verified here.
- Confirm the iPhone and Mac share trusted Wi-Fi and the iPhone can reach `http://<MAC-LAN-IP>:8001/`. If unreachable, verify the Mac's current Wi-Fi IP, Expo `EXPO_PUBLIC_API_URL`, firewall rules for the trusted subnet, and restart Expo.
