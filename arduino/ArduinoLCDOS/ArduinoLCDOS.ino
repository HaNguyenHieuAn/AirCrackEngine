
#include "src/core/LCDKeypadOS.h"
#include "src/apps/SettingsApp/SettingsApp.h"
#include "src/apps/WifiSetApp/WifiSetApp.h"
#include "src/apps/KeyboardApp/KeyboardApp.h"
#include "src/apps/AirCrackApp/AirCrackApp.h"

LCDKeypadOS os;
SettingsApp    settingsApp;
WifiSetApp     wifiSetApp;
KeyboardApp    keyboardApp;
AirCrackApp    airCrackApp;

void setup() {
  Serial.begin(115200);

  // Gui goi tin ACK khoi dong chuan binary cho Python nhan dien ngay
  byte startupAck[] = { 0xAA, 0x02, 0x81, 0x81, 0xBB };
  Serial.write(startupAck, sizeof(startupAck));

  os.registerApp(&airCrackApp);
  os.registerApp(&settingsApp);
  os.registerApp(&wifiSetApp);
  os.registerApp(&keyboardApp);
  os.begin();
}
void loop() { os.update(); }
