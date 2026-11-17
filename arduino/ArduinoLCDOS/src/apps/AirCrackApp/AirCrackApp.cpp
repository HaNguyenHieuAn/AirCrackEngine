#include "AirCrackApp.h"
#include "../KeyboardApp/KeyboardApp.h"
#include "../../core/LCDKeypadDriver.h"
#include "../../core/LCDKeypadOS.h"
#include <EEPROM.h>
#include <string.h>

static const byte PKT_START = 0xAA;
static const byte PKT_END   = 0xBB;
static const char DEFAULT_SERVER_IP[] = "169.254.84.122";
static const int  EEPROM_SERVER_IP_ADDR = 120;

AirCrackApp::AirCrackApp()
  : _state(AC_STATE_MENU),
    _menuIndex(0),
    _scanIndex(0),
    _scanTotal(0),
    _scanChannel(0),
    _scanPower(0),
    _hcfIndex(0),
    _hcfTotal(0),
    _selectedCard(0),
    _statusIface(0),
    _awaitingServerIp(false),
    _appEnterTime(0),
    _lastReqTime(0),
    _pcConnected(true),
    _rxPos(0),
    _receiving(false)
{
  _scanBssid[0] = '\0';
  _hcfName[0] = '\0';
  strcpy(_serverIp, DEFAULT_SERVER_IP);
  for (uint8_t i = 0; i < 4; i++) _cardModes[i] = 0;
}

void AirCrackApp::loadServerIpFromEEPROM() {
  if (EEPROM.read(EEPROM_SERVER_IP_ADDR) == 0xA6) {
    uint8_t len = EEPROM.read(EEPROM_SERVER_IP_ADDR + 1);
    if (len > 0 && len <= 20) {
      for (uint8_t i = 0; i < len; i++) {
        _serverIp[i] = (char)EEPROM.read(EEPROM_SERVER_IP_ADDR + 2 + i);
      }
      _serverIp[len] = '\0';
      return;
    }
  }
  strcpy(_serverIp, DEFAULT_SERVER_IP);
}

void AirCrackApp::saveServerIpToEEPROM() {
  uint8_t len = (uint8_t)strlen(_serverIp);
  if (len == 0 || len > 20) {
    strcpy(_serverIp, DEFAULT_SERVER_IP);
    len = (uint8_t)strlen(_serverIp);
  }
  EEPROM.update(EEPROM_SERVER_IP_ADDR, 0xA6);
  EEPROM.update(EEPROM_SERVER_IP_ADDR + 1, len);
  for (uint8_t i = 0; i < len; i++) {
    EEPROM.update(EEPROM_SERVER_IP_ADDR + 2 + i, (byte)_serverIp[i]);
  }
}

void AirCrackApp::onEnter() {
  if (_awaitingServerIp) {
    _awaitingServerIp = false;
    const char* ip = KeyboardApp::getResult();
    KeyboardApp::clearDone();
    bool isDefault = false;
    if (!ip || ip[0] == '\0') {
      strcpy(_serverIp, DEFAULT_SERVER_IP);
      isDefault = true;
    } else {
      strncpy(_serverIp, ip, 20);
      _serverIp[20] = '\0';
    }
    saveServerIpToEEPROM();
    sendServerIp(_serverIp);
    LCDKeypadDriver* drv = getDriver();
    if (drv) {
      drv->clear();
      drv->printAt(0, 0, isDefault ? F("IP Mac Dinh:") : F("Server IP set:"));
      char l1[17];
      snprintf(l1, sizeof(l1), "%-16s", _serverIp);
      l1[16] = '\0';
      drv->printAt(0, 1, l1);
    }
    _state = AC_STATE_STATUS_VIEW;
    return;
  }

  if (_serverIp[0] == '\0') {
    loadServerIpFromEEPROM();
  }

  _state = AC_STATE_MENU;
  _menuIndex = 0;
  _scanIndex = 0;
  _scanTotal = 0;
  _hcfIndex = 0;
  _hcfTotal = 0;
  _rxPos = 0;
  _receiving = false;
  _appEnterTime = millis();
  _lastReqTime = 0;
  _pcConnected = true;
  while (Serial.available() > 0) Serial.read();
  drawMenu();
}

void AirCrackApp::loadSettings(const byte* data, uint8_t len) {
  loadServerIpFromEEPROM();
  if (data && len >= 2) {
    _selectedCard = data[0] % 4;
    for (uint8_t i = 0; i < 4; i++) _cardModes[i] = data[1] % 4;
    if (len > 2 && data[2] >= 0x20) {
      uint8_t ipLen = len - 2;
      if (ipLen > 20) ipLen = 20;
      memcpy(_serverIp, &data[2], ipLen);
      _serverIp[ipLen] = '\0';
      saveServerIpToEEPROM();
    } else if (len >= 5 && data[2] < 4) {
      for (uint8_t i = 0; i < 4; i++) _cardModes[i] = data[1 + i] % 4;
    }
  }
}

void AirCrackApp::saveMySettings() {
  byte data[2] = { (byte)_selectedCard, (byte)_cardModes[_selectedCard] };
  saveSetting(data, 2);
}

void AirCrackApp::update(KeyCode key) {
  processSerialInput();

  unsigned long now = millis();
  if (now - _appEnterTime < 350) return;

  if (_state == AC_STATE_SCAN_LOADING || _state == AC_STATE_ACTION_LOADING || _state == AC_STATE_HCF_LOADING) {
    if (now - _lastReqTime > 15000) {
      _pcConnected = false;
      _state = AC_STATE_NO_PC;
      drawNoPCScreen();
      return;
    }
  }

  if (key == KEY_NONE) return;

  if (_state == AC_STATE_MENU) {
    if (key == KEY_UP) {
      _menuIndex = (_menuIndex - 1 + 13) % 13;
      drawMenu();
    } else if (key == KEY_DOWN) {
      _menuIndex = (_menuIndex + 1) % 13;
      drawMenu();
    } else if (key == KEY_SELECT) {
      if (_menuIndex == 0) {
        _pcConnected = true;
        _state = AC_STATE_SCAN_LOADING;
        _scanIndex = 0;
        _scanTotal = 0;
        drawLoadingScreen(F("AirCrack Scan"), F("Dang quet AP..."));
        requestScanItem(0);
      } else if (_menuIndex == 1) {
        if (_scanTotal == 0) {
          LCDKeypadDriver* drv = getDriver();
          if (drv) { drv->printAt(0,1,F("Chua co scan  ")); delay(600); drawMenu(); }
          return;
        }
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Select Target"), F("Dang chon AP..."));
        _lastReqTime = millis();
        sendAction(0x01, _scanIndex);
      } else if (_menuIndex == 2) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Monitor Mode"), F("Dang bat mon..."));
        _lastReqTime = millis();
        sendAction(0x02, _selectedCard);
      } else if (_menuIndex == 3) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Capture HS"), F("Dang bat..."));
        _lastReqTime = millis();
        sendAction(0x03, _scanIndex);
      } else if (_menuIndex == 4) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Deauth"), F("Dang gui..."));
        _lastReqTime = millis();
        sendAction(0x04, _scanIndex);
      } else if (_menuIndex == 5) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Convert HC"), F("Dang chuyen..."));
        _lastReqTime = millis();
        sendAction(0x05, 0);
      } else if (_menuIndex == 6) {
        _pcConnected = true;
        _state = AC_STATE_HCF_LOADING;
        _hcfIndex = 0;
        _hcfTotal = 0;
        drawLoadingScreen(F("HC22000 Files"), F("Tai danh sach.."));
        requestHcfItem(0);
      } else if (_menuIndex == 7) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Server Status"), F("Dang kiem tra.."));
        _lastReqTime = millis();
        sendAction(0x06, 0);
      } else if (_menuIndex == 8) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Download WiFi"), F("Dang tai..."));
        _lastReqTime = millis();
        sendAction(0x07, 0);
      } else if (_menuIndex == 9) {
        _selectedCard = (_selectedCard + 1) % 4;
        saveMySettings();
        drawMenu();
      } else if (_menuIndex == 10) {
        _pcConnected = true;
        _cardModes[_selectedCard] = (_cardModes[_selectedCard] + 1) % 4;
        saveMySettings();
        sendCardMode(_selectedCard, _cardModes[_selectedCard]);
        drawMenu();
      } else if (_menuIndex == 11) {
        if (_serverIp[0] == '\0') loadServerIpFromEEPROM();
        _awaitingServerIp = true;
        KeyboardApp::prepareInput(getAppId(), _serverIp, 2);
        if (_os) _os->launchAppById(0x08);
      } else if (_menuIndex == 12) {
        exitApp();
      }
    } else if (key == KEY_LEFT) {
      exitApp();
    }

  } else if (_state == AC_STATE_SCAN_VIEWER) {
    if (key == KEY_DOWN) {
      if (_scanTotal > 1) {
        _scanIndex = (_scanIndex + 1) % _scanTotal;
        requestScanItem(_scanIndex);
      }
    } else if (key == KEY_UP) {
      if (_scanTotal > 1) {
        _scanIndex = (_scanIndex - 1 + _scanTotal) % _scanTotal;
        requestScanItem(_scanIndex);
      }
    } else if (key == KEY_SELECT) {
      if (_scanTotal > 0) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Select Target"), F("Dang chon AP..."));
        _lastReqTime = millis();
        sendAction(0x01, _scanIndex);
      } else {
        _state = AC_STATE_MENU;
        drawMenu();
      }
    } else if (key == KEY_LEFT) {
      _state = AC_STATE_MENU;
      drawMenu();
    }

  } else if (_state == AC_STATE_HCF_VIEWER) {
    if (key == KEY_DOWN) {
      if (_hcfTotal > 1) {
        _hcfIndex = (_hcfIndex + 1) % _hcfTotal;
        requestHcfItem(_hcfIndex);
      }
    } else if (key == KEY_UP) {
      if (_hcfTotal > 1) {
        _hcfIndex = (_hcfIndex - 1 + _hcfTotal) % _hcfTotal;
        requestHcfItem(_hcfIndex);
      }
    } else if (key == KEY_SELECT) {
      if (_hcfTotal > 0) {
        _pcConnected = true;
        _state = AC_STATE_ACTION_LOADING;
        drawLoadingScreen(F("Crack HC22000"), F("Upload&Crack..."));
        _lastReqTime = millis();
        sendAction(0x08, _hcfIndex);
      } else {
        _state = AC_STATE_MENU;
        drawMenu();
      }
    } else if (key == KEY_LEFT) {
      _state = AC_STATE_MENU;
      drawMenu();
    }

  } else if (_state == AC_STATE_STATUS_VIEW || _state == AC_STATE_NO_PC || _state == AC_STATE_TARGET_SELECTED) {
    if (key == KEY_LEFT || key == KEY_SELECT) {
      _state = AC_STATE_MENU;
      drawMenu();
    }
  }
}

void AirCrackApp::requestScanItem(uint8_t index) {
  _lastReqTime = millis();
  byte idx = index;
  sendPacket(CMD_REQ_AIRCRACK_SCAN_ITEM, &idx, 1);
}

void AirCrackApp::requestHcfItem(uint8_t index) {
  _lastReqTime = millis();
  byte idx = index;
  sendPacket(CMD_REQ_HCF_ITEM, &idx, 1);
}

void AirCrackApp::sendAction(byte action, byte extra) {
  byte data[2] = { action, extra };
  byte cs = CMD_AIRCRACK_ACTION ^ data[0] ^ data[1];
  Serial.write(0xAA);
  Serial.write(4);
  Serial.write(CMD_AIRCRACK_ACTION);
  Serial.write(data[0]);
  Serial.write(data[1]);
  Serial.write(cs);
  Serial.write(0xBB);
}

void AirCrackApp::sendCardMode(uint8_t card, uint8_t mode) {
  byte buf[2] = { card, mode };
  sendPacket(CMD_AIRCRACK_CARD_MODE, buf, 2);
}

void AirCrackApp::sendServerIp(const char* ip) {
  if (!ip) return;
  uint8_t len = (uint8_t)strlen(ip);
  if (len > 30) len = 30;
  byte buf[31];
  for (uint8_t i = 0; i < len; i++) buf[i] = (byte)ip[i];
  sendPacket(CMD_AIRCRACK_SERVER_IP, buf, len);
}

void AirCrackApp::sendPacket(byte cmd, const byte* data, byte dataLen) {
  byte len = 1 + dataLen + 1;
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

void AirCrackApp::processSerialInput() {
  while (Serial.available() > 0) {
    byte b = Serial.read();
    if (!_receiving) {
      if (b == PKT_START) { _receiving = true; _rxPos = 0; }
    } else {
      if (_rxPos < (int)sizeof(_rxBuffer)) _rxBuffer[_rxPos++] = b;
      else { _receiving = false; _rxPos = 0; continue; }

      if (_rxPos == 1) {
        byte len = _rxBuffer[0];
        if (len < 2 || len > 28) { _receiving = false; _rxPos = 0; }
      } else if (_rxPos >= 2) {
        byte len = _rxBuffer[0];
        if (_rxPos == (len + 2)) {
          if (_rxBuffer[_rxPos - 1] == PKT_END) {
            byte cmd = _rxBuffer[1];
            byte dataLen = len - 2;
            byte calcChecksum = cmd;
            for (byte i = 0; i < dataLen; i++) calcChecksum ^= _rxBuffer[2 + i];
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

void AirCrackApp::processCommand(byte cmd, const byte* data, byte dataLen) {
  _pcConnected = true;
  if (cmd == RESP_AIRCRACK_SCAN_ITEM) {
    if (dataLen >= 4) {
      _scanIndex = data[0];
      _scanTotal = data[1];
      uint8_t rawLen = data[2];
      uint8_t copyLen = (rawLen > 12) ? 12 : rawLen;
      if (3 + rawLen <= dataLen) {
        memcpy(_scanBssid, &data[3], copyLen);
        _scanBssid[copyLen] = '\0';
        uint8_t pos = 3 + rawLen;
        if (pos + 1 < dataLen) {
          _scanChannel = data[pos++];
          _scanPower = data[pos];
        }
      }
      _state = AC_STATE_SCAN_VIEWER;
      drawScanViewer();
    }
    return;
  }

  if (cmd == RESP_HCF_ITEM) {
    if (dataLen >= 4) {
      _hcfIndex = data[0];
      _hcfTotal = data[1];
      uint8_t rawLen = data[2];
      uint8_t copyLen = (rawLen > 12) ? 12 : rawLen;
      if (3 + rawLen <= dataLen) {
        memcpy(_hcfName, &data[3], copyLen);
        _hcfName[copyLen] = '\0';
      }
      _state = AC_STATE_HCF_VIEWER;
      drawHcfViewer();
    }
    return;
  }

  if (cmd == RESP_AIRCRACK_STATUS) {
    // [iface, msg_len, msg...]
    if (dataLen >= 2) {
      _statusIface = data[0];
      uint8_t rawLen = data[1];
      uint8_t copyLen = (rawLen > 12) ? 12 : rawLen;
      if (2 + rawLen <= dataLen) {
        memcpy(_hcfName, &data[2], copyLen);
        _hcfName[copyLen] = '\0';
      } else {
        _hcfName[0] = '\0';
      }
    }
    _state = AC_STATE_STATUS_VIEW;
    drawStatusView();
    return;
  }
}

void AirCrackApp::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->printAt(0, 0, F("== AIRCRACK =="));
  if (_menuIndex == 0) drv->printAt(0, 1, F(">1.Scan APs     "));
  else if (_menuIndex == 1) drv->printAt(0, 1, F(">2.Sel Target   "));
  else if (_menuIndex == 2) drv->printAt(0, 1, F(">3.Monitor Mode "));
  else if (_menuIndex == 3) drv->printAt(0, 1, F(">4.Capture HS   "));
  else if (_menuIndex == 4) drv->printAt(0, 1, F(">5.Deauth       "));
  else if (_menuIndex == 5) drv->printAt(0, 1, F(">6.Convert HC   "));
  else if (_menuIndex == 6) drv->printAt(0, 1, F(">7.HC Files     "));
  else if (_menuIndex == 7) drv->printAt(0, 1, F(">8.Server Stat  "));
  else if (_menuIndex == 8) drv->printAt(0, 1, F(">9.Download WiFi"));
  else if (_menuIndex == 9) {
    if (_selectedCard == 0) drv->printAt(0, 1, F(">10.Card:AUTO   "));
    else if (_selectedCard == 1) drv->printAt(0, 1, F(">10.Card:W0     "));
    else if (_selectedCard == 2) drv->printAt(0, 1, F(">10.Card:W1     "));
    else drv->printAt(0, 1, F(">10.Card:W2     "));
  } else if (_menuIndex == 10) {
    char line[17];
    const char* mstr[4] = { "MGD", "MON", "AP ", "CLI" };
    snprintf(line, sizeof(line), ">11.Card%u:%-3s   ", (unsigned int)_selectedCard, mstr[_cardModes[_selectedCard]]);
    line[16] = '\0';
    drv->printAt(0, 1, line);
  } else if (_menuIndex == 11) drv->printAt(0, 1, F(">12.Server IP   "));
  else drv->printAt(0, 1, F(">13.Exit        "));
}

void AirCrackApp::drawScanViewer() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  char top[17];
  if (_scanTotal > 0) snprintf(top, sizeof(top), "[%u/%u] %s", (unsigned int)(_scanIndex+1), (unsigned int)_scanTotal, _scanBssid);
  else snprintf(top, sizeof(top), "Scan: %s", _scanBssid);
  top[16] = '\0';
  drv->printAt(0, 0, top);
  char btm[17];
  snprintf(btm, sizeof(btm), "Ch:%-2u Pwr:%-3u", (unsigned int)_scanChannel, (unsigned int)_scanPower);
  btm[16] = '\0';
  drv->printAt(0, 1, btm);
}

void AirCrackApp::drawHcfViewer() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  char top[17];
  if (_hcfTotal > 0) snprintf(top, sizeof(top), "[%u/%u] %s", (unsigned int)(_hcfIndex+1), (unsigned int)_hcfTotal, _hcfName);
  else snprintf(top, sizeof(top), "HC: %s", _hcfName);
  top[16] = '\0';
  drv->printAt(0, 0, top);
  drv->printAt(0, 1, F("SEL:Action LFT"));
}

void AirCrackApp::drawStatusView() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  char l0[17];
  snprintf(l0, sizeof(l0), "IF:%u %-11s", (unsigned int)_statusIface, _hcfName);
  l0[16] = '\0';
  drv->printAt(0, 0, l0);
  drv->printAt(0, 1, F("<-LEFT Back    "));
}

void AirCrackApp::drawLoadingScreen(const __FlashStringHelper* title, const __FlashStringHelper* msg) {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  drv->printAt(0, 0, title);
  drv->printAt(0, 1, msg);
}

void AirCrackApp::drawNoPCScreen() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  drv->printAt(0, 0, F("AirCrack[NoPC]"));
  drv->printAt(0, 1, F("<-LEFT Back    "));
}