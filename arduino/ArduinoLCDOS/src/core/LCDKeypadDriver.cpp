/**
 * LCDKeypadDriver.cpp
 *
 * Implement chi tiet cho LCDKeypadDriver
 */

#include "LCDKeypadDriver.h"

LCDKeypadDriver::LCDKeypadDriver(uint8_t rs, uint8_t en,
                                 uint8_t d4, uint8_t d5, uint8_t d6, uint8_t d7,
                                 uint8_t btnPin, uint8_t blPin)
  : _lcd(rs, en, d4, d5, d6, d7),
    _btnPin(btnPin),
    _blPin(blPin),
    _backlightOn(true),
    _currentKey(KEY_NONE),
    _lastKey(KEY_NONE),
    _lastDebounceTime(0)
{
}

void LCDKeypadDriver::begin(uint8_t cols, uint8_t rows) {
  _lcd.begin(cols, rows);
  pinMode(_blPin, OUTPUT);
  setBacklight(_backlightOn);
  _lcd.clear();
}

KeyCode LCDKeypadDriver::readRawKey() {
  int val = analogRead(_btnPin);
  // Nguong do dien ap phan ap tren pin A0 (DFRobot Shield)
  if (val < 60)   return KEY_RIGHT;
  if (val < 200)  return KEY_UP;
  if (val < 400)  return KEY_DOWN;
  if (val < 600)  return KEY_LEFT;
  if (val < 800)  return KEY_SELECT;
  return KEY_NONE;
}

KeyCode LCDKeypadDriver::getPressedKey() {
  KeyCode raw = readRawKey();
  unsigned long now = millis();

  if (raw != _lastKey) {
    _lastDebounceTime = now;
    _lastKey = raw;
  }

  if ((now - _lastDebounceTime) >= DEBOUNCE_DELAY) {
    if (raw != _currentKey) {
      _currentKey = raw;
      // Tra ve key chi tai thoi diem vua nhan xuong (canh len cua nut)
      if (_currentKey != KEY_NONE) {
        return _currentKey;
      }
    }
  }

  return KEY_NONE;
}

void LCDKeypadDriver::setBacklight(bool enable) {
  _backlightOn = enable;
  digitalWrite(_blPin, _backlightOn ? HIGH : LOW);
}

void LCDKeypadDriver::toggleBacklight() {
  setBacklight(!_backlightOn);
}

void LCDKeypadDriver::clear() {
  _lcd.clear();
}

void LCDKeypadDriver::clearLine(uint8_t row) {
  _lcd.setCursor(0, row);
  _lcd.print(F("                "));
  _lcd.setCursor(0, row);
}

void LCDKeypadDriver::printAt(uint8_t col, uint8_t row, const char* text) {
  _lcd.setCursor(col, row);
  _lcd.print(text);
}

void LCDKeypadDriver::printAt(uint8_t col, uint8_t row, const __FlashStringHelper* text) {
  _lcd.setCursor(col, row);
  _lcd.print(text);
}

void LCDKeypadDriver::printCentered(uint8_t row, const char* text) {
  int len = strlen(text);
  int col = (16 - len) / 2;
  if (col < 0) col = 0;
  clearLine(row);
  printAt(col, row, text);
}

void LCDKeypadDriver::printCentered(uint8_t row, const __FlashStringHelper* text) {
  // Chuyen tu PROGMEM sang buffer de do chieu dai
  char buffer[17];
  strncpy_P(buffer, (PGM_P)text, sizeof(buffer) - 1);
  buffer[sizeof(buffer) - 1] = '\0';
  printCentered(row, buffer);
}

const char* LCDKeypadDriver::getKeyName(KeyCode key) {
  switch (key) {
    case KEY_RIGHT:  return "RIGHT";
    case KEY_UP:     return "UP";
    case KEY_DOWN:   return "DOWN";
    case KEY_LEFT:   return "LEFT";
    case KEY_SELECT: return "SELECT";
    default:         return "NONE";
  }
}
