import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import docker

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Security,
    UploadFile,
    BackgroundTasks,
    Request,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from fastapi.security import APIKeyHeader
import redis
import json
import boto3
from botocore.exceptions import NoCredentialsError

from .config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=True)

app = FastAPI()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception for request {request.method} {request.url}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected internal server error occurred."},
    )


class CodeExecutionRequest(BaseModel):
    session_id: str
    code: str
    env: Dict[str, str] = {}


class PackageInstallationRequest(BaseModel):
    session_id: str
    packages: List[str]


class TerminateSessionRequest(BaseModel):
    session_id: str


def get_session_path(session_id: str) -> Path:
    """Get the path to the session directory."""
    return settings.BASE_SESSION_PATH / session_id


async def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == settings.API_KEY:
        return api_key_header
    else:
        raise HTTPException(status_code=403, detail="Could not validate credentials")


# Add the API key dependency to all routes by creating a new root router
from fastapi import APIRouter

router = APIRouter(dependencies=[Depends(get_api_key)])


# --- Service Clients ---
redis_client = redis.from_url(settings.REDIS_URL) if settings.REDIS_URL else None

# Fallback in-memory storage if Redis is not configured
task_statuses: Dict[str, Any] = {} if not redis_client else None

# S3 client
s3_client = (
    boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    if settings.S3_BUCKET_NAME
    else None
)


# --- Helper Functions ---
def set_status(task_id: str, status: dict, ex: int = 3600):
    """Set the status of a task, using Redis if available."""
    if redis_client:
        redis_client.set(task_id, json.dumps(status), ex=ex)
    else:
        task_statuses[task_id] = status


def get_status_from_store(task_id: str) -> Optional[dict]:
    """Get the status of a task, using Redis if available."""
    if redis_client:
        status_json = redis_client.get(task_id)
        return json.loads(status_json) if status_json else None
    return task_statuses.get(task_id)


def get_session_venv_path(session_path: Path) -> Path:
    """Get the path to the session's virtual environment python executable."""
    return session_path / "venv" / "bin" / "python"


def do_install(session_id: str, packages: List[str]):
    """Install packages into a session's virtual environment using a disposable container."""
    task_id = f"install-{session_id}"
    set_status(task_id, {"status": "installing", "logs": ""})

    session_path = get_session_path(session_id)
    session_path.mkdir(parents=True, exist_ok=True)
    venv_python = get_session_venv_path(session_path)

    client = docker.from_env()
    log_output = ""

    try:
        # Step 1: Create venv if it doesn't exist
        if not venv_python.exists():
            log_output += "Creating virtual environment...\n"
            create_venv_command = ["python", "-m", "venv", "venv"]
            container = client.containers.run(
                image=settings.BASE_IMAGE_NAME,
                command=create_venv_command,
                volumes={str(session_path): {"bind": "/app", "mode": "rw"}},
                working_dir="/app",
                user="appuser",
                remove=True,
                detach=False,
            )
            log_output += container.decode("utf-8")

        # Step 2: Install packages using the venv pip
        log_output += f"Installing packages: {' '.join(packages)}...\n"
        pip_install_command = [str(venv_python), "-m", "pip", "install"] + packages
        container = client.containers.run(
            image=settings.BASE_IMAGE_NAME,
            command=pip_install_command,
            volumes={str(session_path): {"bind": "/app", "mode": "rw"}},
            working_dir="/app",
            user="appuser",
            remove=True,
            detach=False,
        )
        log_output += container.decode("utf-8")

        set_status(task_id, {"status": "success", "logs": log_output})

    except docker.errors.ContainerError as e:
        log_output += f"\nError during installation: {e.stderr.decode('utf-8')}"
        set_status(task_id, {"status": "failed", "logs": log_output, "error": str(e)})
    except Exception as e:
        set_status(task_id, {"status": "failed", "error": str(e), "logs": log_output})


def download_from_s3(session_id: str, filename: str, local_path: Path):
    """Download a file from S3 to a local path."""
    try:
        s3_client.download_file(
            settings.S3_BUCKET_NAME, f"{session_id}/{filename}", str(local_path)
        )
        return True
    except NoCredentialsError:
        logger.error("S3 credentials not available.")
        return False
    except Exception as e:
        logger.error(f"Error downloading from S3: {e}")
        return False


def do_execute(session_id: str, code: str, env: Dict[str, str], task_key: str):
    """Execute code in a disposable container using the session's virtual environment."""
    set_status(task_key, {"status": "running"})

    session_path = get_session_path(session_id)
    session_path.mkdir(parents=True, exist_ok=True)

    code_file_path = session_path / "temp_code.py"
    with code_file_path.open("w") as code_file:
        code_file.write(code)

    client = docker.from_env()
    venv_python = get_session_venv_path(session_path)

    # Use the session's venv python if it exists, otherwise fall back to global python
    python_executable = str(venv_python) if venv_python.exists() else "python"

    try:
        # Before running, sync S3 files if configured
        if s3_client:
            try:
                paginator = s3_client.get_paginator("list_objects_v2")
                pages = paginator.paginate(
                    Bucket=settings.S3_BUCKET_NAME, Prefix=f"{session_id}/"
                )
                for page in pages:
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        local_filename = Path(key).name
                        download_from_s3(
                            session_id, local_filename, session_path / local_filename
                        )
            except Exception as e:
                set_status(
                    task_key,
                    {"status": "failed", "error": f"Failed to sync S3 files: {e}"},
                )
                return

        container = client.containers.run(
            image=settings.BASE_IMAGE_NAME,
            command=[python_executable, "temp_code.py"],
            volumes={str(session_path): {"bind": "/app", "mode": "rw"}},
            working_dir="/app",
            environment=env,
            user="appuser",
            mem_limit="256m",
            cpu_shares=512,
            network_disabled=True,
            detach=False,
            remove=True,
        )

        output = container.decode("utf-8")
        # In this simple model, stdout and stderr are combined.
        # A more advanced implementation could redirect them separately.
        stdout = output
        stderr = ""
        exit_code = 0  # Success exit code

        set_status(
            task_key,
            {
                "status": "success",
                "output": stdout,
                "errors": stderr,
                "exit_code": exit_code,
            },
        )
    except docker.errors.ContainerError as e:
        set_status(
            task_key,
            {
                "status": "failed",
                "output": e.stdout.decode("utf-8") if e.stdout else "",
                "errors": e.stderr.decode("utf-8") if e.stderr else "",
                "exit_code": e.exit_status,
            },
        )
    except Exception as e:
        set_status(task_key, {"status": "failed", "error": str(e)})
    finally:
        if code_file_path.exists():
            code_file_path.unlink()


@router.post("/install", status_code=202)
async def install_packages(
    request: PackageInstallationRequest, background_tasks: BackgroundTasks
):
    """Install packages into a session's virtual environment in the background."""
    task_id = f"install-{request.session_id}"
    background_tasks.add_task(do_install, request.session_id, request.packages)
    return {
        "status": "install_queued",
        "session_id": request.session_id,
        "task_id": task_id,
        "status_url": f"/status/install/{task_id}",
    }


@router.post("/execute", status_code=202)
async def run_code(
    request: CodeExecutionRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(get_api_key),
):
    """Execute code in a session's dedicated Docker container in the background."""
    task_key = f"exec-{request.session_id}-{os.urandom(4).hex()}"
    background_tasks.add_task(
        do_execute, request.session_id, request.code, request.env, task_key
    )
    return {
        "status": "execute_queued",
        "task_id": task_key,
        "status_url": f"/status/execute/{task_key}",
    }


@router.get("/status/{task_type}/{task_id}")
async def get_status(task_type: str, task_id: str, api_key: str = Depends(get_api_key)):
    """Check the status of a background task."""
    status = get_status_from_store(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found.")
    return status


@router.post("/upload", status_code=200)
async def create_upload_file(
    session_id: str = Form(...),
    file: UploadFile = File(...),
    api_key: str = Depends(get_api_key),
):
    """Upload a file to S3 or local session directory."""
    logger.info(
        f"Received upload request for session {session_id} for file {file.filename}"
    )

    if s3_client:
        try:
            s3_client.upload_fileobj(
                file.file, settings.S3_BUCKET_NAME, f"{session_id}/{file.filename}"
            )
            return {"filename": file.filename, "storage": "s3"}
        except NoCredentialsError:
            raise HTTPException(
                status_code=500, detail="S3 credentials not configured on server."
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")
    else:
        # Fallback to local storage
        session_path = get_session_path(session_id)
        session_path.mkdir(parents=True, exist_ok=True)
        file_location = session_path / file.filename
        with file_location.open("wb+") as file_object:
            shutil.copyfileobj(file.file, file_object)
        return {"filename": file.filename, "storage": "local"}


@router.post("/terminate")
def terminate_session(request: TerminateSessionRequest):
    """Terminate a session by deleting its directory."""
    logger.info(f"Received terminate request for session {request.session_id}")
    session_id = request.session_id
    session_path = get_session_path(session_id)

    if session_path.exists():
        shutil.rmtree(session_path)
        message = f"Session {session_id} terminated successfully."
    else:
        message = f"Session {session_id} not found."

    return {"status": "success", "message": message}


@router.get("/download")
async def download_file(
    session_id: str, filename: str, api_key: str = Depends(get_api_key)
):
    """Download a file from S3 or local session directory."""
    if s3_client:
        try:
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.S3_BUCKET_NAME,
                    "Key": f"{session_id}/{filename}",
                },
                ExpiresIn=3600,
            )
            return {"url": url}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Could not generate S3 download link: {e}"
            )
    else:
        # Fallback to local storage
        session_path = get_session_path(session_id)
        file_path = session_path / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(path=str(file_path), filename=filename)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(router)
