/**
 * WifiPbApp.h
 *
 * App 5: Dieu huong va Giao tiep cho Tram Phat WiFi Di Dong (Portable WiFi Hotspot).
 * Chi lam nhiem vu Dieu huong, Giao tiep va Luu tru thiet lap:
 * - 1. Host AP: BAT / TAT
 * - 2. ChayNgam: ON / OFF (Host van phat khi thoat app cho den khi reset hoac chu dong tat)
 * - 3. SyncTruoc: ON / OFF (Sync tu server chu truoc khi phat AP)
 * - 4. Card phat: AUTO / wlan0 / wlan1 / wlan2 (Da card mang, tu nhan dang)
 * - 5. Day 2Card: ON / OFF (Tu dong day du lieu + sua xung dot khi co 2 card mang)
 * - 6. Sync Server (Kich hoat dong bo ngay)
 * - 7. Xem IP & Clients
 * - 8. Thoat ve OS
 */

#ifndef WIFI_PB_APP_H
#define WIFI_PB_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

// Ma lenh giao tiep voi Raspberry Pi
static const byte CMD_HOTSPOT_ACTION  = 0x18; // Arduino -> Pi: [Action, Extra]
static const byte RESP_HOTSPOT_STATUS = 0x98; // Pi -> Arduino: [Status, Clients, IPLastOctet, UpstreamOnline]

// Cac hanh dong Hotspot Action
static const byte ACTION_START_HOST   = 0x01; // Bat Host AP
static const byte ACTION_STOP_HOST    = 0x02; // Tat Host AP
static const byte ACTION_TRIGGER_SYNC = 0x03; // Kich hoat dong bo thu cong
static const byte ACTION_QUERY_STATUS = 0x04; // Yeu cau bao cao trang thai

class WifiPbApp : public AppService {
public:
  WifiPbApp();

  virtual const char* getAppName() override { return "wifi_pb"; }
  virtual uint8_t getAppId() const override { return 0x05; }

  // Nap cai dat hai tang (EEPROM hoac os_settings.json tu PC/Pi)
  virtual void loadSettings(const byte* data, uint8_t len) override;

  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override;

private:
  uint8_t       _menuIdx;
  bool          _isStatusView;

  // Trang thai Host nhan tu Raspberry Pi
  bool          _hostActive;
  uint8_t       _clientCount;
  uint8_t       _ipOctet;
  bool          _upstreamOnline;

  // 4 Thiet lap luu tru chuan theo tai lieu
  bool          _bgRun;          // 1. Chay ngam khi thoat app
  bool          _syncBeforeHost; // 2. Sync server truoc khi bat host
  uint8_t       _interfaceMode;  // 3. Card phat: 0=AUTO, 1=wlan0, 2=wlan1, 3=wlan2
  bool          _dualCardPush;   // 4. Day du lieu khi co 2 card mang

  unsigned long _enterTime;
  unsigned long _lastPollTime;

  // Bo dem nhan Serial chuan khung tin
  byte _rxBuffer[24];
  int  _rxPos;
  bool _receiving;

  void drawScreen();
  void sendAction(byte action, byte extra = 0);
  void saveMySettings();
  void processSerial();
};

#endif // WIFI_PB_APP_H
