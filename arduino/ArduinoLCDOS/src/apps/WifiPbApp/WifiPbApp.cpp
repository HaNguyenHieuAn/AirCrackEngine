/**
 * WifiPbApp.cpp
 *
 * Implement Dieu huong va Giao tiep cho Tram Phat WiFi Di Dong tren Raspberry Pi.
 * Toi uu hoa 100% SRAM bang macro F().
 */

#include "WifiPbApp.h"
#include "../../core/LCDKeypadDriver.h"
#include "../../core/LCDKeypadOS.h"

WifiPbApp::WifiPbApp()
  : _menuIdx(0),
    _isStatusView(false),
    _hostActive(false),
    _clientCount(0),
    _ipOctet(1),
    _upstreamOnline(false),
    _bgRun(false),           // 1. Mac dinh: Tat host khi thoat app
    _syncBeforeHost(true),   // 2. Mac dinh: Sync server truoc khi bat host
    _interfaceMode(0),       // 3. Mac dinh: 0 = AUTO (tu nhan dang)
    _dualCardPush(true),     // 4. Mac dinh: Tu dong day WiFi moi khi co 2 card
    _enterTime(0),
    _lastPollTime(0),
    _rxPos(0),
    _receiving(false)
{
}

void WifiPbApp::loadSettings(const byte* data, uint8_t len) {
  if (data && len >= 4) {
    _bgRun          = (data[0] != 0);
    _syncBeforeHost = (data[1] != 0);
    _interfaceMode  = data[2] % 4; // 0=AUTO, 1=wlan0, 2=wlan1, 3=wlan2
    _dualCardPush   = (data[3] != 0);
  }
}

void WifiPbApp::saveMySettings() {
  byte data[4] = {
    (byte)(_bgRun ? 1 : 0),
    (byte)(_syncBeforeHost ? 1 : 0),
    (byte)_interfaceMode,
    (byte)(_dualCardPush ? 1 : 0)
  };
  saveSetting(data, 4);
}

void WifiPbApp::onEnter() {
  _menuIdx = 0;
  _isStatusView = false;
  _rxPos = 0;
  _receiving = false;
  _enterTime = millis();
  _lastPollTime = millis();

  // Xoa buffer cu
  while (Serial.available() > 0) Serial.read();

  // Yeu cau Raspberry Pi bao cao trang thai ngay khi vao app
  sendAction(ACTION_QUERY_STATUS);
  drawScreen();
}

void WifiPbApp::onExit() {
  // Neu khong bat Chay Ngam (BgRun) ma Host dang chay -> Tu dong tat Host khi thoat!
  if (!_bgRun && _hostActive) {
    sendAction(ACTION_STOP_HOST);
    _hostActive = false;
  }
}

void WifiPbApp::sendAction(byte action, byte extra) {
  byte data[2] = { action, extra };
  byte cs = CMD_HOTSPOT_ACTION ^ data[0] ^ data[1];

  Serial.write(0xAA);
  Serial.write(4); // len = cmd + 2 data + cs
  Serial.write(CMD_HOTSPOT_ACTION);
  Serial.write(data[0]);
  Serial.write(data[1]);
  Serial.write(cs);
  Serial.write(0xBB);
}

void WifiPbApp::processSerial() {
  while (Serial.available() > 0) {
    byte b = Serial.read();

    if (!_receiving) {
      if (b == 0xAA) {
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
        if (len < 2 || len > 20) {
          _receiving = false;
          _rxPos = 0;
        }
      } else if (_rxPos >= 2) {
        byte len = _rxBuffer[0];
        if (_rxPos == (len + 2)) {
          if (_rxBuffer[_rxPos - 1] == 0xBB) {
            byte cmd = _rxBuffer[1];
            byte dataLen = len - 2;

            byte calcChecksum = cmd;
            for (byte i = 0; i < dataLen; i++) {
              calcChecksum ^= _rxBuffer[2 + i];
            }
            byte recvChecksum = _rxBuffer[len];

            if (calcChecksum == recvChecksum && cmd == RESP_HOTSPOT_STATUS && dataLen >= 4) {
              byte st       = _rxBuffer[2];
              byte clients  = _rxBuffer[3];
              byte ipOct    = _rxBuffer[4];
              byte upstream = _rxBuffer[5];

              _hostActive     = (st == 1 || st == 2);
              _clientCount    = clients;
              _ipOctet        = ipOct;
              _upstreamOnline = (upstream != 0);
              drawScreen();
            }
          }
          _receiving = false;
          _rxPos = 0;
        }
      }
    }
  }
}

void WifiPbApp::update(KeyCode key) {
  processSerial();

  unsigned long now = millis();
  if (now - _lastPollTime >= 3500) {
    _lastPollTime = now;
    sendAction(ACTION_QUERY_STATUS);
  }

  // Chống dội phím SELECT ban đầu
  if (now - _enterTime < 350) return;
  if (key == KEY_NONE) return;

  if (_isStatusView) {
    if (key == KEY_LEFT || key == KEY_SELECT) {
      _isStatusView = false;
      drawScreen();
    }
    return;
  }

  if (key == KEY_LEFT) {
    // Thoat ve OS
    LCDKeypadDriver* drv = getDriver();
    if (!_bgRun && _hostActive) {
      if (drv) {
        drv->printAt(0, 0, F("WiFi Portable   "));
        drv->printAt(0, 1, F("Tat Host AP...  "));
      }
      sendAction(ACTION_STOP_HOST);
      _hostActive = false;
      delay(250);
    } else if (_bgRun && _hostActive) {
      if (drv) {
        drv->printAt(0, 0, F("WiFi Portable   "));
        drv->printAt(0, 1, F("Host chay ngam! "));
      }
      delay(250);
    }
    exitApp();
    return;
  }

  if (key == KEY_UP) {
    _menuIdx = (_menuIdx - 1 + 8) % 8;
    drawScreen();
  } else if (key == KEY_DOWN) {
    _menuIdx = (_menuIdx + 1) % 8;
    drawScreen();
  } else if (key == KEY_SELECT) {
    if (_menuIdx == 0) {
      // 1. Toggle Host AP (khong set bien truoc, cho Raspberry Pi tra ve ket qua thuc te)
      LCDKeypadDriver* drv = getDriver();
      if (_hostActive) {
        if (drv) {
          drv->printAt(0, 0, F("AP:DANG TAT...  "));
          drv->printAt(0, 1, F("Dang dung Host.."));
        }
        sendAction(ACTION_STOP_HOST);
      } else {
        if (drv) {
          drv->printAt(0, 0, F("AP:DANG BAT...  "));
          drv->printAt(0, 1, F("Khoi tao AP....."));
        }
        // Gui extra: bit 0: sync_before_host, bit 1-2: interfaceMode
        byte extra = (_syncBeforeHost ? 0x01 : 0x00) | ((_interfaceMode & 0x03) << 1);
        sendAction(ACTION_START_HOST, extra);
      }
    } else if (_menuIdx == 1) {
      // 2. Toggle BgRun (Host o background)
      _bgRun = !_bgRun;
      saveMySettings();
      drawScreen();
    } else if (_menuIdx == 2) {
      // 3. Toggle SyncTruoc (Sync tu server truoc khi bat host)
      _syncBeforeHost = !_syncBeforeHost;
      saveMySettings();
      drawScreen();
    } else if (_menuIdx == 3) {
      // 4. Chon Card phat: AUTO / wlan0 / wlan1 / wlan2
      _interfaceMode = (_interfaceMode + 1) % 4;
      saveMySettings();
      drawScreen();
    } else if (_menuIdx == 4) {
      // 5. Toggle Day 2Card (Day du lieu khi co 2 card mang + tu sua xung dot)
      _dualCardPush = !_dualCardPush;
      saveMySettings();
      drawScreen();
    } else if (_menuIdx == 5) {
      // 6. Sync Server ngay lap tuc
      LCDKeypadDriver* drv = getDriver();
      if (drv) {
        drv->printAt(0, 1, F("Dang Sync Server"));
      }
      sendAction(ACTION_TRIGGER_SYNC, 0x01);
      delay(400);
      drawScreen();
    } else if (_menuIdx == 6) {
      // 7. Xem IP/Status
      _isStatusView = true;
      drawScreen();
    } else if (_menuIdx == 7) {
      // 8. Thoat ve OS
      if (!_bgRun && _hostActive) {
        sendAction(ACTION_STOP_HOST);
        _hostActive = false;
      }
      exitApp();
    }
  }
}

void WifiPbApp::drawScreen() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  if (_isStatusView) {
    char buf[17];
    snprintf(buf, sizeof(buf), "IP:192.168.4.%-3u", (unsigned int)_ipOctet);
    drv->printAt(0, 0, buf);

    char buf2[17];
    snprintf(buf2, sizeof(buf2), "Cl:%u Up:%-3s [LFT]", (unsigned int)_clientCount, _upstreamOnline ? "WAN" : "NO ");
    drv->printAt(0, 1, buf2);
    return;
  }

  // Header dong 0
  if (_hostActive) {
    char h[17];
    snprintf(h, sizeof(h), "AP:BAT [Cl:%-2u]  ", (unsigned int)_clientCount);
    drv->printAt(0, 0, h);
  } else {
    drv->printAt(0, 0, F("AP:TAT (wifi_pb)"));
  }

  // Dong 1: Menu cac setting va thao tac (100% dung macro F())
  if (_menuIdx == 0) {
    drv->printAt(0, 1, _hostActive ? F(">1.Host AP:[BAT]") : F(">1.Host AP:[TAT]"));
  } else if (_menuIdx == 1) {
    drv->printAt(0, 1, _bgRun ? F(">2.ChayNgam: ON ") : F(">2.ChayNgam: OFF"));
  } else if (_menuIdx == 2) {
    drv->printAt(0, 1, _syncBeforeHost ? F(">3.SyncTruoc: ON") : F(">3.SyncTruoc:OFF"));
  } else if (_menuIdx == 3) {
    if (_interfaceMode == 0)      drv->printAt(0, 1, F(">4.Card: [AUTO] "));
    else if (_interfaceMode == 1) drv->printAt(0, 1, F(">4.Card: [wlan0]"));
    else if (_interfaceMode == 2) drv->printAt(0, 1, F(">4.Card: [wlan1]"));
    else                          drv->printAt(0, 1, F(">4.Card: [wlan2]"));
  } else if (_menuIdx == 4) {
    drv->printAt(0, 1, _dualCardPush ? F(">5.Day 2Card: ON") : F(">5.Day 2Card:OFF"));
  } else if (_menuIdx == 5) {
    drv->printAt(0, 1, F(">6.Sync Ngay    "));
  } else if (_menuIdx == 6) {
    drv->printAt(0, 1, F(">7.Xem IP/Status"));
  } else {
    drv->printAt(0, 1, F(">8.Thoat ve OS  "));
  }
}
