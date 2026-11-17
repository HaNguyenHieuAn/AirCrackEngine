/**
 * GameMenuApp.cpp
 *
 * Implement GameMenuApp - Menu Game doc lap va Mini-Game Native tren Arduino LCD
 */

#include "NativeGameApp.h"
#include "../../core/LCDKeypadDriver.h"

// Custom Bitmap cho nhan vat va vat can tren LCD
static const byte CHAR_HERO[8] PROGMEM = {
  B01110,
  B01110,
  B00100,
  B11111,
  B00100,
  B01010,
  B01010,
  B10001
};

static const byte CHAR_MONSTER[8] PROGMEM = {
  B00000,
  B10001,
  B11111,
  B10101,
  B11111,
  B01110,
  B10101,
  B00000
};

static const byte CHAR_HEART[8] PROGMEM = {
  B00000,
  B01010,
  B11111,
  B11111,
  B01110,
  B00100,
  B00000,
  B00000
};

const char* const GAME_MENU_ITEMS[] = {
  "1. Choi Game",
  "2. Diem Cao",
  "3. Do Kho",
  "4. Thoat ve OS"
};
const uint8_t GAME_MENU_COUNT = 4;

const char* const DIFFICULTY_LABELS[] = {
  "De (Easy)",
  "Vua (Medium)",
  "Kho (Hard)"
};

NativeGameApp::NativeGameApp()
  : _state(GAME_STATE_MENU),
    _menuIndex(0),
    _difficulty(1),
    _score(0),
    _highScore(0),
    _playerRow(1),
    _isJumping(false),
    _jumpStartTime(0),
    _obstacleCol(15),
    _obstacleRow(1),
    _lastGameTick(0),
    _gameTickInterval(160)
{
}

void NativeGameApp::loadSettings(const byte* data, uint8_t len) {
  if (data && len >= 1) {
    _difficulty = (data[0] <= 2) ? data[0] : 1;
    _gameTickInterval = (_difficulty == 0) ? 220 : ((_difficulty == 1) ? 160 : 110);
  }
  if (data && len >= 3) {
    _highScore = (unsigned int)data[1] | ((unsigned int)data[2] << 8);
  }
}

void NativeGameApp::onEnter() {
  _state = GAME_STATE_MENU;
  _menuIndex = 0;
  initCustomChars();
  drawMenu();
}

void NativeGameApp::onExit() {
  // Reset trang thai khi roi khoi App
  _state = GAME_STATE_MENU;
}

void NativeGameApp::initCustomChars() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  byte buffer[8];
  memcpy_P(buffer, CHAR_HERO, 8);
  drv->getLCD().createChar(0, buffer);

  memcpy_P(buffer, CHAR_MONSTER, 8);
  drv->getLCD().createChar(1, buffer);

  memcpy_P(buffer, CHAR_HEART, 8);
  drv->getLCD().createChar(2, buffer);
}

void NativeGameApp::update(KeyCode key) {
  switch (_state) {
    case GAME_STATE_MENU:
      handleMenu(key);
      break;
    case GAME_STATE_PLAYING:
      handlePlaying(key);
      break;
    case GAME_STATE_HIGHSCORE:
      handleHighScore(key);
      break;
    case GAME_STATE_DIFFICULTY:
      handleDifficulty(key);
      break;
    case GAME_STATE_GAMEOVER:
      handleGameOver(key);
      break;
  }
}

// ============================================================
//  1. MENU GAME CHINH
// ============================================================
void NativeGameApp::handleMenu(KeyCode key) {
  if (key == KEY_UP) {
    _menuIndex = (_menuIndex - 1 + GAME_MENU_COUNT) % GAME_MENU_COUNT;
    drawMenu();
  } else if (key == KEY_DOWN) {
    _menuIndex = (_menuIndex + 1) % GAME_MENU_COUNT;
    drawMenu();
  } else if (key == KEY_LEFT) {
    // Phim LEFT: Thoat ve OS Menu Tong
    exitApp();
  } else if (key == KEY_SELECT) {
    if (_menuIndex == 0) {
      // Choi game
      startNewGame();
    } else if (_menuIndex == 1) {
      // Xem diem cao
      _state = GAME_STATE_HIGHSCORE;
      drawHighScore();
    } else if (_menuIndex == 2) {
      // Do kho
      _state = GAME_STATE_DIFFICULTY;
      drawDifficulty();
    } else if (_menuIndex == 3) {
      // Thoat ve OS
      exitApp();
    }
  }
}

void NativeGameApp::drawMenu() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  char header[17];
  snprintf(header, sizeof(header), "GAME MENU  [%u/%u]", (unsigned int)(_menuIndex + 1), (unsigned int)GAME_MENU_COUNT);
  drv->printAt(0, 0, header);

  char line[17];
  snprintf(line, sizeof(line), ">%-15s", GAME_MENU_ITEMS[_menuIndex]);
  line[16] = '\0';
  drv->printAt(0, 1, line);
}

// ============================================================
//  2. MINI-GAME RUNNER (NATIVE ARDUINO)
// ============================================================
void NativeGameApp::startNewGame() {
  _state = GAME_STATE_PLAYING;
  _score = 0;
  _playerRow = 1;
  _isJumping = false;
  _obstacleCol = 15;
  _obstacleRow = 1;

  // Chinh toc do theo do kho
  if (_difficulty == 0)      _gameTickInterval = 200; // De
  else if (_difficulty == 1) _gameTickInterval = 140; // Vua
  else                       _gameTickInterval = 90;  // Kho

  _lastGameTick = millis();

  LCDKeypadDriver* drv = getDriver();
  if (drv) drv->clear();
  drawGame();
}

void NativeGameApp::handlePlaying(KeyCode key) {
  unsigned long now = millis();

  // Bam UP de nhay
  if (key == KEY_UP && !_isJumping) {
    _isJumping = true;
    _jumpStartTime = now;
    _playerRow = 0;
  }

  // Bam LEFT hoac SELECT de tam dung / thoat ve Menu Game
  if (key == KEY_LEFT) {
    _state = GAME_STATE_MENU;
    drawMenu();
    return;
  }

  // Kiem tra thoi gian nhay de roi xuong dat
  if (_isJumping && (now - _jumpStartTime >= JUMP_DURATION)) {
    _isJumping = false;
    _playerRow = 1;
  }

  // Vong lap di chuyen quai vat va vat can
  if (now - _lastGameTick >= _gameTickInterval) {
    _lastGameTick = now;

    _obstacleCol--;
    if (_obstacleCol < 0) {
      _obstacleCol = 15;
      _score += 10;
      // Tang toc do nhe sau moi luot
      if (_gameTickInterval > 60) _gameTickInterval -= 2;
    }

    // Kiem tra va cham (Nhan vat o cot 1)
    if (_obstacleCol == 1 && _obstacleRow == _playerRow) {
      // GAME OVER
      _state = GAME_STATE_GAMEOVER;
      if (_score > _highScore) {
        _highScore = _score;
        byte appData[3] = { _difficulty, lowByte(_highScore), highByte(_highScore) };
        saveSetting(appData, 3);
      }
      drawGameOver();
      return;
    }

    drawGame();
  }
}

void NativeGameApp::drawGame() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  // Dong 0:
  // - Cot 0..1: Nhan vat (neu dang nhay)
  // - Cot 6..15: Diem so
  drv->getLCD().setCursor(0, 0);
  if (_playerRow == 0) {
    drv->getLCD().write(byte(0)); // Ve Hero
  } else {
    drv->getLCD().print(' ');
  }
  drv->printAt(1, 0, " ");

  char scoreBuf[15];
  snprintf(scoreBuf, sizeof(scoreBuf), "Score:%4u", _score);
  drv->printAt(6, 0, scoreBuf);

  // Dong 1: Mat dat
  drv->getLCD().setCursor(0, 1);
  if (_playerRow == 1) {
    drv->getLCD().write(byte(0)); // Ve Hero
  } else {
    drv->getLCD().print(' ');
  }

  // Xoa khoang giua nhan vat va vat can
  for (int c = 1; c < 16; c++) {
    if (c == _obstacleCol && _obstacleRow == 1) {
      drv->getLCD().setCursor(c, 1);
      drv->getLCD().write(byte(1)); // Ve Quai vat
    } else {
      drv->printAt(c, 1, "_");
    }
  }
}

// ============================================================
//  3. DIEM CAO (HIGH SCORE)
// ============================================================
void NativeGameApp::handleHighScore(KeyCode key) {
  if (key == KEY_SELECT || key == KEY_LEFT) {
    _state = GAME_STATE_MENU;
    drawMenu();
  }
}

void NativeGameApp::drawHighScore() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->printCentered(0, F("== HIGH SCORE =="));
  char buf[17];
  snprintf(buf, sizeof(buf), "Ky luc: %u pts", _highScore);
  drv->printCentered(1, buf);
}

// ============================================================
//  4. DO KHO (DIFFICULTY)
// ============================================================
void NativeGameApp::handleDifficulty(KeyCode key) {
  if (key == KEY_UP || key == KEY_RIGHT) {
    _difficulty = (_difficulty + 1) % 3;
    drawDifficulty();
  } else if (key == KEY_DOWN) {
    _difficulty = (_difficulty - 1 + 3) % 3;
    drawDifficulty();
  } else if (key == KEY_SELECT || key == KEY_LEFT) {
    _state = GAME_STATE_MENU;
    byte appData[3] = { _difficulty, lowByte(_highScore), highByte(_highScore) };
    saveSetting(appData, 3);
    drawMenu();
  }
}

void NativeGameApp::drawDifficulty() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->printCentered(0, F("== DO KHO =="));
  char buf[17];
  snprintf(buf, sizeof(buf), ">%s", DIFFICULTY_LABELS[_difficulty]);
  drv->printCentered(1, buf);
}

// ============================================================
//  5. GAME OVER
// ============================================================
void NativeGameApp::handleGameOver(KeyCode key) {
  if (key != KEY_NONE) {
    // Bam phim bat ky de quay lai menu game
    _state = GAME_STATE_MENU;
    drawMenu();
  }
}

void NativeGameApp::drawGameOver() {
  LCDKeypadDriver* drv = getDriver();
  if (!drv) return;

  drv->printCentered(0, F("** GAME OVER **"));
  char buf[17];
  snprintf(buf, sizeof(buf), "Score: %u pts", _score);
  drv->printCentered(1, buf);
}
