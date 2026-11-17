"""
Binary protocol definition for LCDKeypadPyEngine.

Giao thức gói tin (binary) giữa Python và Arduino:
    0xAA [Len] [Cmd] [Data...] [Checksum] 0xBB

    Len      = 1 (Cmd) + DataLen + 1 (Checksum)
    Checksum = XOR của tất cả byte từ Cmd đến cuối Data
"""

from dataclasses import dataclass
from typing import Optional, List

from .exceptions import ProtocolError, ChecksumError

# ----------- Framing bytes -----------
START_BYTE: int = 0xAA
END_BYTE: int = 0xBB

# ----------- Commands & Requests -----------
CMD_LCD_LINE1: int = 0x01      # Data: chuỗi text (tối đa 16 ký tự)
CMD_LCD_LINE2: int = 0x02      # Data: chuỗi text (tối đa 16 ký tự)
CMD_LCD_CLEAR: int = 0x03      # Data: không có
CMD_READ_BTN: int = 0x04       # Data: không có (Arduino trả về BTN_STATE)
CMD_SET_BACKLIGHT: int = 0x05  # Data: 1 byte (0=tắt, 1=bật)
CMD_PING: int = 0x06           # Data: sequence/timestamp (4 bytes)
CMD_GET_TELEMETRY: int = 0x07  # Data: không có (yêu cầu báo cáo phần cứng)
CMD_REQ_SETTINGS: int = 0x08   # Arduino -> PC: Yêu cầu PC nạp cài đặt hệ điều hành
CMD_SAVE_SETTINGS: int = 0x09  # Arduino -> PC: Lưu cài đặt mới lên PC (Backlight, Sound...)
CMD_RESET_ALL_SETTINGS: int = 0x0A # Arduino -> PC: Yêu cầu xóa/reset toàn bộ cài đặt về mặc định
CMD_DISPLAY_UPDATE: int = 0x20 # PC -> Arduino: Chuỗi phản hồi hiển thị lên dòng 2 LCD
CMD_REQ_LINUX_SUDO_ITEM: int = 0x30 # Arduino -> PC: [index: 1B] Yêu cầu thông tin lệnh sudo
CMD_REQ_LINUX_INFO: int = 0x31      # Arduino -> PC: Yêu cầu thông tin hệ thống Linux

# ----------- Game & App lifecycle commands -----------
CMD_HOTSPOT_ACTION: int = 0x18 # Arduino -> Pi: [Action, Extra] (Bat/tat AP, sync, query)
CMD_GAME_STATE: int = 0x10   # Data: [health(1B), level(1B), item_id(1B), flags(1B)]
CMD_MENU_UPDATE: int = 0x11  # Data: [line_idx(1B)] + text (tối đa 16 ký tự)
CMD_APP_EXIT: int = 0x12     # Data: không có (yêu cầu thoát app về OS)

# ----------- Responses (Arduino <-> Python) -----------
RESP_ACK: int = 0x81        # Lệnh thành công
RESP_NACK: int = 0x82       # Lệnh thất bại / sai checksum
RESP_BTN_STATE: int = 0x83  # Data: 1 byte (mã nút bấm)
RESP_ERROR: int = 0x84      # Data: 1 byte (mã lỗi)
RESP_PONG: int = 0x86       # Data: echo sequence/timestamp (4 bytes)
RESP_TELEMETRY: int = 0x87  # Data: telemetry buffer
RESP_SETTINGS: int = 0x88   # PC -> Arduino: Dữ liệu cài đặt [Backlight, Sound, Flags...]
RESP_LINUX_SUDO_ITEM: int = 0x8A # PC -> Arduino: [index, total, name_len, name, desc_len, desc]
RESP_LINUX_INFO: int = 0x8B      # PC -> Arduino: [line1_len, line1, line2_len, line2]
RESP_GAME_START: int = 0x90 # Arduino báo Python bắt đầu trò chơi
RESP_BRIDGE_START: int = 0x90 # Alias cho PC Bridge mode
RESP_APP_ENTER: int = 0x90  # Arduino báo vừa vào app PC test (Mở UI)
RESP_APP_LAUNCH: int = 0x91 # Arduino báo chuyển app
RESP_APP_EXIT: int = 0x92   # Arduino báo vừa thoát app PC test (Đóng UI)
RESP_OS_BOOT: int = 0x95    # Arduino báo vừa khởi động lại / Reset
RESP_HOTSPOT_STATUS: int = 0x98 # Pi -> Arduino: [Status, Clients, IPLastOctet, UpstreamOnline]
RESP_DEBUG_LOG: int = 0x99  # Data: log text hoặc debug event từ Arduino

# ----------- Ten goi tin truc quan (phuc vu debugger / logger) -----------
PACKET_NAMES = {
    CMD_LCD_LINE1: "CMD_LCD_LINE1(0x01)",
    CMD_LCD_LINE2: "CMD_LCD_LINE2(0x02)",
    CMD_LCD_CLEAR: "CMD_LCD_CLEAR(0x03)",
    CMD_READ_BTN: "CMD_READ_BTN(0x04)",
    CMD_SET_BACKLIGHT: "CMD_SET_BACKLIGHT(0x05)",
    CMD_PING: "CMD_PING(0x06)",
    CMD_GET_TELEMETRY: "CMD_GET_TELEMETRY(0x07)",
    CMD_REQ_SETTINGS: "CMD_REQ_SETTINGS(0x08)",
    CMD_SAVE_SETTINGS: "CMD_SAVE_SETTINGS(0x09)",
    CMD_RESET_ALL_SETTINGS: "CMD_RESET_ALL_SETTINGS(0x0A)",
    CMD_DISPLAY_UPDATE: "CMD_DISPLAY_UPDATE(0x20)",
    CMD_REQ_LINUX_SUDO_ITEM: "CMD_REQ_LINUX_SUDO_ITEM(0x30)",
    CMD_REQ_LINUX_INFO: "CMD_REQ_LINUX_INFO(0x31)",
    CMD_GAME_STATE: "CMD_GAME_STATE(0x10)",
    CMD_MENU_UPDATE: "CMD_MENU_UPDATE(0x11)",
    CMD_APP_EXIT: "CMD_APP_EXIT(0x12)",
    RESP_ACK: "RESP_ACK(0x81)",
    RESP_NACK: "RESP_NACK(0x82)",
    RESP_BTN_STATE: "RESP_BTN_STATE(0x83)",
    RESP_ERROR: "RESP_ERROR(0x84)",
    RESP_PONG: "RESP_PONG(0x86)",
    RESP_TELEMETRY: "RESP_TELEMETRY(0x87)",
    RESP_SETTINGS: "RESP_SETTINGS(0x88)",
    RESP_LINUX_SUDO_ITEM: "RESP_LINUX_SUDO_ITEM(0x8A)",
    RESP_LINUX_INFO: "RESP_LINUX_INFO(0x8B)",
    RESP_GAME_START: "RESP_GAME_START(0x90)",
    RESP_APP_LAUNCH: "RESP_APP_LAUNCH(0x91)",
    RESP_APP_EXIT: "RESP_APP_EXIT(0x92)",
    CMD_HOTSPOT_ACTION: "CMD_HOTSPOT_ACTION(0x18)",
    RESP_HOTSPOT_STATUS: "RESP_HOTSPOT_STATUS(0x98)",
    RESP_OS_BOOT: "RESP_OS_BOOT(0x95)",
    RESP_DEBUG_LOG: "RESP_DEBUG_LOG(0x99)",
}

# ----------- Button codes -----------
BTN_NONE: int = 0x00
BTN_RIGHT: int = 0x01
BTN_UP: int = 0x02
BTN_DOWN: int = 0x03
BTN_LEFT: int = 0x04
BTN_SELECT: int = 0x05

BUTTON_NAMES = {
    BTN_NONE: "NONE",
    BTN_RIGHT: "RIGHT",
    BTN_UP: "UP",
    BTN_DOWN: "DOWN",
    BTN_LEFT: "LEFT",
    BTN_SELECT: "SELECT",
}

# ----------- LCD limits -----------
LCD_COLS: int = 16
LCD_ROWS: int = 2

# ----------- Packet dataclass -----------
@dataclass
class Packet:
    """Đại diện cho một gói tin giao thức."""
    cmd: int
    data: bytes = b""

    def encode(self) -> bytes:
        """Mã hóa Packet thành bytesready để gửi qua Serial."""
        cmd_byte = bytes([self.cmd])
        data_bytes = self.data
        checksum = self.cmd
        for b in data_bytes:
            checksum ^= b

        length = 1 + len(data_bytes) + 1  # Cmd + Data + Checksum
        packet = bytes([START_BYTE, length]) + cmd_byte + data_bytes + bytes([checksum, END_BYTE])
        return packet

    @classmethod
    def decode(cls, raw: bytes) -> "Packet":
        """Giải mã bytes thành Packet. Ném ProtocolError nếu sai định dạng."""
        if len(raw) < 4:
            raise ProtocolError(f"Gói tin quá ngắn: {len(raw)} byte (cần ít nhất 4)")

        if raw[0] != START_BYTE:
            raise ProtocolError(f"Start byte không khớp: 0x{raw[0]:02X} (cần 0x{START_BYTE:02X})")

        if raw[-1] != END_BYTE:
            raise ProtocolError(f"End byte không khớp: 0x{raw[-1]:02X} (cần 0x{END_BYTE:02X})")

        length = raw[1]
        if length < 2:
            raise ProtocolError(f"Len trường không hợp lệ: {length}")

        if len(raw) != length + 3:  # START_BYTE + Len + ... + END_BYTE
            raise ProtocolError(
                f"Độ dài gói tin không khớp Len: nhận {len(raw)}, mong đợi {length + 2}"
            )

        cmd = raw[2]
        data_len = length - 2  # trừ Cmd và Checksum
        data = raw[3:3 + data_len]
        recv_checksum = raw[3 + data_len]

        # Verify checksum
        calc_checksum = cmd
        for b in data:
            calc_checksum ^= b

        if calc_checksum != recv_checksum:
            raise ChecksumError(
                f"Checksum không khớp: tính được 0x{calc_checksum:02X}, nhận 0x{recv_checksum:02X}"
            )

        return cls(cmd=cmd, data=data)

    @classmethod
    def build_stream(cls, packets: List["Packet"]) -> bytes:
        """Ghép nhiều Packet thành một dải bytes để gửi liên tục."""
        return b"".join(p.encode() for p in packets)

    @classmethod
    def parse_stream(cls, raw: bytes) -> List["Packet"]:
        """Tách một dải bytes thành danh sách Packet. Bỏ qua byte rác giữa các gói."""
        packets, _ = cls.parse_stream_safe(raw)
        return packets

    @classmethod
    def parse_stream_safe(cls, raw: bytes) -> tuple[List["Packet"], int]:
        """
        Tách stream an toàn:
        Trả về (danh sách Packet, số byte đã tiêu thụ an toàn).
        Các byte của gói tin dang dở ở cuối buffer sẽ KHÔNG bị tiêu thụ,
        giúp giữ lại nguyên vẹn cho lần đọc serial tiếp theo mà không bị mất dữ liệu.
        """
        packets: List["Packet"] = []
        consumed = 0
        i = 0
        n = len(raw)

        while i < n:
            # Tìm START_BYTE
            if raw[i] != START_BYTE:
                i += 1
                consumed = i
                continue

            # Cần tối thiểu 2 byte: START + Len
            if i + 1 >= n:
                break  # Chờ thêm byte

            length = raw[i + 1]
            if length < 2 or length > 64:
                # Len bất hợp lý -> START_BYTE giả mạo hoặc nhiễu đường truyền
                i += 1
                consumed = i
                continue

            end_pos = i + length + 3  # START(1) + Len(1) + Payload(length) + END(1)
            if end_pos > n:
                # Gói tin chưa nhận đủ dữ liệu -> DỪNG và bảo toàn buffer
                break

            if raw[end_pos - 1] != END_BYTE:
                # Không kết thúc bằng END_BYTE -> frame hỏng, trượt tiếp
                i += 1
                consumed = i
                continue

            try:
                pkt = cls.decode(raw[i:end_pos])
                packets.append(pkt)
                i = end_pos
                consumed = i
            except (ProtocolError, ChecksumError):
                i += 1
                consumed = i

        return packets, consumed

    @property
    def name(self) -> str:
        """Tên trực quan của gói tin."""
        return PACKET_NAMES.get(self.cmd, f"CMD_0x{self.cmd:02X}")

    @property
    def hex_dump(self) -> str:
        """Chuỗi hex hiển thị toàn bộ frame nhị phân."""
        return self.encode().hex(" ").upper()

    @property
    def button(self) -> Optional[str]:
        """Trả về tên nút bấm nếu gói tin là RESP_BTN_STATE."""
        if self.cmd == RESP_BTN_STATE and len(self.data) >= 1:
            code = self.data[0]
            return BUTTON_NAMES.get(code, f"UNKNOWN(0x{code:02X})")
        return None

    @property
    def is_ack(self) -> bool:
        return self.cmd == RESP_ACK

    @property
    def is_nack(self) -> bool:
        return self.cmd == RESP_NACK

    @property
    def is_error(self) -> bool:
        return self.cmd == RESP_ERROR

    @property
    def is_btn_state(self) -> bool:
        return self.cmd == RESP_BTN_STATE

    @property
    def is_pong(self) -> bool:
        return self.cmd == RESP_PONG

    @property
    def is_telemetry(self) -> bool:
        return self.cmd == RESP_TELEMETRY

    @property
    def is_game_start(self) -> bool:
        return self.cmd == RESP_GAME_START

    @property
    def is_debug_log(self) -> bool:
        return self.cmd == RESP_DEBUG_LOG

    def __repr__(self) -> str:
        btn = self.button
        btn_str = f", button={btn}" if btn else ""
        hex_data = self.data.hex(" ").upper() if self.data else "EMPTY"
        return f"Packet({self.name}, data=[{hex_data}]{btn_str})"