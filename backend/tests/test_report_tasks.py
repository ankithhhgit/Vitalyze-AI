import pytest

from app.tasks import report_processing


def test_pdf_extraction_failure_is_propagated_and_temp_file_cleaned(tmp_path, monkeypatch):
    source = tmp_path / "synthetic-invalid.pdf"
    source.write_bytes(b"synthetic test bytes")

    def fail_extraction(_path):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(report_processing, "extract_text_from_pdf", fail_extraction)

    try:
        report_processing.task_extract_data_from_pdf.run(str(source))
    except RuntimeError as exc:
        assert str(exc) == "synthetic extraction failure"
    else:
        raise AssertionError("Extraction exception should propagate to Celery")

    assert not source.exists()


def test_empty_extraction_is_not_returned_as_a_successful_task_result():
    with pytest.raises(RuntimeError, match="Report extraction produced no text"):
        report_processing.task_run_ai_analysis.run(
            {},
            user_id="65a000000000000000000001",
            filename="synthetic-report.pdf",
        )


def test_database_save_failure_is_not_returned_as_completed(monkeypatch):
    class FailingReportsCollection:
        async def insert_one(self, document):
            raise RuntimeError("synthetic database save failure")

    class FailingDatabase:
        def __getitem__(self, name):
            assert name == "reports"
            return FailingReportsCollection()

    class FakeMongoClient:
        def __init__(self, uri):
            assert uri == report_processing.settings.MONGO_URI

        def __getitem__(self, name):
            assert name == report_processing.settings.MONGO_DB_NAME
            return FailingDatabase()

        def close(self):
            return None

    monkeypatch.setattr(report_processing, "AsyncIOMotorClient", FakeMongoClient)
    monkeypatch.setattr(
        report_processing, "extract_vitals_with_gemini", lambda _text: []
    )
    monkeypatch.setattr(
        report_processing,
        "generate_summary_with_gemini",
        lambda _entities, _text: "Synthetic summary",
    )

    with pytest.raises(RuntimeError, match="Report processing failed"):
        report_processing.task_run_ai_analysis.run(
            {"full_text": "Synthetic report text"},
            user_id="65a000000000000000000001",
            filename="synthetic-report.pdf",
        )
