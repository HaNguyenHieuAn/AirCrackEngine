/**
 * SettingsApp.cpp
 *
 * Implement ung dung Cai Dat He Thong:
 * - Bat / tat den nen LCD
 * - Bat / tat am thanh
 * - Xem thong tin he thong (RAM, Uptime, Baudrate)
 * - Reset toan bo cai dat ve mac dinh (Hoi xac nhan 2 lan truoc khi xoa)
 */

#include "SettingsApp.h"
#include "../../core/LCDKeypadDriver.h"
#include "../../core/LCDKeypadOS.h"
#include <EEPROM.h>

// 6 muc trong danh sach cai dat
static const char* const SETTINGS_MENU_ITEMS[] = {
  "1. Den nen: ON",    // index 0: toggle den nen
  "2. Am thanh: ON",   // index 1: toggle am thanh
  "3. Thong tin OS",   // index 2: xem Uptime, RAM, Baudrate
  "4. Reset All Data", // index 3: reset toan bo ve mac dinh (hoi 2 lan)
  "5. Restart Pi",     // index 4: khoi dong lai Raspberry Pi
  "6. Thoat ve OS"     // index 5: quay lai menu tong
};

SettingsApp::SettingsApp()
  : MenuAppService("Cai Dat (Set)", "=== CAI DAT ===", SETTINGS_MENU_ITEMS, 6, true),
    _mode(SET_MODE_MENU),
    _soundOn(true)
{
}

void SettingsApp::loadSettings(const byte* data, uint8_t len) {
  if (data && len >= 1) {
    _soundOn = (data[0] != 0);
  }
}

void SettingsApp::onEnter() {
  _mode = SET_MODE_MENU;
  MenuAppService::onEnter();
}

void SettingsApp::update(KeyCode key) {
  if (key == KEY_NONE) return;

  if (_mode == SET_MODE_MENU) {
    // Dieu huong danh sach menu binh thuong
    MenuAppService::update(key);

  } else if (_mode == SET_MODE_CONFIRM_STEP1) {
    // HOI XAC NHAN LAN 1
    if (key == KEY_SELECT) {
      // Nguoi dung chon Tiep tuc -> Chuyen sang Buoc xac nhan lan 2
      _mode = SET_MODE_CONFIRM_STEP2;
      drawConfirmStep2();
    } else if (key == KEY_LEFT) {
      // Nguoi dung chon Huy -> Quay ve Menu Cai dat
      _mode = SET_MODE_MENU;
      drawMenu();
    }

  } else if (_mode == SET_MODE_CONFIRM_STEP2) {
    // HOI XAC NHAN LAN 2 (LAN CUOI CUNG TRUOC KHI RESET)
    if (key == KEY_SELECT) {
      // XAC NHAN THUC SU XOA HET DU LIEU
      executeResetAll();
      _mode = SET_MODE_MENU;
      drawMenu();
    } else if (key == KEY_LEFT) {
      // Nguoi dung chon Huy o buoc 2 -> Quay ve an toan, khong xoa gi
      _mode = SET_MODE_MENU;
      drawMenu();
    }

  } else if (_mode == SET_MODE_SYS_INFO) {
    // Bam LEFT hoac SELECT de thoat man hinh Thong tin
    if (key == KEY_LEFT || key == KEY_SELECT) {
      _mode = SET_MODE_MENU;
      drawMenu();
    }
  }
}

void SettingsApp::onItemSelected(uint8_t index) {
  LCDKeypadDriver* drv = getDriver();

  if (index == 0) {
    // 1. Bat / tat den nen LCD
    if (drv) {
      drv->toggleBacklight();
      byte blState = drv->isBacklightOn() ? 1 : 0;
      if (_os) {
        _os->saveAppSetting(0x00, &blState, 1);
      }
      drawMenu();
    }

  } else if (index == 1) {
    // 2. Bat / tat am thanh
    _soundOn = !_soundOn;
    byte sndData[1] = { _soundOn ? (byte)1 : (byte)0 };
    saveSetting(sndData, 1);
    drawMenu();

  } else if (index == 2) {
    // 3. Xem thong tin he thong
    _mode = SET_MODE_SYS_INFO;
    showSystemInfo();

  } else if (index == 3) {
    // 4. Reset All Data -> Chuyen sang man hinh hoi xac nhan lan 1!
    _mode = SET_MODE_CONFIRM_STEP1;
    drawConfirmStep1();

  } else if (index == 4) {
    // 5. Restart Raspberry Pi
    LCDKeypadDriver* drv2 = getDriver();
    if (drv2) {
      drv2->clear();
      drv2->printAt(0, 0, F("Restart Pi..."));
      drv2->printAt(0, 1, F("Dang reboot..."));
    }
    // Gui lenh restart xuong PC
    byte pkt[] = { 0xAA, 0x02, 0x3D, 0x3D, 0xBB };
    Serial.write(pkt, sizeof(pkt));
    delay(1000);
    drawMenu();

  } else if (index == 5) {
    // 6. Thoat ve menu tong
    exitApp();
  }
}

void SettingsApp::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  // Header
  drv->printAt(0, 0, F("=== CAI DAT ==="));

  // Dong 1 hien thi trang thai dong
  if (_selectedIndex == 0) {
    char line[17];
    bool bl = drv->isBacklightOn();
    snprintf(line, sizeof(line), ">1.Den nen: %-4s", bl ? "ON" : "OFF");
    line[16] = '\0';
    drv->printAt(0, 1, line);
  } else if (_selectedIndex == 1) {
    char line[17];
    snprintf(line, sizeof(line), ">2.Am thanh:%-4s", _soundOn ? "ON" : "OFF");
    line[16] = '\0';
    drv->printAt(0, 1, line);
  } else if (_selectedIndex == 2) {
    drv->printAt(0, 1, F(">3.Thong tin OS "));
  } else if (_selectedIndex == 3) {
    drv->printAt(0, 1, F(">4.Reset AllData"));
  } else if (_selectedIndex == 4) {
    drv->printAt(0, 1, F(">5.Restart Pi   "));
  } else {
    drv->printAt(0, 1, F(">6.Thoat ve OS  "));
  }
}

void SettingsApp::drawConfirmStep1() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  drv->printAt(0, 0, F("Xoa het cai dat?"));
  drv->printAt(0, 1, F("SEL:Tiep  LT:Huy"));
}

void SettingsApp::drawConfirmStep2() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  drv->printAt(0, 0, F("XAC NHAN LAN 2! "));
  drv->printAt(0, 1, F("SEL:XOA   LT:Huy"));
}

void SettingsApp::executeResetAll() {
  LCDKeypadDriver* drv = getDriver();
  if (drv) {
    drv->clear();
    drv->printAt(0, 0, F("== DANG XOA...=="));
    drv->printAt(0, 1, F("Reset toan bo..."));
  }

  // 1. Goi OS thuc hien Reset toan bo: Backlight, EEPROM, ca 4 Apps & gui lenh cho PC
  if (_os) {
    _os->resetAllSettings();
  }

  _soundOn = true;
  delay(1200);

  if (drv) {
    drv->printAt(0, 0, F("== DA RESET! == "));
    drv->printAt(0, 1, F("Ve mac dinh OK! "));
  }
  delay(1000);
}

void SettingsApp::showSystemInfo() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->clear();
  char line0[17];
  snprintf(line0, sizeof(line0), "RAM:%3dB Up:%3lus", getFreeRam(), millis() / 1000);
  line0[16] = '\0';
  drv->printAt(0, 0, line0);
  drv->printAt(0, 1, F("OS v3.0  115200b"));
}

int SettingsApp::getFreeRam() {
  extern int __heap_start, *__brkval;
  int v;
  return (int)&v - (__brkval == 0 ? (int)&__heap_start : (int)__brkval);
}
