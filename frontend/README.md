# Company Knowledge Base Admin UI

Vite + React + TypeScript + TailwindCSS admin control panel for the existing
FastAPI Knowledge Base backend.

## Development

```bash
npm install
npm run dev
```

Vite serves the app on `http://localhost:5173` and proxies:

- `/api/*` to `http://localhost:8000`
- `/health/*` to `http://localhost:8000`

## Build

```bash
npm run build
```

The static production build is written to `dist/`.

## Auth Token Strategy

The current backend returns a JWT bearer token from `POST /api/auth/login`.
The admin UI stores it in `localStorage` using the existing static UI key:

```text
company-rag-access-token
```

Axios attaches the token with:

```text
Authorization: Bearer <token>
```

Future hardening should move browser auth to httpOnly secure cookies. That will
need backend support for cookie issuing, CSRF protection, and logout/session
revocation endpoints.

## Current Scope

The UI manages the Company Knowledge Base REST surface:

- document upload, list/detail, delete, reindex, and ACL rows
- code repository ingest, list/detail, delete, reindex, and ACL rows
- user creation/activation
- chat traces, feedback, retrieval analytics, and health

Role, tenant, department, and ownership workflows are intentionally out of scope.
