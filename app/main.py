from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.company.companyController import companyRouter
from app.user.userController import userRouter
from app.auth.authController import authRouter
from app.offer.offerController import offerRouter
from app.health.healthController import healthRouter

description = """
All these configurations are suggested in the doc and
are used in the OpenAPI specification and the automatic API docs UIs.

This is a test of the description. 🚀
"""
app = FastAPI(
    title='DeepTalent API',
    description=description,
    version='0.0.1',
    summary='REST API for deepTalent'
)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter()

app.include_router(companyRouter)
app.include_router(userRouter)
app.include_router(authRouter)
app.include_router(offerRouter)
app.include_router(healthRouter)
