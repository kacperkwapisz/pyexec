<h1 align="center">
  🚀 Advanced Python Execution API
</h1>

<p align="center">
  A secure, scalable, and distributed API for executing Python code in isolated environments.
</p>

<p align="center">
  <a href="https://github.com/kacperkwapisz/pyexec/actions/workflows/docker-image.yml">
    <img src="https://github.com/kacperkwapisz/pyexec/actions/workflows/docker-image.yml/badge.svg" alt="Build Status">
  </a>
  <a href="https://codecov.io/gh/kacperkwapisz/pyexec">
    <img src="https://codecov.io/gh/kacperkwapisz/pyexec/branch/main/graph/badge.svg" alt="Code Coverage">
  </a>
  <a href="./LICENSE.txt">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT">
  </a>
</p>

This API provides a robust, sandboxed environment for running Python code. It is designed for high-load, distributed environments where security, speed, and isolation are critical.

## Table of Contents

- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Usage](#api-usage)
- [Development](#development)
- [License](#license)

## Key Features

- 🛡️ **Secure, Ephemeral Execution**: Each execution runs in a new, disposable Docker container, providing strong kernel-level isolation.
- ⚡ **High Performance**: The "disposable container" model has near-instant startup times (<1s) for running code.
- 📦 **Isolated Dependency Management**: Sessions use independent virtual environments (`venv`), ensuring no cross-contamination of packages.
- 异步 **Asynchronous by Design**: Long-running tasks like package installation are handled in the background, keeping the API fast and responsive.
- 🔍 **Real-time Task Status**: Poll a status endpoint to get updates on your background tasks.
- ☁️ **Cloud-Native Ready**:
  - **Optional Redis Integration**: Use Redis for distributed task status management across multiple API instances.
  - **Optional S3 Integration**: Use an S3-compatible object store for persistent, shared file storage.
- 🔑 **API Key Authentication**: All endpoints are secured and require a per-request API key.

### Enhanced Security

- 🛡️ **Strongly Isolated Execution**: Each execution runs in a new, disposable Docker container. Code is executed by a **non-root user** to minimize risk.
- 🔒 **Resource Sandboxing**: Containers are resource-limited (**256MB memory**, shared CPU) to prevent denial-of-service attacks.
- 🌐 **No Network Access**: Executed code has **no access to the network**, preventing malicious outbound requests.
- ⚡ **High Performance**: The "disposable container" model has near-instant startup times (<1s).
- 📦 **Isolated Dependency Management**: Sessions use independent virtual environments (`venv`).
- ☁️ **Cloud-Native Ready**:
  - **Optional Redis Integration**: Use Redis for distributed task status management.
  - **Optional S3 Integration**: Use S3 for persistent, shared file storage.
- 🔑 **API Key Authentication**: All endpoints are secured via a per-request API key.

## Architecture Overview

The core of the API is a "disposable container" model. Instead of building a new Docker image for every session (which is slow), the API uses a single, pre-built base image (`pyexec-base`) and dynamically manages dependencies using virtual environments (`venv`) on a shared volume.

This provides the best of both worlds: the speed of `venv` and the security of Docker isolation.

```
+---------------------------------+      +--------------------------------+      +--------------------------------+
|       Host Machine / Volume     |      |        API Container           |      |   Disposable Exec Container    |
|---------------------------------|      |--------------------------------|      |--------------------------------|
|                                 |      |                                |      |                                |
|  /data/session-abc/             |      |   +------------------------+   |      |                                |
|    - venv/                      | <------> |      FastAPI / uvicorn   | ------> |  docker run --rm               |
|    - user_file.py               |      |   +------------------------+   |      |    -v /data/session-abc:/app   |
|                                 |      |                                |      |    pyexec-base                 |
|  /data/session-xyz/             |      |                                |      |    /app/venv/bin/python ...    |
|    - venv/                      |      |                                |      |                                |
|    - other_script.py            |      |                                |      |                                |
|                                 |      |                                |      |                                |
+---------------------------------+      +--------------------------------+      +--------------------------------+
```

## Quick Start

1.  **Configure**: Copy the example environment variables into a `.env` file and set your `API_KEY`.
2.  **Run**: `docker-compose up --build`
3.  **Use**: See the [API Usage](#api-usage) section below.

## Configuration

The application is configured using environment variables. For local development, `docker-compose` will automatically load a `.env` file from the project root.

### Example `.env` file:

```
# --- Required ---
# Generate a secure key with: openssl rand -hex 32
API_KEY=your-secret-key-goes-here

# --- Optional for local file storage ---
# The root directory where session data is stored if not using S3.
BASE_SESSION_PATH=/tmp/sessions

# --- Optional Redis for distributed task tracking ---
# REDIS_URL=redis://localhost:6379/0

# --- Optional S3 for distributed file storage ---
# S3_BUCKET_NAME=your-s3-bucket-name
# AWS_ACCESS_KEY_ID=your-access-key
# AWS_SECRET_ACCESS_KEY=your-secret-key
# AWS_REGION=us-east-1
```

## API Usage

All requests must include the `X-API-Key` header with your secret key.

### Understanding Sessions

The API is session-based. A **session** is a dedicated workspace for your code, files, and installed packages. All operations are namespaced by a `session_id`. This ensures that work done in one session does not interfere with another.

**You are responsible for creating the `session_id` on the client-side.** It can be any string, but to avoid conflicts, it should be unique. The recommended way to generate a secure, unique ID is to use a **UUID (Universally Unique Identifier)**.

Here is how you can generate one in Python:

```python
import uuid

# Generate a new, unique session ID
session_id = str(uuid.uuid4())
print(session_id)
# "e.g., '1a8b3f4d-2c6e-4b9a-8f7a-9d6c8b4a0c1d'"
```

You should create a new `session_id` for each independent task or user conversation and then use that same ID for all subsequent calls (`/install`, `/execute`, `/upload`, etc.) related to that task.

### Step 1: Install Packages (Optional)

Installs packages into a session's dedicated virtual environment. This is an asynchronous, non-blocking operation.

**Endpoint**: `POST /install`

```bash
curl -X POST http://localhost:8000/install \
  -H "X-API-Key: your-secret-key-goes-here" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "your-unique-session-id-here",
    "packages": ["pandas", "numpy"]
  }'

# Response (202 Accepted):
# {
#   "status": "install_queued",
#   "task_id": "install-your-unique-session-id-here",
#   "status_url": "/status/install/install-your-unique-session-id-here"
# }
```

### Step 2: Upload Files (Optional)

Uploads files to a session's working directory. They will be stored in S3 if configured, otherwise locally in the session's data volume.

**Endpoint**: `POST /upload`

```bash
curl -X POST "http://localhost:8000/upload" \
  -H "X-API-Key: your-secret-key-goes-here" \
  -F "session_id=your-unique-session-id-here" \
  -F "file=@./data/AAPL.csv"
```

### Step 3: Execute Code

Submits code for execution in a disposable container. This is an asynchronous, non-blocking operation.

**Endpoint**: `POST /execute`

```bash
curl -X POST http://localhost:8000/execute \
  -H "X-API-Key: your-secret-key-goes-here" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "your-unique-session-id-here",
    "code": "import pandas as pd\ndf = pd.read_csv(\"AAPL.csv\")\nprint(df.head(1).to_json())"
  }'

# Response (202 Accepted):
# {
#   "status": "execute_queued",
#   "task_id": "exec-your-unique-session-id-here-xxxxxxxx",
#   "status_url": "/status/execute/exec-your-unique-session-id-here-xxxxxxxx"
# }
```

### Step 4: Check Task Status

Polls the `status_url` returned by `/install` or `/execute` to get the status of a background task.

**Endpoint**: `GET /status/{task_type}/{task_id}`

```bash
curl -X GET http://localhost:8000/status/execute/exec-your-unique-session-id-here-xxxxxxxx \
  -H "X-API-Key: your-secret-key-goes-here"

# Final successful response:
# {
#   "status": "success",
#   "output": "...",
#   "errors": "",
#   "exit_code": 0
# }
```

### Step 5: Terminate Session

Deletes the session's directory, including its virtual environment and any local files.

**Endpoint**: `POST /terminate`

```bash
curl -X POST http://localhost:8000/terminate \
  -H "X-API-Key: your-secret-key-goes-here" \
  -H "Content-Type: application/json" \
  -d '{ "session_id": "your-unique-session-id-here" }'
```

## Development

### Setup Development Environment

```bash
# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install the package in development mode
pip install -e .
```

### Running Tests

Our test suite is built with `pytest` and provides comprehensive coverage for the application. All tests are self-contained and use mocked external services.

```bash
# Run all tests
pytest
```

### GitHub Actions Workflows

This project includes two GitHub Actions workflows:

1. **Build and Push Docker Image**: Triggered on pushes to the `main` branch. This workflow:

   - Runs the tests
   - Builds the Docker image
   - Pushes the image to GitHub Container Registry (ghcr.io)

2. **Run Tests**: Triggered on pull requests to the `main` branch. This workflow:
   - Runs the tests to validate the changes

### Docker Image

The Docker image is available at:

```
ghcr.io/kacperkwapisz/pyexec:latest
```

## License

This project is licensed under the MIT License. See the [LICENSE.txt](./LICENSE.txt) file for details.
