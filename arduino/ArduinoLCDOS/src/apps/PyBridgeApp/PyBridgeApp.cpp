/**
 * PyBridgeApp.cpp
 *
 * Implement Module 2: Cau noi giao tiep hai chieu mau (Communication Bridge Template).
 */

#include "PyBridgeApp.h"
#include "../../core/LCDKeypadDriver.h"

// ----------- Dinh nghia giao thuc binary -----------
static const byte PKT_START = 0xAA;
static const byte PKT_END   = 0xBB;

// Lenh tu Python (PC -> Arduino)
static const byte CMD_LCD_LINE1      = 0x01;
static const byte CMD_LCD_LINE2      = 0x02;
static const byte CMD_LCD_CLEAR      = 0x03;
static const byte CMD_READ_BTN       = 0x04;
static const byte CMD_SET_BACKLIGHT  = 0x05;
static const byte CMD_PING           = 0x06;
static const byte CMD_GET_TELEMETRY  = 0x07;
static const byte CMD_APP_EXIT       = 0x12;
static const byte CMD_DISPLAY_UPDATE = 0x20; // Hien thi text phan hoi tu PC

// Phan hoi tu Arduino (Arduino -> PC)
static const byte RESP_ACK          = 0x81;
static const byte RESP_NACK         = 0x82;
static const byte RESP_BTN_STATE    = 0x83;
static const byte RESP_ERROR        = 0x84;
static const byte RESP_PONG         = 0x86;
static const byte RESP_TELEMETRY    = 0x87;
static const byte RESP_APP_ENTER    = 0x90; // Arduino bao PC bat dau (Mo cua so UI)
static const byte RESP_APP_EXIT     = 0x92; // Arduino bao PC thoat (Dong cua so UI)
static const byte RESP_DEBUG_LOG    = 0x99;

// Ma nut bam quy uoc voi Python
static const byte PROTO_BTN_NONE    = 0x00;
static const byte PROTO_BTN_RIGHT   = 0x01;
static const byte PROTO_BTN_UP      = 0x02;
static const byte PROTO_BTN_DOWN    = 0x03;
static const byte PROTO_BTN_LEFT    = 0x04;
static const byte PROTO_BTN_SELECT  = 0x05;

// Helper do dung luong RAM con trong
static int getFreeRam() {
  extern int __heap_start, *__brkval;
  int v;
  return (int)&v - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}

PyBridgeApp::PyBridgeApp()
  : _rxPos(0),
    _receiving(false),
    _rxPacketCount(0),
    _crcErrorCount(0),
    _lastDisconnectReason(DISC_NONE),
    _lastRawAdc(1023),
    _appEnterTime(0),
    _lastActiveTime(0),
    _lastHeartbeatTime(0),
    _leftKeyHoldStart(0),
    _lastSentButton(PROTO_BTN_NONE)
{
}

void PyBridgeApp::onEnter() {
  _rxPos = 0;
  _receiving = false;
  _rxPacketCount = 0;
  _crcErrorCount = 0;
  _lastDisconnectReason = DISC_NONE;
  _lastRawAdc = analogRead(A0);
  _appEnterTime = millis();
  _lastActiveTime = millis();
  _lastHeartbeatTime = millis();
  _leftKeyHoldStart = 0;
  _lastSentButton = PROTO_BTN_NONE;

  // Xoa buffer cu tren Serial
  while (Serial.available() > 0) {
    Serial.read();
  }

  // Gui thong diep debug va thong bao APP_ENTER len PC (Yeu cau PC tu dong mo cua so UI!)
  sendDebugLog("PC test: App Entered");
  byte enterInfo[1] = { 1 };
  sendPacket(RESP_APP_ENTER, enterInfo, 1);

  drawReadyScreen();
}

void PyBridgeApp::onExit() {
  // Bao dam khi thoat app (du thoat binh thuong hay do timeout), PC luon nhan duoc lenh dong UI
  byte exitInfo[1] = { 0 };
  sendPacket(RESP_APP_EXIT, exitInfo, 1);
  _lastSentButton = PROTO_BTN_NONE;
}

byte PyBridgeApp::keyCodeToProtocolByte(KeyCode key) {
  switch (key) {
    case KEY_RIGHT:  return PROTO_BTN_RIGHT;
    case KEY_UP:     return PROTO_BTN_UP;
    case KEY_DOWN:   return PROTO_BTN_DOWN;
    case KEY_LEFT:   return PROTO_BTN_LEFT;
    case KEY_SELECT: return PROTO_BTN_SELECT;
    default:         return PROTO_BTN_NONE;
  }
}

const char* PyBridgeApp::getButtonName(byte protoBtn) {
  switch (protoBtn) {
    case PROTO_BTN_RIGHT:  return "PHAI (RIGHT)";
    case PROTO_BTN_UP:     return "LEN (UP)     ";
    case PROTO_BTN_DOWN:   return "XUONG (DOWN) ";
    case PROTO_BTN_LEFT:   return "TRAI (LEFT)  ";
    case PROTO_BTN_SELECT: return "SELECT (OK)  ";
    default:               return "NONE         ";
  }
}

void PyBridgeApp::update(KeyCode key) {
  // 1. Luon xu ly luong Serial nhan tu PC truoc
  processSerialInput();

  unsigned long now = millis();
  _lastRawAdc = analogRead(A0);

  // Khoang thoi gian dem 350ms khi moi vao app de chong xung nha phim SELECT
  if (now - _appEnterTime < 350) {
    return;
  }

  // 2. PHIM LEFT LA PHIM QUAY LAI (BACK TO OS MENU)
  // Nguoi dung chi can bam nut LEFT mot lan la lap tuc quay ve Menu Tong cua OS!
  if (key == KEY_LEFT) {
    LCDKeypadDriver* drv = getDriver();
    if (drv) {
      drv->printAt(0, 0, "PC test         ");
      drv->printAt(0, 1, "<- Tro ve OS... ");
    }
    // Gui tin hieu APP_EXIT (0x92) de PC lap tuc dong cua so UI!
    byte exitInfo[1] = { 0 };
    sendPacket(RESP_APP_EXIT, exitInfo, 1);
    sendDebugLog("PC test: User exited via LEFT key");
    delay(200);
    exitApp();
    return;
  }

  // 3. Xu ly cac nut con lai: UP, DOWN, RIGHT, SELECT
  LCDKeypadDriver* drv = getDriver();
  if (drv) {
    // Neu co su kien bam nut moi (canh len cua nut tu getPressedKey)
    if (key != KEY_NONE) {
      byte protoBtn = keyCodeToProtocolByte(key);
      _lastSentButton = protoBtn;
      _lastHeartbeatTime = now;
      _lastActiveTime = now;

      // Gui ngay trang thai nut ve PC
      sendPacket(RESP_BTN_STATE, &_lastSentButton, 1);

      // Cap nhat ngay tren LCD de nguoi dung thay phan hoi tuc thi
      drv->printAt(0, 0, "PC test [LIVE]  ");
      char line1[17];
      snprintf(line1, sizeof(line1), "Nut: %-11s", getButtonName(_lastSentButton));
      line1[16] = '\0';
      drv->printAt(0, 1, line1);
    } else {
      // Kiem tra khi nguoi dung nha tay khoi nut (A0 ve muc khong bam)
      KeyCode rawKey = drv->readRawKey();
      if (rawKey == KEY_NONE && _lastSentButton != PROTO_BTN_NONE) {
        _lastSentButton = PROTO_BTN_NONE;
        sendPacket(RESP_BTN_STATE, &_lastSentButton, 1);
      }
    }

    // Heartbeat moi 1s neu dang ranh de PC biet ket noi van tot
    if (now - _lastHeartbeatTime >= 1000) {
      _lastHeartbeatTime = now;
      sendPacket(RESP_BTN_STATE, &_lastSentButton, 1);
    }
  }

  // --- CO CHE TIMEOUT AN TOAN 60S (BAO VE CHONG TRAN SO AM) ---
  if (_lastActiveTime > 0 && now > _lastActiveTime && (now - _lastActiveTime > 60000UL)) {
    _lastDisconnectReason = DISC_TIMEOUT;
    showDiagnosticScreen(DISC_TIMEOUT);
    exitApp();
    return;
  }
}

void PyBridgeApp::processSerialInput() {
  while (Serial.available() > 0) {
    byte b = Serial.read();

    if (!_receiving) {
      if (b == PKT_START) {
        _receiving = true;
        _rxPos = 0;
      }
    } else {
      if (_rxPos < (int)sizeof(_rxBuffer)) {
        _rxBuffer[_rxPos++] = b;
      } else {
        _crcErrorCount++;
        _receiving = false;
        _rxPos = 0;
        continue;
      }

      if (_rxPos == 1) {
        byte len = _rxBuffer[0];
        if (len < 2 || len > 32) {
          _crcErrorCount++;
          _receiving = false;
          _rxPos = 0;
        }
      } else if (_rxPos >= 2) {
        byte len = _rxBuffer[0];
        if (_rxPos == (len + 2)) {
          if (_rxBuffer[_rxPos - 1] == PKT_END) {
            byte cmd = _rxBuffer[1];
            byte dataLen = len - 2;

            // Kiem tra Checksum XOR
            byte calcChecksum = cmd;
            for (byte i = 0; i < dataLen; i++) {
              calcChecksum ^= _rxBuffer[2 + i];
            }
            byte recvChecksum = _rxBuffer[len];

            if (calcChecksum == recvChecksum) {
              _rxPacketCount++;
              processCommand(cmd, &_rxBuffer[2], dataLen);
            } else {
              _crcErrorCount++;
              sendPacket(RESP_NACK, NULL, 0);
            }
          } else {
            _crcErrorCount++;
          }
          _receiving = false;
          _rxPos = 0;
        }
      }
    }
  }
}

void PyBridgeApp::processCommand(byte cmd, const byte* data, byte dataLen) {
  LCDKeypadDriver* drv = getDriver();
  _lastActiveTime = millis();

  switch (cmd) {
    case CMD_PING: {
      sendPacket(RESP_PONG, data, dataLen);
      return;
    }

    case CMD_GET_TELEMETRY: {
      sendTelemetry();
      return;
    }

    case CMD_DISPLAY_UPDATE: {
      // Hien thi text phan hoi tu PC len dong 2 cua LCD
      if (drv && dataLen > 0) {
        char buf[17];
        byte n = dataLen > 16 ? 16 : dataLen;
        memcpy(buf, data, n);
        buf[n] = '\0';
        drv->printAt(0, 1, buf);
        for (byte i = n; i < 16; i++) drv->getLCD().print(' ');
      }
      sendPacket(RESP_ACK, NULL, 0);
      return;
    }

    case CMD_SET_BACKLIGHT: {
      if (dataLen >= 1 && drv) {
        drv->setBacklight(data[0] != 0);
      }
      sendPacket(RESP_ACK, NULL, 0);
      return;
    }

    case CMD_LCD_LINE1: {
      if (drv) {
        char buf[17];
        byte n = dataLen > 16 ? 16 : dataLen;
        memcpy(buf, data, n);
        buf[n] = '\0';
        drv->printAt(0, 0, buf);
        for (byte i = n; i < 16; i++) drv->getLCD().print(' ');
      }
      sendPacket(RESP_ACK, NULL, 0);
      return;
    }

    case CMD_LCD_LINE2: {
      if (drv) {
        char buf[17];
        byte n = dataLen > 16 ? 16 : dataLen;
        memcpy(buf, data, n);
        buf[n] = '\0';
        drv->printAt(0, 1, buf);
        for (byte i = n; i < 16; i++) drv->getLCD().print(' ');
      }
      sendPacket(RESP_ACK, NULL, 0);
      return;
    }

    case CMD_LCD_CLEAR: {
      if (drv) drv->clear();
      sendPacket(RESP_ACK, NULL, 0);
      return;
    }

    case CMD_READ_BTN: {
      if (drv) {
        KeyCode currentRaw = drv->readRawKey();
        byte currentProtoBtn = keyCodeToProtocolByte(currentRaw);
        sendPacket(RESP_BTN_STATE, &currentProtoBtn, 1);
      }
      return;
    }

    case CMD_APP_EXIT: {
      sendPacket(RESP_ACK, NULL, 0);
      exitApp();
      return;
    }

    default:
      sendPacket(RESP_NACK, NULL, 0);
      return;
  }
}

void PyBridgeApp::sendPacket(byte cmd, const byte* data, byte dataLen) {
  byte len = 1 + dataLen + 1; // cmd + data + checksum
  byte checksum = cmd;

  Serial.write(PKT_START);
  Serial.write(len);
  Serial.write(cmd);

  for (byte i = 0; i < dataLen; i++) {
    Serial.write(data[i]);
    checksum ^= data[i];
  }

  Serial.write(checksum);
  Serial.write(PKT_END);
}

void PyBridgeApp::sendDebugLog(const char* msg) {
  if (!msg) return;
  byte len = (byte)strlen(msg);
  if (len > 30) len = 30;
  sendPacket(RESP_DEBUG_LOG, (const byte*)msg, len);
}

void PyBridgeApp::sendTelemetry() {
  unsigned int uptime = (unsigned int)(millis() / 1000);
  unsigned int freeRam = (unsigned int)getFreeRam();

  byte tele[11];
  tele[0] = lowByte(uptime);
  tele[1] = highByte(uptime);
  tele[2] = lowByte(freeRam);
  tele[3] = highByte(freeRam);
  tele[4] = lowByte(_rxPacketCount);
  tele[5] = highByte(_rxPacketCount);
  tele[6] = _crcErrorCount;
  tele[7] = lowByte(_lastRawAdc);
  tele[8] = highByte(_lastRawAdc);
  tele[9] = 1; // Bridge state active
  tele[10] = (byte)_lastDisconnectReason;

  sendPacket(RESP_TELEMETRY, tele, sizeof(tele));
}

void PyBridgeApp::showDiagnosticScreen(DisconnectReason reason) {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  switch (reason) {
    case DISC_TIMEOUT:
      drv->printAt(0, 0, "ERR:TIMEOUT (60s)");
      sendDebugLog("[ARDUINO ERR] Mat ket noi PC: Timeout 60s");
      break;
    case DISC_LEFT_KEY:
      drv->printAt(0, 0, "EXIT:LEFT KEY   ");
      sendDebugLog("[ARDUINO EXIT] Nguoi dung bam nut LEFT ve OS");
      break;
    case DISC_PC_REQUEST:
      drv->printAt(0, 0, "EXIT:PC REQUEST ");
      sendDebugLog("[ARDUINO EXIT] PC yeu cau thoat app");
      break;
    case DISC_CRC_ERROR:
      drv->printAt(0, 0, "ERR:CRC ERROR   ");
      break;
    case DISC_BUFFER_OVERFLOW:
      drv->printAt(0, 0, "ERR:RX OVERFLOW ");
      break;
    default:
      drv->printAt(0, 0, "DISC:UNKNOWN    ");
      break;
  }

  char line1[17];
  snprintf(line1, sizeof(line1), "R:%u C:%u A:%u", _rxPacketCount, (unsigned int)_crcErrorCount, _lastRawAdc);
  line1[16] = '\0';
  drv->printAt(0, 1, line1);

  delay(1500);
}

void PyBridgeApp::drawReadyScreen() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  drv->printAt(0, 0, "PC test [LIVE]  ");
  drv->printAt(0, 1, "<-LEFT: Ve OS   ");
}
