from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from app.db_setup import init_db
from contextlib import asynccontextmanager
from app import v1_router
from app.middlewares import log_middleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from app.logging.logger import logger
from typing import List, Dict
from app.websocket.connection_manager import manager


# Funktion som körs när vi startar FastAPI -
# perfekt ställe att skapa en uppkoppling till en databas
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield



origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://192.168.56.1:5173",
    "http://192.168.1.186:5173",
    "https://khaledabo.com:81",
    "https://steady-moxie-4e7756.netlify.app",
    "https://dreamy-empanada-b8efec.netlify.app",
    "https://dreamy-empanada-b8efec.netlify.app"
]
app = FastAPI(lifespan=lifespan,  redirect_slashes=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
   
)

app.add_middleware(BaseHTTPMiddleware, dispatch=log_middleware)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(v1_router, prefix="/v1")
# init_weaviate()

# Workspace WebSocket endpoint (existing)
@app.websocket("/v1/ws/workspace/{workspace_id}")
async def workspace_websocket_endpoint(websocket: WebSocket, workspace_id: int):
    try:
        await manager.connect_to_workspace(websocket, workspace_id)
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_from_workspace(websocket, workspace_id)

# New user notifications WebSocket endpoint
@app.websocket("/v1/ws/user/{user_id}")
async def user_websocket_endpoint(websocket: WebSocket, user_id: int):
    try:
        await manager.connect_to_user(websocket, user_id)
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_from_user(websocket, user_id)

