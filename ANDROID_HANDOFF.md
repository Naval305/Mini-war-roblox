# Android Handoff Summary

## Project Goal

- Android tablet runs Roblox.
- App captures the full tablet screen every 3 minutes.
- App performs one anti-AFK tap every 14 minutes.
- Backend handles cropping, market parsing, alert filtering, Discord alerts, and any final image compression decision.

## What Is Already Done

- Native Android app exists under `android/app`.
- Package/application id is `com.miniwar.scanner`.
- Android SDK settings:
  - `minSdk 29`
  - `targetSdk 29`
  - `compileSdk 35`
- Foreground MediaProjection service exists for screen capture.
- AccessibilityService exists for the anti-AFK tap.
- Defaults exist in `ScannerPrefs.java`:
  - Capture interval: `180` seconds
  - Tap interval: `840` seconds
  - Default tap coordinate: `100,100`
  - JPEG quality default: `85`
- App UI supports:
  - Backend upload URL
  - Capture interval
  - Anti-AFK tap interval
  - Tap X/Y coordinates
  - Optional JPEG upload
  - Save settings
  - Open accessibility settings
  - Start/stop screen capture
- Upload contract is multipart `POST` with a single file field named `image`.

## What Is Needed Next

- Add or verify Gradle wrapper files, `gradlew` and `gradlew.bat`, so the user does not need a global Gradle install.
- Build the debug APK with Android Studio or Gradle.
- Test installing the debug APK on the Android tablet.
- Confirm the MediaProjection screen-capture permission flow works.
- Confirm the AccessibilityService appears in Android settings and can be enabled.
- Confirm the anti-AFK tap only happens while the official Roblox package, `com.roblox.client`, is foregrounded.
- Confirm screenshots upload successfully to a backend endpoint.
- Implement or adapt the backend endpoint to receive Android uploads and run the existing crop, Gemini extraction, item filtering, and Discord alert pipeline.
- Decide later whether JPEG compression should stay optional, become the default, or be controlled by backend/network needs.

## Local Setup Notes

Required installed tools:

- Android Studio
- Android SDK Platform 35
- JDK 17, usually bundled with Android Studio
- Android tablet with Developer Options and USB debugging enabled

Roblox must be installed normally on the tablet.

The user is unfamiliar with Android development, so keep future build/run steps explicit and beginner friendly.

## Build Commands

Preferred command after adding the Gradle wrapper:

```powershell
.\gradlew.bat :android:app:assembleDebug
```

Current command if Gradle is installed globally:

```powershell
gradle :android:app:assembleDebug
```

Expected debug APK path:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

## Backend Contract

Android sends:

```http
POST /scan
Content-Type: multipart/form-data
User-Agent: MiniWarAndroidScanner/0.1.0
```

Multipart field:

```text
image = market.png or market.jpg
```

Any `2xx` response should count as success.

## Known Concern

- A previous build attempt in the prior environment failed because the Android Gradle plugin could not be resolved from the configured repositories.
- With Android Studio installed and internet access, first check Gradle sync/build again before changing code.

## Test Plan For This Handoff File

- Run `git diff --check`.
- Open `ANDROID_HANDOFF.md` and verify it is plain Markdown with no secrets.
- Confirm it does not duplicate private `.env` values.
- Confirm it mentions both Android app state and remaining backend work.

## Assumptions

- This summary file should be committed/tracked in the repo.
- File name is `ANDROID_HANDOFF.md` at repo root for easy discovery.
- No implementation changes are included beyond adding this handoff summary file.
