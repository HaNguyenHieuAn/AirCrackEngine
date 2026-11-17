"""
LCDKeypadPyEngine - Thư viện Python điều khiển LCD Keypad Shield qua Arduino Uno R3.

Tối ưu cho thời gian thực (real-time), chính xác, không bỏ lỡ input nút bấm.

Cấu trúc gói:
    lcd_keypad_engine/
        __init__.py        - Xuất các API chính
        exceptions.py      - Các ngoại lệ tùy chỉnh
        protocol.py        - Giao thức binary Arduino <-> Python
        serial_link.py     - Quản lý kết nối Serial + luồng đọc nền
        core.py            - Lop LCDKeypadEngine chinh (API cao cap)

Su dung nhanh:
    from lcd_keypad_engine import LCDKeypadEngine

    eng = LCDKeypadEngine(port="COM3")
    eng.print_line1("Xin chao")
    eng.print_line2("Nhan nut UP")
    btn = eng.wait_for_button()
    print("Ban da nhan:", btn)
    eng.close()
"""

from .core import LCDKeypadEngine, quick_engine, quick_print, quick_clear
from .exceptions import (
    LCDKeypadError,
    SerialConnectionError,
    ProtocolError,
    ChecksumError,
    CommandError,
    TimeoutError,
    ButtonError,
)
from .protocol import (
    Packet,
    CMD_LCD_LINE1,
    CMD_LCD_LINE2,
    CMD_LCD_CLEAR,
    CMD_READ_BTN,
    CMD_SET_BACKLIGHT,
    CMD_PING,
    CMD_GET_TELEMETRY,
    CMD_REQ_SETTINGS,
    CMD_SAVE_SETTINGS,
    CMD_RESET_ALL_SETTINGS,
    CMD_DISPLAY_UPDATE,
    CMD_REQ_LINUX_SUDO_ITEM,
    CMD_REQ_LINUX_INFO,
    CMD_HOTSPOT_ACTION,
    CMD_GAME_STATE,
    CMD_MENU_UPDATE,
    CMD_APP_EXIT,
    RESP_ACK,
    RESP_NACK,
    RESP_BTN_STATE,
    RESP_ERROR,
    RESP_PONG,
    RESP_TELEMETRY,
    RESP_SETTINGS,
    RESP_LINUX_SUDO_ITEM,
    RESP_LINUX_INFO,
    RESP_GAME_START,
    RESP_BRIDGE_START,
    RESP_APP_ENTER,
    RESP_APP_LAUNCH,
    RESP_APP_EXIT,
    RESP_OS_BOOT,
    RESP_HOTSPOT_STATUS,
    RESP_DEBUG_LOG,
    BTN_NONE,
    BTN_RIGHT,
    BTN_UP,
    BTN_DOWN,
    BTN_LEFT,
    BTN_SELECT,
    BUTTON_NAMES,
    PACKET_NAMES,
)
from .serial_link import SerialLink, SerialTechnicalLogger, SerialLinkStats

__version__ = "1.0.0"
__author__ = "LCDKeypadPyEngine"

__all__ = [
    # Core
    "LCDKeypadEngine",
    "quick_engine",
    "quick_print",
    "quick_clear",
    # Exceptions
    "LCDKeypadError",
    "SerialConnectionError",
    "ProtocolError",
    "ChecksumError",
    "CommandError",
    "TimeoutError",
    "ButtonError",
    # Protocol
    "Packet",
    "CMD_LCD_LINE1",
    "CMD_LCD_LINE2",
    "CMD_LCD_CLEAR",
    "CMD_READ_BTN",
    "CMD_SET_BACKLIGHT",
    "CMD_PING",
    "CMD_GET_TELEMETRY",
    "CMD_REQ_SETTINGS",
    "CMD_SAVE_SETTINGS",
    "CMD_RESET_ALL_SETTINGS",
    "CMD_DISPLAY_UPDATE",
    "CMD_REQ_LINUX_SUDO_ITEM",
    "CMD_REQ_LINUX_INFO",
    "CMD_HOTSPOT_ACTION",
    "CMD_GAME_STATE",
    "CMD_MENU_UPDATE",
    "CMD_APP_EXIT",
    "RESP_ACK",
    "RESP_NACK",
    "RESP_BTN_STATE",
    "RESP_ERROR",
    "RESP_PONG",
    "RESP_TELEMETRY",
    "RESP_SETTINGS",
    "RESP_LINUX_SUDO_ITEM",
    "RESP_LINUX_INFO",
    "RESP_GAME_START",
    "RESP_BRIDGE_START",
    "RESP_APP_ENTER",
    "RESP_APP_LAUNCH",
    "RESP_APP_EXIT",
    "RESP_OS_BOOT",
    "RESP_HOTSPOT_STATUS",
    "RESP_DEBUG_LOG",
    "BTN_NONE",
    "BTN_RIGHT",
    "BTN_UP",
    "BTN_DOWN",
    "BTN_LEFT",
    "BTN_SELECT",
    "BUTTON_NAMES",
    "PACKET_NAMES",
    # SerialLink & Logger
    "SerialLink",
    "SerialTechnicalLogger",
    "SerialLinkStats",
]