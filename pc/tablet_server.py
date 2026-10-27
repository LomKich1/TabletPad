#!/usr/bin/env python3
"""
TabletPad - серверная часть для Windows 10/11 (только стандартная библиотека).

Режимы (--mode):
  mouse    - абсолютное позиционирование, касание = левая кнопка мыши
  pen      - абсолютное позиционирование, виртуальное перо Windows Ink с нажимом
  touchpad - относительное движение, тап = клик

Примеры:
  python tablet_server.py --mode pen
  python tablet_server.py --mode mouse --area 0,0,1920,1080
  python tablet_server.py --mode touchpad --host 192.168.1.50   (по Wi-Fi, без adb)
"""
import argparse
import ctypes
import socket
import subprocess
import sys
import time
from ctypes import wintypes

PORT = 8765

user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

# ---------- мышь ----------
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800

user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                               wintypes.DWORD, ctypes.c_size_t]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]


def mouse_event(flags, data=0):
    user32.mouse_event(flags, 0, 0, data & 0xFFFFFFFF, 0)


# ---------- перо (Windows 10+, без драйверов) ----------
PT_PEN = 3
POINTER_FEEDBACK_DEFAULT = 1
PF_NEW = 0x00000001
PF_INRANGE = 0x00000002
PF_INCONTACT = 0x00000004
PF_FIRSTBUTTON = 0x00000010
PF_DOWN = 0x00010000
PF_UPDATE = 0x00020000
PF_UP = 0x00040000
PEN_MASK_PRESSURE = 0x00000001


class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD),
        ("pointerId", wintypes.UINT),
        ("frameId", wintypes.UINT),
        ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE),
        ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", wintypes.POINT),
        ("ptHimetricLocation", wintypes.POINT),
        ("ptPixelLocationRaw", wintypes.POINT),
        ("ptHimetricLocationRaw", wintypes.POINT),
        ("dwTime", wintypes.DWORD),
        ("historyCount", wintypes.UINT),
        ("InputData", wintypes.INT),
        ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", ctypes.c_uint64),
        ("ButtonChangeType", wintypes.DWORD),
    ]


class POINTER_PEN_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("penFlags", wintypes.DWORD),
        ("penMask", wintypes.DWORD),
        ("pressure", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("tiltX", wintypes.INT),
        ("tiltY", wintypes.INT),
    ]


class POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("touchFlags", wintypes.DWORD),
        ("touchMask", wintypes.DWORD),
        ("rcContact", wintypes.RECT),
        ("rcContactRaw", wintypes.RECT),
        ("orientation", wintypes.UINT),
        ("pressure", wintypes.UINT),
    ]


class _PTI_UNION(ctypes.Union):
    _fields_ = [("penInfo", POINTER_PEN_INFO), ("touchInfo", POINTER_TOUCH_INFO)]


class POINTER_TYPE_INFO(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _PTI_UNION)]


class PenDevice:
    def __init__(self):
        create = user32.CreateSyntheticPointerDevice
        create.restype = wintypes.HANDLE
        create.argtypes = [wintypes.DWORD, wintypes.ULONG, wintypes.DWORD]
        self.dev = create(PT_PEN, 1, POINTER_FEEDBACK_DEFAULT)
        if not self.dev:
            raise OSError("CreateSyntheticPointerDevice не удалось: %d" % ctypes.GetLastError())
        self.inject = user32.InjectSyntheticPointerInput
        self.inject.restype = wintypes.BOOL
        self.inject.argtypes = [wintypes.HANDLE, ctypes.POINTER(POINTER_TYPE_INFO), wintypes.UINT]
        self.warned = False

    def send(self, x, y, flags, pressure):
        info = POINTER_TYPE_INFO()
        info.type = PT_PEN
        pen = info.u.penInfo
        pen.pointerInfo.pointerType = PT_PEN
        pen.pointerInfo.pointerId = 0
        pen.pointerInfo.pointerFlags = flags
        pen.pointerInfo.ptPixelLocation.x = x
        pen.pointerInfo.ptPixelLocation.y = y
        pen.penMask = PEN_MASK_PRESSURE
        pen.pressure = pressure
        if not self.inject(self.dev, ctypes.byref(info), 1) and not self.warned:
            self.warned = True
            print("! InjectSyntheticPointerInput ошибка %d" % ctypes.GetLastError())


# ---------- логика ----------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def parse_area(s):
    gm = user32.GetSystemMetrics
    if s == "primary":
        return 0, 0, gm(0), gm(1)
    if s == "all":
        return gm(76), gm(77), gm(78), gm(79)
    x, y, w, h = (int(v) for v in s.split(","))
    return x, y, w, h


class Injector:
    def __init__(self, args):
        self.args = args
        self.mode = args.mode
        self.area = parse_area(args.area)
        self.tw = self.th = 0
        self.down = False
        self.last = (0, 0)
        self.pen = None
        if self.mode == "pen":
            try:
                self.pen = PenDevice()
            except (OSError, AttributeError) as e:
                print("! Режим pen недоступен (%s), переключаюсь на mouse" % e)
                self.mode = "mouse"
        self.rem_x = self.rem_y = 0.0
        self.wheel_acc = 0.0
        self.t_start = 0.0
        self.t_moved = 0
        self.t_last = (0, 0)
        print("Режим: %s, область: %s" % (self.mode, self.area))

    # --- координаты ---
    def map_abs(self, x, y):
        rx, ry, rw, rh = self.area
        nx = x / max(1, self.tw - 1)
        ny = y / max(1, self.th - 1)
        if self.args.keep_aspect and self.tw > 0 and self.th > 0:
            ta = self.tw / self.th
            sa = rw / rh
            if ta > sa:
                f = sa / ta
                nx = (nx - (1 - f) / 2) / f
            else:
                f = ta / sa
                ny = (ny - (1 - f) / 2) / f
        nx = clamp(nx, 0.0, 1.0)
        ny = clamp(ny, 0.0, 1.0)
        return rx + int(nx * (rw - 1)), ry + int(ny * (rh - 1))

    # --- обработка строки ---
    def handle_line(self, line):
        parts = line.split()
        if not parts:
            return
        c = parts[0]
        try:
            if c == "H":
                self.tw, self.th = int(parts[1]), int(parts[2])
                print("Планшет: %dx%d" % (self.tw, self.th))
            elif c in ("D", "M", "U"):
                self.pointer(c, int(parts[1]), int(parts[2]), int(parts[3]))
            elif c == "W":
                self.scroll(int(parts[1]))
            elif c == "R":
                mouse_event(MOUSEEVENTF_RIGHTDOWN)
                mouse_event(MOUSEEVENTF_RIGHTUP)
        except (IndexError, ValueError):
            pass

    def pointer(self, c, x, y, p):
        if self.mode == "touchpad":
            self.touchpad(c, x, y)
            return
        px, py = self.map_abs(x, y)
        self.last = (px, py)
        if self.mode == "pen":
            self.pen_event(c, px, py, p)
        else:
            user32.SetCursorPos(px, py)
            if c == "D":
                mouse_event(MOUSEEVENTF_LEFTDOWN)
                self.down = True
            elif c == "U" and self.down:
                mouse_event(MOUSEEVENTF_LEFTUP)
                self.down = False

    def pen_event(self, c, px, py, p):
        pr = self.args.pressure_fixed or int(p * 1.024)
        pr = clamp(pr, 1, 1024)
        if c == "D":
            self.pen.send(px, py, PF_NEW | PF_INRANGE | PF_INCONTACT | PF_FIRSTBUTTON | PF_DOWN, pr)
            self.down = True
        elif c == "M" and self.down:
            self.pen.send(px, py, PF_INRANGE | PF_INCONTACT | PF_FIRSTBUTTON | PF_UPDATE, pr)
        elif c == "U" and self.down:
            self.pen.send(px, py, PF_UP, 0)
            self.down = False

    def touchpad(self, c, x, y):
        now = time.time()
        if c == "D":
            self.t_last = (x, y)
            self.t_start = now
            self.t_moved = 0
        elif c == "M":
            dx, dy = x - self.t_last[0], y - self.t_last[1]
            self.t_last = (x, y)
            self.t_moved += abs(dx) + abs(dy)
            fx = dx * self.args.speed + self.rem_x
            fy = dy * self.args.speed + self.rem_y
            ix, iy = int(fx), int(fy)
            self.rem_x, self.rem_y = fx - ix, fy - iy
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetCursorPos(pt.x + ix, pt.y + iy)
        elif c == "U":
            if now - self.t_start < 0.25 and self.t_moved < 12:
                mouse_event(MOUSEEVENTF_LEFTDOWN)
                mouse_event(MOUSEEVENTF_LEFTUP)

    def scroll(self, dy):
        self.wheel_acc += dy * self.args.scroll
        n = int(self.wheel_acc)
        if n:
            self.wheel_acc -= n
            mouse_event(MOUSEEVENTF_WHEEL, n)

    def reset(self):
        """Отпустить всё, если связь оборвалась посреди штриха."""
        if self.down:
            if self.mode == "pen":
                self.pen.send(self.last[0], self.last[1], PF_UP, 0)
            elif self.mode == "mouse":
                mouse_event(MOUSEEVENTF_LEFTUP)
            self.down = False


def adb_forward(adb):
    subprocess.run([adb, "forward", "tcp:%d" % PORT, "tcp:%d" % PORT],
                   check=True, capture_output=True)


def main():
    ap = argparse.ArgumentParser(description="TabletPad PC server")
    ap.add_argument("--mode", choices=["mouse", "pen", "touchpad"], default="mouse")
    ap.add_argument("--area", default="primary",
                    help="primary | all | x,y,w,h (область экрана для планшета)")
    ap.add_argument("--no-keep-aspect", dest="keep_aspect", action="store_false",
                    help="растянуть планшет на всю область без сохранения пропорций")
    ap.add_argument("--pressure-fixed", type=int, default=0,
                    help="фиксированный нажим 1..1024 вместо данных с экрана")
    ap.add_argument("--speed", type=float, default=1.5, help="скорость курсора (touchpad)")
    ap.add_argument("--scroll", type=float, default=3.0,
                    help="скорость прокрутки (отрицательное = инвертировать)")
    ap.add_argument("--host", help="IP планшета (Wi-Fi). Без него используется adb по USB")
    ap.add_argument("--adb", default="adb", help="путь к adb.exe")
    args = ap.parse_args()

    inj = Injector(args)
    host = args.host or "127.0.0.1"

    try:
        while True:
            try:
                if not args.host:
                    adb_forward(args.adb)
                sock = socket.create_connection((host, PORT), timeout=5)
                sock.settimeout(5)
                print("Подключено к %s:%d" % (host, PORT))
                buf = b""
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        inj.handle_line(line.decode("ascii", "ignore"))
            except FileNotFoundError:
                print("! adb не найден. Укажите --adb C:\\путь\\adb.exe или добавьте его в PATH")
                return 1
            except subprocess.CalledProcessError as e:
                print("! adb: %s" % (e.stderr or b"").decode("utf-8", "ignore").strip())
            except (OSError, socket.timeout):
                pass
            inj.reset()
            time.sleep(1)
    except KeyboardInterrupt:
        inj.reset()
        print("\nВыход")
    return 0


if __name__ == "__main__":
    sys.exit(main())
