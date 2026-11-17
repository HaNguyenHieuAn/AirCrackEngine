#include "WifiSetApp.h"
#include "../KeyboardApp/KeyboardApp.h"
#include "../../core/LCDKeypadDriver.h"
#include "../../core/LCDKeypadOS.h"
#include <string.h>

static const byte PKT_START = 0xAA;
static const byte PKT_END   = 0xBB;

WifiSetApp::WifiSetApp()
  : _state(WIFiset_STATE_MENU),
    _menuIndex(0),
    _scanIndex(0),
    _scanTotal(0),
    _scanSignal(0),
    _knownIndex(0),
    _knownTotal(0),
    _selectedKnown(0),
    _ifaceMode(0),
    _selectedCard(0),
    _pendingKnown(0),
    _awaitingPassword(false),
    _manualAttempted(false),
    _pcConnected(true),
    _statusIface(0),
    _statusMode(0),
    _appEnterTime(0),
    _lastReqTime(0),
    _rxPos(0),
    _receiving(false)
{
  _scanName[0] = '\0';
  _knownName[0] = '\0';
  for (uint8_t i = 0; i < 4; i++) _cardModes[i] = 0;
}

void WifiSetApp::loadSettings(const byte* data, uint8_t len) {
  if (data && len >= 2) {
    _ifaceMode = data[0] % 4;
    if (len >= 5) {
      for (uint8_t i = 0; i < 4; i++) _cardModes[i] = data[1 + i] % 4;
    } else {
      for (uint8_t i = 0; i < 4; i++) _cardModes[i] = data[1] % 4;
    }
  }
}

void WifiSetApp::saveMySettings() {
  byte data[2] = { (byte)_ifaceMode, (byte)_cardModes[_selectedCard] };
  saveSetting(data, 2);
}

void WifiSetApp::onEnter() {
  // Neu vua quay lai tu Keyboard de nhap mat khau
  if (_awaitingPassword) {
    _awaitingPassword = false;
    _manualAttempted = true;
    const char* pw = KeyboardApp::getResult();
    KeyboardApp::clearDone();
    _state = WIFiset_STATE_CONNECTING;
    LCDKeypadDriver* drv = getDriver();
    if (drv) { drv->printAt(0,0,F("WifiSet Connect")); drv->printAt(0,1,F("Dang ket noi...")); }
    _lastReqTime = millis();
    sendConnectPassword(_pendingKnown, pw);
    return;
  }

  _state = WIFiset_STATE_MENU;
  _menuIndex = 0;
  _scanIndex = 0;
  _scanTotal = 0;
  _knownIndex = 0;
  _knownTotal = 0;
  _rxPos = 0;
  _receiving = false;
  _appEnterTime = millis();
  _lastReqTime = 0;
  _pcConnected = true;
  while (Serial.available() > 0) Serial.read();
  drawMenu();
}

void WifiSetApp::onExit() {
  _state = WIFiset_STATE_MENU;
}

void WifiSetApp::update(KeyCode key) {
  processSerialInput();

  unsigned long now = millis();
  if (now - _appEnterTime < 350) return;

  if (_state == WIFiset_STATE_SCAN_LOADING || _state == WIFiset_STATE_KNOWN_LOADING || _state == WIFiset_STATE_CONNECTING) {
    if (now - _lastReqTime > 15000) {
      _pcConnected = false;
      _state = WIFiset_STATE_NO_PC;
      drawNoPCScreen();
      return;
    }
  }

  if (key == KEY_NONE) return;

  if (_state == WIFiset_STATE_MENU) {
    if (key == KEY_UP) {
      _menuIndex = (_menuIndex - 1 + 7) % 7;
      drawMenu();
    } else if (key == KEY_DOWN) {
      _menuIndex = (_menuIndex + 1) % 7;
      drawMenu();
    } else if (key == KEY_SELECT) {
      if (_menuIndex == 0) {
        _pcConnected = true;
        _state = WIFiset_STATE_SCAN_LOADING;
        _scanIndex = 0;
        _scanTotal = 0;
        drawLoadingScreen(F("WifiSet Scan"), F("Dang quet WiFi.."));
        requestScanItem(0);
      } else if (_menuIndex == 1) {
        _pcConnected = true;
        _state = WIFiset_STATE_KNOWN_LOADING;
        _knownIndex = 0;
        _knownTotal = 0;
        drawLoadingScreen(F("WifiSet Known"), F("Tai danh sach.."));
        requestKnownItem(0);
      } else if (_menuIndex == 2) {
        _pcConnected = true;
        _pendingKnown = _selectedKnown;
        _manualAttempted = false;
        _state = WIFiset_STATE_CONNECTING;
        drawLoadingScreen(F("WifiSet Connect"), F("Dang ket noi..."));
        _lastReqTime = millis();
        sendAction(WIFiset_ACTION_CONNECT_AUTO, _pendingKnown);
      } else if (_menuIndex == 3) {
        _selectedCard = (_selectedCard + 1) % 4;
        _ifaceMode = _selectedCard;
        saveMySettings();
        drawMenu();
      } else if (_menuIndex == 4) {
        _pcConnected = true;
        _cardModes[_selectedCard] = (_cardModes[_selectedCard] + 1) % 4;
        saveMySettings();
        sendCardMode(_selectedCard, _cardModes[_selectedCard]);
        drawMenu();
      } else if (_menuIndex == 5) {
        _pcConnected = true;
        _state = WIFiset_STATE_STATUS_VIEW;
        _lastReqTime = millis();
        sendAction(WIFiset_ACTION_QUERY_STATUS, 0);
        drawLoadingScreen(F("WifiSet Status"), F("Dang lay status"));
      } else if (_menuIndex == 6) {
        exitApp();
      }
    } else if (key == KEY_LEFT) {
      exitApp();
    }

  } else if (_state == WIFiset_STATE_SCAN_VIEWER) {
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
        _pendingKnown = (uint8_t)(0x80 | (_scanIndex & 0x7F));
        _manualAttempted = false;
        _state = WIFiset_STATE_CONNECTING;
        drawLoadingScreen(F("WifiSet Connect"), F("Dang ket noi..."));
        _lastReqTime = millis();
        sendAction(WIFiset_ACTION_CONNECT_AUTO, _pendingKnown);
      } else {
        _state = WIFiset_STATE_MENU;
        drawMenu();
      }
    } else if (key == KEY_LEFT) {
      _state = WIFiset_STATE_MENU;
      drawMenu();
    }

  } else if (_state == WIFiset_STATE_KNOWN_VIEWER) {
    if (key == KEY_DOWN) {
      if (_knownTotal > 1) {
        _knownIndex = (_knownIndex + 1) % _knownTotal;
        _selectedKnown = _knownIndex;
        requestKnownItem(_knownIndex);
      }
    } else if (key == KEY_UP) {
      if (_knownTotal > 1) {
        _knownIndex = (_knownIndex - 1 + _knownTotal) % _knownTotal;
        _selectedKnown = _knownIndex;
        requestKnownItem(_knownIndex);
      }
    } else if (key == KEY_SELECT) {
      _selectedKnown = _knownIndex;
      _pendingKnown = _selectedKnown;
      _manualAttempted = false;
      _state = WIFiset_STATE_CONNECTING;
      drawLoadingScreen(F("WifiSet Connect"), F("Dang ket noi..."));
      _lastReqTime = millis();
      sendAction(WIFiset_ACTION_CONNECT_AUTO, _pendingKnown);
    } else if (key == KEY_LEFT) {
      _state = WIFiset_STATE_MENU;
      drawMenu();
    }

  } else if (_state == WIFiset_STATE_STATUS_VIEW || _state == WIFiset_STATE_NO_PC) {
    if (key == KEY_LEFT || key == KEY_SELECT) {
      _state = WIFiset_STATE_MENU;
      drawMenu();
    }
  }
}

void WifiSetApp::requestScanItem(uint8_t index) {
  _lastReqTime = millis();
  byte idx = index;
  sendPacket(CMD_REQ_WIFI_SCAN_ITEM, &idx, 1);
}

void WifiSetApp::requestKnownItem(uint8_t index) {
  _lastReqTime = millis();
  byte idx = index;
  sendPacket(CMD_REQ_WIFI_KNOWN_ITEM, &idx, 1);
}

void WifiSetApp::sendAction(byte action, byte extra) {
  byte data[2] = { action, extra };
  byte cs = CMD_WIFISET_ACTION ^ data[0] ^ data[1];
  Serial.write(0xAA);
  Serial.write(4);
  Serial.write(CMD_WIFISET_ACTION);
  Serial.write(data[0]);
  Serial.write(data[1]);
  Serial.write(cs);
  Serial.write(0xBB);
}

void WifiSetApp::sendConnectPassword(uint8_t index, const char* pw) {
  byte buf[34];
  buf[0] = index;
  uint8_t pwlen = (uint8_t)strlen(pw);
  if (pwlen > 30) pwlen = 30;
  buf[1] = pwlen;
  for (uint8_t i = 0; i < pwlen; i++) buf[2 + i] = (byte)pw[i];
  sendPacket(CMD_WIFISET_CONNECT_PW, buf, 2 + pwlen);
}

void WifiSetApp::sendCardMode(uint8_t card, uint8_t mode) {
  byte buf[2] = { card, mode };
  sendPacket(CMD_WIFISET_CARD_MODE, buf, 2);
}

void WifiSetApp::sendPacket(byte cmd, const byte* data, byte dataLen) {
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

void WifiSetApp::processSerialInput() {
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

void WifiSetApp::processCommand(byte cmd, const byte* data, byte dataLen) {
  _pcConnected = true;
  if (cmd == RESP_WIFI_SCAN_ITEM) {
    if (dataLen >= 4) {
      _scanIndex = data[0];
      _scanTotal = data[1];
      uint8_t rawLen = data[2];
      uint8_t copyLen = (rawLen > 12) ? 12 : rawLen;
      if (3 + rawLen <= dataLen) {
        memcpy(_scanName, &data[3], copyLen);
        _scanName[copyLen] = '\0';
        uint8_t pos = 3 + rawLen;
        if (pos < dataLen) _scanSignal = data[pos];
        else _scanSignal = 0;
      }
      _state = WIFiset_STATE_SCAN_VIEWER;
      drawScanViewer();
    }
    return;
  }

  if (cmd == RESP_WIFI_KNOWN_ITEM) {
    if (dataLen >= 4) {
      _knownIndex = data[0];
      _knownTotal = data[1];
      uint8_t rawLen = data[2];
      uint8_t copyLen = (rawLen > 12) ? 12 : rawLen;
      if (3 + rawLen <= dataLen) {
        memcpy(_knownName, &data[3], copyLen);
        _knownName[copyLen] = '\0';
      }
      _selectedKnown = _knownIndex;
      _state = WIFiset_STATE_KNOWN_VIEWER;
      drawKnownViewer();
    }
    return;
  }

  if (cmd == RESP_WIFISET_STATUS) {
    // [status, iface, mode, ssid_len, ssid...]
    uint8_t st = (dataLen >= 1) ? data[0] : 0;
    if (dataLen >= 4) {
      _statusIface = data[1];
      _statusMode = data[2];
      uint8_t rawLen = data[3];
      uint8_t copyLen = (rawLen > 16) ? 16 : rawLen;
      if (4 + rawLen <= dataLen) {
        memcpy(_scanName, &data[4], copyLen);
        _scanName[copyLen] = '\0';
      } else {
        _scanName[0] = '\0';
      }
    }

    if (_state == WIFiset_STATE_CONNECTING) {
      if (st == 1) {
        _state = WIFiset_STATE_STATUS_VIEW;
        drawStatusView();
      } else if (st == 2 && !_manualAttempted) {
        _awaitingPassword = true;
        KeyboardApp::prepareInput(getAppId(), "");
        if (_os) _os->launchAppById(0x08);
      } else {
        LCDKeypadDriver* drv = getDriver();
        if (drv) { drv->printAt(0,0,F("Connect FAIL")); drv->printAt(0,1,F("<-LEFT Back")); }
        _state = WIFiset_STATE_NO_PC;
      }
    } else {
      _state = WIFiset_STATE_STATUS_VIEW;
      drawStatusView();
    }
    return;
  }
}

void WifiSetApp::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->printAt(0, 0, F("== WIFI SET =="));
  if (_menuIndex == 0) drv->printAt(0, 1, F(">1.Scan WiFi    "));
  else if (_menuIndex == 1) drv->printAt(0, 1, F(">2.Known WiFi   "));
  else if (_menuIndex == 2) drv->printAt(0, 1, F(">3.Connect Sel  "));
  else if (_menuIndex == 3) {
    if (_selectedCard == 0) drv->printAt(0, 1, F(">4.SelCard:AUTO "));
    else if (_selectedCard == 1) drv->printAt(0, 1, F(">4.SelCard:W0   "));
    else if (_selectedCard == 2) drv->printAt(0, 1, F(">4.SelCard:W1   "));
    else drv->printAt(0, 1, F(">4.SelCard:W2   "));
  } else if (_menuIndex == 4) {
    char line[17];
    const char* mstr[4] = { "MGD", "MON", "AP ", "CLI" };
    snprintf(line, sizeof(line), ">5.Card%u:%-3s    ", (unsigned int)_selectedCard, mstr[_cardModes[_selectedCard]]);
    line[16] = '\0';
    drv->printAt(0, 1, line);
  } else if (_menuIndex == 5) drv->printAt(0, 1, F(">6.Status       "));
  else drv->printAt(0, 1, F(">7.Exit         "));
}

void WifiSetApp::drawScanViewer() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  char top[17];
  if (_scanTotal > 0) snprintf(top, sizeof(top), "[%u/%u] %s", (unsigned int)(_scanIndex+1), (unsigned int)_scanTotal, _scanName);
  else snprintf(top, sizeof(top), "Scan: %s", _scanName);
  top[16] = '\0';
  drv->printAt(0, 0, top);
  char btm[17];
  snprintf(btm, sizeof(btm), "Sig:%-3u SEL/LFT", (unsigned int)_scanSignal);
  btm[16] = '\0';
  drv->printAt(0, 1, btm);
}

void WifiSetApp::drawKnownViewer() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  char top[17];
  if (_knownTotal > 0) snprintf(top, sizeof(top), "[%u/%u] %s", (unsigned int)(_knownIndex+1), (unsigned int)_knownTotal, _knownName);
  else snprintf(top, sizeof(top), "Known: %s", _knownName);
  top[16] = '\0';
  drv->printAt(0, 0, top);
  drv->printAt(0, 1, F("SEL:Connect LFT"));
}

void WifiSetApp::drawStatusView() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  char l0[17];
  snprintf(l0, sizeof(l0), "IF:%u MD:%u     ", (unsigned int)_statusIface, (unsigned int)_statusMode);
  l0[16] = '\0';
  drv->printAt(0, 0, l0);
  char l1[17];
  if (_scanName[0]) snprintf(l1, sizeof(l1), "%-16s", _scanName);
  else snprintf(l1, sizeof(l1), "No SSID [LFT]  ");
  l1[16] = '\0';
  drv->printAt(0, 1, l1);
}

void WifiSetApp::drawLoadingScreen(const __FlashStringHelper* title, const __FlashStringHelper* msg) {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  drv->printAt(0, 0, title);
  drv->printAt(0, 1, msg);
}

void WifiSetApp::drawNoPCScreen() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->clear();
  drv->printAt(0, 0, F("WifiSet [No PC]"));
  drv->printAt(0, 1, F("<-LEFT Back    "));
}