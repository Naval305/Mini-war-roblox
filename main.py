import json
import os
import cv2
import numpy as np
import pandas as pd
import re
import time
import urllib.error
import urllib.request
import pyautogui
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

load_dotenv()

DEFAULT_ITEMS = ["Diamonds", "Uran Ore", "Stable Uran", "Data Cube"]
DEFAULT_SCREENSHOT_REGION = (1400, 150, 2600, 800)
DEFAULT_MIN_ALERT_PERCENTAGE = 27
DEFAULT_MAX_ALERT_PERCENTAGE = 50


def _env_list(name, default):
    value = os.getenv(name)
    if not value:
        return default

    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise ValueError(f"{name} must contain at least one item.")
    return items


def _env_int(name, default):
    value = os.getenv(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _env_region(name, default):
    value = os.getenv(name)
    if not value:
        return default

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError(f"{name} must contain 4 comma-separated integers: x,y,w,h.")

    try:
        x, y, width, height = [int(part) for part in parts]
    except ValueError as exc:
        raise ValueError(f"{name} must contain only integers: x,y,w,h.") from exc

    if width <= 0 or height <= 0:
        raise ValueError(f"{name} width and height must be positive.")
    return (x, y, width, height)


ITEMS = _env_list("ITEMS", DEFAULT_ITEMS)
SCREENSHOT_REGION = _env_region("SCREENSHOT_REGION", DEFAULT_SCREENSHOT_REGION)
REFRESH_INTERVAL_SECONDS = 180
POST_REFRESH_DELAY_SECONDS = 3
MIN_ALERT_PERCENTAGE = _env_int("MIN_ALERT_PERCENTAGE", DEFAULT_MIN_ALERT_PERCENTAGE)
MAX_ALERT_PERCENTAGE = _env_int("MAX_ALERT_PERCENTAGE", DEFAULT_MAX_ALERT_PERCENTAGE)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GOOGLE_API_KEY) if GOOGLE_API_KEY else None

def take_screenshot(region=SCREENSHOT_REGION):
    screenshot = pyautogui.screenshot(region=region)
    image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    image = trim_black_borders(image)
    cv2.imwrite("latest_screenshot.png", image)
    return image


def trim_black_borders(image, threshold=8, padding=0):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    content_mask = gray > threshold

    rows = np.where(content_mask.any(axis=1))[0]
    cols = np.where(content_mask.any(axis=0))[0]
    if rows.size == 0 or cols.size == 0:
        return image

    y1 = max(0, rows[0] - padding)
    y2 = min(image.shape[0], rows[-1] + padding + 1)
    x1 = max(0, cols[0] - padding)
    x2 = min(image.shape[1], cols[-1] + padding + 1)
    return image[y1:y2, x1:x2]


def crop_market_table(img):
    if img is None:
        raise ValueError("Could not read image")

    h, w = img.shape[:2]

    # Convert to HSV for easier color segmentation
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Approximate mask for the tan/orange inner table area.
    # You may need to tune these values slightly.
    lower = np.array([8, 50, 120])
    upper = np.array([35, 220, 255])
    mask = cv2.inRange(hsv, lower, upper)

    # Clean up the mask
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # Find connected regions
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        aspect = cw / max(ch, 1)

        # Ignore tiny regions and the upper Market sign.
        # We want a large-ish, wide-ish region in the lower/middle part.
        if area < 0.05 * w * h:
            continue

        if y + ch < 0.45 * h:
            continue

        if aspect < 0.8 or aspect > 3.0:
            continue

        candidates.append((x, y, cw, ch, area))

    if not candidates:
        raise RuntimeError("Could not find table area. Try adjusting HSV thresholds.")

    # Usually the lower table body is the largest orange/tan region
    x, y, cw, ch, _ = max(candidates, key=lambda c: c[4])

    # Optional padding adjustment.
    # Shrink slightly to avoid wooden frame.
    pad_x = int(cw * 0.03)
    pad_y = int(ch * 0.04)

    x1 = max(0, x + pad_x)
    y1 = max(0, y + pad_y)
    x2 = min(w, x + cw - pad_x)
    y2 = min(h, y + ch - pad_y)

    crop = img[y1:y2, x1:x2]

    return crop


def _timer_to_seconds(timer_text):
    if not timer_text:
        return REFRESH_INTERVAL_SECONDS

    try:
        minutes, seconds = timer_text.split(":", maxsplit=1)
        return int(minutes) * 60 + int(seconds)
    except ValueError:
        return REFRESH_INTERVAL_SECONDS


def _cv2_to_pil(image):
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _extract_json_object(text):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"Gemini did not return a JSON object: {text}")

    return json.loads(text[start : end + 1])


def _normalize_timer(value):
    if value is None:
        return None

    match = re.search(r"(\d{1,2})\D+(\d{2})", str(value))
    if not match:
        return None

    minutes = int(match.group(1))
    seconds = int(match.group(2))
    return f"{minutes:02d}:{seconds:02d}"


def _normalize_int(value):
    if value is None:
        return None

    text = str(value).replace(",", "")
    match = re.search(r"-?\d+", text)
    return int(match.group()) if match else None


def _normalize_percentage(value):
    if value is None:
        return None

    text = str(value).replace("%", "").replace(",", "")
    match = re.search(r"[+-]?\d+", text)
    return int(match.group()) if match else None


def _extract_market_with_gemini(crop):
    if gemini_client is None:
        raise RuntimeError("GOOGLE_API_KEY is not set.")

    prompt = """
You are a strict data extraction tool. Return only valid JSON and no markdown.

Extract the visible market table from this image.

Schema:
{
  "next_price_in": "MM:SS",
  "items": [
    {"item_name": "string", "price": 1234, "percentage": -12}
  ]
}

Rules:
- Read only market rows inside the wooden board.
- Ignore the Market title/header and all UI outside the board.
- If a row is partially cut off at the top or bottom, omit it.
- price must be an integer without "$".
- percentage must be a signed integer. Green plus values are positive; red minus values are negative.
- Include all fully visible item rows, even if the percentage is not in the alert range.
""".strip()

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[_cv2_to_pil(crop), prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return _extract_json_object(response.text or "")


def _market_json_to_result(data):
    rows = []
    for item in data.get("items", []):
        item_name = str(item.get("item_name", "")).strip()
        if not item_name:
            continue

        rows.append(
            {
                "Item Name": item_name,
                "Price": _normalize_int(item.get("price")),
                "Percentage": _normalize_percentage(item.get("percentage")),
            }
        )

    return _normalize_timer(data.get("next_price_in")), pd.DataFrame(rows)


def get_alert_items(
    items,
    min_percentage=MIN_ALERT_PERCENTAGE,
    max_percentage=MAX_ALERT_PERCENTAGE,
):
    if items.empty:
        return items

    allowed_items = {item.casefold() for item in ITEMS}
    percentages = items["Percentage"].fillna(-10_000)
    return items[
        items["Item Name"].str.casefold().isin(allowed_items)
        & (percentages >= min_percentage)
        & (percentages <= max_percentage)
    ].reset_index(drop=True)


def notify(alert_items):
    message = format_discord_message(alert_items)
    print("Alert items:")
    print(alert_items.to_string(index=False))

    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL is not set; skipped Discord notification.")
        return

    send_discord_notification(message)


def format_discord_message(alert_items):
    lines = ["**Mini War Market Alert**"]
    for _, item in alert_items.iterrows():
        lines.append(
            f"- {item['Item Name']}: {item['Price']}$ ({item['Percentage']:+.0f}%)"
        )
    return "\n".join(lines)


def send_discord_notification(message):
    payload = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 300:
                print(f"Discord notification failed with status {response.status}.")
    except urllib.error.URLError as exc:
        print(f"Discord notification failed: {exc}")


def extract_market_table():
    screenshot = take_screenshot()
    crop = crop_market_table(screenshot)
    cv2.imwrite("latest_crop.png", crop)
    data = _extract_market_with_gemini(crop)
    return _market_json_to_result(data)


def main():
    while True:
        started_at = time.monotonic()
        try:
            next_price_in, items = extract_market_table()
        except Exception as exc:
            print(f"Could not extract market table: {exc}")
            time.sleep(10)
            continue

        elapsed = time.monotonic() - started_at
        alert_items = get_alert_items(items)

        print(f"\nNext Price In: {next_price_in}")
        print(items.to_string(index=False))

        if not alert_items.empty:
            notify(alert_items)
        else:
            print(
                f"No items between {MIN_ALERT_PERCENTAGE}% and "
                f"{MAX_ALERT_PERCENTAGE}%."
            )

        seconds_until_refresh = _timer_to_seconds(next_price_in)
        sleep_seconds = max(
            POST_REFRESH_DELAY_SECONDS,
            seconds_until_refresh - elapsed + POST_REFRESH_DELAY_SECONDS,
        )
        print(f"Sleeping {sleep_seconds:.1f}s until after the next refresh...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
