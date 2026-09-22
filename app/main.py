from fastapi import FastAPI

app = FastAPI(title="RevSignal API")


@app.get("/")
async def root():
    return {"message": "RevSignal API is running"}