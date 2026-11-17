import os
import getpass
from pathlib import Path
import paramiko

# --- Cấu hình kết nối SSH (Đọc từ biến môi trường hoặc nhập trực tiếp) ---
HOST = os.environ.get("ACNG_SSH_HOST", "").strip()
PORT = int(os.environ.get("ACNG_SSH_PORT", "22"))
USERNAME = os.environ.get("ACNG_SSH_USER", "").strip()
PASSWORD = os.environ.get("ACNG_SSH_PASSWORD", "")

# Đường dẫn
LOCAL_DIR = Path(__file__).resolve().parent
REMOTE_DIR = os.environ.get("ACNG_REMOTE_DIR", "").strip()

SKIP_NAMES = {".git", ".idea", "__pycache__", "build", "aircrack_files", "known_wifi.json", "serial_technical_trace.log"}

def ensure_remote_dir(sftp, remote_path):
    """Tạo thư mục trên remote nếu chưa tồn tại (giống mkdir -p)"""
    dirs = remote_path.split("/")
    current_path = ""
    for d in dirs:
        if not d:
            continue
        current_path += f"/{d}"
        try:
            sftp.stat(current_path)
        except IOError:
            sftp.mkdir(current_path)

def sync_folder(sftp, local_path, remote_path):
    """Đệ quy đồng bộ thư mục từ local lên remote"""
    for item in local_path.iterdir():
        if item.name in SKIP_NAMES or item.suffix in {".log", ".cap", ".pcap", ".hc22000", ".pyc"}:
            continue
        local_item = item
        remote_item = f"{remote_path}/{item.name}"

        if local_item.is_dir():
            ensure_remote_dir(sftp, remote_item)
            sync_folder(sftp, local_item, remote_item)
        elif local_item.is_file():
            need_upload = True
            try:
                remote_stat = sftp.stat(remote_item)
                local_stat = local_item.stat()
                if remote_stat.st_size == local_stat.st_size and remote_stat.st_mtime >= local_stat.st_mtime:
                    need_upload = False
            except IOError:
                pass

            if need_upload:
                print(f"Đang đồng bộ: {local_item.relative_to(LOCAL_DIR)} -> {remote_item}")
                sftp.put(str(local_item), remote_item)

def main():
    if not LOCAL_DIR.exists():
        print(f"Lỗi: Thư mục nguồn không tồn tại tại {LOCAL_DIR}")
        return

    host = HOST or input("SSH Host/IP: ").strip()
    username = USERNAME or input("SSH Username: ").strip()
    password = PASSWORD or getpass.getpass("SSH Password: ")
    remote_dir = REMOTE_DIR or f"/home/{username}/AC_NG/Engine"

    print(f"Đang kết nối tới {host}...")
    transport = paramiko.Transport((host, PORT))
    transport.connect(username=username, password=password)
    sftp = paramiko.SFTPClient.from_transport(transport)

    print(f"Bắt đầu đồng bộ từ [{LOCAL_DIR}] lên [{remote_dir}]...")
    ensure_remote_dir(sftp, remote_dir)
    sync_folder(sftp, LOCAL_DIR, remote_dir)

    sftp.close()
    transport.close()
    print("Đồng bộ hoàn tất!")

if __name__ == "__main__":
    main()
