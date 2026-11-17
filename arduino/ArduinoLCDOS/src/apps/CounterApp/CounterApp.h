/**
 * CounterApp.h
 *
 * Vi du mau ve cach tao mot App moi tren Arduino LCD OS chi voi khoang 30 dong code.
 * Day la ung dung bo dem (Counter):
 *   - Phim UP: Tang so dem (+1)
 *   - Phim DOWN: Giam so dem (-1)
 *   - Phim SELECT: Dat lai ve 0
 *   - Phim LEFT: Thoat ve Menu Tong cua OS (exitApp)
 */

#ifndef COUNTER_APP_H
#define COUNTER_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

class CounterApp : public AppService {
public:
  CounterApp() : _count(0) {}

  // 1. Ten hien thi tren OS Menu
  virtual const char* getAppName() override {
    return "Bo Dem (Count)";
  }

  virtual uint8_t getAppId() const override { return 0x04; }

  // Nap so dem da luu khi OS khoi dong
  virtual void loadSettings(const byte* data, uint8_t len) override {
    if (data && len >= 2) {
      _count = (int)(int16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8));
    }
  }

  // 2. Goi khi mo App
  virtual void onEnter() override {
    drawScreen();
  }

  // 3. Vong lap xu ly phim
  virtual void update(KeyCode key) override {
    if (key == KEY_UP) {
      _count++;
      saveCount();
      drawScreen();
    } else if (key == KEY_DOWN) {
      _count--;
      saveCount();
      drawScreen();
    } else if (key == KEY_RIGHT) {
      // YEU CAU: BAM PHIM RIGHT DE TRO VE 0
      _count = 0;
      saveCount();
      drawScreen();
    } else if (key == KEY_SELECT) {
      _count = 0;
      saveCount();
      drawScreen();
    } else if (key == KEY_LEFT) {
      // THOAT VE MENU TONG CUA OS
      exitApp();
    }
  }

  // 4. Goi khi dong App
  virtual void onExit() override {}

private:
  int _count;

  void saveCount() {
    byte cData[2] = { lowByte(_count), highByte(_count) };
    saveSetting(cData, 2);
  }

  void drawScreen() {
    LCDKeypadDriver* drv = getDriver();
    if (!drv) return;

    drv->printAt(0, 0, "=== BO DEM ===  ");
    char buf[17];
    snprintf(buf, sizeof(buf), "Val:%-4d [RT->0]", _count);
    buf[16] = '\0';
    drv->printAt(0, 1, buf);
  }
};

#endif // COUNTER_APP_H
