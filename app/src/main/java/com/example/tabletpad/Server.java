package com.example.tabletpad;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * TCP-сервер на планшете. ПК подключается к порту 8765
 * (через "adb forward" по USB или напрямую по Wi-Fi).
 * Протокол: текстовые строки.
 *   H w h        - размер экрана планшета (при подключении)
 *   D x y p      - касание началось (p = нажим 0..1000)
 *   M x y p      - палец движется
 *   U x y p      - палец поднят
 *   W dy         - прокрутка двумя пальцами
 *   R            - правый клик (тап двумя пальцами)
 *   P            - keep-alive
 */
public class Server implements Runnable {
    public interface Listener {
        void onState(String state);
    }

    public static final int PORT = 8765;

    private final LinkedBlockingQueue<String> queue = new LinkedBlockingQueue<String>();
    private final Listener listener;
    private volatile boolean running = true;
    private volatile boolean connected = false;
    private volatile int width = 0;
    private volatile int height = 0;
    private ServerSocket serverSocket;

    public Server(Listener listener) {
        this.listener = listener;
    }

    public void start() {
        Thread t = new Thread(this, "pad-server");
        t.setDaemon(true);
        t.start();
    }

    public void stop() {
        running = false;
        try {
            if (serverSocket != null) serverSocket.close();
        } catch (IOException ignored) {
        }
    }

    public void setSize(int w, int h) {
        width = w;
        height = h;
        if (connected) send("H " + w + " " + h);
    }

    public void send(String line) {
        if (connected) queue.offer(line);
    }

    @Override
    public void run() {
        try {
            serverSocket = new ServerSocket();
            serverSocket.setReuseAddress(true);
            serverSocket.bind(new InetSocketAddress(PORT));
        } catch (IOException e) {
            listener.onState("Не открыть порт " + PORT + ": " + e.getMessage());
            return;
        }
        while (running) {
            listener.onState("Ожидание ПК...");
            Socket s = null;
            try {
                s = serverSocket.accept();
                s.setTcpNoDelay(true);
                queue.clear();
                OutputStream out = s.getOutputStream();
                out.write(("H " + width + " " + height + "\n").getBytes("UTF-8"));
                out.flush();
                connected = true;
                listener.onState("ПК подключен");
                List<String> batch = new ArrayList<String>();
                while (running) {
                    String first = queue.poll(1, TimeUnit.SECONDS);
                    StringBuilder sb = new StringBuilder();
                    if (first == null) {
                        sb.append("P\n");
                    } else {
                        sb.append(first).append('\n');
                        batch.clear();
                        queue.drainTo(batch);
                        for (String l : batch) sb.append(l).append('\n');
                    }
                    out.write(sb.toString().getBytes("UTF-8"));
                    out.flush();
                }
            } catch (Exception e) {
                if (running) {
                    try {
                        Thread.sleep(200);
                    } catch (InterruptedException ignored) {
                    }
                }
            } finally {
                connected = false;
                if (s != null) {
                    try {
                        s.close();
                    } catch (IOException ignored) {
                    }
                }
            }
        }
    }
}
