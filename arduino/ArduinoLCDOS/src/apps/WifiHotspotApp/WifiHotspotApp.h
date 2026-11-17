/**
 * WifiHotspotApp.h
 *
 * App 5: Dieu khien Tram Phat WiFi Di Dong (Portable WiFi Hotspot Controller)
 * Danh cho Raspberry Pi 3B v1.2 (Kali Linux) ket hop Arduino LCD Keypad Shield.
 *
 * Tinh nang:
 * 1. Bat / Tat Host AP (Access Point) va Web Server tren Raspberry Pi.
 * 2. Cai dat chay ngam (BgRun): Thoat app van giu Host tiep tuc phat.
 * 3. Cai dat dong bo (SyncOnBoot): Tu dong sync WiFi tu Master Server ve Pi truoc khi phat AP.
 * 4. Chon card mang phat: AUTO / wlan0 / wlan1 (nhan dien da card mang).
 * 5. Day du lieu 2 card (DualPush): Tu dong day WiFi moi len server khi co 2 card mang + auto conflict resolution.
 * 6. Xem IP tram phat & so luong thiet bi ket noi (Clients).
 */

#ifndef WIFI_HOTSPOT_APP_H
#define WIFI_HOTSPOT_APP_H

#include <Arduino.h>
#include "../../core/MenuAppService.h"

// Cac ma lenh dieu khien Hotspot mo rong
static const byte CMD_HOTSPOT_ACTION    = 0x18; // Arduino -> Pi: [Action, Extra]
static const byte RESP_HOTSPOT_STATUS   = 0x98; // Pi -> Arduino: [Status, Clients, IPLastOctet, UpstreamOnline]

// Cac hanh dong Hotspot Action
static const byte ACTION_START_HOST     = 0x01; // Bat Host AP
static const byte ACTION_STOP_HOST      = 0x02; // Tat Host AP
static const byte ACTION_TRIGGER_SYNC   = 0x03; // Kich hoat dong bo tu Master Server
static const byte ACTION_QUERY_STATUS   = 0x04; // Yeu cau Pi bao cao trang thai

enum HotspotAppMode : byte {
  HS_MODE_MENU,       // Che do xem menu va danh sach tuy chon
  HS_MODE_STATUS_VIEW // Che do xem thong so chi tiet (IP, Clients, Upstream)
};

class WifiHotspotApp : public MenuAppService {
public:
  WifiHotspotApp();

  virtual const char* getAppName() override { return "WiFi Hotspot"; }
  virtual uint8_t getAppId() const override { return 0x05; }

  // Nap cai dat hai tang (EEPROM hoac os_settings.json)
  virtual void loadSettings(const byte* data, uint8_t len) override;

  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onItemSelected(uint8_t index) override;
  virtual void onBackSelected() override;
  virtual void onExit() override;
  virtual void drawMenu() override;

  // Getter trang thai
  bool isHostActive() const { return _hostActive; }
  bool isBgRunEnabled() const { return _bgRun; }
  bool isSyncBeforeHostEnabled() const { return _syncBeforeHost; }
  uint8_t getInterfaceMode() const { return _interfaceMode; }
  bool isDualCardPushEnabled() const { return _dualCardPush; }

private:
  HotspotAppMode _mode;

  // Trang thai Host nhan tu Raspberry Pi
  bool    _hostActive;
  bool    _isSyncing;
  uint8_t _clientCount;
  uint8_t _ipLastOctet;
  bool    _upstreamOnline;

  // Cac tuy chon cai dat luu tru
  bool    _bgRun;            // true: thoat app van giu host; false: thoat app la tat host
  bool    _syncBeforeHost;   // true: dong bo tu master server truoc khi phat AP
  uint8_t _interfaceMode;    // 0: AUTO, 1: wlan0, 2: wlan1
  bool    _dualCardPush;     // true: day du lieu len server khi co 2 card mang

  unsigned long _enterTime;
  unsigned long _lastStatusQueryTime;

  // Xu ly giao tiep Serial
  void processSerialPackets();
  void sendHotspotAction(byte action, byte extra = 0x00);
  void saveMySettings();

  // Hien thi
  void drawStatusView();
  void showActionToast(const char* line1, const char* line2);
};

#endif // WIFI_HOTSPOT_APP_H
