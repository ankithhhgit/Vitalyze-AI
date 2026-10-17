# Project Status

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
