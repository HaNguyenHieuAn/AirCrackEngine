/**
 * MenuAppService.cpp
 *
 * Implement MenuAppService framework
 */

#include "MenuAppService.h"
#include "LCDKeypadDriver.h"

MenuAppService::MenuAppService(const char* appName,
                               const char* menuTitle,
                               const char* const* items,
                               uint8_t itemCount,
                               bool autoExitOnLeft)
  : _appName(appName),
    _menuTitle(menuTitle),
    _items(items),
    _itemCount(itemCount),
    _selectedIndex(0),
    _autoExitOnLeft(autoExitOnLeft)
{
}

void MenuAppService::onEnter() {
  _selectedIndex = 0;
  drawMenu();
}

void MenuAppService::update(KeyCode key) {
  if (key == KEY_NONE) return;

  if (key == KEY_UP) {
    if (_itemCount > 0) {
      _selectedIndex = (_selectedIndex - 1 + _itemCount) % _itemCount;
      drawMenu();
    }
  } else if (key == KEY_DOWN) {
    if (_itemCount > 0) {
      _selectedIndex = (_selectedIndex + 1) % _itemCount;
      drawMenu();
    }
  } else if (key == KEY_SELECT) {
    if (_itemCount > 0) {
      onItemSelected(_selectedIndex);
    }
  } else if (key == KEY_LEFT) {
    onBackSelected();
  }
}

void MenuAppService::onBackSelected() {
  if (_autoExitOnLeft) {
    exitApp(); // Quay ve OS Menu Tong
  }
}

void MenuAppService::setSelectedIndex(uint8_t idx) {
  if (idx < _itemCount) {
    _selectedIndex = idx;
    drawMenu();
  }
}

void MenuAppService::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv || _itemCount == 0) return;

  // Dong 0: Header menu
  char header[17];
  if (_menuTitle) {
    snprintf(header, sizeof(header), "%-16s", _menuTitle);
    header[16] = '\0';
    drv->printAt(0, 0, header);
  } else {
    snprintf(header, sizeof(header), "MENU       [%u/%u]", (unsigned int)(_selectedIndex + 1), (unsigned int)_itemCount);
    drv->printAt(0, 0, header);
  }

  // Dong 1: Muc dang chon kem theo con tro ">"
  char line[17];
  const char* itemText = _items[_selectedIndex];
  snprintf(line, sizeof(line), ">%-15s", itemText ? itemText : "");
  line[16] = '\0';
  drv->printAt(0, 1, line);
}
