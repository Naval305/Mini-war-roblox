package com.miniwar.scanner;

import android.content.Context;
import android.content.SharedPreferences;

final class ScannerPrefs {
    static final String PREFS_NAME = "mini_war_scanner";
    static final String KEY_BACKEND_URL = "backend_url";
    static final String KEY_CAPTURE_INTERVAL_SECONDS = "capture_interval_seconds";
    static final String KEY_TAP_INTERVAL_SECONDS = "tap_interval_seconds";
    static final String KEY_TAP_X = "tap_x";
    static final String KEY_TAP_Y = "tap_y";
    static final String KEY_USE_JPEG = "use_jpeg";
    static final String KEY_JPEG_QUALITY = "jpeg_quality";

    static final int DEFAULT_CAPTURE_INTERVAL_SECONDS = 180;
    static final int DEFAULT_TAP_INTERVAL_SECONDS = 14 * 60;
    static final int DEFAULT_TAP_X = 100;
    static final int DEFAULT_TAP_Y = 100;
    static final int DEFAULT_JPEG_QUALITY = 85;

    private ScannerPrefs() {}

    static SharedPreferences get(Context context) {
        return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    static String getOptionalString(SharedPreferences prefs, String key, String defaultValue) {
        String value = prefs.getString(key, "");
        if (value != null && !value.trim().isEmpty()) {
            return value.trim();
        }
        return defaultValue == null ? "" : defaultValue.trim();
    }

    static void putOptionalString(SharedPreferences.Editor editor, String key, String value) {
        String trimmedValue = value == null ? "" : value.trim();
        if (trimmedValue.isEmpty()) {
            editor.remove(key);
        } else {
            editor.putString(key, trimmedValue);
        }
    }

    static int getPositiveInt(SharedPreferences prefs, String key, int defaultValue) {
        String value = prefs.getString(key, String.valueOf(defaultValue));
        try {
            int parsed = Integer.parseInt(value.trim());
            return parsed > 0 ? parsed : defaultValue;
        } catch (NumberFormatException exc) {
            return defaultValue;
        }
    }
}
