# Mini War Market Alert

Continuously screenshots the Roblox market board, crops the board, extracts market data with Gemini, and sends Discord alerts for configured items in the configured percentage range.

## Home PC Setup

1. Install Python 3.12+.

2. Install `uv`:

```powershell
pip install uv
```

3. Copy this project folder to the home PC.

4. In the project folder, install dependencies:

```powershell
uv sync
```

5. Create `.env` from `.env.example`:

```powershell
copy .env.example .env
```

Then fill in:

```env
GEMINI_API_KEY=your_gemini_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook
```

6. Open Roblox and keep the market board visible.

7. Run:

```powershell
uv run python main.py
```

Or double-click:

```text
run.bat
```

## Calibration

If the script cannot find the board on the home PC, adjust this value in `.env`:

```env
SCREENSHOT_REGION=1400,150,2600,800
```

After a run, inspect:

```text
latest_screenshot.png
latest_crop.png
```

`latest_screenshot.png` should include the game window and board. `latest_crop.png` should contain the cropped market board/table.

## Alerts

Only these items are eligible for alerts. Configure them in `.env`:

```env
ITEMS=Diamonds,Uran Ore,Stable Uran,Data Cube
```

Alert percentage range:

```env
MIN_ALERT_PERCENTAGE=27
MAX_ALERT_PERCENTAGE=50
```

`.env` is ignored by git. Keep API keys and Discord webhooks private.
