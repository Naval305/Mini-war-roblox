from datetime import UTC
from datetime import datetime

from fastapi import FastAPI
from fastapi import File
from fastapi import HTTPException
from fastapi import UploadFile

from market_scanner import ensure_debug_dir
from market_scanner import notify
from market_scanner import process_image_bytes

app = FastAPI(title="Mini War Scanner API", version="0.1.0")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/scan")
async def scan(image: UploadFile = File(...)):
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    save_prefix = str(ensure_debug_dir() / f"scan_{timestamp}")

    try:
        result = process_image_bytes(image_bytes, save_prefix=save_prefix)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result.alert_items.empty:
        notify(result.alert_items)

    return {
        "ok": True,
        "next_price_in": result.next_price_in,
        "items": result.items.to_dict(orient="records"),
        "alert_items": result.alert_items.to_dict(orient="records"),
        "debug": {
            "screenshot_path": result.screenshot_path,
            "crop_path": result.crop_path,
        },
    }
