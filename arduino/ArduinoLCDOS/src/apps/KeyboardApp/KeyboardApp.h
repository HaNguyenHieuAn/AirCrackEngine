#ifndef KEYBOARD_APP_H
#define KEYBOARD_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

class KeyboardApp : public AppService {
public:
  KeyboardApp();

  virtual const char* getAppName() override { return "Keyboard"; }
  virtual uint8_t getAppId() const override { return 0x08; }
  virtual void loadSettings(const byte* data, uint8_t len) override {}

  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override {}

  // Chuan bi nhap lieu cho App goi (callerAppId). Ket qua doc qua getResult().
  static void prepareInput(uint8_t callerAppId, const char* initial = "", uint8_t startMode = 0);
  static const char* getResult() { return _kbText; }
  static bool isDone() { return _kbDone; }
  static void clearDone() { _kbDone = false; }

private:
  static char _kbText[21];
  static uint8_t _kbCallerId;
  static bool _kbDone;
  static uint8_t _kbMode;
  static uint8_t _kbSel;
  static uint8_t _kbCursor;
  static bool _kbPrepared;
  static unsigned long _enterTime;

  static const char* const _modeNames[4];
  static const char* const _modeChars[4];

  void drawScreen();
  uint8_t modeLen() const;
  char currentChar() const;
};

#endif // KEYBOARD_APP_H