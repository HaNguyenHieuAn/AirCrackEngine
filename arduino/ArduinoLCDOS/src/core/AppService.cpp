/**
 * AppService.cpp
 *
 * Implement lien ket giua AppService va LCDKeypadOS
 */

#include "AppService.h"
#include "LCDKeypadOS.h"

void AppService::exitApp() {
  if (_os) {
    _os->returnToMainMenu();
  }
}

void AppService::saveSetting(const byte* data, uint8_t len) {
  if (_os && data && len > 0) {
    _os->saveAppSetting(getAppId(), data, len);
  }
}

LCDKeypadDriver* AppService::getDriver() {
  if (_os) {
    return &(_os->getDriver());
  }
  return nullptr;
}
