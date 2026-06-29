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
