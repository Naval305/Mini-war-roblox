import os
import time

import cv2
import numpy as np
import pyautogui

from backend.common.market_scanner import MAX_ALERT_PERCENTAGE
from backend.common.market_scanner import MIN_ALERT_PERCENTAGE
from backend.common.market_scanner import notify
from backend.common.market_scanner import process_image

DEFAULT_SCREENSHOT_REGION = (1400, 150, 2600, 800)
REFRESH_INTERVAL_SECONDS = 180
POST_REFRESH_DELAY_SECONDS = 3


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


SCREENSHOT_REGION = _env_region("SCREENSHOT_REGION", DEFAULT_SCREENSHOT_REGION)


def take_screenshot(region=SCREENSHOT_REGION):
    screenshot = pyautogui.screenshot(region=region)
    image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    return trim_black_borders(image)


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


def extract_market_table():
    screenshot = take_screenshot()
    return process_image(screenshot)


def desktop_poll_once():
    started_at = time.monotonic()
    result = extract_market_table()
    elapsed = time.monotonic() - started_at
    return result, elapsed


def _timer_to_seconds(timer_text):
    if not timer_text:
        return REFRESH_INTERVAL_SECONDS

    try:
        minutes, seconds = timer_text.split(":", maxsplit=1)
        return int(minutes) * 60 + int(seconds)
    except ValueError:
        return REFRESH_INTERVAL_SECONDS


def compute_sleep_seconds(next_price_in, elapsed):
    seconds_until_refresh = _timer_to_seconds(next_price_in)
    return max(
        POST_REFRESH_DELAY_SECONDS,
        seconds_until_refresh - elapsed + POST_REFRESH_DELAY_SECONDS,
    )


def main():
    while True:
        try:
            result, elapsed = desktop_poll_once()
        except Exception as exc:
            print(f"Could not extract market table: {exc}")
            time.sleep(10)
            continue

        print(f"\nNext Price In: {result.next_price_in}")
        print(result.items.to_string(index=False))

        if not result.alert_items.empty:
            notify(result.alert_items)
        else:
            print(
                f"No items between {MIN_ALERT_PERCENTAGE}% and "
                f"{MAX_ALERT_PERCENTAGE}%."
            )

        sleep_seconds = compute_sleep_seconds(result.next_price_in, elapsed)
        print(f"Sleeping {sleep_seconds:.1f}s until after the next refresh...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
