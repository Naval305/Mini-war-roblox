import time

from market_scanner import compute_sleep_seconds
from market_scanner import desktop_poll_once
from market_scanner import MAX_ALERT_PERCENTAGE
from market_scanner import MIN_ALERT_PERCENTAGE
from market_scanner import notify


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
