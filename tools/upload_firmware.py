"""
upload_firmware.py - Tu dong bien dich va nap firmware ArduinoLCDOS len bo Arduino Uno.
Chay: python upload_firmware.py [COMx]
"""
import subprocess
import shutil
import sys
import os

ARDUINO_CLI = os.environ.get("ARDUINO_CLI_PATH") or shutil.which("arduino-cli") or "arduino-cli"
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.dirname(TOOLS_DIR)
SKETCH_DIR = os.path.join(ENGINE_DIR, "arduino", "ArduinoLCDOS")
FQBN = "arduino:avr:uno"

def find_port():
    try:
        import serial.tools.list_ports as list_ports
        ports = list(list_ports.comports())
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
            if "1a86" in hwid or "2341" in hwid:
                score += 50

            if score > 0:
                candidates.append((score, p.device))

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

        if len(ports) == 1:
            return ports[0].device
    except Exception:
        pass
    return None

def run(cmd, desc):
    print(f"\n>>> {desc}")
    print(f"    {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    if result.returncode != 0:
        print(f"!!! That bai (exit code {result.returncode})")
        return False
    print("OK")
    return True

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_port()
    if not port:
        print("\n[LOI NGHIEP TRONG] Khong tim thay bat ky cong COM nao cua Arduino!")
        print("Vui long kiem tra lai day cap USB ket noi giua bo Arduino va may tinh.")
        sys.exit(1)
    print(f"=== TU DONG NHAN DIEN CONG ARDUINO: {port} ===")

    # 1. Compile
    if not run([ARDUINO_CLI, "compile", "--fqbn", FQBN, SKETCH_DIR], "Compile firmware ArduinoLCDOS"):
        sys.exit(1)

    # 2. Upload
    if not run([ARDUINO_CLI, "upload", "-p", port, "--fqbn", FQBN, SKETCH_DIR], f"Upload firmware len {port}"):
        sys.exit(1)

    print(f"\n=== Firmware ArduinoLCDOS da duoc nap thanh cong len {port} @ 115200 baud! ===")

if __name__ == "__main__":
    main()
