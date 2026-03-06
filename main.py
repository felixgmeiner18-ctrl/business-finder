import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import delete_business, get_businesses, init_db, update_business, upsert_business
from scraper import search_businesses


class UpdatePayload(BaseModel):
    status: str | None = None
    notes: str | None = None


class SearchPayload(BaseModel):
    region: str


def run_search(region: str):
    try:
        businesses = search_businesses(region)
        count = 0
        for b in businesses:
            if upsert_business(b["name"], b["phone"], b["address"], b["category"], region):
                count += 1
        print(f"[search] {region}: {len(businesses)} found, {count} new")
    except RuntimeError as e:
        print(f"[search] error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/businesses")
def list_businesses(
    status: str | None = Query(None),
    region: str | None = Query(None),
    category: str | None = Query(None),
):
    return get_businesses(status=status, region=region, category=category)


@app.post("/search")
def trigger_search(payload: SearchPayload):
    if not payload.region.strip():
        raise HTTPException(400, "Region cannot be empty")
    thread = threading.Thread(target=run_search, args=(payload.region.strip(),), daemon=True)
    thread.start()
    return {"message": f"Search started for '{payload.region}'"}


@app.patch("/businesses/{business_id}")
def update(business_id: int, payload: UpdatePayload):
    update_business(business_id, status=payload.status, notes=payload.notes)
    return {"ok": True}


@app.delete("/businesses/{business_id}")
def delete(business_id: int):
    delete_business(business_id)
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
