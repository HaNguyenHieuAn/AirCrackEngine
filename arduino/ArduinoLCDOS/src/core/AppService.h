/**
 * AppService.h
 *
 * Lop co so (Base Class / Interface) cho tat ca cac ung dung va service.
 * Moi App la mot module doc lap co the duoc nap vao LCDKeypadOS.
 */

#ifndef APP_SERVICE_H
#define APP_SERVICE_H

#include <Arduino.h>
#include "LCDKeypadDriver.h"

// Forward declaration
class LCDKeypadOS;

class AppService {
public:
  virtual ~AppService() {}

  // Ten hien thi tren Main Menu (toi da 15 ky tu)
  virtual const char* getAppName() = 0;

  // Dinh danh duy nhat cua App (0: Default, 1: NativeGame, 2: PCTest, 3: Settings, 4: Counter...)
  virtual uint8_t getAppId() const { return 0; }

  // Nap cai dat rieng cua App (duoc goi ngay khi OS khoi dong / nhan settings tu PC)
  virtual void loadSettings(const byte* data, uint8_t len) {}

  // Yeu cau OS luu cai dat rieng cua App (vua luu EEPROM vua dong bo len PC)
  void saveSetting(const byte* data, uint8_t len);

  // Goi khi ung dung bat dau duoc khoi chay
  virtual void onEnter() {}

  // Vong lap xu ly cua ung dung
  // key: Phím vừa được nhấn (edge-triggered: KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_SELECT, KEY_NONE)
  virtual void update(KeyCode key) = 0;

  // Goi khi ung dung thoat va chuan bi tra ve Menu Tong
  virtual void onExit() {}

  // Gan OS context vao App (duoc goi boi LCDKeypadOS::registerApp)
  void setOS(LCDKeypadOS* osInstance) { _os = osInstance; }

  // Yeu cau OS thoat App hien tai va tro ve Menu Tong
  void exitApp();

protected:
  LCDKeypadOS* _os = nullptr;

  // Helper lay driver man hinh va phim bam
  LCDKeypadDriver* getDriver();
};

#endif // APP_SERVICE_H
