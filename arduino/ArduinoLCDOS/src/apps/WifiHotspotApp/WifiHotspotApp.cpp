/**
 * WifiHotspotApp.cpp
 *
 * Implement ung dung dieu khien Portable WiFi Hotspot tren Arduino LCD OS.
 */

#include "WifiHotspotApp.h"
#include "../../core/LCDKeypadDriver.h"
#include "../../core/LCDKeypadOS.h"

static const char* const HOTSPOT_MENU_ITEMS[] = {
  "1. Host AP: ---",    // index 0: Toggle Host
  "2. Chay ngam: --",   // index 1: Background run
  "3. Sync truoc: --",  // index 2: Sync from master server before AP
  "4. Card phat: --",   // index 3: Wireless interface
  "5. Day 2 card: --",  // index 4: Dual card push to server
  "6. Xem IP/Status",   // index 5: View IP, client count, status
  "7. Thoat ve OS"      // index 6: Exit app
};

WifiHotspotApp::WifiHotspotApp()
  : MenuAppService("WiFi Hotspot", "== WIFI HOTSPOT ==", HOTSPOT_MENU_ITEMS, 7, false),
    _mode(HS_MODE_MENU),
    _hostActive(false),
    _isSyncing(false),
    _clientCount(0),
    _ipLastOctet(1),
    _upstreamOnline(false),
    _bgRun(false),            // Mac dinh: Tat host khi thoat app
    _syncBeforeHost(true),    // Mac dinh: Dong bo server truoc khi phat
    _interfaceMode(0),        // 0 = AUTO, 1 = wlan0, 2 = wlan1
    _dualCardPush(true),      // Mac dinh: Tu dong day WiFi moi khi co 2 card
    _enterTime(0),
    _lastStatusQueryTime(0)
{
}

void WifiHotspotApp::loadSettings(const byte* data, uint8_t len) {
  if (data && len >= 4) {
    _bgRun          = (data[0] != 0);
    _syncBeforeHost = (data[1] != 0);
    _interfaceMode  = data[2] % 3;
    _dualCardPush   = (data[3] != 0);
  }
}

void WifiHotspotApp::saveMySettings() {
  byte data[4] = {
    (byte)(_bgRun ? 1 : 0),
    (byte)(_syncBeforeHost ? 1 : 0),
    (byte)_interfaceMode,
    (byte)(_dualCardPush ? 1 : 0)
  };
  saveSetting(data, 4);
}

void WifiHotspotApp::onEnter() {
  _mode = HS_MODE_MENU;
  _enterTime = millis();
  _lastStatusQueryTime = millis();

  // Yeu cau Raspberry Pi bao cao trang thai Hotspot ngay khi vua vao app
  sendHotspotAction(ACTION_QUERY_STATUS);

  MenuAppService::onEnter();
}

void WifiHotspotApp::onExit() {
  // Neu khong bat chay ngam, dam bao host tat khi nguoi dung thoat ra
  if (!_bgRun && _hostActive) {
    sendHotspotAction(ACTION_STOP_HOST);
    _hostActive = false;
  }
}

void WifiHotspotApp::onBackSelected() {
  if (_mode == HS_MODE_STATUS_VIEW) {
    _mode = HS_MODE_MENU;
    drawMenu();
    return;
  }

  // Nguoi dung bam phim LEFT tai Menu chinh cua Hotspot
  if (!_bgRun && _hostActive) {
    // Thong bao tat host va thoat
    showActionToast("<- Thoat App...", "Dang tat Host...");
    sendHotspotAction(ACTION_STOP_HOST);
    _hostActive = false;
    delay(400);
  } else if (_bgRun && _hostActive) {
    // Host van chay tiep o background
    showActionToast("<- Thoat App...", "Host chay ngam!");
    delay(400);
  }

  exitApp();
}

void WifiHotspotApp::update(KeyCode key) {
  // 1. Xu ly phan hoi Serial tu Raspberry Pi
  processSerialPackets();

  unsigned long now = millis();

  // 2. Hoi trang thai Pi dinh ky moi 4 giay
  if (now - _lastStatusQueryTime >= 4000) {
    _lastStatusQueryTime = now;
    sendHotspotAction(ACTION_QUERY_STATUS);
  }

  // 3. Khoang dem chong doi phim SELECT khi moi vao
  if (now - _enterTime < 350) return;

  if (key == KEY_NONE) return;

  if (_mode == HS_MODE_STATUS_VIEW) {
    if (key == KEY_LEFT || key == KEY_SELECT) {
      _mode = HS_MODE_MENU;
      drawMenu();
    }
    return;
  }

  // Che do Menu chinh
  MenuAppService::update(key);
}

void WifiHotspotApp::onItemSelected(uint8_t index) {
  switch (index) {
    case 0: { // 1. Toggle Host
      if (_hostActive) {
        showActionToast("WiFi AP: TAT...", "Gui lenh tat...");
        sendHotspotAction(ACTION_STOP_HOST);
        _hostActive = false;
      } else {
        if (_syncBeforeHost) {
          showActionToast("WiFi AP: SYNC...", "Dong bo server..");
          sendHotspotAction(ACTION_START_HOST, 0x01); // 0x01: Start with sync
        } else {
          showActionToast("WiFi AP: BAT...", "Khoi dong AP...");
          sendHotspotAction(ACTION_START_HOST, 0x00); // 0x00: Direct start
        }
        _hostActive = true;
      }
      delay(400);
      drawMenu();
      break;
    }

    case 1: { // 2. Toggle Chay ngam (BgRun)
      _bgRun = !_bgRun;
      saveMySettings();
      drawMenu();
      break;
    }

    case 2: { // 3. Toggle Sync truoc khi bat host
      _syncBeforeHost = !_syncBeforeHost;
      saveMySettings();
      drawMenu();
      break;
    }

    case 3: { // 4. Cycle Card phat (AUTO -> wlan0 -> wlan1)
      _interfaceMode = (_interfaceMode + 1) % 3;
      saveMySettings();
      drawMenu();
      break;
    }

    case 4: { // 5. Toggle Day 2 card (DualPush)
      _dualCardPush = !_dualCardPush;
      saveMySettings();
      drawMenu();
      break;
    }

    case 5: { // 6. Xem chi tiet IP & Status
      _mode = HS_MODE_STATUS_VIEW;
      drawStatusView();
      break;
    }

    case 6: { // 7. Thoat ve OS
      onBackSelected();
      break;
    }
  }
}

void WifiHotspotApp::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  // Dong 0: Header trang thai tong the
  char header[17];
  if (_isSyncing) {
    snprintf(header, sizeof(header), "AP: DANG DONG BO");
  } else if (_hostActive) {
    snprintf(header, sizeof(header), "AP: BAT  [Cl:%u]", (unsigned int)_clientCount);
  } else {
    snprintf(header, sizeof(header), "AP: DANG TAT    ");
  }
  header[16] = '\0';
  drv->printAt(0, 0, header);

  // Dong 1: Menu item hien tai
  char line[17];
  switch (_selectedIndex) {
    case 0:
      snprintf(line, sizeof(line), ">1.Host: %-6s", _hostActive ? "DANG BAT" : "DANG TAT");
      break;
    case 1:
      snprintf(line, sizeof(line), ">2.ChayNgam: %-3s", _bgRun ? "ON " : "OFF");
      break;
    case 2:
      snprintf(line, sizeof(line), ">3.SyncTruoc:%-3s", _syncBeforeHost ? "ON " : "OFF");
      break;
    case 3: {
      const char* ifStr = (_interfaceMode == 1) ? "wlan0" : (_interfaceMode == 2 ? "wlan1" : "AUTO ");
      snprintf(line, sizeof(line), ">4.Card: %-6s", ifStr);
      break;
    }
    case 4:
      snprintf(line, sizeof(line), ">5.Day2Card: %-3s", _dualCardPush ? "ON " : "OFF");
      break;
    case 5:
      snprintf(line, sizeof(line), ">6.Xem IP/Status");
      break;
    default:
      snprintf(line, sizeof(line), ">7.Thoat ve OS  ");
      break;
  }
  line[16] = '\0';
  drv->printAt(0, 1, line);
}

void WifiHotspotApp::drawStatusView() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();

  char l0[17];
  char l1[17];

  if (_hostActive) {
    snprintf(l0, sizeof(l0), "IP: 192.168.4.%u", (unsigned int)_ipLastOctet);
    snprintf(l1, sizeof(l1), "Cl:%u Up:%-3s [LFT]", (unsigned int)_clientCount, _upstreamOnline ? "WAN" : "NO ");
  } else {
    snprintf(l0, sizeof(l0), "Host: DANG TAT  ");
    snprintf(l1, sizeof(l1), "Upstream: %-3s [LFT]", _upstreamOnline ? "ON " : "OFF");
  }
  l0[16] = '\0';
  l1[16] = '\0';

  drv->printAt(0, 0, l0);
  drv->printAt(0, 1, l1);
}

void WifiHotspotApp::showActionToast(const char* line1, const char* line2) {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  drv->printAt(0, 0, line1);
  drv->printAt(0, 1, line2);
}

void WifiHotspotApp::sendHotspotAction(byte action, byte extra) {
  byte data[2] = { action, extra };
  byte len = 1 + 2 + 1; // cmd + data + cs
  byte cs = CMD_HOTSPOT_ACTION ^ data[0] ^ data[1];

  Serial.write(0xAA);
  Serial.write(len);
  Serial.write(CMD_HOTSPOT_ACTION);
  Serial.write(data[0]);
  Serial.write(data[1]);
  Serial.write(cs);
  Serial.write(0xBB);
}

void WifiHotspotApp::processSerialPackets() {
  while (Serial.available() > 0) {
    byte b = Serial.peek();
    if (b == 0xAA) {
      if (Serial.available() < 4) break;

      byte start = Serial.read(); // 0xAA
      byte len   = Serial.read();
      byte cmd   = Serial.read();

      if (len < 2 || len > 32) continue;

      byte dataLen = len - 2;
      byte dataBuf[32];
      for (byte i = 0; i < dataLen; i++) {
        dataBuf[i] = Serial.read();
      }

      byte recvChecksum = Serial.read();
      byte endByte = Serial.read();

      if (endByte == 0xBB) {
        byte calcChecksum = cmd;
        for (byte i = 0; i < dataLen; i++) calcChecksum ^= dataBuf[i];

        if (calcChecksum == recvChecksum) {
          if (cmd == RESP_HOTSPOT_STATUS && dataLen >= 4) {
            // [Status, Clients, IPLastOctet, UpstreamOnline]
            byte st = dataBuf[0];
            _isSyncing      = (st == 2);
            _hostActive     = (st == 1 || st == 2);
            _clientCount    = dataBuf[1];
            _ipLastOctet    = dataBuf[2];
            _upstreamOnline = (dataBuf[3] != 0);

            if (_mode == HS_MODE_MENU) {
              drawMenu();
            } else {
              drawStatusView();
            }
          }
        }
      }
    } else {
      Serial.read();
    }
  }
}
