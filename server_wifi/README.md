# ACNG `server_wifi` — Máy Chủ Giải Mã WPA/WPA2 Handshake (`.hc22000`)

`server_wifi` là dịch vụ REST API (FastAPI, cổng `9000`) nhận các file băm bắt tay WPA/WPA2 (`.hc22000`) từ ứng dụng **`AirCrack`** trên Arduino LCD OS / Raspberry Pi, thực hiện giải mã bằng **Hashcat (`-m 22000`)** kết hợp bộ giải mã chuẩn **IEEE 802.11i PBKDF2-HMAC-SHA1 (PMKID & EAPOL)**, và trả kết quả `(SSID, Password)` trực tiếp về màn hình LCD 16x2 cũng như lưu vào `Known WiFi`.

---

## 1. Cấu Trúc Thư Mục `server_wifi/`

```text
server_wifi/
├── main.py                 # FastAPI Server xử lý /status, /upload, /hash, /wifi (cổng 9000)
├── requirements.txt        # Các thư viện Python cần thiết (fastapi, uvicorn, python-multipart)
├── README.md               # Hướng dẫn cài đặt Hashcat, Wordlist và khởi chạy Server
├── hashcat/                # [Tự đặt vào - Git Ignored] Thư mục chứa bộ cài Hashcat (hashcat.exe / hashcat.bin)
├── rockyou.txt             # [Tự đặt vào - Git Ignored] Từ điển mật khẩu dùng để crack
├── uploads/                # [Python tự sinh - Git Ignored] Chứa các file .hc22000 và .pot được tải lên
└── cracked.json            # [Python tự sinh - Git Ignored] Cơ sở dữ liệu các mạng WiFi đã giải mã
```

> **Lưu ý bảo mật**: Các thư mục/file được sinh tự động hoặc chứa dữ liệu nhạy cảm (`uploads/`, `cracked.json`, `rockyou.txt`, `hashcat/`) đều đã được chặn trong `.gitignore` để không bao giờ bị đẩy lên GitHub.

---

## 2. Hướng Dẫn Đặt Thư Mục `hashcat` và Từ Điển `rockyou.txt`

### Bước 1: Tải và đặt thư mục `hashcat` vào `server_wifi/hashcat/`
1. Tải bản phát hành chính thức của **Hashcat** (ví dụ `hashcat-7.1.2.7z` từ [https://hashcat.net/hashcat/](https://hashcat.net/hashcat/)).
2. Giải nén và đổi tên thư mục thành **`hashcat`**, sau đó đặt trực tiếp vào bên trong `server_wifi/` sao cho đường dẫn tới file thực thi là:
   - **Trên Windows**: `server_wifi/hashcat/hashcat.exe`
   - **Trên Linux**: `server_wifi/hashcat/hashcat.bin` (hoặc cài qua `sudo apt install hashcat`)
   *(Lưu ý: `main.py` cũng tự động nhận diện nếu bạn để nguyên tên thư mục giải nén dạng `server_wifi/hashcat-7.1.2/hashcat.exe` hoặc đặt biến môi trường `HASHCAT_PATH`)*.

### Bước 2: Đặt file từ điển `rockyou.txt` vào `server_wifi/`
- Đặt file từ điển mật khẩu của bạn tại đường dẫn:
  ```text
  server_wifi/rockyou.txt
  ```
- Mỗi dòng trong `rockyou.txt` là 1 mật khẩu ứng viên (WPA/WPA2 yêu cầu độ dài từ 8 đến 63 ký tự).

---

## 3. Cài Đặt & Khởi Chạy Server

### Bước 1: Cài đặt thư viện Python
```bash
pip install -r server_wifi/requirements.txt
```

### Bước 2: Chạy Server (Lắng nghe trên `0.0.0.0:9000`)
```bash
python server_wifi/main.py
```

### Bước 3: Kiểm tra trạng thái Server
Mở trình duyệt hoặc chạy `curl`:
```bash
curl http://127.0.0.1:9000/status
```
Phản hồi JSON:
```json
{
  "status": "online",
  "time": "2026-10-26 23:15:00",
  "queued": 0,
  "cracked_count": 0,
  "hashcat_available": true
}
```
Khi `"hashcat_available": true`, `server_wifi` đã nhận diện thành công `hashcat` trong thư mục `server_wifi/hashcat/`!

---

## 4. Các Endpoint API Phục Vụ `AirCrackApp`

| Phương thức | Endpoint | Chức năng trên Arduino LCD OS (`AirCrack`) |
| :---: | :--- | :--- |
| `GET` | `/status` | **Mục `9.Server Status`**: Kiểm tra kết nối tới Server và tổng số WiFi đã crack (`SrvOK Crk:X`). |
| `POST` | `/upload` | **Mục `11.Send Hash` (Bước 1)**: Nhận file `.hc22000` gửi từ Raspberry Pi lưu vào `server_wifi/uploads/`. |
| `POST` | `/hash` | **Mục `11.Send Hash` (Bước 2)**: Chạy Hashcat `-m 22000` (kèm bộ giải mã IEEE 802.11i) với `rockyou.txt` và trả về `ssid`, `bssid`, `password`. |
| `GET` | `/wifi` | **Mục `10.DL Cracked`**: Trả về danh sách toàn bộ các mạng WiFi đã giải mã trong `cracked.json` để Raspberry Pi lưu vào `Known WiFi`. |
| `POST` | `/wifi` | Thêm thủ công một cặp `(ssid, password)` vào danh sách đã giải mã. |
