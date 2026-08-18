from fastapi import FastAPI

app = FastAPI(title="T1D Prediction API", version="0.1.0")


@app.get("/")
async def root():
    return {"message": "T1D Prediction API", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
