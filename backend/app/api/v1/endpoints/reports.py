import shutil
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from typing import List, Optional
from pathlib import Path
from celery.result import AsyncResult
from celery import chain
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.tasks.celery_app import celery
from app.tasks.report_processing import task_extract_data_from_pdf, task_run_ai_analysis
from app.models.user import UserInDB
from app.models.report import ReportInDB
from app.api.v1.endpoints.auth import get_current_active_user, get_current_user
from app.db.mongodb import get_database

try:
    from app.services.storage_service import storage_service
except ImportError:
    storage_service = None

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("temp_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_report(
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    1. Uploads PDF to Temp Storage.
    2. (Optional) Uploads to Google Cloud Storage.
    3. Triggers Celery Chain: Extract -> Analyze -> Save to DB.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDFs allowed.")

    safe_filename = f"{current_user.id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        gcs_path = None
        
        if storage_service:
            try:
                file.file.seek(0)
                gcs_destination = f"users/{current_user.id}/{safe_filename}"
                gcs_path = storage_service.upload_file(file.file, gcs_destination)
                logger.info(f"File uploaded to GCS: {gcs_path}")
            except Exception as e:
                logger.error(f"GCS Upload failed: {e}")
        
        workflow = chain(
            task_extract_data_from_pdf.s(str(file_path)),
            task_run_ai_analysis.s(
                user_id=str(current_user.id), 
                filename=file.filename,
                gcs_path=gcs_path  # Pass the cloud path if it exists
            )
        )
        
        task = workflow.apply_async()

        try:
            await db["report_jobs"].insert_one(
                {
                    "_id": task.id,
                    "user_id": str(current_user.id),
                    "filename": file.filename,
                    "created_at": datetime.now(timezone.utc),
                }
            )
        except Exception:
            logger.exception("Failed to persist report task ownership")
            task.revoke(terminate=False)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to record report processing status.",
            )
        
        return {
            "task_id": task.id, 
            "message": "Report uploaded successfully. Analysis started."
        }
        
    except HTTPException:
        raise
    except Exception:
        logger.exception("Report upload failed")
        raise HTTPException(status_code=500, detail="Internal Server Error during upload.")
    finally:
        file.file.close()


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Check the status of the background analysis chain.
    """
    try:
        job = await db["report_jobs"].find_one(
            {"_id": task_id, "user_id": str(current_user.id)}
        )
    except Exception:
        logger.exception("Failed to load report task ownership")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report status is temporarily unavailable.",
        )

    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report task not found")

    task_result = AsyncResult(task_id, app=celery)
    
    response = {"status": task_result.state}
    
    if task_result.state == 'SUCCESS':
        response["result"] = task_result.result
    elif task_result.state == 'FAILURE':
        response["error"] = "Report processing failed."
        
    return response


@router.get("/history", response_model=List[ReportInDB])
async def get_user_report_history(
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_database)
):
    """
    Fetches all past analyzed reports for the logged-in user.
    This data is used to generate the History Charts on the frontend.
    """
    reports = []
    
    cursor = db["reports"].find({"user_id": str(current_user.id)}).sort("upload_date", -1)
    
    async for doc in cursor:
        reports.append(ReportInDB(**doc))
        
    return reports
