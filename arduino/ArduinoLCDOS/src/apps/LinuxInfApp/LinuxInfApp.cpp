/**
 * LinuxInfApp.cpp
 *
 * Implement Module: Ung dung LinuxInf tren Arduino LCD OS.
 * Cho phep xem danh sach cac lenh sudo (chay qua sudo -l tren Linux) va thong tin Linux.
 * Toi uu hoa 100% SRAM bang F() macro de tiet kiem bo nho chip ATmega328P.
 */

#include "LinuxInfApp.h"
#include "../../core/LCDKeypadDriver.h"

// ----------- Giao thuc binary -----------
static const byte PKT_START = 0xAA;
static const byte PKT_END   = 0xBB;

// Ma lenh giao tiep voi PC
static const byte CMD_REQ_LINUX_SUDO_ITEM = 0x30; // Yeu cau 1 lenh sudo theo index
static const byte CMD_REQ_LINUX_INFO      = 0x31; // Yeu cau thong tin Linux
static const byte RESP_LINUX_SUDO_ITEM    = 0x8A; // PC tra ve lenh sudo [idx, total, name, desc]
static const byte RESP_LINUX_INFO         = 0x8B; // PC tra ve thong tin he thong [line1, line2]

LinuxInfApp::LinuxInfApp()
  : _state(LINUX_STATE_MENU),
    _menuIndex(0),
    _appEnterTime(0),
    _lastReqTime(0),
    _currentCmdIndex(0),
    _totalCmdCount(0),
    _rxPos(0),
    _receiving(false)
{
  _cmdName[0] = '\0';
  _cmdDesc[0] = '\0';
}

void LinuxInfApp::onEnter() {
  _state = LINUX_STATE_MENU;
  _menuIndex = 0;
  _currentCmdIndex = 0;
  _totalCmdCount = 0;
  _rxPos = 0;
  _receiving = false;
  _appEnterTime = millis();

  // Xoa buffer cu tren Serial
  while (Serial.available() > 0) {
    Serial.read();
  }

  drawMenu();
}

void LinuxInfApp::onExit() {
  _state = LINUX_STATE_MENU;
}

void LinuxInfApp::update(KeyCode key) {
  // 1. Luon doc va xu ly luong Serial nhan tu PC truoc
  processSerialInput();

  unsigned long now = millis();

  // Khoang dem an toan 350ms khi moi vao de chong xung sut ap phim SELECT
  if (now - _appEnterTime < 350) {
    return;
  }

  // 2. Kiem tra timeout khi dang cho phan hoi tu PC
  if (_state == LINUX_STATE_SUDO_LOADING || _state == LINUX_STATE_INFO_LOADING) {
    if (now - _lastReqTime > 2500) {
      _state = LINUX_STATE_NO_PC;
      drawNoPCScreen();
      return;
    }
  }

  if (key == KEY_NONE) return;

  // 3. Xu ly phim bam theo tung trang thai
  if (_state == LINUX_STATE_MENU) {
    if (key == KEY_UP) {
      _menuIndex = (_menuIndex - 1 + 3) % 3;
      drawMenu();
    } else if (key == KEY_DOWN) {
      _menuIndex = (_menuIndex + 1) % 3;
      drawMenu();
    } else if (key == KEY_SELECT) {
      if (_menuIndex == 0) {
        // Chon 1. Sudo Privs -> Yeu cau PC gui lenh dau tien (index = 0)
        _state = LINUX_STATE_SUDO_LOADING;
        _currentCmdIndex = 0;
        _totalCmdCount = 0;
        drawLoadingScreen(F("Linux Sudo Privs"), F("Dang doc sudo -l"));
        requestSudoItem(0);
      } else if (_menuIndex == 1) {
        // Chon 2. Linux Info -> Yeu cau thong tin Linux
        _state = LINUX_STATE_INFO_LOADING;
        drawLoadingScreen(F("Linux SystemInfo"), F("Dang lay info..."));
        requestLinuxInfo();
      } else if (_menuIndex == 2) {
        // Chon 3. Thoat ve OS
        exitApp();
      }
    } else if (key == KEY_LEFT) {
      // Bam LEFT tren Menu -> Quay ve Menu Tong cua OS
      exitApp();
    }

  } else if (_state == LINUX_STATE_SUDO_VIEWER) {
    // Trinh duyet cac lenh Sudo
    if (key == KEY_DOWN) {
      if (_totalCmdCount > 1) {
        _currentCmdIndex = (_currentCmdIndex + 1) % _totalCmdCount;
        requestSudoItem(_currentCmdIndex);
      }
    } else if (key == KEY_UP) {
      if (_totalCmdCount > 1) {
        _currentCmdIndex = (_currentCmdIndex - 1 + _totalCmdCount) % _totalCmdCount;
        requestSudoItem(_currentCmdIndex);
      }
    } else if (key == KEY_SELECT) {
      // YEU CAU: Cac lenh nay khong dung de execute duoc!
      // Khi bam SELECT, man hinh thong bao ro rang "Chi xem (No Exec)"
      LCDKeypadDriver* drv = getDriver();
      if (drv) {
        drv->printAt(0, 1, F("Chi xem (No Exec)"));
        delay(700);
        drawSudoViewer();
      }
    } else if (key == KEY_LEFT) {
      // Bam LEFT -> Quay ve Menu LinuxInf
      _state = LINUX_STATE_MENU;
      drawMenu();
    }

  } else if (_state == LINUX_STATE_INFO_VIEWER || _state == LINUX_STATE_NO_PC) {
    // Bam LEFT hoac SELECT de quay ve Menu LinuxInf
    if (key == KEY_LEFT || key == KEY_SELECT) {
      _state = LINUX_STATE_MENU;
      drawMenu();
    }
  }
}

void LinuxInfApp::requestSudoItem(uint8_t index) {
  _lastReqTime = millis();
  byte idx = index;
  sendPacket(CMD_REQ_LINUX_SUDO_ITEM, &idx, 1);
}

void LinuxInfApp::requestLinuxInfo() {
  _lastReqTime = millis();
  sendPacket(CMD_REQ_LINUX_INFO, NULL, 0);
}

void LinuxInfApp::processSerialInput() {
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
        _receiving = false;
        _rxPos = 0;
        continue;
      }

      if (_rxPos == 1) {
        byte len = _rxBuffer[0];
        if (len < 2 || len > 38) {
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
              processCommand(cmd, &_rxBuffer[2], dataLen);
            }
          }
          _receiving = false;
          _rxPos = 0;
        }
      }
    }
  }
}

void LinuxInfApp::processCommand(byte cmd, const byte* data, byte dataLen) {
  if (cmd == RESP_LINUX_SUDO_ITEM) {
    // Data: [index(1B), total(1B), name_len(1B), name(NB), desc_len(1B), desc(MB)]
    if (dataLen >= 4) {
      uint8_t idx = data[0];
      uint8_t total = data[1];
      uint8_t nLen = data[2];
      if (nLen > 16) nLen = 16;

      if (3 + nLen <= dataLen) {
        memcpy(_cmdName, &data[3], nLen);
        _cmdName[nLen] = '\0';

        uint8_t dPos = 3 + data[2];
        if (dPos < dataLen) {
          uint8_t dLen = data[dPos++];
          if (dLen > 16) dLen = 16;
          if (dPos + dLen <= dataLen) {
            memcpy(_cmdDesc, &data[dPos], dLen);
            _cmdDesc[dLen] = '\0';
          } else {
            _cmdDesc[0] = '\0';
          }
        } else {
          _cmdDesc[0] = '\0';
        }

        _currentCmdIndex = idx;
        _totalCmdCount = total;
        _state = LINUX_STATE_SUDO_VIEWER;
        drawSudoViewer();
      }
    }
    return;

  } else if (cmd == RESP_LINUX_INFO) {
    // Data: [line1_len(1B), line1(NB), line2_len(1B), line2(MB)]
    // Dung chung buffer _cmdName va _cmdDesc de tiet kiem SRAM
    if (dataLen >= 2) {
      uint8_t l1Len = data[0];
      if (l1Len > 16) l1Len = 16;
      memcpy(_cmdName, &data[1], l1Len);
      _cmdName[l1Len] = '\0';

      uint8_t pos2 = 1 + data[0];
      if (pos2 < dataLen) {
        uint8_t l2Len = data[pos2++];
        if (l2Len > 16) l2Len = 16;
        if (pos2 + l2Len <= dataLen) {
          memcpy(_cmdDesc, &data[pos2], l2Len);
          _cmdDesc[l2Len] = '\0';
        } else {
          _cmdDesc[0] = '\0';
        }
      } else {
        _cmdDesc[0] = '\0';
      }

      _state = LINUX_STATE_INFO_VIEWER;
      drawLinuxInfo();
    }
    return;
  }
}

void LinuxInfApp::sendPacket(byte cmd, const byte* data, byte dataLen) {
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

void LinuxInfApp::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->printAt(0, 0, F("=== LINUX INF =="));
  if (_menuIndex == 0) {
    drv->printAt(0, 1, F(">1.Sudo Privs   "));
  } else if (_menuIndex == 1) {
    drv->printAt(0, 1, F(">2.Linux Info   "));
  } else {
    drv->printAt(0, 1, F(">3.Thoat ve OS  "));
  }
}

void LinuxInfApp::drawSudoViewer() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();

  // Dong tren: Ten lenh co chi so [1/N] (toi da 16 ky tu)
  char topBuf[17];
  if (_totalCmdCount > 0) {
    snprintf(topBuf, sizeof(topBuf), "[%u/%u] %s", (unsigned int)(_currentCmdIndex + 1), (unsigned int)_totalCmdCount, _cmdName);
  } else {
    snprintf(topBuf, sizeof(topBuf), "Lenh: %s", _cmdName);
  }
  topBuf[16] = '\0';
  drv->printAt(0, 0, topBuf);

  // Dong duoi: Mo ta chi tiet lenh (toi da 16 ky tu)
  char btmBuf[17];
  snprintf(btmBuf, sizeof(btmBuf), "%-16s", _cmdDesc);
  btmBuf[16] = '\0';
  drv->printAt(0, 1, btmBuf);
}

void LinuxInfApp::drawLinuxInfo() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  drv->printAt(0, 0, _cmdName);
  drv->printAt(0, 1, _cmdDesc);
}

void LinuxInfApp::drawLoadingScreen(const __FlashStringHelper* title, const __FlashStringHelper* msg) {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  drv->printAt(0, 0, title);
  drv->printAt(0, 1, msg);
}

void LinuxInfApp::drawNoPCScreen() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  drv->printAt(0, 0, F("LinuxInf [No PC]"));
  drv->printAt(0, 1, F("<-LEFT de quay ve"));
}
