# CẨM NANG PHÁT TRIỂN & TÀI LIỆU KỸ THUẬT TOÀN DIỆN
# HỆ SINH THÁI ACNG — ARDUINO LCD OS & PYTHON COORDINATOR

> **Repository**: `ACNG`  
> **Tốc độ truyền chuẩn**: 115200 Baud (Ping RTT ~3.6ms - 7.6ms, 0.0% Packet Loss)  
> **Nền tảng hỗ trợ**: Linux (Kali Linux, Raspberry Pi OS, Debian, Ubuntu) & Windows 10/11  
> **Phần cứng mục tiêu**: Arduino Uno R3 (ATmega328P 16MHz, 32KB Flash, 2KB SRAM) & DFRobot LCD 16x2 Keypad Shield  
> **Ngôn ngữ**: C++11 (Arduino Firmware) & Python 3.10+ (Coordinator & Serial Engine)

---

## MỤC LỤC
1. [Tổng Quan Kiến Trúc Hệ Thống](#1-tổng-quan-kiến-trúc-hệ-thống)
2. [Sơ Đồ Phần Cứng & Mạch Phân Áp Nút Bấm A0](#2-sơ-đồ-phần-cứng--mạch-phân-áp-nút-bấm-a0)
3. [Cấu Trúc Repository & Thiết Kế Module Hóa](#3-cấu-trúc-repository--thiết-kế-module-hóa)
4. [Cơ Chế Bắt Tay Khởi Động & Lưu Trữ Hai Tầng](#4-cơ-chế-bắt-tay-khởi-động--lưu-trữ-hai-tầng)
5. [Kiến Trúc Các Ứng Dụng Cốt Lõi (AirCrack, WiFi Set, Keyboard, Settings)](#5-kiến-trúc-các-ứng-dụng-cốt-lõi)
6. [Bảng Mã Lệnh Giao Thức Nhị Phân 115200 Baud](#6-bảng-mã-lệnh-giao-thức-nhị-phân-115200-baud)
7. [Hướng Dẫn Phát Triển & Đăng Ký App Mới](#7-hướng-dẫn-phát-triển--đăng-ký-app-mới)
8. [Các Tối Ưu Hóa Kỹ Thuật Quan Trọng Trên ATmega328P](#8-các-tối-ưu-hóa-kỹ-thuật-quan-trọng-trên-atmega328p)

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG

Hệ thống được thiết kế theo mô hình **Hybrid Embedded OS**: giao diện hiển thị LCD 16x2, máy trạng thái (State Machine) và xử lý nút bấm thời gian thực chạy trực tiếp trên vi điều khiển **Arduino Uno R3**, trong khi các tác vụ hệ thống Linux, quản lý card mạng (`nmcli`, `iw`), bắt gói tin (`airodump-ng`, `aireplay-ng`, `hcxpcapngtool`) và đồng bộ Server được điều phối bởi **`python/console_coordinator.py`**.

```text
+-----------------------------------------------------------------------------------------------+
|                                   PYTHON COORDINATOR LAYER                                    |
|                                                                                               |
|   [os_settings.json] <======> [console_coordinator.py] <======> [Network / Wireless Tools]    |
|   [known_wifi.json]           (Central Coordinator Daemon)      (nmcli, iw, aircrack-ng,      |
|                                             |                    hcxpcapngtool, HTTP Client)  |
+---------------------------------------------+-------------------------------------------------+
                                              ||
                                              ||  UART Serial @ 115200 Baud
                                              ||  Khung tin nhị phân: 0xAA [LEN] [CMD] [DATA] [XOR] 0xBB
                                              ||
+---------------------------------------------+-------------------------------------------------+
|                                      ARDUINO LCD OS LAYER                                     |
|                                                                                               |
|     [AirCrackApp]          [WifiSetApp]           [KeyboardApp]          [SettingsApp]        |
|     (AppId: 0x09)          (AppId: 0x07)          (AppId: 0x08)          (AppId: 0x03)        |
|           \                      |                      |                      /              |
|            +---------------------+----------------------+---------------------+               |
|                                                 |                                             |
|                                      [AppService Interface]                                   |
|                                                 |                                             |
|                                         [LCDKeypadOS Core]                                    |
|                        (Menu Router, Settings Sync, Inter-App Navigation, EEPROM)             |
|                                                 |                                             |
|                                         [LCDKeypadDriver]                                     |
|                              (LiquidCrystal 4-bit mode, Debounce ADC A0)                      |
+-----------------------------------------------------------------------------------------------+
```

---

## 2. SƠ ĐỒ PHẦN CỨNG & MẠCH PHÂN ÁP NÚT BẤM A0

### 2.1. Sơ đồ kết nối chân (Pinout Mapping)
Shield LCD Keypad DFRobot cắm trực tiếp lên Arduino Uno R3:
- **Chân điều khiển LCD (HD44780 4-bit mode)**: `D4`, `D5`, `D6`, `D7`, `D8` (`RS`), `D9` (`EN`), `D10` (`Backlight`).
- **Chân nút bấm**: Cả 5 nút bấm vật lý nối vào chân **`Analog A0`** qua cầu phân áp điện trở.

### 2.2. Bảng ngưỡng ADC chân A0

| Nút Bấm | Điện áp thực tế | Giá trị ADC chuẩn | Ngưỡng phần mềm | Mã KeyCode | Mã Giao Thức |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RIGHT**  | ~0.00 V | 0    | `ADC < 60`   | `KEY_RIGHT`  | `0x01` |
| **UP**     | ~0.71 V | 145  | `ADC < 200`  | `KEY_UP`     | `0x02` |
| **DOWN**   | ~1.61 V | 329  | `ADC < 400`  | `KEY_DOWN`   | `0x03` |
| **LEFT**   | ~2.47 V | 505  | `ADC < 600`  | `KEY_LEFT`   | `0x04` |
| **SELECT** | ~3.62 V | 741  | `ADC < 800`  | `KEY_SELECT` | `0x05` |
| **NONE**   | ~5.00 V | 1023 | `ADC >= 800` | `KEY_NONE`   | `0x00` |

> **Chống trôi áp khi nhả phím `SELECT`**: Khi vào mỗi App hoặc chuyển màn hình con, hệ thống áp dụng khoảng đệm an toàn `350ms` (`if (now - _enterTime < 350) return;`), triệt tiêu hoàn toàn xung sụt áp quét qua vùng `LEFT` khi người dùng nhả nút `SELECT`.

---

## 3. CẤU TRÚC REPOSITORY & THIẾT KẾ MODULE HÓA

```text
ACNG/
├── arduino/
│   └── ArduinoLCDOS/
│       ├── ArduinoLCDOS.ino                # Điểm vào Firmware: đăng ký các App & khởi chạy OS
│       ├── build.bat                       # Biên dịch firmware ra thư mục build/
│       ├── sync.bat                        # Chạy sync.py đồng bộ sang Raspberry Pi
│       └── src/
│           ├── core/
│           │   ├── AppService.h/.cpp       # Giao diện chuẩn cho mọi ứng dụng
│           │   ├── LCDKeypadDriver.h/.cpp  # Điều khiển LCD 16x2 & lọc dội phím A0
│           │   ├── LCDKeypadOS.h/.cpp      # Quản lý vòng đời App, chuyển tiếp gói tin Serial & EEPROM
│           │   └── MenuAppService.h/.cpp   # Lớp cơ sở tạo menu cuộn
│           └── apps/
│               ├── AirCrackApp/            # [0x09] Kiểm thử WiFi, bắt Handshake, chuyển đổi & gửi crack .hc22000
│               ├── WifiSetApp/             # [0x07] Quét WiFi, quản lý Known WiFi & chế độ Card mạng
│               ├── KeyboardApp/            # [0x08] Bàn phím ảo 16x2 dùng chung giữa các App
│               ├── SettingsApp/            # [0x03] Cài đặt hệ thống & Reset 2 bước
│               ├── NativeGameApp/          # [0x01] Mini-game offline (Module mở rộng)
│               ├── PyBridgeApp/            # [0x02] Kiểm thử cầu nối PC (Module mở rộng)
│               ├── CounterApp/             # [0x04] Bộ đếm lưu EEPROM (Module mở rộng)
│               ├── WifiPbApp/              # [0x05] Điều khiển Hotspot AP (Module mở rộng)
│               └── LinuxInfApp/            # [0x06] Kiểm tra quyền sudo -l & Linux Info (Module mở rộng)
├── python/
│   ├── console_coordinator.py              # Dịch vụ điều phối trung tâm trên Linux/Windows
│   ├── os_settings.json                    # Lưu trữ cấu hình hệ thống & từng App
│   ├── server_display.py                   # Giao diện hiển thị trên Desktop
│   └── lcd_keypad_engine/                  # Thư viện giao tiếp Serial nhị phân 115200 baud
├── server_wifi/
│   ├── main.py                             # FastAPI Server (:9000) giải mã .hc22000 bằng Hashcat & IEEE 802.11i
│   ├── requirements.txt                    # Thư viện phụ thuộc (fastapi, uvicorn, python-multipart)
│   └── README.md                           # Hướng dẫn đặt thư mục hashcat/ và rockyou.txt
├── tools/
│   ├── upload_firmware.py                  # Tự động biên dịch & nạp code qua arduino-cli
│   └── diagnose_connection.py              # Đo kiểm Ping RTT & Telemetry
└── sync.py                                 # Đồng bộ mã nguồn qua SFTP (đọc cấu hình từ biến môi trường)
```

---

## 4. CƠ CHẾ BẮT TAY KHỞI ĐỘNG & LƯU TRỮ HAI TẦNG

1. **Bắt tay 2 giây khi khởi động (`Boot Handshake`)**:
   - Khi cấp nguồn hoặc Reset, Arduino nạp cấu hình dự phòng từ EEPROM, gửi `RESP_OS_BOOT (0x95)` và `CMD_REQ_SETTINGS (0x08)` lên Python Coordinator.
   - Nếu Coordinator đang chạy, nó đọc `python/os_settings.json` và trả về `RESP_SETTINGS (0x88)` trong `< 10ms`. Arduino áp dụng cài đặt đèn nền, âm thanh và phân phối cấu hình riêng cho từng App qua `loadSettings()`.
   - Nếu sau `2000ms` không có phản hồi (chạy Offline bằng nguồn rời), Arduino tự động vào Menu Tổng với dữ liệu trong EEPROM.
2. **Lưu trữ hai tầng (EEPROM + JSON)**:
   - Mọi thay đổi cài đặt trong App khi gọi `saveSetting(data, len)` đều được ghi đồng thời vào **EEPROM nội bộ** (địa chỉ `10 + AppId * 8`) và gửi gói `CMD_SAVE_SETTINGS (0x09)` lên Python để lưu vào `python/os_settings.json`.

---

## 5. KIẾN TRÚC CÁC ỨNG DỤNG CỐT LÕI

### 5.1. Liên kết liên ứng dụng (`Inter-App IPC`) với `KeyboardApp` (AppId `0x08`)
`LCDKeypadOS` cung cấp cơ chế chuyển ngữ cảnh giữa các App mà không cần quay về Menu Tổng:
- **`WifiSetApp` -> `KeyboardApp`**:
  - Khi người dùng chọn một mạng WiFi trong `Scan WiFi`:
    - Nếu mạng đã có trong `Known WiFi` (`knownFlag == 1`), `WifiSetApp` gửi thẳng lệnh `CMD_WIFI_CONNECT (0x3D)` kèm mật khẩu rỗng để Python tự tra mật khẩu đã lưu và kết nối ngay.
    - Nếu mạng chưa có trong `Known WiFi`, `WifiSetApp` gọi `KeyboardApp::setupForWifi(ssid, returnAppIndex)` và chuyển sang `KeyboardApp`. Sau khi người dùng bấm `OK`, `KeyboardApp` gửi `CMD_WIFI_CONNECT (0x3D)` kèm `SSID\tPassword` và tự động mở lại `WifiSetApp` ở màn hình chờ kết quả kết nối.
- **`AirCrackApp` -> `KeyboardApp`**:
  - Khi chọn mục `12.Server IP`, `AirCrackApp` gọi `KeyboardApp::setupForServerIp(currentServerIp, returnAppIndex)` để điền sẵn IP hiện tại lên màn hình bàn phím cho phép chỉnh sửa.
  - Khi người dùng bấm `OK` trên `KeyboardApp`:
    - Nếu chuỗi nhập vào bị xóa trống, `AirCrackApp::setServerIp("")` tự động khôi phục về IP mặc định `169.254.84.122`.
    - Đồng thời gửi `CMD_AIRCRACK_SET_SERVER (0x45)` lên Python Coordinator để lưu đồng bộ vào `os_settings.json`.

### 5.2. Luồng xử lý `AirCrackApp` (AppId `0x09`) & `console_coordinator.py`
- **Quản lý Card & Mode**: Tự động liệt kê danh sách card không dây thực tế (`iw dev`), cho phép chọn card bất kỳ (`wlan0`, `wlan1`...) và chuyển đổi `Managed` / `Monitor` độc lập.
- **Quét AP & Bắt Handshake**:
  - Hỗ trợ quét AP ở cả chế độ `Monitor` (`airodump-ng` CSV) và `Managed` (`nmcli` / `iw`).
  - Khi chạy `Capture HS`, Python khởi chạy tiến trình nền `airodump-ng --bssid <BSSID> --channel <CH> --write cap_<name> --output-format pcap` và bắn gói `aireplay-ng --deauth` để thu thập EAPOL Handshake.
- **Chuyển đổi & Giải mã trên Server**:
  - `Cap->HC22000` chạy `hcxpcapngtool` để trích xuất thông tin xác thực WPA/WPA2 ra file `.hc22000` lưu tại `python/aircrack_files/`.
  - `Send Hash` tải file `.hc22000` được chọn lên Server qua `POST /upload` và gọi `POST /hash`. Nếu tìm thấy mật khẩu, Coordinator tự động lưu cặp `(SSID, password)` vào `known_wifi.json` và trả kết quả `PW:<password>` về hiển thị trên màn hình LCD 16x2.

---

## 6. BẢNG MÃ LỆNH GIAO THỨC NHỊ PHÂN 115200 BAUD

### 6.1. Cấu trúc khung tin (Framed Packet)
```text
+------------+------------+------------+--------------------+------------+------------+
| START BYTE | LENGTH (L) |  CMD/RESP  |    PAYLOAD DATA    |  CHECKSUM  |  END BYTE  |
|    0xAA    |   1 Byte   |   1 Byte   |    0..60 Bytes     |   1 Byte   |    0xBB    |
+------------+------------+------------+--------------------+------------+------------+
```
- `LENGTH = 1 (CMD/RESP) + len(PAYLOAD) + 1 (CHECKSUM)`
- `CHECKSUM = CMD ^ PAYLOAD[0] ^ PAYLOAD[1] ^ ... ^ PAYLOAD[n-1]`

### 6.2. Bảng mã lệnh chi tiết

| Mã Hex | Tên Lệnh / Phản Hồi | Hướng | Payload | Mô tả chức năng |
| :---: | :--- | :---: | :--- | :--- |
| `0x05` | `CMD_SET_BACKLIGHT` | PC <-> Arduino | `[0x00/0x01]` | Bật / tắt đèn nền LCD |
| `0x06` | `CMD_PING` | PC -> Arduino | `Timestamp (4B)` | Kiểm tra kết nối & đo độ trễ RTT |
| `0x07` | `CMD_GET_TELEMETRY` | PC -> Arduino | Trống | Yêu cầu báo cáo Free RAM, Uptime, ADC |
| `0x08` | `CMD_REQ_SETTINGS` | Arduino -> PC | Trống | Yêu cầu nạp cài đặt khi khởi động |
| `0x09` | `CMD_SAVE_SETTINGS` | Arduino -> PC | `[AppId, Data...]` | Lưu cài đặt của App lên `os_settings.json` |
| `0x0A` | `CMD_RESET_ALL_SETTINGS` | Arduino -> PC | Trống | Khôi phục cài đặt gốc toàn hệ thống |
| `0x32` | `CMD_WIFI_SET_MODE` | Arduino -> PC | `[Mode]` | Đổi chế độ hoạt động WiFi tổng |
| `0x33` | `CMD_REQ_WIFI_SCAN_ITEM` | Arduino -> PC | `[Index]` | Yêu cầu thông tin mạng WiFi quét được thứ `Index` |
| `0x34` | `CMD_REQ_WIFI_KNOWN_ITEM`| Arduino -> PC | `[Index]` | Yêu cầu thông tin mạng Known WiFi thứ `Index` |
| `0x37` | `CMD_AIRCRACK_SET_CARD` | Arduino -> PC | `[CardIdx, Mode]` | Chọn card mạng & đổi chế độ trong `AirCrack` |
| `0x38` | `CMD_AIRCRACK_ACTION` | Arduino -> PC | `[ActionId, Extra]` | Thực thi tác vụ `AirCrack` (`0x01`..`0x08`) |
| `0x39` | `CMD_REQ_AIRCRACK_SCAN_ITEM` | Arduino -> PC | `[Index]` | Yêu cầu thông tin AP quét được thứ `Index` |
| `0x3A` | `CMD_REQ_IFACE_LIST` | Arduino -> PC | `[AppTag]` | Yêu cầu danh sách các card mạng không dây (`wlan*`) |
| `0x3B` | `CMD_SET_CARD_MODE` | Arduino -> PC | `[CardIdx, Mode]` | Chuyển mode (`Managed`/`Monitor`/`AP`) cho card |
| `0x3D` | `CMD_WIFI_CONNECT` | Arduino -> PC | `SSID\tPassword` | Kết nối vào mạng WiFi (tự tra Known WiFi nếu pass rỗng) |
| `0x44` | `CMD_REQ_HC22000_ITEM` | Arduino -> PC | `[Index]` | Yêu cầu tên file `.hc22000` thứ `Index` |
| `0x45` | `CMD_AIRCRACK_SET_SERVER` | Arduino -> PC | `ServerIP (ASCII)` | Cập nhật địa chỉ IP của Server giải mã |
| `0x81` | `RESP_ACK` | Hai chiều | Trống | Xác nhận gói tin hợp lệ |
| `0x86` | `RESP_PONG` | Arduino -> PC | `Timestamp (4B)` | Phản hồi gói Ping |
| `0x87` | `RESP_TELEMETRY` | Arduino -> PC | `11 Bytes` | Báo cáo thông số phần cứng Arduino |
| `0x88` | `RESP_SETTINGS` | PC -> Arduino | `[Sys + AppBlocks]` | Gói cài đặt hệ thống và các App |
| `0x8A` | `RESP_WIFI_SCAN_ITEM` | PC -> Arduino | `[Idx, Total, Known, Ch, Sig, Len, SSID]` | Trả về 1 mục WiFi quét được (kèm cờ `Known`) |
| `0x8B` | `RESP_WIFI_KNOWN_ITEM` | PC -> Arduino | `[Idx, Total, Len, SSID]` | Trả về 1 mục trong danh sách Known WiFi |
| `0x8F` | `RESP_AIRCRACK_SCAN_ITEM` | PC -> Arduino | `[Idx, Total, Len, Label, Ch, Pwr]` | Trả về 1 AP trong danh sách quét của `AirCrack` |
| `0x90` | `RESP_APP_ENTER` | Arduino -> PC | `[AppId]` | Thông báo người dùng vừa mở App |
| `0x92` | `RESP_APP_EXIT` | Arduino -> PC | `[0x00]` | Thông báo người dùng thoát App về Menu Tổng |
| `0x95` | `RESP_OS_BOOT` | Arduino -> PC | Trống | Thông báo Arduino vừa khởi động |
| `0x9A` | `RESP_IFACE_LIST` | PC -> Arduino | `[Count, Modes, Names...]` | Danh sách tên card mạng và mode hiện tại |
| `0x9B` | `RESP_WIFI_ACTION` | PC -> Arduino | `[CardIdx, Len, Msg]` | Thông báo kết quả thực thi lên dòng 2 LCD |
| `0x9C` | `RESP_HC22000_ITEM` | PC -> Arduino | `[Idx, Total, Len, FileName]` | Trả về tên file `.hc22000` thứ `Index` |

---

## 7. HƯỚNG DẪN PHÁT TRIỂN & ĐĂNG KÝ APP MỚI

1. **Tạo thư mục App mới** trong `arduino/ArduinoLCDOS/src/apps/MyApp/` kế thừa từ lớp `AppService` (`src/core/AppService.h`).
2. **Định nghĩa các phương thức vòng đời**:
   - `getAppName()`: Chuỗi hiển thị trên Menu Tổng (`<= 15` ký tự).
   - `getAppId()`: Mã định danh duy nhất cho App.
   - `onEnter()`, `update(KeyCode key)`, `onExit()`: Xử lý hiển thị và phím bấm.
   - `onSerialPacket(byte cmd, const byte* payload, uint8_t len)`: Nhận gói tin phản hồi trực tiếp từ `console_coordinator.py`.
3. **Đăng ký trong `ArduinoLCDOS.ino`**:
   ```cpp
   #include "src/apps/MyApp/MyApp.h"
   MyApp myApp;

   void setup() {
     // ...
     os.registerApp(&myApp);
     os.begin();
   }
   ```

---

## 8. CÁC TỐI ƯU HÓA KỸ THUẬT QUAN TRỌNG TRÊN ATMEGA328P

1. **Quản lý bộ nhớ SRAM nghiêm ngặt (`<= 60%` SRAM)**:
   - Chip ATmega328P chỉ có `2048 Bytes` SRAM. Mọi chuỗi hằng số được đặt trong PROGMEM (`F()`) hoặc truyền qua bộ đệm tĩnh dùng chung để giữ lượng SRAM trống trên `800 Bytes`, đảm bảo ngăn xếp (Stack) không bao giờ tràn khi xử lý các khung tin Serial dài.
2. **Truyền tải danh sách theo từng mục (`Paginated Item Fetching`)**:
   - Thay vì gửi toàn bộ danh sách hàng chục mạng WiFi hay file `.hc22000` cùng lúc gây tràn bộ đệm UART 64-byte của Arduino Uno, Arduino chỉ yêu cầu từng mục theo chỉ số `Index` (`0x33`, `0x34`, `0x39`, `0x44`) mỗi khi người dùng bấm `UP`/`DOWN`.
3. **Đồng bộ luồng Serial đa luồng an toàn trên Python**:
   - `SerialLink` trong `python/lcd_keypad_engine/serial_link.py` tự động phân loại các gói tin sự kiện bất đồng bộ (`0x08`..`0x45`, `0x90`, `0x92`, `0x95`) chuyển thẳng vào `event_Callback` mà không giữ khóa `_lock`, cho phép `console_coordinator.py` gửi gói phản hồi ngay lập tức trong chính hàm xử lý sự kiện mà không xảy ra Deadlock.
