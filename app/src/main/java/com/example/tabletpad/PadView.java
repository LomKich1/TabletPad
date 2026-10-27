package com.example.tabletpad;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.MotionEvent;
import android.view.View;

public class PadView extends View {
    private Server server;
    private String status = "Запуск...";
    private final Paint textPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint dotPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final float density;

    private boolean touching = false;
    private boolean gesture = false;
    private long gestureStart;
    private float gestureMoved;
    private float lastGy;
    private float scrollAcc;
    private int lastX, lastY, lastP;
    private boolean dotVisible = false;

    public PadView(Context context) {
        super(context);
        density = getResources().getDisplayMetrics().density;
        textPaint.setColor(Color.GRAY);
        textPaint.setTextSize(18 * density);
        textPaint.setTextAlign(Paint.Align.CENTER);
        dotPaint.setColor(Color.WHITE);
        dotPaint.setStyle(Paint.Style.STROKE);
        dotPaint.setStrokeWidth(2 * density);
        setBackgroundColor(Color.BLACK);
    }

    public void setServer(Server s) {
        server = s;
        if (getWidth() > 0) server.setSize(getWidth(), getHeight());
    }

    public void setStatus(String s) {
        status = s;
        invalidate();
    }

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        if (server != null) server.setSize(w, h);
    }

    @Override
    protected void onDraw(Canvas c) {
        c.drawColor(Color.BLACK);
        c.drawText(status, getWidth() / 2f, getHeight() / 2f, textPaint);
        c.drawText("Кнопка «Назад» - выход", getWidth() / 2f,
                getHeight() / 2f + 30 * density, textPaint);
        if (dotVisible) {
            c.drawCircle(lastX, lastY, 24 * density, dotPaint);
        }
    }

    private int clamp(int v, int lo, int hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    private void sendPoint(String type, MotionEvent e) {
        lastX = clamp((int) e.getX(0), 0, Math.max(0, getWidth() - 1));
        lastY = clamp((int) e.getY(0), 0, Math.max(0, getHeight() - 1));
        lastP = clamp((int) (e.getPressure(0) * 1000), 0, 1000);
        sendLast(type);
    }

    private void sendLast(String type) {
        if (server != null) server.send(type + " " + lastX + " " + lastY + " " + lastP);
    }

    private float avgY(MotionEvent e) {
        return (e.getY(0) + e.getY(1)) / 2f;
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                gesture = false;
                touching = true;
                dotVisible = true;
                sendPoint("D", e);
                invalidate();
                break;

            case MotionEvent.ACTION_POINTER_DOWN:
                if (!gesture && e.getPointerCount() == 2) {
                    if (touching) {
                        sendLast("U");
                        touching = false;
                    }
                    gesture = true;
                    gestureStart = e.getEventTime();
                    gestureMoved = 0;
                    scrollAcc = 0;
                    lastGy = avgY(e);
                }
                break;

            case MotionEvent.ACTION_MOVE:
                if (gesture) {
                    if (e.getPointerCount() >= 2) {
                        float gy = avgY(e);
                        float dy = gy - lastGy;
                        lastGy = gy;
                        gestureMoved += Math.abs(dy);
                        scrollAcc += dy;
                        int send = (int) scrollAcc;
                        if (send != 0) {
                            scrollAcc -= send;
                            if (server != null) server.send("W " + send);
                        }
                    }
                } else if (touching) {
                    sendPoint("M", e);
                    invalidate();
                }
                break;

            case MotionEvent.ACTION_UP:
                if (gesture) {
                    boolean tap = gestureMoved < 20 * density
                            && (e.getEventTime() - gestureStart) < 350;
                    if (tap && server != null) server.send("R");
                    gesture = false;
                } else if (touching) {
                    sendPoint("U", e);
                }
                touching = false;
                dotVisible = false;
                invalidate();
                break;

            case MotionEvent.ACTION_CANCEL:
                if (touching) sendLast("U");
                touching = false;
                gesture = false;
                dotVisible = false;
                invalidate();
                break;
        }
        return true;
    }
}
