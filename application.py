"""
    The entry file for the FastAPI application.
    No need to change anything here use router.py to add new points and functionality

    DEBUG setting / OPENAI_API_KEY are read from .env file.
    (see config.py)
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import config
from app.demo import router
from app.chat import router as chat_router
from fastapi.responses import HTMLResponse
from fastapi import APIRouter

application = FastAPI(title="FastAPI Responses API Demo", version="1.0", debug=config.DEBUG)

application.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

root_router = APIRouter()


@root_router.get("/", response_class=HTMLResponse)
async def root():
    return "Welcome to the FastAPI Responses Demo"

application.include_router(root_router)
application.include_router(chat_router)

# This is the main router for the application
application.include_router(router)
