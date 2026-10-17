# Vitalyze.ai Interview Demo Runbook

## Current readiness

- The latest backend regression suite has 38 passing tests (11 warnings; no failures, skips, or blocked tests). `pip check`, `git diff --check`, TypeScript, and offline Android/iOS bundle exports passed. Local MongoDB, Redis, Celery worker, and Beat startup were verified.
- Synthetic backend flows and frontend Axios-to-FastAPI connectivity were checked locally. Google Maps, Vertex AI, WhatsApp, scanned-PDF OCR, and actual mobile-screen flows remain unverified.
- Checkpoint `634e5b1` contains reviewed Phase 3B/3C changes. The separate runtime/security checkpoint is recorded in the work log and Git history.
- Do not use real patient records or real WhatsApp recipients for the demo. WhatsApp sends require explicit approval.

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
- FastAPI imported and startup connected to local MongoDB. Local OpenAPI returned 12 route paths, including reports and reminders. Google service-account file and Maps key are intentionally absent; startup logged that Maps is disabled and GCS credential initialization is unavailable.
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
- Mocked Maps API flow passed: valid synthetic result returned 200, malformed coordinates returned 422, a mocked provider exception collapsed to `200 []`, and missing Maps configuration returned 503. Google Maps was not contacted; the missing API key blocks real location results. Device location permission and Google Maps link opening were not verified without a mobile runtime.
- Mocked chatbot flow passed with a synthetic valid response; whitespace-only input returned 422 and missing credentials returned a generic 502 without leaking the synthetic path/URL. Vertex AI was not contacted.
- Trends/history was exercised as part of the synthetic report flow: the authenticated history endpoint returned the newly saved structured value. The chart component itself was not rendered because there is no simulator/web runtime.
- WhatsApp service/task logging was hardened after inspection found phone numbers, medicine names, and provider error/response content were logged or returned in task results. They now log generic status plus exception class only and return generic task statuses. Four mocked success/failure/privacy tests passed; no WhatsApp API request was made.
- WhatsApp HTTP calls use a 10-second timeout, covered by the mocked request test. Automatic retries and duplicate-send idempotency are not implemented; review those semantics before production delivery.
- After the WhatsApp privacy/timeout changes, the worker was restarted and again reached `ready`; Beat restarted successfully against the empty local demo database.

Actual mobile UI requests remain unverified: no iOS simulator/Xcode output is available, and `react-native-web`/`react-dom` are absent for Expo web. No live integration is considered verified until exercised safely against the intended controlled service. Further runtime commands, per-feature outcomes, and fixes will be logged here as milestones complete.

## API URL setup by target

`frontendv3/services/api.ts` reads `EXPO_PUBLIC_API_URL` at bundle time. Set it before starting Expo; restart Metro after changing it. The fallback is `http://localhost:8000/api/v1`.

```sh
# iOS Simulator on this Mac
EXPO_PUBLIC_API_URL=http://localhost:8000/api/v1 npx expo start --localhost

# Android Studio emulator (host machine is 10.0.2.2 from the emulator)
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000/api/v1 npx expo start --localhost

# Physical device: replace with this Mac's current private Wi-Fi IPv4 address.
# Find it with: ipconfig getifaddr en0 (or check the active Wi-Fi interface).
EXPO_PUBLIC_API_URL=http://<MAC-LAN-IP>:8000/api/v1 npx expo start --lan
```

For a physical-device demo, start Uvicorn bound to the LAN interface (`--host 0.0.0.0`) and Expo in LAN mode. Keep both devices on a trusted private Wi-Fi network; set the host firewall to allow ports 8000 and 8081 only from that trusted subnet, and ensure the router has no port forwarding for either port. Do not use public Wi-Fi, a public tunnel, or expose these development servers to the internet. This LAN device route has not been exercised in this verification; the currently running local services are loopback-only. The API URL is embedded into the app bundle, so rebuild/restart Expo after changing it.

## Final checks for the current runtime milestone

- Backend regression suite: 38 passed, 0 failed, 0 skipped, 0 blocked; 11 warnings.
- Frontend TypeScript: passed. Offline Android and iOS JavaScript exports: passed. These exports do not verify native launch or user-facing screens.
- Frontend lint: unavailable because no `lint` script is declared. No component or mobile E2E test script is declared either.
- Backend `pip check`: passed. `git diff --check`: passed.
- Post-checkpoint code changes include Celery Redis TLS selection with `ssl.CERT_REQUIRED` for managed `rediss://`, configurable frontend API URL, WhatsApp log/result redaction, and a bounded WhatsApp request timeout. They are captured in the second checkpoint commit; managed Redis TLS was not live-tested.

## Safe local start commands

Run these in separate terminals. The backend environment file must contain local URLs and placeholders only; do not copy real production credentials into a demo environment.

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

## Manual checks still required before the demo

- Launch Expo Go on the actual demo device and confirm login, authenticated API access, and report history against the synthetic local account.
- Run a synthetic digital PDF through upload, processing, status polling, and history. If demonstrating scanned PDFs, install/verify local OCR dependencies first; scanned-PDF OCR was blocked in this environment.
- On a device, grant and deny location permission, confirm nearby-pharmacy results and Google Maps link handling. Real Google Maps results require a valid restricted Maps key and were not tested here.
- Verify chatbot display with a configured provider only if safe demo credentials are available; otherwise use the previously tested mocked route result and label it as mocked.
- Review reminder creation/scheduling without dispatching a message. WhatsApp delivery was not tested; do not send to a real recipient without explicit approval and a controlled test number.
- Confirm trends/history charts visually match the synthetic report values; API history was checked, chart rendering was not.
