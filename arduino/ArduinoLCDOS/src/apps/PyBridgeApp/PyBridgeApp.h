/**
 * PyBridgeApp.h
 *
 * Module 2: Ung dung cau noi giao tiep hai chieu mau (Communication Bridge Template).
 * Giup Arduino ket noi truc tiep voi Python server tren PC:
 * - Doc nut bam tren Shield va gui ngay len PC.
 * - Nhan phan hoi chu / trang thai tu PC va hien thi len LCD 16x2.
 * - Tich hop toan bo cac ban sua loi: Loc xung phim LEFT, chong tran so timeout, telemetry, 115200 baud.
 */

#ifndef PY_BRIDGE_APP_H
#define PY_BRIDGE_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

// Ly do ngat ket noi / thoat app de chan doan
enum DisconnectReason : byte {
  DISC_NONE = 0,
  DISC_TIMEOUT = 1,        // Timeout: Qua 60s khong nhan goi tin hop le tu PC
  DISC_LEFT_KEY = 2,       // Bam nut LEFT tren shield de quay lai OS Menu
  DISC_PC_REQUEST = 3,     // PC yeu cau thoat app (CMD_APP_EXIT)
  DISC_CRC_ERROR = 4,      // Sai Checksum goi tin
  DISC_BUFFER_OVERFLOW = 5 // Tran bo dem nhan Serial
};

class PyBridgeApp : public AppService {
public:
  PyBridgeApp();

  virtual const char* getAppName() override { return "PC test"; }
  virtual uint8_t getAppId() const override { return 0x02; }
  virtual void loadSettings(const byte* data, uint8_t len) override {}
  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override;

  DisconnectReason getLastDisconnectReason() const { return _lastDisconnectReason; }
  unsigned int getRxPacketCount() const { return _rxPacketCount; }
  byte getCrcErrorCount() const { return _crcErrorCount; }

private:
  // Bo dem nhan Serial toi uu
  byte _rxBuffer[32];
  int  _rxPos;
  bool _receiving;

  // Thong so ky thuat & chan doan
  unsigned int     _rxPacketCount;
  byte             _crcErrorCount;
  DisconnectReason _lastDisconnectReason;
  unsigned int     _lastRawAdc;

  // Thoi gian va su kien
  unsigned long _appEnterTime;
  unsigned long _lastActiveTime;
  unsigned long _lastHeartbeatTime;
  unsigned long _leftKeyHoldStart;
  byte          _lastSentButton;

  // Xu ly Serial va goi tin
  void processSerialInput();
  void processCommand(byte cmd, const byte* data, byte dataLen);
  void sendPacket(byte cmd, const byte* data, byte dataLen);
  void sendDebugLog(const char* msg);
  void sendTelemetry();

  // Hien thi
  void drawReadyScreen();
  void showDiagnosticScreen(DisconnectReason reason);
  const char* getButtonName(byte protoBtn);

  // Helper chuyen doi KeyCode sang ma nut cua giao thuc
  byte keyCodeToProtocolByte(KeyCode key);
};

#endif // PY_BRIDGE_APP_H
