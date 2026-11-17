/**
 * LCDKeypadDriver.h
 *
 * Thu vien dieu khien LCD 16x2 va doc ban phim tro khang A0
 * cho DFRobot LCD Keypad Shield tren Arduino Uno / Nano / Mega.
 */

#ifndef LCD_KEYPAD_DRIVER_H
#define LCD_KEYPAD_DRIVER_H

#include <Arduino.h>
#include <LiquidCrystal.h>

// Ma nut bam
enum KeyCode : byte {
  KEY_NONE   = 0x00,
  KEY_RIGHT  = 0x01,
  KEY_UP     = 0x02,
  KEY_DOWN   = 0x03,
  KEY_LEFT   = 0x04,
  KEY_SELECT = 0x05
};

class LCDKeypadDriver {
public:
  // Khoi tao voi cac chan mac dinh cua LCD Keypad Shield
  LCDKeypadDriver(uint8_t rs = 8, uint8_t en = 9,
                  uint8_t d4 = 4, uint8_t d5 = 5, uint8_t d6 = 6, uint8_t d7 = 7,
                  uint8_t btnPin = A0, uint8_t blPin = 10);

  // Khoi dong phan cung
  void begin(uint8_t cols = 16, uint8_t rows = 2);

  // Truy cap truc tiep doi tuong LiquidCrystal
  LiquidCrystal& getLCD() { return _lcd; }

  // Doc nut bam hien tai (khong debounce)
  KeyCode readRawKey();

  // Doc nut bam co debounce va phat hien canh (edge detection)
  // Chi tra ve KEY khi nut vua moi duoc nhan (nhan 1 lan)
  KeyCode getPressedKey();

  // Kiem tra nut hien tai dang duoc giu
  KeyCode getCurrentKey() const { return _currentKey; }

  // Quan ly den nen
  void setBacklight(bool enable);
  bool isBacklightOn() const { return _backlightOn; }
  void toggleBacklight();

  // Tien ich hien thi tren LCD
  void clear();
  void clearLine(uint8_t row);
  void printAt(uint8_t col, uint8_t row, const char* text);
  void printAt(uint8_t col, uint8_t row, const __FlashStringHelper* text);
  void printCentered(uint8_t row, const char* text);
  void printCentered(uint8_t row, const __FlashStringHelper* text);

  // Lay ten nut bam de debug
  static const char* getKeyName(KeyCode key);

private:
  LiquidCrystal _lcd;
  uint8_t _btnPin;
  uint8_t _blPin;
  bool _backlightOn;

  KeyCode _currentKey;
  KeyCode _lastKey;
  unsigned long _lastDebounceTime;
  const unsigned long DEBOUNCE_DELAY = 35; // ms
};

#endif // LCD_KEYPAD_DRIVER_H
