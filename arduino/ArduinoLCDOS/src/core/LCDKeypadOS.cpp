/**
 * LCDKeypadOS.cpp
 *
 * Implement chi tiet he dieu hanh LCDKeypadOS cho Arduino
 */

#include "LCDKeypadOS.h"
#include <EEPROM.h>

LCDKeypadOS::LCDKeypadOS()
  : _appCount(0),
    _currentRunningApp(-1),
    _selectedAppIndex(0),
    _state(OS_STATE_MAIN_MENU),
    _lastMenuRefresh(0)
{
  for (uint8_t i = 0; i < MAX_APPS; i++) {
    _apps[i] = nullptr;
  }
}

void LCDKeypadOS::begin() {
  _driver.begin(16, 2);

  // 1. Doc cai dat tu EEPROM noi bo (fallback khi offline khong co PC)
  if (EEPROM.read(0) == 0xA5) {
    _driver.setBacklight(EEPROM.read(1) != 0);
    // Nap cai dat rieng cho tung App tu EEPROM
    for (uint8_t i = 0; i < _appCount; i++) {
      if (_apps[i] != nullptr) {
        uint8_t aId = _apps[i]->getAppId();
        if (aId > 0) {
          int eeAddr = 10 + (aId * 8);
          uint8_t aLen = EEPROM.read(eeAddr);
          if (aLen > 0 && aLen <= 8) {
            byte aBuf[8];
            for (uint8_t k = 0; k < aLen; k++) aBuf[k] = EEPROM.read(eeAddr + 1 + k);
            _apps[i]->loadSettings(aBuf, aLen);
          }
        }
      }
    }
  }

  // Splash Screen khoi dong
  _driver.printCentered(0, F("== ARDUINO OS =="));
  _driver.printCentered(1, F("Doi PC (2s)...  "));

  // 2. Gui tin hieu Reset / Khoi dong len PC de PC dong bat ky cua so nao dang mo do
  byte bootPkt[] = { 0xAA, 0x02, 0x95, 0x95, 0xBB }; // RESP_OS_BOOT (0x95)
  Serial.write(bootPkt, sizeof(bootPkt));

  // 3. Gui yeu cau lay Cài Đặt (Settings) tu PC
  byte reqPkt[] = { 0xAA, 0x02, 0x08, 0x08, 0xBB }; // CMD_REQ_SETTINGS (0x08)
  Serial.write(reqPkt, sizeof(reqPkt));

  // 4. Cho phan hoi cai dat tu PC toi da 2 giay (2000ms)
  unsigned long tStart = millis();
  bool pcFound = false;

  while (millis() - tStart < 2000) {
    if (Serial.available() >= 4) {
      if (Serial.peek() == 0xAA) {
        byte bStart = Serial.read(); // 0xAA
        byte bLen   = Serial.read();
        byte bCmd   = Serial.read();

        if (bLen >= 2 && bLen <= 64) {
          byte dataLen = bLen - 2;
          byte dataBuf[64];
          unsigned long readTimeout = millis();
          for (byte i = 0; i < dataLen; i++) {
            while (Serial.available() == 0 && (millis() - readTimeout < 50));
            dataBuf[i] = Serial.read();
          }
          while (Serial.available() < 2 && (millis() - readTimeout < 50));
          byte recvChecksum = Serial.read();
          byte endByte = Serial.read();

          if (endByte == 0xBB) {
            byte calcChecksum = bCmd;
            for (byte i = 0; i < dataLen; i++) calcChecksum ^= dataBuf[i];

            if (calcChecksum == recvChecksum && bCmd == 0x88) { // RESP_SETTINGS (0x88)
              pcFound = true;
              dispatchAppSettings(dataBuf, dataLen);
              _driver.printCentered(1, F("PC Da Ket Noi!  "));
              delay(400);
              break;
            }
          }
        }
      } else {
        Serial.read();
      }
    }
  }

  // 5. Neu sau 2 giay khong co phan hoi tu PC -> Tu dong vao OS voi cai dat hien tai
  if (!pcFound) {
    _driver.printCentered(1, F("Offline Mode    "));
    delay(300);
  }

  _driver.clear();
  _state = OS_STATE_MAIN_MENU;
  drawMainMenu();
}

bool LCDKeypadOS::registerApp(AppService* app) {
  if (_appCount >= MAX_APPS || app == nullptr) {
    return false;
  }

  _apps[_appCount] = app;
  app->setOS(this);
  _appCount++;
  return true;
}

int8_t LCDKeypadOS::findAppIndexById(uint8_t appId) const {
  for (uint8_t i = 0; i < _appCount; i++) {
    if (_apps[i] != nullptr && _apps[i]->getAppId() == appId) {
      return (int8_t)i;
    }
  }
  return -1;
}

bool LCDKeypadOS::launchAppById(uint8_t appId) {
  int8_t idx = findAppIndexById(appId);
  if (idx < 0) return false;
  launchApp((uint8_t)idx);
  return true;
}

void LCDKeypadOS::dispatchAppSettings(const byte* payload, uint8_t len) {
  if (!payload || len < 2) return;

  // 1. Cai dat he thong (Backlight)
  bool bl = (payload[0] != 0);
  _driver.setBacklight(bl);
  EEPROM.update(0, 0xA5);
  EEPROM.update(1, bl ? 1 : 0);

  // 2. Doc va phan phoi block cai dat cua tung App
  // Dinh dang moi block: [AppId(1B), DataLen(1B), Data...]
  uint8_t pos = 2;
  while (pos + 2 <= len) {
    uint8_t aId = payload[pos++];
    uint8_t dLen = payload[pos++];
    if (pos + dLen > len) break; // Bao ve vuot qua buffer

    for (uint8_t i = 0; i < _appCount; i++) {
      if (_apps[i] != nullptr && _apps[i]->getAppId() == aId) {
        _apps[i]->loadSettings(&payload[pos], dLen);
        break;
      }
    }

    // Luu luon vao EEPROM noi bo de du phong khi offline
    if (aId > 0 && dLen <= 8) {
      int eeAddr = 10 + (aId * 8);
      if (eeAddr + dLen < 1000) {
        EEPROM.update(eeAddr, dLen);
        for (uint8_t k = 0; k < dLen; k++) {
          EEPROM.update(eeAddr + 1 + k, payload[pos + k]);
        }
      }
    }

    pos += dLen;
  }
}

void LCDKeypadOS::saveAppSetting(uint8_t appId, const byte* data, uint8_t len) {
  // 1. Luu vao EEPROM noi bo
  if (appId == 0) {
    if (len >= 1) {
      bool bl = (data[0] != 0);
      _driver.setBacklight(bl);
      EEPROM.update(0, 0xA5);
      EEPROM.update(1, bl ? 1 : 0);
    }
  } else {
    int eeAddr = 10 + (appId * 8);
    if (eeAddr + len < 1000) {
      EEPROM.update(0, 0xA5);
      EEPROM.update(eeAddr, len);
      for (uint8_t k = 0; k < len; k++) {
        EEPROM.update(eeAddr + 1 + k, data[k]);
      }
    }
  }

  // 2. Gui goi tin CMD_SAVE_SETTINGS (0x09) len PC de luu vao os_settings.json
  byte pktLen = 1 + 1 + len + 1; // cmd + appId + data + checksum
  byte cs = 0x09 ^ appId;
  for (uint8_t k = 0; k < len; k++) cs ^= data[k];

  Serial.write(0xAA);
  Serial.write(pktLen);
  Serial.write(0x09); // CMD_SAVE_SETTINGS
  Serial.write(appId);
  for (uint8_t k = 0; k < len; k++) Serial.write(data[k]);
  Serial.write(cs);
  Serial.write(0xBB);
}

void LCDKeypadOS::resetAllSettings() {
  // 1. Reset he thong: Bat den nen
  _driver.setBacklight(true);

  // 2. Ghi de EEPROM noi bo ve mac dinh
  EEPROM.update(0, 0xA5); // Signature
  EEPROM.update(1, 1);    // Backlight ON

  // App 1 (NativeGame): diff=1, highScore=0
  int addr1 = 10 + (1 * 8);
  EEPROM.update(addr1, 3);
  EEPROM.update(addr1 + 1, 1);
  EEPROM.update(addr1 + 2, 0);
  EEPROM.update(addr1 + 3, 0);

  // App 4 (Counter): count=0
  int addr4 = 10 + (4 * 8);
  EEPROM.update(addr4, 2);
  EEPROM.update(addr4 + 1, 0);
  EEPROM.update(addr4 + 2, 0);

  // 3. Reset toan bo cac App dang chay trong RAM
  for (uint8_t i = 0; i < _appCount; i++) {
    if (_apps[i] != nullptr) {
      uint8_t aId = _apps[i]->getAppId();
      if (aId == 0x01) {
        byte defData[3] = { 1, 0, 0 }; // Diff=1, HS=0
        _apps[i]->loadSettings(defData, 3);
      } else if (aId == 0x04) {
        byte defData[2] = { 0, 0 };    // Count=0
        _apps[i]->loadSettings(defData, 2);
      } else if (aId == 0x02) {
        byte defData[1] = { 1 };       // Echo=1
        _apps[i]->loadSettings(defData, 1);
      } else if (aId == 0x06) {
        EEPROM.update(120, 0x00);      // Clear saved custom Server IP -> back to default
        byte defData[2] = { 0, 0 };
        _apps[i]->loadSettings(defData, 2);
      }
    }
  }

  // 4. Gui lenh CMD_RESET_ALL_SETTINGS (0x0A) len PC de reset file os_settings.json
  byte resetPkt[] = { 0xAA, 0x02, 0x0A, 0x0A, 0xBB };
  Serial.write(resetPkt, sizeof(resetPkt));
}

void LCDKeypadOS::update() {
  KeyCode key = _driver.getPressedKey();

  if (_state == OS_STATE_MAIN_MENU) {
    processOSSerial();
    handleMainMenu(key);
  } else if (_state == OS_STATE_APP_RUNNING) {
    if (_currentRunningApp >= 0 && _currentRunningApp < _appCount) {
      _apps[_currentRunningApp]->update(key);
    }
  }
}

// Helper do luong Free RAM
static int getOSFreeRam() {
  extern int __heap_start, *__brkval;
  int v;
  return (int)&v - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}

void LCDKeypadOS::processOSSerial() {
  while (Serial.available() > 0) {
    byte b = Serial.peek();
    if (b == 0xAA) {
      // Cho du tối thiểu 4 byte để kiểm tra frame
      unsigned long t0 = millis();
      while (Serial.available() < 4 && (millis() - t0 < 30));
      if (Serial.available() < 4) break;

      byte start = Serial.read(); // 0xAA
      byte len   = Serial.read();
      byte cmd   = Serial.read();

      if (len < 2 || len > 64) {
        continue;
      }

      byte dataLen = len - 2;
      byte dataBuf[64];
      for (byte i = 0; i < dataLen; i++) {
        while (Serial.available() == 0 && (millis() - t0 < 30));
        dataBuf[i] = Serial.read();
      }

      while (Serial.available() < 2 && (millis() - t0 < 30));
      byte recvChecksum = Serial.read();
      byte endByte = Serial.read();

      if (endByte == 0xBB) {
        // Tinh toan Checksum XOR
        byte calcChecksum = cmd;
        for (byte i = 0; i < dataLen; i++) {
          calcChecksum ^= dataBuf[i];
        }

        if (calcChecksum == recvChecksum) {
          if (cmd == 0x06) {
            // CMD_PING -> Phan hoi RESP_PONG ngay
            byte pong[9];
            pong[0] = 0xAA;
            pong[1] = 1 + dataLen + 1;
            pong[2] = 0x86; // RESP_PONG
            byte cs = 0x86;
            for (byte k = 0; k < dataLen; k++) {
              pong[3 + k] = dataBuf[k];
              cs ^= dataBuf[k];
            }
            pong[3 + dataLen] = cs;
            pong[4 + dataLen] = 0xBB;
            Serial.write(pong, 5 + dataLen);
          } else if (cmd == 0x07) {
            // CMD_GET_TELEMETRY -> Tra ve telemetry o tang OS
            unsigned int uptime = (unsigned int)(millis() / 1000);
            unsigned int freeRam = (unsigned int)getOSFreeRam();
            unsigned int a0 = analogRead(A0);

            byte tele[16];
            tele[0] = 0xAA;
            tele[1] = 13; // cmd + 11B data + checksum
            tele[2] = 0x87; // RESP_TELEMETRY
            tele[3] = lowByte(uptime);
            tele[4] = highByte(uptime);
            tele[5] = lowByte(freeRam);
            tele[6] = highByte(freeRam);
            tele[7] = 0x00; // rxPackets
            tele[8] = 0x00;
            tele[9] = 0x00; // crcErr
            tele[10] = lowByte(a0);
            tele[11] = highByte(a0);
            tele[12] = (byte)_state; // 0 = OS_STATE_MAIN_MENU
            tele[13] = 0x00; // lastErr

            byte cs = 0x87;
            for (byte k = 3; k < 14; k++) cs ^= tele[k];
            tele[14] = cs;
            tele[15] = 0xBB;
            Serial.write(tele, sizeof(tele));
          } else if (cmd == 0x88) {
            // RESP_SETTINGS -> Dong bo cai dat he thong & tung App tu PC
            dispatchAppSettings(dataBuf, dataLen);
          }
          // Cac goi khac (nhu CMD_GAME_STATE 0x10): Tuyet doi khong tu dong cuop quyen Menu Tong!
        }
      }
    } else {
      // Xoa byte rac tren Serial de giu buffer sach se
      Serial.read();
    }
  }
}

void LCDKeypadOS::handleMainMenu(KeyCode key) {
  if (_appCount == 0) {
    _driver.printCentered(0, F("== ARDUINO OS =="));
    _driver.printCentered(1, F("No Apps Loaded!"));
    return;
  }

  if (key == KEY_UP) {
    _selectedAppIndex = (_selectedAppIndex - 1 + _appCount) % _appCount;
    drawMainMenu();
  } else if (key == KEY_DOWN) {
    _selectedAppIndex = (_selectedAppIndex + 1) % _appCount;
    drawMainMenu();
  } else if (key == KEY_SELECT) {
    launchApp(_selectedAppIndex);
  }
}

void LCDKeypadOS::launchApp(uint8_t index) {
  if (index >= _appCount || _apps[index] == nullptr) return;

  _currentRunningApp = index;
  _state = OS_STATE_APP_RUNNING;
  _driver.clear();

  // Kich hoat lifecycle cua App
  _apps[_currentRunningApp]->onEnter();
}

void LCDKeypadOS::returnToMainMenu() {
  if (_currentRunningApp >= 0 && _currentRunningApp < _appCount) {
    if (_apps[_currentRunningApp] != nullptr) {
      _apps[_currentRunningApp]->onExit();
    }
  }

  _currentRunningApp = -1;
  _state = OS_STATE_MAIN_MENU;
  _driver.clear();
  drawMainMenu();
}

void LCDKeypadOS::drawMainMenu() {
  if (_appCount == 0) return;

  // Dong 1: Header va vi tri app hien tai (vd: "OS MENU    [1/3]")
  char header[17];
  snprintf(header, sizeof(header), "OS MENU    [%u/%u]", (unsigned int)(_selectedAppIndex + 1), (unsigned int)_appCount);
  _driver.printAt(0, 0, header);

  // Dong 2: Ten ung dung co con tro ">"
  char appLine[17];
  const char* name = _apps[_selectedAppIndex]->getAppName();
  snprintf(appLine, sizeof(appLine), ">%-15s", name ? name : "Unknown");
  // Bao dam dung 16 ky tu
  appLine[16] = '\0';
  _driver.printAt(0, 1, appLine);
}
