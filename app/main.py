import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.database import init_db
from app.routers import images, posts, suggestions

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AI Image Understanding & Content Matching Engine",
    description="FlyRank Backend Track capstone — vision tagging, semantic matching, and a mismatch guard.",
    version="1.1.0",
)


@app.on_event("startup")
def on_startup():
    init_db()  # alembic upgrade head


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Bad input -> clean 422 with details, never a 500 (shared requirement #2).
    # jsonable_encoder-safe: strip non-serializable ctx objects.
    errs = [{k: v for k, v in e.items() if k in ("loc", "msg", "type")} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errs})


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(images.router)
app.include_router(posts.router)
app.include_router(suggestions.router)
