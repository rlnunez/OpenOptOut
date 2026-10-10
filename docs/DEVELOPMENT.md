# Local Development Guide

This guide walks through setting up a fast local development loop (hot-reload API and frontend) without Docker.

> [!NOTE]
> If you are looking to run OpenOptOut in **production** natively on a server without containers (systemd + nginx on Linux, or Windows Service + IIS on Windows), see [`docs/NATIVE_INSTALL.md`](NATIVE_INSTALL.md) instead.

---

## Prerequisites

- **Python:** 3.11 or newer (Python 3.12 recommended)
- **Node.js:** v18 or newer and npm
- **Operating System:** Linux, macOS, or Windows
- **Playwright Dependencies:** System libraries required for headless browser automation

---

## 1. Backend Setup

From the repository root:

```bash
# 1. Create and activate a virtual environment
python3 -m venv backend/venv
source backend/venv/bin/activate       # On Windows: backend\venv\Scripts\activate

# 2. Install backend dependencies
pip install -r backend/requirements.txt

# 3. Configure environment
cp .env.example .env
# Generate a secret key: openssl rand -hex 32
# Set SECRET_KEY in your .env file

# 4. Start the development API server with hot-reload
uvicorn backend.main:app --reload
```

- **API Server:** http://localhost:8000
- **Interactive Swagger Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

> [!IMPORTANT]
> **Always run `uvicorn` from the repository root.** The backend uses package-relative imports (`from .models ...`), so executing `cd backend && uvicorn main:app` will fail with an import error.

---

## 2. Playwright Browser Setup

The opt-out automation and discovery engines use Playwright to drive headless Firefox. After installing Python dependencies, install the Playwright browser binaries:

```bash
# With the virtual environment active:
playwright install firefox
playwright install-deps firefox
```

*(On Windows, `playwright install-deps` is not needed; on Linux, it installs the necessary system graphics and font libraries).*

---

## 3. Frontend Setup

In a separate terminal window:

```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite dev server with hot-module replacement
npm run dev
```

- **Frontend App:** http://localhost:3000
- The Vite dev server automatically proxies `/api` calls to the FastAPI backend at `http://localhost:8000`.

---

## 4. Running Tests

OpenOptOut includes a self-contained tier-based test suite that runs without external services:

```bash
cd backend
python3 -m tests.run_tests
```

To run a specific test subsystem:
```bash
python3 -m tests.run_tests --only plugins
python3 -m tests.run_tests --only saml
python3 -m tests.run_tests --tier 1
```

To run the full test suite and Docker profile matrix inside containers:
```bash
./scripts/test-docker-matrix.sh
```

For full test suite documentation, including test tiers and CI setup, see [`backend/tests/TESTING.md`](../backend/tests/TESTING.md).

---

## 5. Working on Plugins & Broker Add-ons

- **Writing Plugins:** See the [Plugin Developer Guide](PLUGINS.md) and [`backend/plugins/docs/WRITING_PLUGINS.md`](../backend/plugins/docs/WRITING_PLUGINS.md).
- **Writing Declarative Broker Specs:** See [`docs/INTERPRETER.md`](INTERPRETER.md).
- **Project Structure & Architecture:** See [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).
- **Contributing Guidelines:** See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
