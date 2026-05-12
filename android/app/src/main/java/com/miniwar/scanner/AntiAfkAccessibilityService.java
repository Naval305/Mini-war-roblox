package com.miniwar.scanner;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.SharedPreferences;
import android.graphics.Path;
import android.os.Handler;
import android.os.Looper;
import android.view.accessibility.AccessibilityEvent;

public class AntiAfkAccessibilityService extends AccessibilityService {
    private static final String ROBLOX_PACKAGE_NAME = "com.roblox.client";

    private final Handler handler = new Handler(Looper.getMainLooper());
    private String currentPackageName = "";

    private final Runnable tapRunnable = new Runnable() {
        @Override
        public void run() {
            performTap();
            scheduleNextTap();
        }
    };

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        handler.removeCallbacks(tapRunnable);
        scheduleNextTap();
    }

    private void performTap() {
        if (!ROBLOX_PACKAGE_NAME.equals(currentPackageName)) {
            return;
        }

        SharedPreferences prefs = ScannerPrefs.get(this);
        int x = ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_TAP_X, ScannerPrefs.DEFAULT_TAP_X);
        int y = ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_TAP_Y, ScannerPrefs.DEFAULT_TAP_Y);

        Path path = new Path();
        path.moveTo(x, y);
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0, 80);
        GestureDescription gesture = new GestureDescription.Builder().addStroke(stroke).build();
        dispatchGesture(gesture, null, null);
    }

    private void scheduleNextTap() {
        int intervalSeconds = ScannerPrefs.getPositiveInt(
            ScannerPrefs.get(this),
            ScannerPrefs.KEY_TAP_INTERVAL_SECONDS,
            ScannerPrefs.DEFAULT_TAP_INTERVAL_SECONDS
        );
        handler.postDelayed(tapRunnable, intervalSeconds * 1000L);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        CharSequence packageName = event.getPackageName();
        currentPackageName = packageName == null ? "" : packageName.toString();
    }

    @Override
    public void onInterrupt() {
        handler.removeCallbacks(tapRunnable);
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(tapRunnable);
        super.onDestroy();
    }
}
