from fastapi import APIRouter

from erf.api.v1 import admin, auth, email_actions, reports, requests

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(requests.router)
api_router.include_router(requests.tasks_router)
api_router.include_router(reports.router)
api_router.include_router(admin.router)
api_router.include_router(email_actions.router)
