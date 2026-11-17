"""
LCDKeypadEngine - Thư viện Python điều khiển LCD Keypad Shield qua Arduino.

API cao cấp, ẩn toàn bộ giao thức binary. Phù hợp cho các dự án cần
điều khiển LCD và đọc nút bấm từ Python với độ trễ thấp (real-time).

Sử dụng:
    from lcd_keypad_engine import LCDKeypadEngine

    engine = LCDKeypadEngine(port="COM3")
    engine.print_line1("Xin chao!")
    engine.print_line2("Nhan nut UP")

    while True:
        btn = engine.wait_for_button(timeout=1.0)
        if btn == "UP":
            engine.print_line1("Ban da nhan UP")
            break
"""

import logging
import threading
import time
from typing import Optional, Callable, List

from .serial_link import SerialLink
from .protocol import (
    CMD_LCD_LINE1, CMD_LCD_LINE2, CMD_LCD_CLEAR, CMD_READ_BTN, CMD_SET_BACKLIGHT,
    RESP_ACK, RESP_BTN_STATE,
    BTN_NONE, BTN_RIGHT, BTN_UP, BTN_DOWN, BTN_LEFT, BTN_SELECT,
    BUTTON_NAMES,
)
from .exceptions import (
    LCDKeypadError, SerialConnectionError, CommandError, TimeoutError,
)

logger = logging.getLogger("lcd_keypad_engine")


class LCDKeypadEngine:
    """
    Engine chính điều khiển LCD Keypad Shield qua Arduino Uno R3.

    Parameters
    ----------
    port : str, optional
        Cổng serial (ví dụ "COM3"). Nếu None sẽ tự động quét tìm Arduino.
    baudrate : int
        Tốc độ baud (mặc định 115200).
    timeout : float
        Timeout chờ phản hồi từ Arduino (giây).
    auto_open : bool
        Nếu True, tự động mở kết nối khi khởi tạo.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 2.0,
        auto_open: bool = True,
        console_debug: bool = False,
    ):
        self._link = SerialLink(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            auto_open=auto_open,
            console_debug=console_debug,
        )
        self._button_callback: Optional[Callable[[str], None]] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._last_button: str = "NONE"
        self._last_button_lock = threading.Lock()
        self._opened = auto_open

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._link.is_open

    def open(self) -> None:
        """Mở kết nối đến Arduino."""
        self._link.open()
        self._opened = True

    def close(self) -> None:
        """Đóng kết nối và dừng tất cả luồng nền."""
        self.stop_button_monitoring()
        self._link.close()
        self._opened = False

    def __enter__(self) -> "LCDKeypadEngine":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # LCD control
    # ------------------------------------------------------------------
    def print_line1(self, text: str) -> None:
        """
        Viết text lên hàng 1 của LCD (tối đa 16 ký tự).

        Nếu text dài hơn 16 ký tự sẽ bị cắt. Nếu ngắn hơn sẽ được đệm
        khoảng trắng để xóa ký tự cũ.
        """
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        # Cắt và encode
        encoded = text[:16].encode("utf-8", errors="replace")
        self._link.send_command(CMD_LCD_LINE1, encoded, wait_response=True)
        logger.debug("In hang 1: %r", text)

    def print_line2(self, text: str) -> None:
        """
        Viết text lên hàng 2 của LCD (tối đa 16 ký tự).
        """
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        encoded = text[:16].encode("utf-8", errors="replace")
        self._link.send_command(CMD_LCD_LINE2, encoded, wait_response=True)
        logger.debug("In hang 2: %r", text)

    def clear(self) -> None:
        """Xóa toàn bộ màn hình LCD."""
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        self._link.send_command(CMD_LCD_CLEAR, wait_response=True)
        logger.debug("Xoa man hinh LCD")

    def set_backlight(self, on: bool = True) -> None:
        """
        Bật/tắt đèn nền LCD (nếu shield hỗ trợ chân backlight).

        Parameters
        ----------
        on : bool
            True = bật, False = tắt.
        """
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        self._link.send_command(CMD_SET_BACKLIGHT, bytes([1 if on else 0]), wait_response=True)

    # ------------------------------------------------------------------
    # Button reading
    # ------------------------------------------------------------------
    def read_button(self, timeout: float = 0.1) -> str:
        """
        Đọc trạng thái nút bấm hiện tại.

        Parameters
        ----------
        timeout : float
            Thời gian chờ (giây) nếu chưa có sự kiện nút mới.

        Returns
        -------
        str
            Tên nút bấm: "NONE", "RIGHT", "UP", "DOWN", "LEFT", "SELECT".
        """
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        # Chờ phản hồi BTN_STATE từ Arduino (Arduino tự động gửi khi nút thay đổi)
        pkt = self._link._packet_queue.get(timeout=timeout)  # noqa: SLF001
        btn_name = pkt.button
        if btn_name is None:
            raise LCDKeypadError(f"Nhận gói không phải BTN_STATE: {pkt!r}")

        with self._last_button_lock:
            self._last_button = btn_name
        return btn_name

    def wait_for_button(self, timeout: Optional[float] = None) -> str:
        """
        Chờ cho đến khi có nút bấm được nhấn (khác NONE).

        Parameters
        ----------
        timeout : float, optional
            Thời gian tối đa chờ (giây). Nếu None, chờ vĩnh viễn.

        Returns
        -------
        str
            Tên nút bấm được nhấn.

        Raises
        ------
        TimeoutError
            Nếu không có nút nào được nhấn trong thời gian quy định.
        """
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        start = time.time()
        while True:
            remaining = None if timeout is None else max(0.0, timeout - (time.time() - start))
            if remaining is not None and remaining <= 0:
                raise TimeoutError(f"Không có nút nào được nhấn trong {timeout} giây")

            try:
                btn = self.read_button(timeout=min(remaining, 0.1) if remaining else 0.1)
            except TimeoutError:
                # read_button timeout thì tiếp tục loop
                if timeout is not None and time.time() - start >= timeout:
                    raise
                continue

            if btn != "NONE":
                return btn

    def wait_for_button_release(self, timeout: Optional[float] = None) -> None:
        """
        Chờ cho đến khi nút bấm được nhả (trở về NONE).
        """
        if not self.is_open:
            raise SerialConnectionError("Kết nối chưa mở. Gọi engine.open() trước.")

        start = time.time()
        while True:
            remaining = None if timeout is None else max(0.0, timeout - (time.time() - start))
            if remaining is not None and remaining <= 0:
                raise TimeoutError("Nút bấm vẫn đang được nhấn sau timeout")

            try:
                btn = self.read_button(timeout=min(remaining, 0.1) if remaining else 0.1)
            except TimeoutError:
                if timeout is not None and time.time() - start >= timeout:
                    raise
                continue

            if btn == "NONE":
                return

    @property
    def last_button(self) -> str:
        """Trả về tên nút bấm lần cuối được ghi nhận."""
        with self._last_button_lock:
            return self._last_button

    def get_button_history(self) -> List[str]:
        """Lấy và xóa toàn bộ lịch sử sự kiện nút bấm đang xếp hàng."""
        return self._link.drain_buttons()

    # ------------------------------------------------------------------
    # Button monitoring (background)
    # ------------------------------------------------------------------
    def set_button_callback(self, callback: Callable[[str], None]) -> None:
        """
        Đăng ký hàm callback được gọi khi trạng thái nút bấm thay đổi.

        callback nhận một tham số: tên nút bấm (ví dụ "UP", "NONE").
        """
        self._button_callback = callback
        self._link.set_button_callback(callback)

    def start_button_monitoring(self, poll_interval: float = 0.05) -> None:
        """
        Bắt đầu theo dõi nút bấm trong luồng nền.

        Khi nút bấm thay đổi, callback sẽ được gọi (nếu đã đăng ký).
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            return  # Đang chạy

        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(poll_interval,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Da bat dau monitoring nut bam (khoang cach %.3fs)", poll_interval)

    def stop_button_monitoring(self) -> None:
        """Dừng luồng theo dõi nút bấm."""
        self._monitor_stop.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
        self._monitor_thread = None

    def _monitor_loop(self, poll_interval: float) -> None:
        """Vòng lặp nền: đọc nút bấm định kỳ và gọi callback khi có thay đổi."""
        while not self._monitor_stop.is_set():
            try:
                if self.is_open:
                    btn = self.read_button(timeout=0.05)
                    with self._last_button_lock:
                        prev = self._last_button
                    if btn != prev:
                        with self._last_button_lock:
                            self._last_button = btn
                        if self._button_callback:
                            try:
                                self._button_callback(btn)
                            except Exception as e:  # noqa: BLE001
                                logger.error("Loi trong button callback: %s", e)
            except Exception as e:  # noqa: BLE001
                logger.debug("Loi trong monitor loop: %s", e)

            self._monitor_stop.wait(poll_interval)

    # ------------------------------------------------------------------
    # Convenience: display + button
    # ------------------------------------------------------------------
    def show_message(self, line1: str, line2: str = "") -> None:
        """Hiển thị thông báo lên hai hàng LCD."""
        self.print_line1(line1)
        if line2:
            self.print_line2(line2)

    def wait_for_any_button(self, timeout: Optional[float] = None) -> str:
        """Đồng thời với wait_for_button (alias)."""
        return self.wait_for_button(timeout=timeout)

    # ------------------------------------------------------------------
    # Technical Diagnostics & Health Monitoring
    # ------------------------------------------------------------------
    def ping(self, timeout: float = 1.0) -> Optional[float]:
        """Đo độ trễ khứ hồi Ping/RTT (ms) đến Arduino."""
        return self._link.ping(timeout=timeout)

    def get_telemetry(self, timeout: float = 1.5) -> Optional[dict]:
        """Lấy telemetry trạng thái phần cứng (RAM, Uptime, lỗi CRC, ADC A0) từ Arduino."""
        return self._link.get_telemetry(timeout=timeout)

    def get_diagnostics_report(self) -> str:
        """Xuất báo cáo chi tiết kỹ thuật về đường truyền."""
        return self._link.get_diagnostics_report()

    def reconnect(self) -> bool:
        """Kết nối lại cổng Serial."""
        return self._link.reconnect()

    def __repr__(self) -> str:
        return f"LCDKeypadEngine(port={self._link.port!r}, open={self.is_open})"


# ----------- Module-level quick API (dùng nhanh không cần tạo class) -----------
_default_engine: Optional[LCDKeypadEngine] = None


def quick_engine(port: Optional[str] = None, **kwargs) -> LCDKeypadEngine:
    """
    Tạo (hoặc trả lại) engine mặc định singleton.
    """
    global _default_engine
    if _default_engine is None or not _default_engine.is_open:
        _default_engine = LCDKeypadEngine(port=port, **kwargs)
    return _default_engine


def quick_print(line1: str, line2: str = "", port: Optional[str] = None) -> None:
    """In nhanh thông báo lên LCD qua engine mặc định."""
    eng = quick_engine(port=port)
    eng.print_line1(line1)
    if line2:
        eng.print_line2(line2)


def quick_clear(port: Optional[str] = None) -> None:
    """Xóa màn hình LCD qua engine mặc định."""
    eng = quick_engine(port=port)
    eng.clear()