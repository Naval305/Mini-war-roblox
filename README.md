# Mini War Market Alert

Continuously screenshots the Roblox market board, crops the board, extracts market data with Groq, and sends Discord alerts for configured items in the configured percentage range.

## Home PC Setup

1. Install Python 3.12+.

2. Install `uv`:

```powershell
pip install uv
```

3. Copy this project folder to the home PC.

4. In the project folder, install dependencies:

```powershell
uv sync --extra desktop
```

5. Create `.env` from `.env.example`:

```powershell
copy .env.example .env
```

Then fill in:

```env
GROQ_API_KEY=your_groq_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook
```

6. Open Roblox and keep the market board visible.

7. Run:

```powershell
uv run --extra desktop python -m backend.desktop.main
```

Or double-click:

```text
run.bat
```

This desktop mode still works exactly as the original flow:

```text
PC screenshot -> crop -> Groq -> filter -> Discord alert
```

## Calibration

If the script cannot find the board on the home PC, adjust this value in `.env`:

```env
SCREENSHOT_REGION=1400,150,2600,800
```

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

## Android Backend Mode

The repo can also run as a backend for the Android tablet app.

In this mode:

```text
Android screenshot upload -> backend crop -> Groq -> filter -> Discord alert
```

### Start The Backend

1. Install dependencies:

```powershell
uv sync
```

2. Run the API server:

```powershell
uv run uvicorn backend.api.app:app --host 0.0.0.0 --port 8000
```

3. Point the Android app backend URL to:

```text
http://YOUR_PC_IP:8000/scan
```

If the tablet and PC are on the same Wi-Fi, replace `YOUR_PC_IP` with the PC's local network IP.

### Deploy To Render

This backend is stateless and can run on a Render Free Web Service without keeping your laptop on. Free services can spin down after inactivity, so the first upload after a quiet period may be slower while Render wakes the service. While the Android scanner is active, the default 180-second capture interval should usually keep it warm.

#### Option A: Blueprint

1. Push this repo to GitHub, GitLab, or Bitbucket.
2. In Render, create a new **Blueprint** from the repo.
3. Render will read `render.yaml` and create the `mini-war-scanner-api` web service.
4. Fill in these environment variables when Render prompts for them:

```env
GROQ_API_KEY=your_groq_api_key
DISCORD_WEBHOOK_URL=your_discord_webhook
```

Optional env vars:

```env
ITEMS=Diamonds,Uran Ore,Stable Uran,Data Cube
MIN_ALERT_PERCENTAGE=27
MAX_ALERT_PERCENTAGE=50
GROQ_MODEL=groq-3-flash-preview
```

#### Option B: Manual Web Service

1. In Render, create a new **Web Service** from the repo.
2. Choose **Docker** as the runtime.
3. Select the **Free** instance type.
4. Set the health check path to:

```text
/health
```

5. Add the same environment variables listed above.

After deployment, copy the Render service URL and set the Android backend upload URL to:

```text
https://YOUR_RENDER_SERVICE.onrender.com/scan
```

### API Contract

Endpoint:

```http
POST /scan
Content-Type: multipart/form-data
```

Multipart field:

```text
image = market.png or market.jpg
```

Success response:

```json
{
  "ok": true,
  "next_price_in": "02:51",
  "items": [],
  "alert_items": []
}
```

## Android Tablet Capture App

This repo also includes a native Android client under `android/app` for running the Roblox farming screen on an Android tablet while a backend does the market parsing.

The Android app currently does two lightweight jobs:

1. Captures the full tablet screen every 180 seconds by default.
2. Performs one configured accessibility tap every 14 minutes by default for anti-AFK while Roblox is the foreground app.

The app does **not** crop or parse the image on the tablet. It uploads the screenshot to a backend URL as `multipart/form-data` with a single file field named `image`. Cropping, Groq extraction, item filtering, and Discord alerts should happen on the backend.

### Android Requirements

- Android 10+.
- Permission to install a custom APK.
- Manual screen-capture approval when starting the scanner.
- Accessibility service enabled for the anti-AFK tap.

### Build APK

From the repo root:

```bash
gradle :android:app:assembleDebug
```

The debug APK will be created at:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Install that APK on the tablet.

### Tablet Setup

1. Open **Mini War Scanner**.
2. Fill in the backend upload URL, for example:

```text
https://your-render-service.onrender.com/scan
```

3. Keep **Capture interval seconds** at `180` unless the market refresh timing changes.
4. Set **Tap X coordinate** and **Tap Y coordinate** to a safe Roblox screen position. The anti-AFK service only taps while the official Roblox package, `com.roblox.client`, is foregrounded.
5. Keep **Anti-AFK tap interval seconds** at `840` for one tap every 14 minutes.
6. Leave JPEG compression disabled for PNG uploads, or enable JPEG if the backend/network needs smaller images.
7. Tap **Save Settings**.
8. Tap **Open Accessibility Settings** and enable **Mini War Anti-AFK Tapper**.
9. Return to the app and tap **Start Screen Capture**.
10. Accept Android's screen-capture prompt.
11. Switch back to Roblox and leave the market visible.

### Backend Upload Contract

The Android app sends:

```http
POST /scan
Content-Type: multipart/form-data
User-Agent: MiniWarAndroidScanner/0.1.0
```

Multipart fields:

```text
image = market.png or market.jpg
```

A successful backend response should return any `2xx` HTTP status. Non-`2xx` statuses are shown in the scanner notification.
