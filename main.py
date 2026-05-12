import json
import os
import cv2
import easyocr
import numpy as np
import pandas as pd
import re
import time
import urllib.error
import urllib.request
import warnings
from difflib import get_close_matches
import pyautogui
from dotenv import load_dotenv

load_dotenv() 

warnings.filterwarnings("ignore", message="'pin_memory' argument is set as true.*")
reader = easyocr.Reader(["en"], gpu=False, verbose=False)

SCREENSHOT_REGION = (1400, 150, 2600, 800)
REFRESH_INTERVAL_SECONDS = 180
POST_REFRESH_DELAY_SECONDS = 3
MIN_ALERT_PERCENTAGE = 30
MAX_ALERT_PERCENTAGE = 42
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

KNOWN_ITEMS = [
    "Coin Bag",
    "Research",
    "Diamonds",
    "Uran Ore",
    "Stable Uran",
    "Data Cube",
    "Dark Matter",
    "Alien Essence",
]


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

        if y < 0.20 * h:
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


def _ocr_column(reader, image, x1_ratio, x2_ratio, y2_ratio=0.78, scale=2, allowlist=None):
    h, w = image.shape[:2]
    x1 = int(w * x1_ratio)
    x2 = int(w * x2_ratio)
    y2 = int(h * y2_ratio)
    crop = image[:y2, x1:x2]
    scaled = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    kwargs = {"detail": 1, "paragraph": False}
    if allowlist:
        kwargs["allowlist"] = allowlist

    entries = []
    for bbox, text, confidence in reader.readtext(scaled, **kwargs):
        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]
        entries.append(
            {
                "text": text,
                "confidence": float(confidence),
                "center_y": ((min(ys) + max(ys)) / 2) / scale,
                "x1": x1 + (min(xs) / scale),
            }
        )

    return sorted(entries, key=lambda entry: entry["center_y"])


def _clean_item_name(text):
    text = re.sub(r"[^A-Za-z ]+", "", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip().title()

    match = get_close_matches(text, KNOWN_ITEMS, n=1, cutoff=0.72)
    return match[0] if match else text


def _merge_name_entries(entries):
    merged = []
    for entry in entries:
        if merged and abs(merged[-1]["center_y"] - entry["center_y"]) <= 14:
            merged[-1]["text"] = f'{merged[-1]["text"]} {entry["text"]}'
            merged[-1]["center_y"] = (merged[-1]["center_y"] + entry["center_y"]) / 2
            merged[-1]["confidence"] = min(merged[-1]["confidence"], entry["confidence"])
        else:
            merged.append(entry.copy())

    return merged


def _clean_price(text):
    digits = "".join(re.findall(r"\d+", text))

    if len(digits) > 5 and len(set(digits[:3])) == 1:
        digits = digits[1:]

    # EasyOCR often reads the trailing "$" as a final digit on this font.
    # Keep obvious 5-digit prices like 24600, trim suspicious currency tails.
    if len(digits) == 5 and not digits.endswith("00"):
        digits = digits[:-1]
    elif len(digits) == 4 and digits.endswith(("3", "5")):
        digits = digits[:-1]

    return int(digits) if digits else None


def _clean_percentage(text, sign):
    digits = "".join(re.findall(r"\d+", text))

    if "%" in text and len(digits) > 2 and digits.endswith("6"):
        digits = digits[:-1]
    if len(digits) > 2 and digits.endswith("96"):
        digits = digits[:-2]
    elif len(digits) == 2 and digits[0] == digits[1]:
        digits = digits[:1]

    # The sign and percent glyph are commonly read as 4/5 and 9.
    if digits and digits[0] in {"4", "5"}:
        digits = digits[1:]
    if sign == "-" and len(digits) == 3 and digits[1] == "4":
        digits = digits[0] + digits[2]
    if len(digits) == 3 and digits[1] == digits[2]:
        digits = digits[:2]
    if len(digits) > 1 and digits.endswith("9"):
        digits = digits[:-1]

    value = int(digits) if digits else None
    if value is None:
        return None
    return value if sign == "+" else -value


def _percentage_sign_for_row(image, center_y, y2_ratio=0.78):
    h, w = image.shape[:2]
    rows_h = int(h * y2_ratio)
    band = max(18, int(h * 0.055))
    y1 = max(0, int(center_y) - band)
    y2 = min(rows_h, int(center_y) + band)
    x1 = int(w * 0.68)
    x2 = int(w * 0.90)
    crop = image[y1:y2, x1:x2]

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([45, 80, 80]), np.array([85, 255, 255]))
    red_low = cv2.inRange(hsv, np.array([0, 60, 80]), np.array([10, 255, 255]))
    red_high = cv2.inRange(hsv, np.array([170, 60, 80]), np.array([179, 255, 255]))
    red = cv2.bitwise_or(red_low, red_high)

    return "+" if cv2.countNonZero(green) >= cv2.countNonZero(red) else "-"


def _nearest_by_y(entries, center_y, max_distance=28):
    if not entries:
        return None

    nearest = min(entries, key=lambda entry: abs(entry["center_y"] - center_y))
    if abs(nearest["center_y"] - center_y) > max_distance:
        return None
    return nearest


def _ocr_percentage_for_row(reader, image, center_y):
    h, w = image.shape[:2]
    rows_h = int(h * 0.78)
    band = max(24, int(h * 0.07))
    y1 = max(0, int(center_y) - band)
    y2 = min(rows_h, int(center_y) + band)
    x1 = int(w * 0.72)
    x2 = int(w * 0.88)
    crop = image[y1:y2, x1:x2]
    scaled = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    return " ".join(
        reader.readtext(
            scaled,
            detail=0,
            paragraph=False,
            allowlist="0123456789%",
        )
    )


def _extract_next_price_in(reader, image):
    h = image.shape[0]
    timer_crop = image[int(h * 0.78) :, :]
    scaled = cv2.resize(timer_crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    text = " ".join(reader.readtext(scaled, detail=0, paragraph=False))
    digits = "".join(re.findall(r"\d+", text))

    if len(digits) >= 5:
        return f"{digits[-5:-3]}:{digits[-2:]}"
    if len(digits) >= 4:
        return f"{digits[-4:-2]}:{digits[-2:]}"
    return None


def _timer_to_seconds(timer_text):
    if not timer_text:
        return REFRESH_INTERVAL_SECONDS

    try:
        minutes, seconds = timer_text.split(":", maxsplit=1)
        return int(minutes) * 60 + int(seconds)
    except ValueError:
        return REFRESH_INTERVAL_SECONDS


def get_alert_items(
    items,
    min_percentage=MIN_ALERT_PERCENTAGE,
    max_percentage=MAX_ALERT_PERCENTAGE,
):
    if items.empty:
        return items

    percentages = items["Percentage"].fillna(-10_000)
    return items[
        (percentages >= min_percentage) & (percentages <= max_percentage)
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

    name_entries = _merge_name_entries(_ocr_column(reader, crop, 0.14, 0.48, scale=2))
    price_entries = _ocr_column(reader, crop, 0.48, 0.64, scale=4, allowlist="0123456789S$")

    rows = []
    for name_entry in name_entries:
        item_name = _clean_item_name(name_entry["text"])
        if not item_name:
            continue

        price_entry = _nearest_by_y(price_entries, name_entry["center_y"])
        sign = _percentage_sign_for_row(crop, name_entry["center_y"])
        percentage_text = _ocr_percentage_for_row(reader, crop, name_entry["center_y"])

        rows.append(
            {
                "Item Name": item_name,
                "Price": _clean_price(price_entry["text"]) if price_entry else None,
                "Percentage": _clean_percentage(percentage_text, sign),
            }
        )

    return _extract_next_price_in(reader, crop), pd.DataFrame(rows)


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
