#ifndef AIRCRACK_APP_H
#define AIRCRACK_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

static const byte CMD_AIRCRACK_ACTION        = 0x36;
static const byte CMD_REQ_AIRCRACK_SCAN_ITEM = 0x37;
static const byte CMD_REQ_HCF_ITEM           = 0x38;
static const byte CMD_AIRCRACK_CARD_MODE     = 0x3B;
static const byte CMD_AIRCRACK_SERVER_IP      = 0x3C;

static const byte RESP_AIRCRACK_SCAN_ITEM    = 0x8F;
static const byte RESP_AIRCRACK_STATUS        = 0x9B;
static const byte RESP_HCF_ITEM              = 0x9C;

enum AirCrackState : byte {
  AC_STATE_MENU,
  AC_STATE_SCAN_LOADING,
  AC_STATE_SCAN_VIEWER,
  AC_STATE_TARGET_SELECTED,
  AC_STATE_ACTION_LOADING,
  AC_STATE_STATUS_VIEW,
  AC_STATE_HCF_LOADING,
  AC_STATE_HCF_VIEWER,
  AC_STATE_NO_PC
};

class AirCrackApp : public AppService {
public:
  AirCrackApp();

  virtual const char* getAppName() override { return "AirCrack"; }
  virtual uint8_t getAppId() const override { return 0x06; }
  virtual void loadSettings(const byte* data, uint8_t len) override;

  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override {}

private:
  AirCrackState _state;
  uint8_t _menuIndex;

  uint8_t _scanIndex;
  uint8_t _scanTotal;
  char    _scanBssid[13];
  uint8_t _scanChannel;
  uint8_t _scanPower;

  uint8_t _hcfIndex;
  uint8_t _hcfTotal;
  char    _hcfName[13];

  uint8_t _selectedCard;
  uint8_t _cardModes[4];
  char    _serverIp[21];

  // reuse _hcfName for status to save RAM
  uint8_t _statusIface;

  unsigned long _appEnterTime;
  unsigned long _lastReqTime;
  bool _pcConnected;
  bool _awaitingServerIp;

  byte _rxBuffer[32];
  int  _rxPos;
  bool _receiving;

  void processSerialInput();
  void processCommand(byte cmd, const byte* data, byte dataLen);
  void sendPacket(byte cmd, const byte* data, byte dataLen);
  void sendAction(byte action, byte extra = 0);
  void sendCardMode(uint8_t card, uint8_t mode);
  void sendServerIp(const char* ip);
  void saveMySettings();
  void loadServerIpFromEEPROM();
  void saveServerIpToEEPROM();

  void requestScanItem(uint8_t index);
  void requestHcfItem(uint8_t index);

  void drawMenu();
  void drawScanViewer();
  void drawHcfViewer();
  void drawStatusView();
  void drawLoadingScreen(const __FlashStringHelper* title, const __FlashStringHelper* msg);
  void drawNoPCScreen();
};

#endif // AIRCRACK_APP_H