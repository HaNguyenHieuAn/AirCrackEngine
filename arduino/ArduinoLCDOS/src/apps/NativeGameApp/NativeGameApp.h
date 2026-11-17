/**
 * NativeGameApp.h
 *
 * Module 1: Mini-game offline native "Dungeon Runner" chay 100% doc lap tren Arduino.
 */

#ifndef NATIVE_GAME_APP_H
#define NATIVE_GAME_APP_H

#include <Arduino.h>
#include "../../core/AppService.h"

enum GameAppState : byte {
  GAME_STATE_MENU,
  GAME_STATE_PLAYING,
  GAME_STATE_HIGHSCORE,
  GAME_STATE_DIFFICULTY,
  GAME_STATE_GAMEOVER
};

class NativeGameApp : public AppService {
public:
  NativeGameApp();

  virtual const char* getAppName() override { return "Dungeon Game"; }
  virtual uint8_t getAppId() const override { return 0x01; }
  virtual void loadSettings(const byte* data, uint8_t len) override;
  virtual void onEnter() override;
  virtual void update(KeyCode key) override;
  virtual void onExit() override;

private:
  GameAppState _state;
  uint8_t _menuIndex;

  uint8_t _difficulty; // 0=Easy, 1=Medium, 2=Hard
  unsigned int _score;
  unsigned int _highScore;

  int8_t _playerRow;   // 0 = Tren khong, 1 = Duoi dat
  bool   _isJumping;
  unsigned long _jumpStartTime;
  const unsigned long JUMP_DURATION = 450; // ms

  int8_t _obstacleCol;
  uint8_t _obstacleRow;
  unsigned long _lastGameTick;
  unsigned long _gameTickInterval;

  void initCustomChars();
  void handleMenu(KeyCode key);
  void handlePlaying(KeyCode key);
  void handleHighScore(KeyCode key);
  void handleDifficulty(KeyCode key);
  void handleGameOver(KeyCode key);

  void drawMenu();
  void drawGame();
  void drawHighScore();
  void drawDifficulty();
  void drawGameOver();

  void startNewGame();
};

#endif // NATIVE_GAME_APP_H
