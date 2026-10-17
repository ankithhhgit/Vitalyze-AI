# Vitalyze.ai Interview Demo Runbook

## Current readiness

- Phase 3B/3C backend changes have a local automated baseline of 32 passing tests (11 warnings; no failures, skips, or blocked tests).
- This is mocked-test coverage. It does not verify live MongoDB, Redis/Celery, Google Maps, Vertex AI, WhatsApp, or mobile-to-API connectivity.
- Safe checkpoint commit `1b2977d` contains the reviewed Phase 3B/3C code, tests, environment template, and project docs. Runtime verification has not yet started.
- Do not use real patient records or real WhatsApp recipients for the demo. WhatsApp sends require explicit approval.

## Verification sequence

1. Start local/test MongoDB and Redis and verify connectivity without touching production data.
2. Start the Celery worker and, if the configured schedules require it, Beat against the local Redis broker.
3. Start FastAPI using local/test configuration and synthetic test data.
4. Start `frontendv3` Expo and verify the app's API base URL and frontend-to-backend requests.
5. Verify the report analyzer first with a synthetic PDF, then reminders with mocked/no-send messaging, pharmacy locator, chatbot, and trends/history.
6. Run backend regression tests and available frontend checks after any approved fixes.

## Results

Runtime commands and verified outcomes will be recorded here as each milestone is completed. No live integration is considered verified until exercised safely against the intended controlled service.
