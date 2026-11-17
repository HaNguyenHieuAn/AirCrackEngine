"""
diagnose_connection.py - Bo cong cu kiem tra chan doan SerialLink va Telemetry Arduino.
Chay: python diagnose_connection.py [COMx]
"""

import sys
import os
import time
from typing import Optional, List, Dict, Any

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(TOOLS_DIR)
PYTHON_DIR = os.path.join(ENGINE_DIR, "python")
sys.path.insert(0, PYTHON_DIR)

from lcd_keypad_engine import (
    LCDKeypadEngine,
    CMD_PING,
    CMD_GET_TELEMETRY,
    CMD_READ_BTN,
    RESP_PONG,
    RESP_TELEMETRY,
    RESP_BTN_STATE,
)
import serial.tools.list_ports


def print_header(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title.upper()}")
    print(f"{'='*70}")


def scan_hardware_ports() -> List[Dict[str, Any]]:
    print_header("1. Quét Cổng Serial & Nhận Diện Phần Cứng")
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("  [!] Không tìm thấy bất kỳ cổng COM nào trên máy tính!")
        return []

    detected_devices = []
    print(f"  Tìm thấy {len(ports)} cổng COM:")
    for p in ports:
        vid_hex = f"0x{p.vid:04X}" if p.vid else "N/A"
        pid_hex = f"0x{p.pid:04X}" if p.pid else "N/A"
        chip_type = "Không xác định"

        if p.vid in (0x2341, 0x0043, 0x2A03):
            chip_type = "Arduino Official (ATmega16U2 / FTDI)"
        elif p.vid == 0x1A86 or (p.pid and p.pid == 0x7523):
            chip_type = "Arduino Clone (WCH CH340 USB-UART)"
        elif p.vid == 0x10C4:
            chip_type = "Silicon Labs CP210x"
        elif p.vid == 0x0403:
            chip_type = "FTDI FT232"

        is_uno = (
            chip_type != "Không xác định"
            or "arduino" in (p.description or "").lower()
            or "ch340" in (p.description or "").lower()
        )

        detected_devices.append({
            "device": p.device,
            "description": p.description,
            "vid": vid_hex,
            "pid": pid_hex,
            "chip_type": chip_type,
            "is_arduino_candidate": is_uno,
        })

        star = "[★ KHUYÊN DÙNG]" if is_uno else " "
        print(f"  -> {p.device:6s} | {chip_type:35s} | VID:PID={vid_hex}:{pid_hex} {star}")
    return detected_devices


def test_ping_latency(eng: LCDKeypadEngine, count: int = 25) -> Dict[str, Any]:
    print_header(f"2. Kiểm Tra Độ Trễ Ping RTT Tại 115200 Baud ({count} Lần)")
    rtts = []
    dropped = 0

    for i in range(1, count + 1):
        rtt = eng.ping(timeout=0.4)
        if rtt is not None:
            rtts.append(rtt)
            bar = "#" * int(min(rtt, 25))
            print(f"  Gói {i:02d}/{count:02d}: RTT = {rtt:6.2f} ms | {bar}")
        else:
            dropped += 1
            print(f"  Gói {i:02d}/{count:02d}: [!] TIMEOUT")
        time.sleep(0.04)

    success_count = len(rtts)
    loss_rate = (dropped / count) * 100.0
    min_rtt = min(rtts) if rtts else 0.0
    max_rtt = max(rtts) if rtts else 0.0
    avg_rtt = sum(rtts) / len(rtts) if rtts else 0.0

    print(f"\n  - Thành công: {success_count}/{count} ({100.0 - loss_rate:.1f}%)")
    print(f"  - Rớt gói: {dropped}/{count} ({loss_rate:.1f}%)")
    if rtts:
        print(f"  - Độ trễ min/avg/max: {min_rtt:.2f} ms / {avg_rtt:.2f} ms / {max_rtt:.2f} ms")

    return {"loss_rate": loss_rate, "avg_rtt": avg_rtt}


def test_telemetry(eng: LCDKeypadEngine) -> None:
    print_header("3. Thu Thập Telemetry Phần Cứng")
    tele = eng.get_telemetry(timeout=1.0)
    if not tele:
        print("  [!] Không thể lấy telemetry từ Arduino.")
        return

    print(f"  - Thời gian chạy (Uptime): {tele.get('uptime_seconds')} giây")
    print(f"  - RAM còn trống (SRAM):    {tele.get('free_ram_bytes')} bytes / 2048 bytes")
    print(f"  - Tổng lỗi CRC phát hiện:  {tele.get('crc_errors_arduino')} lỗi")
    print(f"  - ADC A0 hiện tại:         {tele.get('analog_a0_raw')}")


def main(port: Optional[str] = None):
    devs = scan_hardware_ports()
    target_port = port
    if not target_port:
        cands = [d["device"] for d in devs if d["is_arduino_candidate"]]
        target_port = cands[0] if cands else (devs[0]["device"] if devs else None)

    if not target_port:
        print("\n[LỖI] Không tìm thấy cổng COM!")
        return

    print_header(f"Khởi Tạo Kết Nối Đến {target_port} @ 115200 Baud")
    try:
        eng = LCDKeypadEngine(port=target_port, baudrate=115200, timeout=2.0)
    except Exception as e:
        print(f"  [LỖI] Không thể mở cổng: {e}")
        return

    print("  [OK] Đã mở cổng thành công!")
    test_ping_latency(eng, count=20)
    test_telemetry(eng)
    eng.close()
    print("\n=== HOÀN TẤT CHẨN ĐOÁN ===\n")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    main(p)
