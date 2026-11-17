/**
 * LinuxInfApp.h
 *
 * Module: Ung dung LinuxInf tren Arduino LCD OS.
 * Tinh nang:
 * 1. Menu lua chon chuc nang:
 *    - 1. Sudo Privs (Kiem tra va liet ke cac lenh sudo duoc phep chay tren Linux qua sudo -l)
 *    - 2. Linux Info (Xem Hostname, Kernel, Uptime may chu Linux)
 *    - 3. Thoat ve OS
 * 2. Trinh duyet lenh Sudo (Sudo Command Viewer):
 *    - Dong tren: [STT/Tong] Ten lenh (vi du: [1/5] systemctl)
 *    - Dong duoi: Mo ta chi tiet chuc nang (vi du: Dich vu he thong)
 *    - Bam UP / DOWN: Di chuyen giua cac lenh de xem thong tin
 *    - Bam SELECT: Hien thi canh bao "Chi xem (No Exec)" - khong dung de thuc thi lenh
 *    - Bam LEFT: Quay ve Menu LinuxInf / OS Menu tuc thi
 */

#ifndef LINUX_INF_APP_H
#define LINUX_INF_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

enum LinuxInfState : byte {
  LINUX_STATE_MENU,           // Menu chon chuc nang chinh
  LINUX_STATE_SUDO_LOADING,   // Dang gui lenh va cho danh sach tu PC
  LINUX_STATE_SUDO_VIEWER,    // Dang xem danh sach lenh sudo
  LINUX_STATE_INFO_LOADING,   // Dang cho thong tin Linux tu PC
  LINUX_STATE_INFO_VIEWER,    // Dang xem thong tin Hostname/Kernel/Uptime
  LINUX_STATE_NO_PC           // Bao loi chua ket noi PC
};

class LinuxInfApp : public AppService {
public:
  LinuxInfApp();

  virtual const char* getAppName() override { return "LinuxInf"; }
  virtual uint8_t getAppId() const override { return 0x06; }
  virtual void loadSettings(const byte* data, uint8_t len) override {}

  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override;

private:
  LinuxInfState _state;
  uint8_t       _menuIndex;
  unsigned long _appEnterTime;
  unsigned long _lastReqTime;

  // Du lieu hien thi (Dung chung buffer de toi uu toi da bo nho SRAM)
  uint8_t _currentCmdIndex;
  uint8_t _totalCmdCount;
  char    _cmdName[17];
  char    _cmdDesc[17];

  // Bo dem nhan Serial toi uu (42 bytes vua khit frame 36B)
  byte    _rxBuffer[40];
  int     _rxPos;
  bool    _receiving;

  // Xu ly Serial
  void processSerialInput();
  void processCommand(byte cmd, const byte* data, byte dataLen);
  void sendPacket(byte cmd, const byte* data, byte dataLen);

  // Yeu cau du lieu tu PC
  void requestSudoItem(uint8_t index);
  void requestLinuxInfo();

  // Ve giao dien man hinh
  void drawMenu();
  void drawSudoViewer();
  void drawLinuxInfo();
  void drawLoadingScreen(const __FlashStringHelper* title, const __FlashStringHelper* msg);
  void drawNoPCScreen();
};

#endif // LINUX_INF_APP_H
