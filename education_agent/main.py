from fastapi import FastAPI
from .education_api import router as education_router

app = FastAPI(title="Education Agent API")

app.include_router(education_router)


@app.get("/")
def root():
    return {"message": "Education Agent is running"}