from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from config.cognilex_db import connect_to_mongodb,close_mongodb_connection


from routes.user_route import router as user_router
from routes.admin_route import router as admin_router
from routes.lawyer_route import router as lawyer_router
from routes.lawyerDashboard_route import router as lawyer_dashboard_router
from routes.appointment_route import router as appointment_router
from routes.feedback_route import router as feedback_router
from routes.chat_route import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_to_mongodb()

    os.makedirs("uploads/lawyers", exist_ok=True)
    print("✅ Uploads directory ready")

    yield
    close_mongodb_connection()

app = FastAPI(title="CogniLex Backend",lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "https://www.cognilex.systems"],
    allow_credentials=True,
    allow_methods=["*"],
)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(user_router)
app.include_router(admin_router)
app.include_router(lawyer_router)
app.include_router(lawyer_dashboard_router)
app.include_router(appointment_router)
app.include_router(feedback_router)
app.include_router(chat_router)


@app.get("/")
async def root():
    return {"message": "CogniLex Backend API is running", "status": "healthy"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}