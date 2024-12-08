from fastapi import APIRouter
from .routers import  image_router, transfer_router

v1_router = APIRouter()


# v1_router.include_router(user_router.router, prefix="/users", tags=["users"])
# v1_router.include_router(login_router.router, prefix="/login", tags=["login"])
v1_router.include_router(image_router.router, prefix="/images", tags=["images"])
v1_router.include_router(transfer_router.router, prefix="/transfer", tags=["transfer"])


