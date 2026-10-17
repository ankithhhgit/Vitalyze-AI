import pytest
import fitz
from bson import ObjectId

from app.tasks import report_processing


def test_text_based_pdf_is_extracted_without_ocr(tmp_path):
    path = tmp_path / "synthetic-text-report.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Synthetic hemoglobin value 12.5 g/dL")
    document.save(path)
    document.close()

    assert "Synthetic hemoglobin value 12.5 g/dL" in report_processing.extract_text_from_pdf(str(path))


def test_invalid_pdf_returns_actionable_extraction_error(tmp_path):
    path = tmp_path / "synthetic-invalid.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(report_processing.ReportExtractionError, match="valid PDF"):
        report_processing.extract_text_from_pdf(str(path))


def test_scanned_pdf_without_local_ocr_has_actionable_error(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-scanned.pdf"
    document = fitz.open()
    pix = fitz.Pixmap(fitz.csRGB, (0, 0, 2, 2), 0)
    pix.clear_with(0xFFFFFF)
    page = document.new_page()
    page.insert_image(page.rect, pixmap=pix)
    document.save(path)
    document.close()
    monkeypatch.setattr(report_processing.shutil, "which", lambda _name: None)

    with pytest.raises(report_processing.ReportExtractionError, match="install Tesseract and Poppler"):
        report_processing.extract_text_from_pdf(str(path))


def test_local_preview_persists_text_without_fabricating_findings(monkeypatch):
    saved = {}

    class ReportsCollection:
        async def insert_one(self, document):
            saved.update(document)
            return type("InsertResult", (), {"inserted_id": ObjectId("65a000000000000000000012")})()

    class Database:
        def __getitem__(self, name):
            assert name == "reports"
            return ReportsCollection()

    class FakeMongoClient:
        def __init__(self, _uri):
            pass
        def __getitem__(self, _name):
            return Database()
        def close(self):
            pass

    monkeypatch.setattr(report_processing, "AsyncIOMotorClient", FakeMongoClient)
    monkeypatch.setenv("REPORT_ANALYSIS_MODE", "local")
    monkeypatch.setattr(report_processing, "extract_vitals_with_gemini", lambda _text: pytest.fail("AI provider must not run in local mode"))
    monkeypatch.setattr(report_processing, "generate_summary_with_gemini", lambda *_args: pytest.fail("AI provider must not run in local mode"))
    result = report_processing.task_run_ai_analysis.run(
        {"full_text": "Synthetic report text; no diagnosis supplied."},
        user_id="65a000000000000000000001",
        filename="synthetic-report.pdf",
    )

    assert result["status"] == "COMPLETED"
    assert result["analysis_mode"] == "local_extraction_preview"
    assert result["report_id"] == "65a000000000000000000012"
    assert result["vital_indicators"] == []
    assert "LOCAL EXTRACTION PREVIEW" in result["simple_summary"]
    assert saved["raw_text"] == "Synthetic report text; no diagnosis supplied."


def test_configured_ai_failure_does_not_persist_a_completed_report(monkeypatch):
    monkeypatch.setenv("REPORT_ANALYSIS_MODE", "ai")
    monkeypatch.setattr(report_processing.settings, "GEMINI_API_KEY", "synthetic-gemini-key")
    monkeypatch.setattr(
        report_processing,
        "extract_vitals_with_gemini",
        lambda _text: (_ for _ in ()).throw(RuntimeError("synthetic provider failure")),
    )
    monkeypatch.setattr(
        report_processing,
        "AsyncIOMotorClient",
        lambda *_args: pytest.fail("Failed AI analysis must not persist a report"),
    )

    with pytest.raises(RuntimeError, match="synthetic provider failure"):
        report_processing.task_run_ai_analysis.run(
            {"full_text": "Synthetic text"},
            user_id="65a000000000000000000001",
            filename="synthetic-report.pdf",
        )


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


def test_ai_mode_uses_gemini_service_and_persists_findings(monkeypatch):
    saved = {}
    seen = {}

    class ReportsCollection:
        async def insert_one(self, document):
            saved.update(document)
            return type("InsertResult", (), {"inserted_id": ObjectId("65a000000000000000000013")})()

    class Database:
        def __getitem__(self, name):
            assert name == "reports"
            return ReportsCollection()

    class FakeMongoClient:
        def __init__(self, _uri):
            pass

        def __getitem__(self, _name):
            return Database()

        def close(self):
            pass

    def fake_generate_json(prompt):
        seen["json_prompt"] = prompt
        return '[{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}]'

    def fake_generate_text(prompt):
        seen["summary_prompt"] = prompt
        return "Synthetic patient-friendly summary."

    monkeypatch.setenv("REPORT_ANALYSIS_MODE", "ai")
    monkeypatch.setattr(report_processing.settings, "GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setattr(report_processing, "AsyncIOMotorClient", FakeMongoClient)
    monkeypatch.setattr(
        report_processing.gemini_service, "generate_json", fake_generate_json
    )
    monkeypatch.setattr(
        report_processing.gemini_service, "generate_text", fake_generate_text
    )

    result = report_processing.task_run_ai_analysis.run(
        {"full_text": "Synthetic report text"},
        user_id="65a000000000000000000001",
        filename="synthetic-report.pdf",
    )

    assert result["analysis_mode"] == "ai_analysis"
    assert result["vital_indicators"] == [{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}]
    assert result["simple_summary"] == "Synthetic patient-friendly summary."
    assert saved["structured_entities"] == [{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}]
    assert "Synthetic report text" in seen["json_prompt"]


def test_report_mode_reads_from_settings_when_env_absent(monkeypatch):
    saved = {}

    class ReportsCollection:
        async def insert_one(self, document):
            saved.update(document)
            return type("InsertResult", (), {"inserted_id": ObjectId("65a000000000000000000015")})()

    class Database:
        def __getitem__(self, name):
            assert name == "reports"
            return ReportsCollection()

    class FakeMongoClient:
        def __init__(self, _uri):
            pass

        def __getitem__(self, _name):
            return Database()

        def close(self):
            pass

    monkeypatch.delenv("REPORT_ANALYSIS_MODE", raising=False)
    monkeypatch.setattr(report_processing.settings, "REPORT_ANALYSIS_MODE", "ai")
    monkeypatch.setattr(report_processing.settings, "GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setattr(report_processing, "AsyncIOMotorClient", FakeMongoClient)
    monkeypatch.setattr(
        report_processing, "extract_vitals_with_gemini",
        lambda _text: [{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}],
    )
    monkeypatch.setattr(
        report_processing, "generate_summary_with_gemini",
        lambda _entities, _text: "Synthetic settings-driven summary.",
    )

    result = report_processing.task_run_ai_analysis.run(
        {"full_text": "Synthetic report text"},
        user_id="65a000000000000000000001",
        filename="synthetic-report.pdf",
    )

    assert result["analysis_mode"] == "ai_analysis"
    assert saved["simple_summary"] == "Synthetic settings-driven summary."


def test_ai_mode_without_gemini_key_falls_back_to_local_preview(monkeypatch):
    saved = {}

    class ReportsCollection:
        async def insert_one(self, document):
            saved.update(document)
            return type("InsertResult", (), {"inserted_id": ObjectId("65a000000000000000000014")})()

    class Database:
        def __getitem__(self, name):
            assert name == "reports"
            return ReportsCollection()

    class FakeMongoClient:
        def __init__(self, _uri):
            pass

        def __getitem__(self, _name):
            return Database()

        def close(self):
            pass

    monkeypatch.setenv("REPORT_ANALYSIS_MODE", "ai")
    monkeypatch.setattr(report_processing.settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(report_processing, "AsyncIOMotorClient", FakeMongoClient)
    monkeypatch.setattr(
        report_processing,
        "extract_vitals_with_gemini",
        lambda _text: pytest.fail("AI provider must not run without GEMINI_API_KEY"),
    )

    result = report_processing.task_run_ai_analysis.run(
        {"full_text": "Synthetic report text"},
        user_id="65a000000000000000000001",
        filename="synthetic-report.pdf",
    )

    assert result["analysis_mode"] == "local_extraction_preview"
    assert result["vital_indicators"] == []
    assert "LOCAL EXTRACTION PREVIEW" in result["simple_summary"]


def test_extract_vitals_rejects_non_array_gemini_output(monkeypatch):
    monkeypatch.setattr(
        report_processing.gemini_service,
        "generate_json",
        lambda _prompt: '{"Indicator": "Hemoglobin"}',
    )

    with pytest.raises(RuntimeError, match="AI report interpretation failed"):
        report_processing.extract_vitals_with_gemini("Synthetic report text")


def test_extract_vitals_parses_fenced_json_response(monkeypatch):
    monkeypatch.setattr(
        report_processing.gemini_service,
        "generate_json",
        lambda _prompt: '```json\n[{"Indicator": "WBC", "Value": "6.0"}]\n```',
    )

    assert report_processing.extract_vitals_with_gemini("Synthetic text") == [
        {"Indicator": "WBC", "Value": "6.0"}
    ]
