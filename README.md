# Ask_Data

Enterprise AI Analytics Platform

Ask_Data is a FastAPI and Next.js platform for secure, role-based analytics over approved external data sources. It combines natural-language querying, governed access control, and exportable results with MongoDB Atlas as the internal application store.

## Overview

The platform is designed for organizations that want employees to ask business questions in plain English while administrators retain control over data access, permissions, and connection management.

Core capabilities:

- Admin onboarding and role-based authentication
- Secure connection management for MySQL, PostgreSQL, and MongoDB sources
- Permission-scoped employee access to approved datasets
- Natural-language analysis, query execution, and export
- MongoDB Atlas-backed internal persistence for users, permissions, logs, and metadata

## Project Structure

The repository is organized as follows:

- `expo_project/backend/` - FastAPI service, services, schemas, and tests
- `expo_project/frontend/` - Next.js application and UI components
- `expo_project/scripts/` - Setup, verification, and smoke-test utilities
- `expo_project/docs/` - Project documentation and hackathon notes

## Architecture

- Frontend: Next.js
- Backend: FastAPI + Uvicorn
- Internal store: MongoDB Atlas
- External data sources: MySQL, PostgreSQL, MongoDB

The frontend communicates with the backend through a server-side proxy so client requests stay consistent across environments.

## Key Features

- Secure organization-based authentication
- Admin-managed employee provisioning
- Encrypted connection credential storage
- Metadata discovery for approved sources
- Analytics query and export workflows
- Fallback AI behavior when no provider key is configured

## Local Setup

Prerequisites:

- Python 3.10+
- Node.js 18+
- MongoDB Atlas account or compatible MongoDB instance

Environment configuration:

```bash
copy expo_project\.env.example expo_project\.env
```

Required backend values:

- `MONGO_URL`
- `JWT_SECRET_KEY`
- `ENCRYPTION_KEY`

Optional AI values:

- `OPENAI_API_KEY`
- `GROQ_API_KEY`

Install and run locally:

```bash
cd expo_project
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
```

Start the backend:

```bash
cd expo_project\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Start the frontend:

```bash
cd expo_project\frontend
npm run dev -- --port 3000
```

Health check:

```bash
curl http://localhost:8000/health
```

## API Documentation

- Backend health: `http://localhost:8000/health`
- OpenAPI docs: `http://localhost:8000/docs`

## Notes

- Secrets are excluded from version control through `.gitignore`.
- The backend requires a reachable MongoDB connection at startup.
- The frontend is a Node.js app and is not intended for static export.

## License

This repository does not currently declare a license.
