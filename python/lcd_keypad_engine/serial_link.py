"""
SerialLink - Bộ quản lý kết nối Serial và Logger kỹ thuật chi tiết cao cho Arduino LCD OS.

Tính năng kỹ thuật:
  - Ghi vết kỹ thuật cấp độ microsecond (Technical Trace Logger) vào file `serial_technical_trace.log`.
  - Phân tích chi tiết từng gói tin TX / RX kèm Hex dump, mã lệnh, dữ liệu giải mã và checksum.
  - Bộ đệm an toàn (Safe Stream Parser) chống mất gói tin và không xóa nhầm byte dang dở.
  - Đo kiểm độ trễ khứ hồi (Ping/RTT) và thu thập Telemetry phần cứng Arduino.
  - Giám sát sức khỏe luồng đọc (Thread Health Watchdog) và phát hiện chính xác lỗi ngắt kết nối USB.
  - Tự động bắt tay (Handshake) và đồng bộ trạng thái khi Arduino khởi động hoặc reset.
"""

import threading
import queue
import time
import os
import sys
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any, Tuple

import serial
import serial.tools.list_ports

from .protocol import (
    Packet, START_BYTE, END_BYTE,
    CMD_LCD_LINE1, CMD_LCD_LINE2, CMD_LCD_CLEAR, CMD_READ_BTN, CMD_SET_BACKLIGHT,
    CMD_PING, CMD_GET_TELEMETRY, CMD_GAME_STATE, CMD_MENU_UPDATE, CMD_APP_EXIT,
    RESP_ACK, RESP_NACK, RESP_BTN_STATE, RESP_ERROR, RESP_PONG, RESP_TELEMETRY,
    RESP_GAME_START, RESP_APP_LAUNCH, RESP_DEBUG_LOG,
    BTN_NONE, BTN_RIGHT, BTN_UP, BTN_DOWN, BTN_LEFT, BTN_SELECT,
    BUTTON_NAMES, PACKET_NAMES,
)
from .exceptions import (
    SerialConnectionError, ProtocolError, ChecksumError,
    CommandError, TimeoutError, LCDKeypadError,
)

logger = logging.getLogger("lcd_keypad_engine")


# ==============================================================================
# 1. BỘ GHI VẾT KỸ THUẬT CHI TIẾT (TECHNICAL TRACE LOGGER)
# ==============================================================================
class SerialTechnicalLogger:
    """
    Logger kỹ thuật chuyên sâu cho giao tiếp Serial nhị phân.
    Ghi vết chi tiết từng microsecond ra file `serial_technical_trace.log`.
    """

    def __init__(self, log_path: Optional[str] = None, console_echo: bool = False):
        if log_path is None:
            # Lưu tại thư mục gốc của LCDKeypadPyEngine
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_path = os.path.join(base_dir, "serial_technical_trace.log")
        self.log_path = log_path
        self.console_echo = console_echo
        self._lock = threading.Lock()
        self._init_log_file()

    def _init_log_file(self) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                f.write(f"\n{'='*80}\n")
                f.write(f"[{ts}] === SERIAL TECHNICAL TRACE LOGGER KHOI DONG ===\n")
                f.write(f"{'='*80}\n")
        except Exception as e:
            logger.error("Không thể khởi tạo file log kỹ thuật: %s", e)

    def log(self, category: str, message: str, hex_data: Optional[bytes] = None) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        hex_str = f" | HEX: {hex_data.hex(' ').upper()}" if hex_data else ""
        line = f"[{ts}] [{category:8s}] {message}{hex_str}\n"

        if self.console_echo:
            print(line, end="", flush=True)

        with self._lock:
            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
            except Exception:
                pass

    def log_tx(self, pkt: Packet, raw_bytes: bytes) -> None:
        desc = self._describe_packet(pkt)
        self.log("TX -->", f"Len={len(raw_bytes)}B {pkt.name} | {desc}", hex_data=raw_bytes)

    def log_rx(self, pkt: Packet, raw_bytes: bytes) -> None:
        desc = self._describe_packet(pkt)
        self.log("RX <--", f"Len={len(raw_bytes)}B {pkt.name} | {desc}", hex_data=raw_bytes)

    def log_unframed(self, raw_bytes: bytes) -> None:
        self.log("NOISE", f"Phat hien {len(raw_bytes)} byte ngoai khung giao thuc", hex_data=raw_bytes)

    def log_error(self, err_type: str, details: str) -> None:
        self.log("ERROR", f"[{err_type}] {details}")

    def log_event(self, event_type: str, details: str) -> None:
        self.log("EVENT", f"[{event_type}] {details}")

    def _describe_packet(self, pkt: Packet) -> str:
        if pkt.cmd == CMD_GAME_STATE and len(pkt.data) >= 4:
            hp, lv, itm, flg = pkt.data[0], pkt.data[1], pkt.data[2], pkt.data[3]
            alive = "ALIVE" if (flg & 0x01) else "DEAD"
            over = "GAMEOVER" if (flg & 0x02) else "RUNNING"
            return f"HUD: HP={hp} LV={lv} Item={itm} State={alive}|{over}"
        if pkt.cmd == RESP_BTN_STATE:
            return f"Key={pkt.button} (Code=0x{pkt.data[0]:02X})"
        if pkt.cmd == RESP_GAME_START and len(pkt.data) >= 2:
            return f"Dungeon Launch Request (BL={pkt.data[0]}, Diff={pkt.data[1]})"
        if pkt.cmd == RESP_DEBUG_LOG:
            try:
                return f"Arduino Msg: {pkt.data.decode('utf-8', errors='replace')}"
            except Exception:
                return f"Arduino Raw Msg: {pkt.data.hex(' ')}"
        if pkt.cmd == RESP_TELEMETRY and len(pkt.data) >= 9:
            uptime = int.from_bytes(pkt.data[0:2], "little")
            free_ram = int.from_bytes(pkt.data[2:4], "little")
            rx_count = int.from_bytes(pkt.data[4:6], "little")
            crc_err = pkt.data[6]
            a0_raw = int.from_bytes(pkt.data[7:9], "little")
            return f"Tele: Up={uptime}s FreeRAM={free_ram}B RxPkt={rx_count} CRC_Err={crc_err} A0_ADC={a0_raw}"
        return f"DataLen={len(pkt.data)}"


# ==============================================================================
# 2. BỘ ĐO LƯỜNG THỐNG KÊ KẾT NỐI (CONNECTION METRICS)
# ==============================================================================
@dataclass
class SerialLinkStats:
    tx_packets: int = 0
    rx_packets: int = 0
    tx_bytes: int = 0
    rx_bytes: int = 0
    crc_errors: int = 0
    corrupted_frames: int = 0
    unframed_bytes: int = 0
    disconnect_count: int = 0
    last_tx_time: float = 0.0
    last_rx_time: float = 0.0
    last_rtt_ms: float = 0.0
    last_disconnect_time: float = 0.0
    last_disconnect_reason: str = "Chưa có sự cố"

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "tx_packets": self.tx_packets,
            "rx_packets": self.rx_packets,
            "tx_bytes": self.tx_bytes,
            "rx_bytes": self.rx_bytes,
            "crc_errors": self.crc_errors,
            "corrupted_frames": self.corrupted_frames,
            "disconnect_count": self.disconnect_count,
            "seconds_since_last_rx": round(now - self.last_rx_time, 2) if self.last_rx_time > 0 else None,
            "seconds_since_last_tx": round(now - self.last_tx_time, 2) if self.last_tx_time > 0 else None,
            "last_rtt_ms": round(self.last_rtt_ms, 2),
            "last_disconnect_reason": self.last_disconnect_reason,
        }


# ==============================================================================
# 3. LỚP QUẢN LÝ KẾT NỐI SERIALLINK
# ==============================================================================
class SerialLink:
    """
    Lớp quản lý kết nối Serial đến Arduino kèm bộ Debugger & Logger kỹ thuật cao cấp.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 2.0,
        write_timeout: float = 2.0,
        auto_open: bool = True,
        console_debug: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.console_debug = console_debug

        self._serial: Optional[serial.Serial] = None
        self._lock = threading.RLock()
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._packet_queue: queue.Queue[Packet] = queue.Queue()
        self._response_event = threading.Event()
        self._last_response: Optional[Packet] = None

        # Callbacks
        self._button_callback: Optional[Callable[[str], None]] = None
        self._game_start_callback: Optional[Callable[[dict], None]] = None
        self._disconnect_callback: Optional[Callable[[str], None]] = None

        self._opened = False
        self.stats = SerialLinkStats()
        self.tech_logger = SerialTechnicalLogger(console_echo=console_debug)

        if auto_open:
            self.open()

    # ------------------------------------------------------------------
    # Port discovery
    # ------------------------------------------------------------------
    @staticmethod
    def list_ports() -> List[str]:
        """Trả về danh sách tên cổng serial có sẵn."""
        return [p.device for p in serial.tools.list_ports.comports()]

    @staticmethod
    def find_arduino_port() -> Optional[str]:
        """Tự động quét và nhận diện cổng Arduino Uno / CH340 một cách thông minh nhất."""
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

            # Kiem tra cong COM tren Linux (/dev/ttyACM* hoac /dev/ttyUSB*)
            dev_lower = p.device.lower()
            if "ttyacm" in dev_lower:
                score += 90
            elif "ttyusb" in dev_lower:
                score += 70

            if score > 0:
                candidates.append((score, p.device))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        # Neu chi co duy nhat 1 cong COM tren toan bo may tinh
        if len(ports) == 1:
            return ports[0].device

        return None

    # ------------------------------------------------------------------
    # Open / Close / Reconnect
    # ------------------------------------------------------------------
    def open(self) -> None:
        """Mở cổng serial. Tự động nhận diện cổng nếu chưa chỉ định hoặc cổng cũ không còn tồn tại."""
        if self._opened and self._serial is not None and self._serial.is_open:
            return

        available = self.list_ports()
        # Neu self.port chua co hoac cong cu da bi rut khoi may tinh, tu dong quet lai cong moi!
        if not self.port or self.port not in available:
            self.port = self.find_arduino_port()

        port = self.port
        if port is None:
            err_msg = "Không tìm thấy cổng Arduino Uno. Vui lòng cắm cáp USB."
            self.tech_logger.log_error("PORT_NOT_FOUND", err_msg)
            raise SerialConnectionError(err_msg)

        self.tech_logger.log_event("PORT_OPENING", f"Đang mở cổng {port} @ {self.baudrate} baud...")

        try:
            if "://" in str(port):
                self._serial = serial.serial_for_url(
                    port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.write_timeout,
                )
            else:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    write_timeout=self.write_timeout,
                    dsrdtr=False,
                    rtscts=False,
                )

            # Xóa sạch bộ đệm USB Windows
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

            # Chờ Arduino hoàn tất Bootloader sau xung DTR reset (1.8s)
            self.tech_logger.log_event("BOOT_WAIT", "Chờ Arduino Uno hoàn tất chu kỳ reset phần cứng (1.8s)...")
            time.sleep(1.8)

            self._opened = True
            self.port = port
            self.tech_logger.log_event("PORT_OPEN_OK", f"Đã mở cổng {port} thành công.")

            # Bắt đầu luồng đọc nền
            self._stop_event.clear()
            self._read_thread = threading.Thread(target=self._read_loop, name="SerialLinkReadThread", daemon=True)
            self._read_thread.start()

            # Bắt tay với Arduino
            self._wait_for_ack(timeout=0.5)

        except serial.SerialException as e:
            self._opened = False
            self._serial = None
            err_msg = f"Lỗi phần cứng khi mở cổng {port}: {e}"
            self.tech_logger.log_error("OPEN_FAILED", err_msg)
            raise SerialConnectionError(err_msg) from e

    def _wait_for_ack(self, timeout: float = 2.0) -> None:
        """Chờ Arduino gửi gói RESP_ACK khởi động sau khi mở cổng."""
        self._response_event.clear()
        self._last_response = None
        got = self._response_event.wait(timeout=timeout)
        if got and self._last_response is not None and self._last_response.is_ack:
            self.tech_logger.log_event("HANDSHAKE_OK", "Nhận được gói ACK khởi động xác nhận từ Arduino.")
        else:
            self.tech_logger.log_event("HANDSHAKE_WARN", f"Không nhận được ACK khởi động trong {timeout}s (Arduino có thể đã boot từ trước).")

    def reconnect(self, max_retries: int = 3, retry_delay: float = 1.0) -> bool:
        """Thử ngắt và kết nối lại cổng Serial một cách an toàn."""
        self.tech_logger.log_event("RECONNECT", f"Bắt đầu quá trình Reconnect cổng {self.port} (Tối đa {max_retries} lần)...")
        self.close()
        time.sleep(0.5)

        for attempt in range(1, max_retries + 1):
            try:
                self.tech_logger.log_event("RECONNECT_TRY", f"Thử kết nối lại lần {attempt}/{max_retries}...")
                self.open()
                if self.is_open:
                    self.tech_logger.log_event("RECONNECT_OK", f"Kết nối lại cổng {self.port} thành công ở lần thử {attempt}!")
                    return True
            except Exception as e:
                self.tech_logger.log_error("RECONNECT_ERR", f"Lần {attempt} thất bại: {e}")
                time.sleep(retry_delay)

        self.tech_logger.log_error("RECONNECT_FAILED", "Toàn bộ các lần thử kết nối lại đều thất bại.")
        return False

    def close(self) -> None:
        """Đóng cổng serial và dừng an toàn luồng đọc."""
        self.tech_logger.log_event("CLOSING", "Đang đóng kết nối Serial...")
        self._stop_event.set()
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=1.0)

        with self._lock:
            if self._serial is not None:
                try:
                    if self._serial.is_open:
                        self._serial.close()
                except Exception as e:
                    self.tech_logger.log_error("CLOSE_ERR", f"Lỗi khi đóng cổng: {e}")
            self._serial = None
            self._opened = False

        self.tech_logger.log_event("CLOSED", "Đã đóng cổng serial hoàn tất.")

    @property
    def is_open(self) -> bool:
        return (
            self._opened
            and not self._stop_event.is_set()
            and self._serial is not None
            and self._serial.is_open
        )

    @property
    def is_read_thread_alive(self) -> bool:
        return self._read_thread is not None and self._read_thread.is_alive()

    # ------------------------------------------------------------------
    # Background read loop (Safe Stream Parser & Anomaly Detector)
    # ------------------------------------------------------------------
    def _read_loop(self) -> None:
        """Luồng đọc nền: Đọc liên tục, parse gói tin an toàn và ghi log kỹ thuật."""
        buffer = bytearray()
        self.tech_logger.log_event("THREAD_START", "Luồng đọc Serial (Read Thread) đã kích hoạt.")

        while not self._stop_event.is_set():
            if not self.is_open:
                time.sleep(0.01)
                continue

            try:
                waiting = self._serial.in_waiting
                if waiting > 0:
                    chunk = self._serial.read(min(waiting, 256))
                    if chunk:
                        buffer.extend(chunk)
                        self.stats.rx_bytes += len(chunk)
                        self.stats.last_rx_time = time.time()

                        # Parse các gói tin bằng Safe Stream Parser
                        packets, consumed = Packet.parse_stream_safe(bytes(buffer))

                        # Ghi nhận byte rác hoặc byte ngoài khung nếu có
                        if consumed > 0:
                            # Cắt bỏ các byte đã parse an toàn, GIỮ LẠI gói dở dang ở cuối
                            processed_slice = bytes(buffer[:consumed])
                            del buffer[:consumed]

                            # Kiểm tra xem có byte rác trước gói tin đầu tiên không
                            if not packets and consumed > 0:
                                self.stats.unframed_bytes += consumed
                                self.tech_logger.log_unframed(processed_slice)

                        for pkt in packets:
                            self.stats.rx_packets += 1
                            self.tech_logger.log_rx(pkt, pkt.encode())
                            self._handle_incoming_packet(pkt)

            except (serial.SerialException, OSError) as e:
                # Phát hiện lỗi phần cứng USB (rút cáp, mất nguồn, brownout reset)
                now_ts = time.time()
                self.stats.disconnect_count += 1
                self.stats.last_disconnect_time = now_ts
                self.stats.last_disconnect_reason = f"{type(e).__name__}: {e}"

                self.tech_logger.log_error(
                    "SERIAL_DISCONNECT",
                    f"PHÁT HIỆN ĐỨT KẾT NỐI VẬT LÝ / LỖI USB! Chi tiết: {self.stats.last_disconnect_reason}",
                )

                if self._disconnect_callback:
                    try:
                        self._disconnect_callback(self.stats.last_disconnect_reason)
                    except Exception as cb_err:
                        self.tech_logger.log_error("CB_ERR", f"Lỗi trong disconnect_callback: {cb_err}")

                self._stop_event.set()
                try:
                    if self._serial is not None:
                        self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self._opened = False
                break

            except Exception as e:
                self.tech_logger.log_error("READ_UNEXPECTED", f"Ngoại lệ không mong muốn trong read loop: {e}")

            time.sleep(0.005)

        self.tech_logger.log_event("THREAD_EXIT", "Luồng đọc Serial (Read Thread) đã kết thúc.")

    def _handle_incoming_packet(self, pkt: Packet) -> None:
        """Điều phối gói tin nhận được."""
        # Phản hồi cho lệnh đang chờ (Sync commands)
        if pkt.is_ack or pkt.is_nack or pkt.is_error or pkt.is_pong or pkt.is_telemetry:
            self._last_response = pkt
            self._response_event.set()
            return

        # Nút bấm (BTN_STATE)
        if pkt.is_btn_state:
            self._packet_queue.put(pkt)
            btn_name = pkt.button or "UNKNOWN"
            if self._button_callback:
                try:
                    self._button_callback(btn_name)
                except Exception as e:
                    self.tech_logger.log_error("BTN_CB_ERR", f"Lỗi trong button_callback: {e}")
            return

        # Tín hiệu khởi động game từ Arduino (RESP_GAME_START)
        if pkt.is_game_start:
            self._packet_queue.put(pkt)
            game_params = {
                "backlight": bool(pkt.data[0]) if len(pkt.data) >= 1 else True,
                "difficulty": pkt.data[1] if len(pkt.data) >= 2 else 1,
            }
            self.tech_logger.log_event(
                "GAME_START_REQ",
                f"Arduino kích hoạt Game PC! Backlight={game_params['backlight']}, Difficulty={game_params['difficulty']}",
            )
            if self._game_start_callback:
                try:
                    self._game_start_callback(game_params)
                except Exception as e:
                    self.tech_logger.log_error("GAME_CB_ERR", f"Lỗi trong game_start_callback: {e}")
            return

        # Tin nhắn Debug từ Arduino (RESP_DEBUG_LOG)
        if pkt.is_debug_log:
            try:
                log_txt = pkt.data.decode("utf-8", errors="replace")
                self.tech_logger.log("ARDUINO", f"[Log từ Arduino OS] {log_txt}")
            except Exception:
                pass
            return

        # Các gói tin khác đưa vào hàng đợi
        self._packet_queue.put(pkt)
        # Nếu là tín hiệu khởi động từ Arduino OS (RESP_OS_BOOT 0x95 hoặc CMD_REQ_SETTINGS 0x08), đánh thức _wait_for_ack ngay
        if pkt.cmd in (0x95, 0x08):
            self._last_response = pkt
            self._response_event.set()

    # ------------------------------------------------------------------
    # Gửi lệnh & gói tin (Send / Diagnostics)
    # ------------------------------------------------------------------
    def send_packet(self, packet: Packet) -> None:
        """Gửi một Packet qua Serial kèm kiểm tra lỗi và ghi log chi tiết."""
        if not self.is_open:
            err_msg = "Không thể gửi dữ liệu: Cổng Serial chưa mở hoặc đã bị đứt kết nối!"
            self.tech_logger.log_error("TX_FAILED", err_msg)
            raise SerialConnectionError(err_msg)

        data = packet.encode()
        with self._lock:
            try:
                self._serial.write(data)
                self.stats.tx_bytes += len(data)
                self.stats.tx_packets += 1
                self.stats.last_tx_time = time.time()
                self.tech_logger.log_tx(packet, data)
            except (serial.SerialException, OSError) as e:
                err_msg = f"Lỗi ghi dữ liệu ra Serial (có thể cổng đã bị ngắt): {e}"
                self.tech_logger.log_error("TX_ERROR", err_msg)
                self._stop_event.set()
                try:
                    if self._serial is not None:
                        self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self._opened = False
                raise SerialConnectionError(err_msg) from e

    def send_command(
        self,
        cmd: int,
        data: bytes = b"",
        wait_response: bool = True,
        timeout: Optional[float] = None,
    ) -> Optional[Packet]:
        """Gửi lệnh và chờ phản hồi với cơ chế timeout chi tiết."""
        pkt = Packet(cmd=cmd, data=data)
        self.send_packet(pkt)

        if not wait_response:
            return None

        timeout = timeout if timeout is not None else self.timeout
        self._response_event.clear()
        self._last_response = None

        got = self._response_event.wait(timeout=timeout)
        if not got:
            err_msg = f"Hết thời gian chờ (Timeout {timeout}s) không nhận phản hồi từ Arduino cho {pkt.name}"
            self.tech_logger.log_error("TIMEOUT", err_msg)
            raise TimeoutError(err_msg)

        resp = self._last_response
        if resp is None:
            raise TimeoutError(f"Sự kiện phản hồi kích hoạt nhưng không có gói tin cho {pkt.name}")

        if resp.is_nack:
            err_msg = f"Arduino trả về NACK (từ chối lệnh / sai checksum) cho {pkt.name}"
            self.tech_logger.log_error("NACK", err_msg)
            raise CommandError(err_msg)

        if resp.is_error:
            err_code = resp.data[0] if resp.data else 0x00
            err_msg = f"Arduino trả về ERROR (mã 0x{err_code:02X}) cho {pkt.name}"
            self.tech_logger.log_error("CMD_ERR", err_msg)
            raise CommandError(err_msg)

        return resp

    # ------------------------------------------------------------------
    # Công cụ chẩn đoán kỹ thuật nâng cao (Ping / Telemetry / Health)
    # ------------------------------------------------------------------
    def ping(self, timeout: float = 1.0) -> Optional[float]:
        """
        Đo độ trễ khứ hồi (Round Trip Time - RTT) đến Arduino tính bằng millisecond.
        Trả về None nếu timeout hoặc thất bại.
        """
        send_ts = time.time()
        # Chuyển timestamp (mod 2^32) thành 4 bytes
        ts_bytes = (int(send_ts * 1000) & 0xFFFFFFFF).to_bytes(4, "little", signed=False)

        try:
            resp = self.send_command(CMD_PING, ts_bytes, wait_response=True, timeout=timeout)
            if resp and resp.is_pong:
                rtt_ms = (time.time() - send_ts) * 1000.0
                self.stats.last_rtt_ms = rtt_ms
                self.tech_logger.log_event("PING_OK", f"Round-Trip Latency: {rtt_ms:.2f} ms")
                return rtt_ms
        except Exception as e:
            self.tech_logger.log_error("PING_FAILED", f"Lỗi ping: {e}")
        return None

    def get_telemetry(self, timeout: float = 1.5) -> Optional[Dict[str, Any]]:
        """
        Yêu cầu Arduino báo cáo tình trạng phần cứng thời gian thực.
        """
        try:
            resp = self.send_command(CMD_GET_TELEMETRY, wait_response=True, timeout=timeout)
            if resp and resp.is_telemetry and len(resp.data) >= 9:
                uptime = int.from_bytes(resp.data[0:2], "little")
                free_ram = int.from_bytes(resp.data[2:4], "little")
                rx_count = int.from_bytes(resp.data[4:6], "little")
                crc_err = resp.data[6]
                a0_val = int.from_bytes(resp.data[7:9], "little")
                state = resp.data[9] if len(resp.data) >= 10 else 0
                last_err = resp.data[10] if len(resp.data) >= 11 else 0

                telemetry = {
                    "uptime_seconds": uptime,
                    "free_ram_bytes": free_ram,
                    "rx_packets_arduino": rx_count,
                    "crc_errors_arduino": crc_err,
                    "analog_a0_raw": a0_val,
                    "arduino_state": state,
                    "last_error_code": last_err,
                }
                self.tech_logger.log_event("TELEMETRY", f"Arduino Telemetry: {telemetry}")
                return telemetry
        except Exception as e:
            self.tech_logger.log_error("TELEMETRY_ERR", f"Lỗi lấy telemetry: {e}")
        return None

    def get_diagnostics_report(self) -> str:
        """Xuất báo cáo chẩn đoán tình trạng đường truyền dạng văn bản chi tiết."""
        stats = self.stats.to_dict()
        thread_status = "ĐANG CHẠY TỐT" if self.is_read_thread_alive else "ĐÃ DỪNG / LỖI"
        port_status = "MỞ" if self.is_open else "ĐÓNG / MẤT KẾT NỐI"

        report = [
            "================ BÁO CÁO CHẨN ĐOÁN KỸ THUẬT SERIAL ================",
            f"  - Cổng Serial: {self.port} | Baudrate: {self.baudrate} | Trạng thái: {port_status}",
            f"  - Luồng đọc nền (Read Thread): {thread_status}",
            f"  - Tổng gói đã gửi (TX Packets): {stats['tx_packets']} ({stats['tx_bytes']} bytes)",
            f"  - Tổng gói đã nhận (RX Packets): {stats['rx_packets']} ({stats['rx_bytes']} bytes)",
            f"  - Lỗi Checksum / Frame hỏng: {stats['crc_errors']} / {stats['corrupted_frames']}",
            f"  - Số lần ngắt kết nối vật lý (Disconnect Count): {stats['disconnect_count']}",
            f"  - Lý do ngắt kết nối gần nhất: {stats['last_disconnect_reason']}",
            f"  - Độ trễ Ping gần nhất: {stats['last_rtt_ms']} ms",
            f"  - Thời gian kể từ gói RX cuối: {stats['seconds_since_last_rx']} giây",
            f"  - File log chi tiết: {self.tech_logger.log_path}",
            "===================================================================",
        ]
        return "\n".join(report)

    # ------------------------------------------------------------------
    # Callbacks & Quản lý nút bấm
    # ------------------------------------------------------------------
    def set_button_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        self._button_callback = callback

    def set_game_start_callback(self, callback: Optional[Callable[[dict], None]]) -> None:
        self._game_start_callback = callback

    def set_disconnect_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        self._disconnect_callback = callback

    def get_last_button(self, timeout: float = 0.1) -> Optional[str]:
        try:
            pkt = self._packet_queue.get(timeout=timeout)
            return pkt.button
        except queue.Empty:
            return None

    def drain_buttons(self) -> List[str]:
        results: List[str] = []
        while True:
            try:
                pkt = self._packet_queue.get_nowait()
                name = pkt.button
                if name:
                    results.append(name)
            except queue.Empty:
                break
        return results

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "SerialLink":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
