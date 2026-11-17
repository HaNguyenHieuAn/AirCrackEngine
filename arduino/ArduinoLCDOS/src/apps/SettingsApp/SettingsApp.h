/**
 * SettingsApp.h
 *
 * Ung dung Cai Dat He Thong (Settings) cho LCD Keypad OS:
 * 1. Den nen: ON / OFF
 * 2. Am thanh: ON / OFF
 * 3. Thong tin OS: RAM, Uptime, Version, Baudrate
 * 4. Reset All Data: Khoi phuc cai dat goc (Hoi xac nhan 2 lan truoc khi xoa)
 * 5. Thoat ve OS
 */

#ifndef SETTINGS_APP_H
#define SETTINGS_APP_H

#include <Arduino.h>
#include "../../core/MenuAppService.h"

enum SettingsMode : byte {
  SET_MODE_MENU,           // Danh sach cai dat chinh
  SET_MODE_CONFIRM_STEP1,  // Hoi xac nhan lan 1: "Xoa het cai dat?"
  SET_MODE_CONFIRM_STEP2,  // Hoi xac nhan lan 2: "XAC NHAN LAN 2!"
  SET_MODE_SYS_INFO        // Xem thong tin he thong
};

class SettingsApp : public MenuAppService {
public:
  SettingsApp();

  virtual const char* getAppName() override { return "Cai Dat (Set)"; }
  virtual uint8_t getAppId() const override { return 0x03; }
  virtual void loadSettings(const byte* data, uint8_t len) override;

  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onItemSelected(uint8_t index) override;
  virtual void drawMenu() override;

private:
  SettingsMode _mode;
  bool _soundOn;

  void drawConfirmStep1();
  void drawConfirmStep2();
  void executeResetAll();
  void showSystemInfo();
  int getFreeRam();
};

#endif // SETTINGS_APP_H
