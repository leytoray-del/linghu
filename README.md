# Engineering Resource Requests

An internal web application for planning, requesting and approving engineering resources for projects,
pre-sales work and service requests. It replaces the previous Microsoft Forms and Power Automate process
and implements the department's resource request policy:

- Requests are submitted through one form that mirrors the original 14 questions.
- Requests need at least five working days of notice. The system counts working days, excluding
  weekends and public holidays, and classifies anything shorter as urgent, which then requires a
  justification.
- Each request is routed automatically by its type of support to the leader of the Support Team or
  the Development Team. The team leader assigns named engineers and approves, returns or rejects it.
  The director then gives the final approval, which confirms the allocation.
- Every step sends an email and is recorded in an append-only history. Overdue approvals trigger
  reminders, and approved requests close automatically after their planned end date.
- Team leaders assign engineers full time or part time (25%, 50% or 75%). The resource load view shows
  each engineer's weekly booking in percent, so overbooking is visible before it happens.
- Requesters can ask to move the dates or change the headcount of an approved request. The team leader
  reviews the change against availability in the new period, and the allocation is updated in place.
- Approval emails carry a calendar file, so engineers add their assignment to Outlook in one click.
- Approvers receive one digest email each working morning, and directors receive a weekly summary of
  activity, waiting approvals and work starting in the next two weeks. Urgent requests still trigger
  individual reminders.
- "Copy as new request" prefills a new request from an earlier one.
- Team leaders and the director see yearly reports and an Excel export.

## Repository layout

```text
backend/        FastAPI service (Python 3.12+), SQLite through SQLAlchemy 2 and Alembic
  src/erf/
    api/          HTTP routes, request-scoped dependencies (session, CSRF, roles)
    services/     Use cases: workflow transitions, requests, resources, reports, admin, auth
    domain/       Framework-free rules: state machine, working-day calendar, urgency, validation
    repositories/ Database queries
    db/models/    ORM models
    jobs/         Email outbox delivery, reminders, auto-close, session clean-up
    infrastructure/mail/  SMTP and log mail transports
    templates/email/      Notification templates
  migrations/   Alembic migrations
  tests/        Unit tests (domain) and integration tests (API, jobs, migrations)
frontend/       Vue 3, TypeScript, Element Plus, Pinia, Vue Router
deploy/         systemd units, Caddy site, environment template and release scripts
docs/           Design document (Chinese), UI prototype and deployment guide
```

## Local development

Requirements: Python 3.12 or newer with [uv](https://docs.astral.sh/uv/), and Node.js 20 or newer.

```bash
cd backend
uv sync
uv run erf migrate
uv run erf seed --demo
uv run uvicorn --factory erf.main:create_app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The Vite dev server forwards `/api` to the backend on port 8000.
The API reference is available at http://localhost:8000/api/docs outside production.

### Demo accounts

`erf seed --demo` creates the accounts below, all with the password `Demo@2026!`, together with eleven
requests in every workflow state. Demo requests are created through the real services with a simulated
clock, so their history, tasks and allocations are authentic. Their emails are marked as not delivered.

| Account | Role |
| --- | --- |
| alex.tan@example.com, serene.koh@example.com | Project managers (requesters) |
| priya.nair@example.com | Team leader, Support Team |
| daniel.lim@example.com | Team leader, Development Team |
| grace.wong@example.com | Director |
| ahmad.rahman@example.com, meiling.chua@example.com, … | Engineers |
| pmo@example.com | Viewer (reports) |
| admin@example.com | Administrator |

## Quality checks

```bash
cd backend && uv run ruff format --check src tests migrations && uv run ruff check src tests migrations && uv run mypy && uv run pytest
```

```bash
cd frontend && npm run lint && npm run build
```

The same checks run in GitHub Actions (`.github/workflows/ci.yml`), which also builds a release archive
for every push to `main`.

## Configuration

All settings are environment variables with the `ERF_` prefix; see `backend/.env.example` for
development and `deploy/env/erf.env.example` for production. Workflow parameters such as the minimum
notice period and reminder intervals are changed by administrators in the application.

## Deployment

The application is designed to share a small server with other services: one Python process of about
100 MB, a SQLite file, and an existing Caddy instance for HTTPS. See `docs/部署指南.md` for the
step-by-step guide. In short:

```bash
deploy/scripts/build-release.sh --demo
```

```bash
sudo bash deploy/scripts/install.sh --domain your-host.duckdns.org
```

```bash
sudo bash deploy/scripts/release.sh erf-<version>.tar.gz --seed-demo
```

Pushes to `main` can also deploy automatically through GitHub Actions over SSH once the repository
secrets and variables described in the guide are set.

Each release is unpacked into its own directory, the database is backed up before migrations, and
the service rolls back automatically if the new version does not pass its health check.
