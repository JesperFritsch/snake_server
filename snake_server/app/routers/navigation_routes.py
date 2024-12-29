from fastapi import APIRouter
from snake_server.app.services import nav_services

router = APIRouter()

@router.get("/")
async def root():
    return nav_services.serve_root()