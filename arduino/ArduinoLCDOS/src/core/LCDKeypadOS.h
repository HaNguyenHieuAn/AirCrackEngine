/**
 * LCDKeypadOS.h
 *
 * Thu vien Menu Tong / He dieu hanh cho Arduino voi LCD Keypad Shield.
 * Quan ly vong doi (Lifecycle) cua cac App/Service, dieu huong va ve menu tong.
 */

#ifndef LCD_KEYPAD_OS_H
#define LCD_KEYPAD_OS_H

#include <Arduino.h>
#include "LCDKeypadDriver.h"
#include "AppService.h"

enum OSState : byte {
  OS_STATE_MAIN_MENU,
  OS_STATE_APP_RUNNING
};

class LCDKeypadOS {
public:
  static const uint8_t MAX_APPS = 4;

  LCDKeypadOS();

  // Khoi dong he dieu hanh va phan cung
  void begin();

  // Nap mot ung dung vao he dieu hanh (Service Registry)
  bool registerApp(AppService* app);

  // Tim index cua App theo AppId
  int8_t findAppIndexById(uint8_t appId) const;

  // Khoi chay App theo AppId (dung cho giao tiep lien App, vd Keyboard)
  bool launchAppById(uint8_t appId);

  // Vong lap chinh cua he dieu hanh, goi trong void loop() cua Arduino
  void update();

  // Tra ve Menu Tong (duoc goi khi app thoat)
  void returnToMainMenu();

  // Lay driver phan cung LCD Keypad
  LCDKeypadDriver& getDriver() { return _driver; }

  // Lay so luong app da dang ky
  uint8_t getAppCount() const { return _appCount; }

  // Lay trang thai OS
  OSState getState() const { return _state; }

  // Lay index cua App dang duoc chon
  uint8_t getSelectedAppIndex() const { return _selectedAppIndex; }

  // Phan phoi du lieu cai dat den tung App dua theo AppId
  void dispatchAppSettings(const byte* payload, uint8_t len);

  // Luu cai dat cua App hoac System (vua vao EEPROM vua gui len PC)
  void saveAppSetting(uint8_t appId, const byte* data, uint8_t len);

  // Khoi phuc cai dat goc (Reset All Data) cho ca he thong va toan bo cac App
  void resetAllSettings();

private:
  LCDKeypadDriver _driver;
  AppService* _apps[MAX_APPS];
  uint8_t _appCount;
  int8_t _currentRunningApp;
  uint8_t _selectedAppIndex;
  OSState _state;

  unsigned long _lastMenuRefresh;

  void handleMainMenu(KeyCode key);
  void drawMainMenu();
  void launchApp(uint8_t index);
  void processOSSerial();
};

#endif // LCD_KEYPAD_OS_H
