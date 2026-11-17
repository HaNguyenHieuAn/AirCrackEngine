# CẨM NANG TRIỂN KHAI VÀ VẬN HÀNH THỰC TẾ TRÊN RASPBERRY PI (KALI LINUX)
## Hệ Sinh Thái ACNG — Arduino LCD OS & Python Wireless Coordinator

> **Mục tiêu**: Hướng dẫn chi tiết từng bước để triển khai, nạp firmware, cấu hình dịch vụ chạy ngầm (`arduino-coordinator.service`) và vận hành toàn bộ các tính năng quản lý WiFi (`WiFi Set`) & kiểm thử bảo mật không dây (`AirCrack`) trên **Raspberry Pi** kết hợp **Arduino Uno R3 + LCD 16x2 Keypad Shield**.

---

## 1. TỔNG QUAN KIẾN TRÚC PHẦN CỨNG & KẾT NỐI

Hệ thống hoạt động theo mô hình **Headless Embedded Node** (vận hành độc lập qua màn hình LCD 16x2 và 5 phím bấm trên Arduino, không cần gắn màn hình HDMI hay bàn phím rời cho Raspberry Pi):

- **Phần cứng trung tâm**: Raspberry Pi (Chạy Kali Linux / Raspberry Pi OS).
- **Thiết bị điều khiển & hiển thị**: Bo **Arduino Uno R3 + DFRobot LCD 16x2 Keypad Shield** nối với Raspberry Pi qua cáp USB (UART Serial **115200 Baud**, thường nhận `/dev/ttyUSB0` hoặc `/dev/ttyACM0`).
- **Giao diện mạng**:
  - `wlan0`: Card Wi-Fi onboard trên Raspberry Pi (ưu tiên kết nối WiFi / quản lý mạng).
  - `wlan1`: USB Wi-Fi rời hỗ trợ Monitor Mode & Packet Injection (ví dụ: TP-Link TL-WN722N, dùng cho `AirCrack`).
  - `eth0`: Cổng mạng LAN kết nối tới máy chủ giải mã băm (`server_wifi`, mặc định `169.254.84.122:9000`).

```text
+---------------------------------------------------------------------------------+
|                         RASPBERRY PI (KALI LINUX)                               |
|                                                                                 |
|   [wlan0 (Onboard)]          <---> Quét & kết nối WiFi (nmcli / NetworkManager) |
|   [wlan1 (USB Wi-Fi)]        <---> Monitor Mode, Capture EAPOL, Deauth Attack   |
|   [eth0 (LAN Ethernet)]      <---> Kết nối Server giải mã .hc22000 (:9000)      |
|   [console_coordinator.py]   <---> Dịch vụ điều phối trung tâm (systemd)        |
+---------------------------------------------------------------------------------+
                                       ||
                                       ||  Cáp USB Serial (/dev/ttyUSB0 @ 115200)
                                       ||
+---------------------------------------------------------------------------------+
|                       ARDUINO UNO + LCD KEYPAD SHIELD                           |
|  - Màn hình LCD 16x2 hiển thị: Menu OS, AirCrack, WiFi Set, Keyboard, Cài đặt   |
|  - 5 Nút bấm điều khiển: UP, DOWN, LEFT, RIGHT, SELECT                          |
+---------------------------------------------------------------------------------+
```

---

## 2. CHUẨN BỊ MÔI TRƯỜNG TRÊN RASPBERRY PI

### 2.1. Cài đặt các gói công cụ hệ thống và Python
Mở terminal trên Raspberry Pi và chạy:
```bash
sudo apt-get update -y
sudo apt-get install -y python3-serial network-manager iw wireless-tools aircrack-ng hcxtools avrdude psmisc
```

### 2.2. Phân quyền cổng Serial cho User
Để mở cổng `/dev/ttyUSB*` hoặc `/dev/ttyACM*` không bị lỗi `Permission denied`:
```bash
sudo usermod -a -G dialout $USER
```

### 2.3. Cấu hình Sudo NOPASSWD cho các công cụ mạng (`nmcli`, `iw`, `aircrack-ng`)
Để `console_coordinator.py` có thể tự động chuyển mode card (`Managed` / `Monitor`), quét AP, bắt gói tin và kết nối WiFi mà không bị treo chờ mật khẩu:
```bash
sudo python3 python/console_coordinator.py --setup-sudo
```
Hoặc cấu hình trực tiếp:
```bash
echo "$USER ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/arduino-coordinator
sudo chmod 0440 /etc/sudoers.d/arduino-coordinator
```

---

## 3. BIÊN DỊCH VÀ NẠP FIRMWARE LÊN ARDUINO UNO

### Cách 1: Tự động biên dịch & nạp bằng `upload_firmware.py`
Nếu máy đã cài `arduino-cli`:
```bash
python3 tools/upload_firmware.py
```

### Cách 2: Nạp trực tiếp file `.hex` trên Raspberry Pi bằng `avrdude`
1. Biên dịch trên máy phát triển bằng `arduino/ArduinoLCDOS/build.bat` (hoặc `arduino-cli compile --fqbn arduino:avr:uno arduino/ArduinoLCDOS --output-dir arduino/ArduinoLCDOS/build`).
2. Dừng dịch vụ Coordinator tạm thời (nếu đang chạy) để giải phóng cổng `/dev/ttyUSB0`:
   ```bash
   sudo systemctl stop arduino-coordinator.service
   ```
3. Nạp file `.hex` vào Arduino Uno:
   ```bash
   avrdude -c arduino -p m328p -P /dev/ttyUSB0 -b 115200 -D -U flash:w:ArduinoLCDOS.ino.hex:i
   ```
4. Khởi động lại dịch vụ Coordinator:
   ```bash
   sudo systemctl start arduino-coordinator.service
   ```

---

## 4. HƯỚNG DẪN SỬ DỤNG CÁC ỨNG DỤNG TRÊN ARDUINO LCD OS

Trên Menu Tổng của màn hình LCD 16x2, dùng phím **`UP`** / **`DOWN`** để chọn ứng dụng và nhấn **`SELECT`** để vào:

### 4.1. `AirCrack` (Kiểm thử bảo mật WiFi & Giải mã Handshake WPA2)
- `1.Card: wlanX`: Bấm `SELECT` để chuyển đổi giữa các card mạng không dây (`wlan0`, `wlan1`...).
- `2.Mode: Managed/Monitor`: Bấm `SELECT` để bật/tắt chế độ `Monitor` trực tiếp trên card đang chọn.
- `3.Scan APs`: Quét các Access Point thực tế xung quanh. Dùng `UP`/`DOWN` để xem từng AP (`SSID`, kênh `C`, cường độ sóng) và bấm `SELECT` để chọn làm mục tiêu (`Target`).
- `4.Select Target`: Duyệt lại danh sách AP đã quét và khóa mục tiêu.
- `5.Monitor Mode`: Kích hoạt nhanh chế độ Monitor và nhảy tới đúng kênh (`Channel`) của AP mục tiêu.
- `6.Capture HS`: Chạy `airodump-ng` bắt gói bắt tay WPA2 EAPOL của AP mục tiêu, đồng thời bắn gói `deauth` ngầm để kích hoạt thiết bị kết nối lại.
- `7.Deauth Attack`: Gửi gói `aireplay-ng --deauth` tới AP mục tiêu.
- `8.Cap->HC22000`: Dừng tiến trình bắt gói và gọi `hcxpcapngtool` chuyển đổi các file `.cap`/`.pcap` sang định dạng `.hc22000` (lưu trong `python/aircrack_files/`).
- `9.Server Status`: Kiểm tra kết nối tới Server giải mã (`GET /status`) và hiển thị số lượng WiFi đã crack.
- `10.DL Cracked`: Tải toàn bộ danh sách WiFi đã giải mã từ Server (`GET /wifi`) về lưu tự động vào `Known WiFi`.
- `11.Send Hash`: Duyệt danh sách các file `.hc22000` hiện có, bấm `SELECT` để tải file lên Server (`POST /upload` & `POST /hash`). Khi giải mã thành công, màn hình hiển thị trực tiếp `PW:<mật_khẩu>` và tự động lưu vào `Known WiFi`.
- `12.Server IP`:
  - Khi bấm `SELECT`, ứng dụng mở `Keyboard` với **địa chỉ Server IP hiện tại được điền sẵn** để bạn chỉnh sửa nhanh.
  - Nếu xóa trống hoàn toàn rồi nhấn `OK`, hệ thống tự động đặt lại về IP mặc định (`169.254.84.122`).

### 4.2. `WiFi Set` (Quản lý Card mạng & Kết nối WiFi thông minh)
- `1.Iface Mode`: Chuyển chế độ hoạt động tổng thể.
- `2.wlan0: [Man/Mon/AP]` & `3.wlan1: [Man/Mon/AP]`: Xem và đổi mode riêng cho từng card mạng vật lý.
- `4.Scan WiFi`:
  - Quét danh sách WiFi thực tế qua `nmcli` / `iw`.
  - Các mạng đã lưu mật khẩu trong `Known WiFi` được đánh dấu **`*`** ở đầu tên.
  - **Kết nối thông minh**:
    - Nếu chọn WiFi **đã có trong Known WiFi**: Kết nối ngay lập tức bằng mật khẩu đã lưu, **không cần nhập lại mật khẩu**.
    - Nếu chọn WiFi **chưa biết**: Tự động mở ứng dụng `Keyboard` để nhập mật khẩu, sau đó thực hiện kết nối và lưu vào `Known WiFi`.
- `5.Known WiFi`: Duyệt danh sách các mạng WiFi đã lưu (tự động tổng hợp từ `known_wifi.json`, `os_settings.json` và các profile của NetworkManager) và bấm `SELECT` để kết nối ngay.

### 4.3. `Keyboard` (Bàn phím ảo 16x2)
- Dùng `LEFT` / `RIGHT` để di chuyển con trỏ trên dải ký tự ở dòng 2.
- Dùng `UP` để chọn ký tự tại con trỏ thêm vào chuỗi ở dòng 1.
- Dùng `DOWN` để xóa lùi 1 ký tự (`Backspace`), hoặc giữ `DOWN` để xóa nhanh.
- Các nút chức năng cuối dải:
  - `<`: Xóa 1 ký tự
  - `A`: Chuyển đổi bộ ký tự (`abc` -> `ABC` -> `123` -> `SYM`)
  - `OK`: Xác nhận lưu và tự động quay về ứng dụng đã gọi (`WiFi Set` hoặc `AirCrack`)
  - `X`: Hủy thao tác và quay lại.

### 4.4. `Cai Dat (Set)` (Cài đặt hệ thống)
- `1. Den nen: ON/OFF`: Bật/tắt đèn nền LCD (lưu vào EEPROM & `os_settings.json`).
- `2. Am thanh: ON/OFF`: Bật/tắt âm thanh.
- `3. Thong tin OS`: Xem dung lượng `Free RAM`, `Uptime` và `Baudrate`.
- `4. Reset AllData`: Khôi phục cài đặt gốc toàn bộ OS (có xác nhận 2 bước an toàn).

---

## 5. CÀI ĐẶT CHẠY TỰ ĐỘNG CÙNG HỆ THỐNG (SYSTEMD)

Trên Raspberry Pi, bạn chỉ cần chạy 1 lệnh duy nhất để cài đặt dịch vụ Systemd `arduino-coordinator.service`:

```bash
python3 python/console_coordinator.py --install-autostart
```

Lệnh trên sẽ tự động tạo, kích hoạt (`enable`) và khởi chạy (`start`) dịch vụ `/etc/systemd/system/arduino-coordinator.service` với nội dung chuẩn:

```ini
[Unit]
Description=Arduino LCD OS Central Coordinator Service
After=network.target

[Service]
Type=simple
User=<your_username>
WorkingDirectory=/home/<your_username>/AC_NG/Engine/python
ExecStart=/usr/bin/python3 /home/<your_username>/AC_NG/Engine/python/console_coordinator.py --headless
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Các lệnh kiểm tra và quản lý dịch vụ:
```bash
# Kiểm tra trạng thái hoạt động:
sudo systemctl status arduino-coordinator.service

# Xem log hoạt động thời gian thực:
sudo journalctl -u arduino-coordinator.service -f

# Khởi động lại dịch vụ sau khi cập nhật code Python:
sudo systemctl restart arduino-coordinator.service
```

---

## 6. CẤU HÌNH & CHẠY MÁY CHỦ GIẢI MÃ `server_wifi` (PORT 9000)

Để sử dụng các chức năng `9.Server Status`, `10.DL Cracked`, và `11.Send Hash` trong ứng dụng `AirCrack`:

1. **Đặt thư mục `hashcat` và từ điển `rockyou.txt` vào `server_wifi/`**:
   - Giải nén bộ cài Hashcat vào `server_wifi/hashcat/` (đường dẫn `server_wifi/hashcat/hashcat.exe` trên Windows hoặc `server_wifi/hashcat/hashcat.bin` trên Linux).
   - Đặt file từ điển mật khẩu tại `server_wifi/rockyou.txt`.
   - *(Các thư mục `server_wifi/hashcat/`, `server_wifi/uploads/`, `server_wifi/cracked.json` và `server_wifi/rockyou.txt` đều được `.gitignore` tự động loại trừ để bảo mật và tránh đẩy file nặng lên Git)*.
2. **Khởi chạy `server_wifi` trên PC/Server**:
   ```bash
   pip install -r server_wifi/requirements.txt
   python server_wifi/main.py
   ```
3. **Cấu hình `12.Server IP` trên Arduino**:
   - Mặc định hệ thống trỏ tới `169.254.84.122` (cổng `9000`).
   - Bạn có thể bấm `12.Server IP` trong `AirCrack` để chỉnh sửa trực tiếp IP hiện tại trên bàn phím LCD 16x2 (hoặc xóa trống rồi bấm `OK` để quay về IP mặc định).

---

## 7. CƠ CHẾ KHÓA ĐƠN TIẾN TRÌNH & TỰ ĐỘNG CHIẾM QUYỀN (`SingleInstanceLockWithTakeover`)

`console_coordinator.py` tích hợp cơ chế khóa đơn tiến trình trên cổng loopback `127.0.0.1:49281`:
- Đảm bảo **chỉ duy nhất một tiến trình** giữ cổng Serial `/dev/ttyUSB0` tại một thời điểm, tránh hoàn toàn lỗi xung đột gói tin nhị phân (`Serial Timeout / NACK`).
- Khi bạn chạy một tiến trình `console_coordinator.py` mới, nó sẽ tự động gửi tín hiệu `SHUTDOWN` yêu cầu tiến trình cũ đóng cổng Serial an toàn trước khi tiếp quản.
