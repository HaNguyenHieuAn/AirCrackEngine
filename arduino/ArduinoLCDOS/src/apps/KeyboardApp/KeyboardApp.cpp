#include "KeyboardApp.h"
#include "../../core/LCDKeypadDriver.h"
#include "../../core/LCDKeypadOS.h"
#include <string.h>

char KeyboardApp::_kbText[21] = "";
uint8_t KeyboardApp::_kbCallerId = 0;
bool KeyboardApp::_kbDone = false;
uint8_t KeyboardApp::_kbMode = 0;
uint8_t KeyboardApp::_kbSel = 0;
uint8_t KeyboardApp::_kbCursor = 0;
bool KeyboardApp::_kbPrepared = false;
unsigned long KeyboardApp::_enterTime = 0;

const char* const KeyboardApp::_modeNames[4] = { "abc", "ABC", "123", "sym" };
const char* const KeyboardApp::_modeChars[4] = {
  "abcdefghijklmnopqrstuvwxyz",
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "0123456789.:",
  "!@#$%^&*()-_=+[]{};:,.<>/?"
};

KeyboardApp::KeyboardApp() {}

void KeyboardApp::prepareInput(uint8_t callerAppId, const char* initial, uint8_t startMode) {
  _kbCallerId = callerAppId;
  _kbPrepared = true;
  _kbDone = false;
  _kbMode = startMode % 4;
  _kbSel = 0;
  _kbText[0] = '\0';
  if (initial) {
    strncpy(_kbText, initial, 20);
    _kbText[20] = '\0';
  }
  _kbCursor = (uint8_t)strlen(_kbText);
  if (_kbCursor > 20) _kbCursor = 20;
}

void KeyboardApp::onEnter() {
  if (!_kbPrepared) {
    _kbCallerId = 0;
    _kbText[0] = '\0';
    _kbCursor = 0;
    _kbDone = false;
    _kbMode = 0;
    _kbSel = 0;
  }
  _kbPrepared = false;
  _enterTime = millis();
  LCDKeypadDriver* drv = getDriver();
  if (drv) drv->clear();
  drawScreen();
}

void KeyboardApp::update(KeyCode key) {
  unsigned long now = millis();
  if (now - _enterTime < 350) return;
  if (key == KEY_NONE) return;

  if (key == KEY_LEFT) {
    _kbMode = (_kbMode + 1) % 4;
    _kbSel = 0;
    drawScreen();
  } else if (key == KEY_DOWN) {
    uint8_t ml = modeLen();
    if (ml > 0) _kbSel = (_kbSel + 1) % ml;
    drawScreen();
  } else if (key == KEY_UP) {
    if (_kbCursor < 20) {
      uint8_t len = (uint8_t)strlen(_kbText);
      if (_kbCursor >= len) {
        _kbText[_kbCursor] = currentChar();
        _kbText[_kbCursor + 1] = '\0';
      } else {
        _kbText[_kbCursor] = currentChar();
      }
      _kbCursor++;
      uint8_t newLen = (uint8_t)strlen(_kbText);
      if (_kbCursor > newLen) _kbCursor = newLen;
    }
    drawScreen();
  } else if (key == KEY_RIGHT) {
    uint8_t len = (uint8_t)strlen(_kbText);
    if (len == 0) return;
    _kbCursor++;
    if (_kbCursor > len) _kbCursor = 0;
    drawScreen();
  } else if (key == KEY_SELECT) {
    _kbText[_kbCursor] = '\0';
    _kbDone = true;
    if (_kbCallerId == 0 || _kbCallerId == getAppId()) {
      if (_os) _os->returnToMainMenu();
    } else {
      if (_os) _os->launchAppById(_kbCallerId);
    }
  }
}

uint8_t KeyboardApp::modeLen() const {
  return (uint8_t)strlen(_modeChars[_kbMode]);
}

char KeyboardApp::currentChar() const {
  uint8_t ml = modeLen();
  if (ml == 0) return ' ';
  if (_kbSel >= ml) return _modeChars[_kbMode][0];
  return _modeChars[_kbMode][_kbSel];
}

void KeyboardApp::drawScreen() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;
  char l0[17];
  snprintf(l0, sizeof(l0), "KB:%-3s [%c]    ", _modeNames[_kbMode], currentChar());
  l0[16] = '\0';
  drv->printAt(0, 0, l0);

  char l1[17];
  // show text with cursor
  uint8_t len = (uint8_t)strlen(_kbText);
  uint8_t start = 0;
  if (_kbCursor > 15) start = _kbCursor - 15;
  if (start + 16 > len + 1) {
    // pad
  }
  for (uint8_t i = 0; i < 16; i++) {
    uint8_t idx = start + i;
    if (idx < len) l1[i] = _kbText[idx];
    else if (idx == _kbCursor) l1[i] = '_';
    else l1[i] = ' ';
  }
  l1[16] = '\0';
  drv->printAt(0, 1, l1);

  uint8_t textLen = (uint8_t)strlen(_kbText);
  LiquidCrystal& lcd = drv->getLCD();
  if (_kbCursor < textLen && _kbCursor >= start) {
    lcd.setCursor(_kbCursor - start, 1);
    lcd.blink();
  } else {
    lcd.noBlink();
    lcd.noCursor();
  }
}