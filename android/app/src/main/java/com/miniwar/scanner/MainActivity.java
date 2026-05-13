package com.miniwar.scanner;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

public class MainActivity extends Activity {
    private static final int REQUEST_MEDIA_PROJECTION = 1001;
    private static final int REQUEST_NOTIFICATIONS = 1002;

    private EditText backendUrlInput;
    private EditText captureIntervalInput;
    private EditText tapIntervalInput;
    private EditText tapXInput;
    private EditText tapYInput;
    private CheckBox useJpegInput;
    private EditText jpegQualityInput;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestNotificationPermissionIfNeeded();
        buildUi();
    }

    private void buildUi() {
        SharedPreferences prefs = ScannerPrefs.get(this);

        ScrollView scrollView = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(36, 36, 36, 36);
        scrollView.addView(root);

        TextView title = new TextView(this);
        title.setText("Mini War Android Scanner");
        title.setTextSize(24);
        title.setGravity(Gravity.CENTER_HORIZONTAL);
        root.addView(title);

        TextView help = new TextView(this);
        help.setText("Start this app, accept screen capture, then switch back to Roblox. Enable the accessibility service once for the anti-AFK tap.");
        help.setPadding(0, 24, 0, 24);
        root.addView(help);

        String backendUrl = ScannerPrefs.getOptionalString(prefs, ScannerPrefs.KEY_BACKEND_URL, BuildConfig.BACKEND_URL);
        backendUrlInput = addInput(root, "Backend upload URL", backendUrl);

        captureIntervalInput = addInput(root, "Capture interval seconds", String.valueOf(ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_CAPTURE_INTERVAL_SECONDS, ScannerPrefs.DEFAULT_CAPTURE_INTERVAL_SECONDS)));
        tapIntervalInput = addInput(root, "Anti-AFK tap interval seconds", String.valueOf(ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_TAP_INTERVAL_SECONDS, ScannerPrefs.DEFAULT_TAP_INTERVAL_SECONDS)));
        tapXInput = addInput(root, "Tap X coordinate", String.valueOf(ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_TAP_X, ScannerPrefs.DEFAULT_TAP_X)));
        tapYInput = addInput(root, "Tap Y coordinate", String.valueOf(ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_TAP_Y, ScannerPrefs.DEFAULT_TAP_Y)));

        useJpegInput = new CheckBox(this);
        useJpegInput.setText("Compress upload as JPEG instead of PNG");
        useJpegInput.setChecked(prefs.getBoolean(ScannerPrefs.KEY_USE_JPEG, false));
        root.addView(useJpegInput);

        jpegQualityInput = addInput(root, "JPEG quality if enabled", String.valueOf(ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_JPEG_QUALITY, ScannerPrefs.DEFAULT_JPEG_QUALITY)));

        Button saveButton = new Button(this);
        saveButton.setText("Save Settings");
        saveButton.setOnClickListener(view -> saveSettings());
        root.addView(saveButton);

        Button startButton = new Button(this);
        startButton.setText("Start Screen Capture");
        startButton.setOnClickListener(view -> startCaptureFlow());
        root.addView(startButton);

        Button stopButton = new Button(this);
        stopButton.setText("Stop Screen Capture");
        stopButton.setOnClickListener(view -> stopService(new Intent(this, ScreenCaptureService.class)));
        root.addView(stopButton);

        Button accessibilityButton = new Button(this);
        accessibilityButton.setText("Open Accessibility Settings");
        accessibilityButton.setOnClickListener(view -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        root.addView(accessibilityButton);

        Button appSettingsButton = new Button(this);
        appSettingsButton.setText("Open App Settings");
        appSettingsButton.setOnClickListener(view -> {
            Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName()));
            startActivity(intent);
        });
        root.addView(appSettingsButton);

        setContentView(scrollView);
    }

    private EditText addInput(LinearLayout root, String label, String value) {
        TextView textView = new TextView(this);
        textView.setText(label);
        textView.setPadding(0, 18, 0, 0);
        root.addView(textView);

        EditText editText = new EditText(this);
        editText.setSingleLine(true);
        editText.setText(value);
        root.addView(editText);
        return editText;
    }

    private void saveSettings() {
        SharedPreferences.Editor editor = ScannerPrefs.get(this).edit();
        ScannerPrefs.putOptionalString(editor, ScannerPrefs.KEY_BACKEND_URL, backendUrlInput.getText().toString());

        editor
            .putString(ScannerPrefs.KEY_CAPTURE_INTERVAL_SECONDS, captureIntervalInput.getText().toString().trim())
            .putString(ScannerPrefs.KEY_TAP_INTERVAL_SECONDS, tapIntervalInput.getText().toString().trim())
            .putString(ScannerPrefs.KEY_TAP_X, tapXInput.getText().toString().trim())
            .putString(ScannerPrefs.KEY_TAP_Y, tapYInput.getText().toString().trim())
            .putBoolean(ScannerPrefs.KEY_USE_JPEG, useJpegInput.isChecked())
            .putString(ScannerPrefs.KEY_JPEG_QUALITY, jpegQualityInput.getText().toString().trim())
            .apply();

        View currentFocus = getCurrentFocus();
        if (currentFocus != null) {
            InputMethodManager imm = (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
            imm.hideSoftInputFromWindow(currentFocus.getWindowToken(), 0);
        }
        Toast.makeText(this, "Settings saved", Toast.LENGTH_SHORT).show();
    }

    private void startCaptureFlow() {
        saveSettings();
        MediaProjectionManager manager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        startActivityForResult(manager.createScreenCaptureIntent(), REQUEST_MEDIA_PROJECTION);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_MEDIA_PROJECTION) {
            return;
        }

        if (resultCode != RESULT_OK || data == null) {
            Toast.makeText(this, "Screen capture permission was not granted", Toast.LENGTH_LONG).show();
            return;
        }

        Intent serviceIntent = new Intent(this, ScreenCaptureService.class);
        serviceIntent.putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, resultCode);
        serviceIntent.putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, data);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
        Toast.makeText(this, "Capture service ready. Use notification buttons to start/stop.", Toast.LENGTH_LONG).show();
    }

    private void requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[] { Manifest.permission.POST_NOTIFICATIONS }, REQUEST_NOTIFICATIONS);
        }
    }
}
