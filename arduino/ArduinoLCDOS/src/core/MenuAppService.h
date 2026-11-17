/**
 * MenuAppService.h
 *
 * Khung suon (Template / Framework) don gian hoa viec tao bat ky Menu con nao.
 * Chi can truyen danh sach cac muc (Items) va xu ly onItemSelected(),
 * toan bo viec cuon menu, ve man hinh, bat phim UP/DOWN/SELECT/LEFT
 * duoc xu ly tu dong.
 */

#ifndef MENU_APP_SERVICE_H
#define MENU_APP_SERVICE_H

#include <Arduino.h>
#include "AppService.h"

class MenuAppService : public AppService {
public:
  MenuAppService(const char* appName,
                 const char* menuTitle,
                 const char* const* items,
                 uint8_t itemCount,
                 bool autoExitOnLeft = true);

  // Thua ke tu AppService
  virtual const char* getAppName() override { return _appName; }
  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override {}

  // Callback xu ly khi nguoi dung bam SELECT tai mot muc
  virtual void onItemSelected(uint8_t index) = 0;

  // Callback xu ly khi nguoi dung bam LEFT (mac dinh: thoat app quay ve OS)
  virtual void onBackSelected();

  // Ve lai toan bo man hinh menu
  virtual void drawMenu();

  // Helper lay index dang chon
  uint8_t getSelectedIndex() const { return _selectedIndex; }
  void setSelectedIndex(uint8_t idx);

protected:
  const char* _appName;
  const char* _menuTitle;
  const char* const* _items;
  uint8_t _itemCount;
  uint8_t _selectedIndex;
  bool _autoExitOnLeft;
};

#endif // MENU_APP_SERVICE_H
