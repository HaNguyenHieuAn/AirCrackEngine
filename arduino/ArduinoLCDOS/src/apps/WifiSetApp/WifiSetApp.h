#ifndef WIFI_SET_APP_H
#define WIFI_SET_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

static const byte CMD_WIFISET_ACTION        = 0x19;
static const byte CMD_REQ_WIFI_SCAN_ITEM    = 0x32;
static const byte CMD_REQ_WIFI_KNOWN_ITEM   = 0x33;
static const byte CMD_WIFISET_CONNECT_PW    = 0x34;
static const byte CMD_WIFISET_CARD_MODE     = 0x35;

static const byte RESP_WIFI_SCAN_ITEM       = 0x8C;
static const byte RESP_WIFI_KNOWN_ITEM      = 0x8D;
static const byte RESP_WIFISET_STATUS       = 0x8E;

static const byte WIFiset_ACTION_SCAN_REQ     = 0x01;
static const byte WIFiset_ACTION_KNOWN_REQ    = 0x02;
static const byte WIFiset_ACTION_CONNECT_AUTO = 0x03;
static const byte WIFiset_ACTION_QUERY_STATUS = 0x06;

enum WifiSetState : byte {
  WIFiset_STATE_MENU,
  WIFiset_STATE_SCAN_LOADING,
  WIFiset_STATE_SCAN_VIEWER,
  WIFiset_STATE_KNOWN_LOADING,
  WIFiset_STATE_KNOWN_VIEWER,
  WIFiset_STATE_CONNECTING,
  WIFiset_STATE_STATUS_VIEW,
  WIFiset_STATE_NO_PC
};

class WifiSetApp : public AppService {
public:
  WifiSetApp();

  virtual const char* getAppName() override { return "WifiSet"; }
  virtual uint8_t getAppId() const override { return 0x07; }

  virtual void loadSettings(const byte* data, uint8_t len) override;
  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override;

private:
  WifiSetState _state;
  uint8_t _menuIndex;

  // Scan list
  uint8_t _scanIndex;
  uint8_t _scanTotal;
  char    _scanName[17];
  uint8_t _scanSignal;

  // Known list
  uint8_t _knownIndex;
  uint8_t _knownTotal;
  char    _knownName[17];
  uint8_t _selectedKnown;

  // Card settings
  uint8_t _ifaceMode;       // 0=AUTO,1=wlan0,2=wlan1,3=wlan2
  uint8_t _selectedCard;    // 0..3
  uint8_t _cardModes[4];    // 0=Managed,1=Monitor,2=AP,3=Client

  // Connect flow
  uint8_t _pendingKnown;
  bool _awaitingPassword;
  bool _manualAttempted;
  bool _pcConnected;

  // Status
  // reuse _scanName for status to save RAM
  uint8_t _statusIface;
  uint8_t _statusMode;

  unsigned long _appEnterTime;
  unsigned long _lastReqTime;

  byte _rxBuffer[32];
  int  _rxPos;
  bool _receiving;

  void processSerialInput();
  void processCommand(byte cmd, const byte* data, byte dataLen);
  void sendPacket(byte cmd, const byte* data, byte dataLen);
  void sendAction(byte action, byte extra = 0);
  void sendConnectPassword(uint8_t index, const char* pw);
  void sendCardMode(uint8_t card, uint8_t mode);

  void requestScanItem(uint8_t index);
  void requestKnownItem(uint8_t index);

  void drawMenu();
  void drawScanViewer();
  void drawKnownViewer();
  void drawStatusView();
  void drawLoadingScreen(const __FlashStringHelper* title, const __FlashStringHelper* msg);
  void drawNoPCScreen();
  void saveMySettings();
};

#endif // WIFI_SET_APP_H