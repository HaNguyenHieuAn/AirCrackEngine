"""
server_display.py - May chu hien thi truc quan Python nhan su kien tu Arduino LCD OS.

Chuc nang:
- Mo cua so giao dien Pygame hien dai.
- Khi nguoi dung bam nut bat ky tren Arduino LCD Shield (UP, DOWN, LEFT, RIGHT, SELECT),
  cua so lap tuc thay doi chu, mau sac, bieu tuong va mo ta chi tiet theo thoi gian thuc.
- Gui phan hoi hai chieu (Bidirectional Feedback) ve man hinh LCD Arduino.
- Tich hop cong cu giam sat Ping RTT, Auto-Recovery tu dong ket noi lai khi rut cap.
- Ho tro phim tat PC: Mui ten test nut, [B] bat/tat den nen, [P] do ping, [ESC] thoat.
"""

import sys
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

# Bo sung duong dan thu vien
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import pygame
from lcd_keypad_engine import (
    LCDKeypadEngine,
    CMD_LCD_LINE1,
    CMD_LCD_LINE2,
    CMD_LCD_CLEAR,
    CMD_SET_BACKLIGHT,
    CMD_PING,
    RESP_BRIDGE_START,
    RESP_BTN_STATE,
    RESP_DEBUG_LOG,
    BTN_UP, BTN_DOWN, BTN_LEFT, BTN_RIGHT, BTN_SELECT, BTN_NONE,
)
import serial.tools.list_ports

# Ma lenh hien thi text phan hoi tu PC ve Arduino
CMD_DISPLAY_UPDATE = 0x20

# Mau sac giao dien
COLOR_BG = (18, 22, 32)
COLOR_CARD_BG = (28, 34, 48)
COLOR_BORDER = (50, 60, 85)
COLOR_TEXT_MAIN = (240, 244, 250)
COLOR_TEXT_MUTED = (140, 155, 180)

# Mau theo tung nut bam
BTN_STYLES = {
    "UP": {
        "title": "▲ NUT LEN (UP KEY)",
        "color": (0, 225, 255),       # Cyan
        "desc": "Arduino vua gui tin hieu nut LEN (UP)!",
        "action": "Len / Tang gia tri / Di chuyen tien",
        "code": "0x02",
        "lcd_ack": "PC: Nhan Nut LEN",
    },
    "DOWN": {
        "title": "▼ NUT XUONG (DOWN KEY)",
        "color": (255, 145, 0),      # Cam
        "desc": "Arduino vua gui tin hieu nut XUONG (DOWN)!",
        "action": "Xuong / Giam gia tri / Cuon trang",
        "code": "0x03",
        "lcd_ack": "PC: Nhan XUONG",
    },
    "LEFT": {
        "title": "◀ NUT TRAI (LEFT) -> VE OS",
        "color": (195, 110, 255),    # Tim
        "desc": "Arduino vua bam nut TRAI de quay ve Menu Tong cua OS!",
        "action": "Quay ve Menu Tong cua OS (Back to OS Menu)",
        "code": "0x04",
        "lcd_ack": "PC: <- Ve OS...",
    },
    "RIGHT": {
        "title": "▶ NUT PHAI (RIGHT KEY)",
        "color": (50, 255, 130),     # Xanh la
        "desc": "Arduino vua gui tin hieu nut PHAI (RIGHT)!",
        "action": "Sang phai / Chuyen muc tiep theo",
        "code": "0x01",
        "lcd_ack": "PC: Nhan Nut PHAI",
    },
    "SELECT": {
        "title": "● NUT SELECT (XAC NHAN)",
        "color": (255, 225, 50),     # Vang
        "desc": "Arduino vua gui tin hieu nut XAC NHAN (SELECT)!",
        "action": "Xac nhan / Chon / Thuc thi lenh",
        "code": "0x05",
        "lcd_ack": "PC: Nhan SELECT",
    },
    "NONE": {
        "title": "DANG CHO TIN HIEU TU ARDUINO...",
        "color": (130, 145, 170),    # Xam bac
        "desc": "Hay chon 'PC Bridge' tren Arduino va bam nut bat ky tren Shield.",
        "action": "Chua co nut nao duoc nhan",
        "code": "0x00",
        "lcd_ack": "PC: Ready...",
    },
}


def find_arduino_port() -> Optional[str]:
    """Tu dong tim cong COM cua Arduino Uno / CH340 mot cach thong minh nhat."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    arduino_vids = {0x2341, 0x0043, 0x2A03, 0x1B4F, 0x1A86, 0x10C4, 0x0403}
    candidates = []

    for p in ports:
        score = 0
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()

        if p.vid and p.vid in arduino_vids:
            score += 100
        if p.vid == 0x1A86 and p.pid == 0x7523:
            score += 50
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

        if score > 0:
            candidates.append((score, p.device))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    if len(ports) == 1:
        return ports[0].device

    return None


@dataclass
class ButtonHistoryItem:
    name: str
    timestamp: float


def main(port: Optional[str] = None):
    # 1. Khoi tao Pygame
    pygame.init()
    screen_w, screen_h = 760, 520
    screen = pygame.display.set_mode((screen_w, screen_h))
    pygame.display.set_caption("Arduino LCD OS - Python Bridge Server [115200 Baud]")
    clock = pygame.time.Clock()

    font_title = pygame.font.SysFont("consolas", 22, bold=True)
    font_large = pygame.font.SysFont("consolas", 32, bold=True)
    font_med = pygame.font.SysFont("consolas", 18, bold=True)
    font_regular = pygame.font.SysFont("consolas", 16)
    font_small = pygame.font.SysFont("consolas", 13)

    # 2. Ket noi Arduino
    target_port = port or find_arduino_port()
    engine: Optional[LCDKeypadEngine] = None

    if target_port:
        try:
            print(f"[Bridge Server] Dang mo ket noi {target_port} @ 115200 baud...")
            engine = LCDKeypadEngine(port=target_port, baudrate=115200, timeout=2.0)
            print("[Bridge Server] KET NOI THANH CONG!")
        except Exception as e:
            print(f"[Bridge Server] Loi mo cong: {e}")

    current_btn = "NONE"
    last_pressed_btn = "NONE"
    total_press_count = 0
    history: List[ButtonHistoryItem] = []
    backlight_state = True
    last_ping_time = time.time()
    last_reconnect_attempt = 0.0

    running = True

    while running:
        now = time.time()

        # --- A. XU LY SU KIEN CUA SO PYGAME ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_b:
                    # Phim B: Bat / tat den nen LCD Arduino
                    backlight_state = not backlight_state
                    if engine and engine.is_open:
                        try:
                            engine._link.send_command(
                                CMD_SET_BACKLIGHT,
                                bytes([1 if backlight_state else 0]),
                                wait_response=False,
                            )
                        except Exception:
                            pass
                elif event.key == pygame.K_c:
                    # Phim C: Xoa LCD Arduino
                    if engine and engine.is_open:
                        try:
                            engine._link.send_command(CMD_LCD_CLEAR, wait_response=False)
                        except Exception:
                            pass
                elif event.key == pygame.K_p:
                    # Phim P: Do Ping tuc thoi
                    if engine and engine.is_open:
                        engine.ping(timeout=0.4)

                # Ho tro phim mui ten PC gia lap nut Arduino
                key_sim_map = {
                    pygame.K_UP: "UP",
                    pygame.K_DOWN: "DOWN",
                    pygame.K_LEFT: "LEFT",
                    pygame.K_RIGHT: "RIGHT",
                    pygame.K_RETURN: "SELECT",
                    pygame.K_SPACE: "SELECT",
                }
                if event.key in key_sim_map:
                    sim_btn = key_sim_map[event.key]
                    current_btn = sim_btn
                    last_pressed_btn = sim_btn
                    total_press_count += 1
                    history.insert(0, ButtonHistoryItem(name=sim_btn, timestamp=now))
                    if len(history) > 6:
                        history.pop()

        # --- B. DOC DU LIEU TU ARDUINO SERIAL LINK ---
        if engine and engine.is_open:
            try:
                while not engine._link._packet_queue.empty():
                    pkt = engine._link._packet_queue.get_nowait()

                    # Nhan thong bao Arduino vua vao PC Bridge
                    if pkt.is_game_start:
                        print("[Bridge Server] Nhan tin hieu START tu Arduino!")
                        # Gui phan hoi chao mung len LCD
                        welcome_txt = "PC: Connected OK".encode("utf-8")
                        engine._link.send_command(CMD_DISPLAY_UPDATE, welcome_txt, wait_response=False)
                        continue

                    if pkt.is_debug_log:
                        try:
                            print(f"[ARDUINO MSG] {pkt.data.decode('utf-8', errors='replace')}")
                        except Exception:
                            pass
                        continue

                    # Nhan trang thai nut bam thuc te tu Arduino Shield
                    if pkt.button is not None:
                        new_btn = pkt.button
                        if new_btn != current_btn:
                            current_btn = new_btn
                            if current_btn != "NONE":
                                last_pressed_btn = current_btn
                                total_press_count += 1
                                history.insert(0, ButtonHistoryItem(name=current_btn, timestamp=now))
                                if len(history) > 6:
                                    history.pop()

                                # Gui phan hoi nguoc lai Arduino de hien tren LCD
                                ack_str = BTN_STYLES.get(current_btn, {}).get("lcd_ack", "PC: OK")
                                try:
                                    engine._link.send_command(
                                        CMD_DISPLAY_UPDATE,
                                        ack_str.encode("utf-8"),
                                        wait_response=False,
                                    )
                                except Exception:
                                    pass
            except Exception:
                pass

            # Do ping dinh ky moi 4 giay
            if now - last_ping_time >= 4.0:
                last_ping_time = now
                engine.ping(timeout=0.3)

        else:
            # Tu dong thu ket noi lai neu chua mo hoac bi dut cap
            if now - last_reconnect_attempt >= 2.0:
                last_reconnect_attempt = now
                target_port = target_port or find_arduino_port()
                if target_port:
                    try:
                        if engine is None:
                            engine = LCDKeypadEngine(port=target_port, baudrate=115200, timeout=2.0)
                        else:
                            engine.reconnect(max_retries=1)
                    except Exception:
                        pass

        # --- C. VE GIAO DIEN DO HOA (PYGAME UI) ---
        screen.fill(COLOR_BG)

        # 1. Header Bar
        pygame.draw.rect(screen, COLOR_CARD_BG, (15, 12, screen_w - 30, 48), border_radius=8)
        title_surf = font_title.render("ARDUINO LCD OS  |  PYTHON BRIDGE SERVER", True, COLOR_TEXT_MAIN)
        screen.blit(title_surf, (28, 22))

        # Trạng thái kết nối
        is_conn = engine is not None and engine.is_open and engine._link.is_read_thread_alive
        st_color = (50, 230, 110) if is_conn else (255, 75, 75)
        st_text = f"● ONLINE [{target_port or 'N/A'}]" if is_conn else "○ OFFLINE (RECONNECTING)"
        st_surf = font_med.render(st_text, True, st_color)
        screen.blit(st_surf, (screen_w - st_surf.get_width() - 30, 24))

        # 2. Main Hero Card (Khung hien thi nut bam trung tam)
        card_rect = pygame.Rect(15, 72, screen_w - 30, 240)
        btn_style = BTN_STYLES.get(last_pressed_btn if current_btn == "NONE" else current_btn, BTN_STYLES["NONE"])
        highlight_color = btn_style["color"]

        # Nen Card
        pygame.draw.rect(screen, COLOR_CARD_BG, card_rect, border_radius=12)
        # Vien Card co mau theo nut
        pygame.draw.rect(screen, highlight_color, card_rect, width=3, border_radius=12)

        # Trạng thái nút hiện tại
        status_sub = "NUT DANG DUOC BAM:" if current_btn != "NONE" else "NUT VUA BAM GAN NHAT:"
        screen.blit(font_small.render(status_sub, True, COLOR_TEXT_MUTED), (35, 90))

        # Tieu de nut bam to lon
        main_label = btn_style["title"] if (current_btn != "NONE" or last_pressed_btn != "NONE") else "DANG CHO TIN HIEU TU ARDUINO..."
        main_surf = font_large.render(main_label, True, highlight_color)
        screen.blit(main_surf, (35, 115))

        # Dòng mo ta tieng Viet
        screen.blit(font_med.render(btn_style["desc"], True, COLOR_TEXT_MAIN), (35, 168))

        # Tac vu tuong ung
        act_label = f"Hanh dong logic: {btn_style['action']}"
        screen.blit(font_regular.render(act_label, True, COLOR_TEXT_MUTED), (35, 205))

        # Ma Protocol Hex
        code_label = f"Giao thuc nhan: RESP_BTN_STATE (0x83)  |  Ma Byte: {btn_style['code']}"
        screen.blit(font_small.render(code_label, True, (120, 140, 170)), (35, 240))

        # Phan hoi LCD nguoc lai
        ack_label = f"Chuoi phan hoi gui ve LCD: '{btn_style['lcd_ack']}'"
        screen.blit(font_small.render(ack_label, True, (100, 200, 180)), (35, 265))

        # 3. Bottom Panels: Lich su nut & Thong so Serial
        panel_y = 324
        panel_h = 180

        # Panel Trai: Lich su cac nut da bam
        left_w = 420
        pygame.draw.rect(screen, COLOR_CARD_BG, (15, panel_y, left_w, panel_h), border_radius=8)
        pygame.draw.rect(screen, COLOR_BORDER, (15, panel_y, left_w, panel_h), width=1, border_radius=8)

        screen.blit(font_med.render("LICH SU NUT BAM (MOI NHAT TRUOC)", True, COLOR_TEXT_MAIN), (28, panel_y + 12))

        if not history:
            screen.blit(font_regular.render("Chua co nut nao duoc bam.", True, COLOR_TEXT_MUTED), (28, panel_y + 45))
        else:
            for idx, item in enumerate(history[:5]):
                elapsed = now - item.timestamp
                hist_style = BTN_STYLES.get(item.name, BTN_STYLES["NONE"])
                hist_line = f"#{total_press_count - idx:02d} | {item.name:7s} - cach day {elapsed:4.1f}s"
                screen.blit(font_regular.render(hist_line, True, hist_style["color"]), (28, panel_y + 40 + idx * 24))

        # Panel Phai: Thong so ky thuat & Phim tat
        right_x = 15 + left_w + 12
        right_w = screen_w - right_x - 15
        pygame.draw.rect(screen, COLOR_CARD_BG, (right_x, panel_y, right_w, panel_h), border_radius=8)
        pygame.draw.rect(screen, COLOR_BORDER, (right_x, panel_y, right_w, panel_h), width=1, border_radius=8)

        screen.blit(font_med.render("THONG SO KY THUAT", True, COLOR_TEXT_MAIN), (right_x + 15, panel_y + 12))

        tx_cnt = engine._link.stats.tx_packets if engine else 0
        rx_cnt = engine._link.stats.rx_packets if engine else 0
        rtt_val = engine._link.stats.last_rtt_ms if engine else 0.0

        stats_lines = [
            f"Baudrate:     115200 bps",
            f"Do tre Ping:  {rtt_val:.1f} ms",
            f"Tong TX / RX: {tx_cnt} / {rx_cnt} goi",
            f"Tong nut bam: {total_press_count} lan",
            f"Den nen LCD:  {'BAT (HIGH)' if backlight_state else 'TAT (LOW)'} [Phim B]",
            f"Phim tat:     [B] Den nen | [P] Ping | [ESC] Thoat",
        ]
        for i, s_line in enumerate(stats_lines):
            screen.blit(font_small.render(s_line, True, COLOR_TEXT_MUTED), (right_x + 15, panel_y + 38 + i * 22))

        pygame.display.flip()
        clock.tick(30)

    # 4. Don dep khi thoat
    if engine:
        try:
            engine.close()
        except Exception:
            pass
    pygame.quit()
    print("[Bridge Server] Da dong cua so va ngat ket noi Serial an toan.")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    main(p)
