package com.miniwar.scanner;

import android.app.PendingIntent;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;
import android.util.Log;

public class ScreenCaptureService extends Service {
    public static final String ACTION_START = "com.miniwar.scanner.ACTION_START";
    public static final String ACTION_STOP = "com.miniwar.scanner.ACTION_STOP";

    static final String EXTRA_RESULT_CODE = "result_code";
    static final String EXTRA_RESULT_DATA = "result_data";

    private static final String CHANNEL_ID = "screen_capture";
    private static final int NOTIFICATION_ID = 20;

    private HandlerThread workerThread;
    private Handler workerHandler;
    private MediaProjection mediaProjection;
    private final AtomicBoolean captureInProgress = new AtomicBoolean(false);
    private final AtomicBoolean isCaptureEnabled = new AtomicBoolean(false);

    private final Runnable captureRunnable = new Runnable() {
        @Override
        public void run() {
            if (isCaptureEnabled.get()) {
                captureOnce();
            }
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        workerThread = new HandlerThread("MiniWarCaptureWorker");
        workerThread.start();
        workerHandler = new Handler(workerThread.getLooper());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) {
            stopSelf();
            return START_NOT_STICKY;
        }

        String action = intent.getAction();
        if (ACTION_START.equals(action)) {
            startCaptureWithDelay();
            return START_STICKY;
        } else if (ACTION_STOP.equals(action)) {
            stopCapture();
            return START_STICKY;
        }

        startForeground(NOTIFICATION_ID, buildNotification("Ready to capture"));

        if (!intent.hasExtra(EXTRA_RESULT_CODE) || !intent.hasExtra(EXTRA_RESULT_DATA)) {
            stopSelf();
            return START_NOT_STICKY;
        }

        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
        Intent resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        MediaProjectionManager manager = (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        mediaProjection = manager.getMediaProjection(resultCode, resultData);
        if (mediaProjection == null) {
            stopSelf();
            return START_NOT_STICKY;
        }

        mediaProjection.registerCallback(new MediaProjection.Callback() {
            @Override
            public void onStop() {
                stopSelf();
            }
        }, workerHandler);

        return START_STICKY;
    }

    private void startCaptureWithDelay() {
        isCaptureEnabled.set(true);
        updateNotification("Starting in 10 seconds...");
        workerHandler.removeCallbacks(captureRunnable);
        workerHandler.postDelayed(captureRunnable, 10000L);
    }

    private void stopCapture() {
        isCaptureEnabled.set(false);
        workerHandler.removeCallbacks(captureRunnable);
        updateNotification("Capture stopped. Ready.");
    }

    private void captureOnce() {
        if (mediaProjection == null || !captureInProgress.compareAndSet(false, true)) {
            scheduleNextCapture();
            return;
        }

        updateNotification("Capturing screenshot");

        DisplayMetrics metrics = new DisplayMetrics();
        WindowManager windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        windowManager.getDefaultDisplay().getRealMetrics(metrics);
        int width = metrics.widthPixels;
        int height = metrics.heightPixels;
        int densityDpi = metrics.densityDpi;

        ImageReader reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        final VirtualDisplay[] virtualDisplay = new VirtualDisplay[1];
        AtomicBoolean finished = new AtomicBoolean(false);

        Runnable timeoutRunnable = () -> {
            if (finished.compareAndSet(false, true)) {
                updateNotification("Capture timed out; waiting for next interval");
                finishCapture(reader, virtualDisplay[0]);
            }
        };

        reader.setOnImageAvailableListener(imageReader -> {
            if (!finished.compareAndSet(false, true)) {
                return;
            }
            workerHandler.removeCallbacks(timeoutRunnable);

            Image image = null;
            try {
                image = imageReader.acquireLatestImage();
                if (image != null) {
                    Bitmap bitmap = imageToBitmap(image, width, height);
                    uploadBitmap(bitmap);
                    bitmap.recycle();
                }
            } catch (Exception exc) {
                updateNotification("Capture failed: " + exc.getClass().getSimpleName());
            } finally {
                if (image != null) {
                    image.close();
                }
                finishCapture(imageReader, virtualDisplay[0]);
            }
        }, workerHandler);

        virtualDisplay[0] = mediaProjection.createVirtualDisplay(
            "MiniWarScreenCapture",
            width,
            height,
            densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            reader.getSurface(),
            null,
            workerHandler
        );
        workerHandler.postDelayed(timeoutRunnable, 10000L);
    }

    private void finishCapture(ImageReader imageReader, VirtualDisplay virtualDisplay) {
        if (virtualDisplay != null) {
            virtualDisplay.release();
        }
        imageReader.close();
        captureInProgress.set(false);
        scheduleNextCapture();
    }

    private Bitmap imageToBitmap(Image image, int width, int height) {
        Image.Plane plane = image.getPlanes()[0];
        ByteBuffer buffer = plane.getBuffer();
        int pixelStride = plane.getPixelStride();
        int rowStride = plane.getRowStride();
        int rowPadding = rowStride - pixelStride * width;
        Bitmap paddedBitmap = Bitmap.createBitmap(width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888);
        paddedBitmap.copyPixelsFromBuffer(buffer);
        Bitmap croppedBitmap = Bitmap.createBitmap(paddedBitmap, 0, 0, width, height);
        paddedBitmap.recycle();
        return croppedBitmap;
    }

    private void uploadBitmap(Bitmap bitmap) throws IOException {
        SharedPreferences prefs = ScannerPrefs.get(this);
        String backendUrl = BuildConfig.BACKEND_URL.trim();
        boolean useJpeg = prefs.getBoolean(ScannerPrefs.KEY_USE_JPEG, false);
        int jpegQuality = Math.min(100, Math.max(1, ScannerPrefs.getPositiveInt(prefs, ScannerPrefs.KEY_JPEG_QUALITY, ScannerPrefs.DEFAULT_JPEG_QUALITY)));

        if (backendUrl.isEmpty()) {
            updateNotification("Captured screenshot; backend URL is empty");
            return;
        }

        Bitmap.CompressFormat format = useJpeg ? Bitmap.CompressFormat.JPEG : Bitmap.CompressFormat.PNG;
        String extension = useJpeg ? "jpg" : "png";
        String mimeType = useJpeg ? "image/jpeg" : "image/png";
        ByteArrayOutputStream outputStream = new ByteArrayOutputStream();
        bitmap.compress(format, useJpeg ? jpegQuality : 100, outputStream);
        byte[] imageBytes = outputStream.toByteArray();

        String boundary = "MiniWarBoundary" + System.currentTimeMillis();
        HttpURLConnection connection = (HttpURLConnection) new URL(backendUrl).openConnection();
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(30000);
        connection.setDoOutput(true);
        connection.setRequestMethod("POST");
        connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
        connection.setRequestProperty("User-Agent", "MiniWarAndroidScanner/0.1.0");

        try (DataOutputStream request = new DataOutputStream(new BufferedOutputStream(connection.getOutputStream()))) {
            request.writeBytes("--" + boundary + "\r\n");
            request.writeBytes("Content-Disposition: form-data; name=\"image\"; filename=\"market." + extension + "\"\r\n");
            request.writeBytes("Content-Type: " + mimeType + "\r\n\r\n");
            request.write(imageBytes);
            request.writeBytes("\r\n--" + boundary + "--\r\n");
        }

        int statusCode = connection.getResponseCode();
        if (statusCode >= 200 && statusCode < 300) {
            updateNotification(String.format(Locale.US, "Uploaded screenshot (%d KB)", Math.max(1, imageBytes.length / 1024)));
        } else {
            updateNotification("Upload failed with HTTP " + statusCode);
        }
        connection.disconnect();
    }

    private void scheduleNextCapture() {
        if (workerHandler == null || !isCaptureEnabled.get()) {
            return;
        }
        int intervalSeconds = ScannerPrefs.getPositiveInt(
            ScannerPrefs.get(this),
            ScannerPrefs.KEY_CAPTURE_INTERVAL_SECONDS,
            ScannerPrefs.DEFAULT_CAPTURE_INTERVAL_SECONDS
        );
        workerHandler.postDelayed(captureRunnable, intervalSeconds * 1000L);
    }

    private Notification buildNotification(String text) {
        Intent startIntent = new Intent(this, ScreenCaptureService.class);
        startIntent.setAction(ACTION_START);
        int flags = PendingIntent.FLAG_IMMUTABLE;
        PendingIntent startPendingIntent = PendingIntent.getService(this, 1, startIntent, flags);

        Intent stopIntent = new Intent(this, ScreenCaptureService.class);
        stopIntent.setAction(ACTION_STOP);
        PendingIntent stopPendingIntent = PendingIntent.getService(this, 2, stopIntent, flags);

        Notification.Builder builder = new Notification.Builder(this, CHANNEL_ID);
        return builder
            .setContentTitle("Mini War Scanner")
            .setContentText(text)
            .setSmallIcon(com.miniwar.scanner.R.drawable.ic_notification)
            .setOngoing(true)
            .addAction(new Notification.Action.Builder(null, "Start", startPendingIntent).build())
            .addAction(new Notification.Action.Builder(null, "Stop", stopPendingIntent).build())
            .build();
    }

    private void updateNotification(String text) {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.notify(NOTIFICATION_ID, buildNotification(text));
    }

    private void createNotificationChannel() {
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "Screen Capture",
            NotificationManager.IMPORTANCE_LOW
        );
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(channel);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        if (workerHandler != null) {
            workerHandler.removeCallbacksAndMessages(null);
        }
        if (mediaProjection != null) {
            MediaProjection projection = mediaProjection;
            mediaProjection = null;
            projection.stop();
        }
        if (workerThread != null) {
            workerThread.quitSafely();
        }
        super.onDestroy();
    }
}
