#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include "config.h"

// Глобальные переменные
extern volatile bool active;
extern volatile unsigned long t_start;
extern volatile int groupIndex;
extern volatile int measurementInGroup;
extern volatile bool collectingData;
extern volatile unsigned long sessionId;  // Получается с ПК
extern volatile int maxGroups;  // 0 = бесконечно

// Для прямого доступа к портам
extern volatile uint8_t* portOutputRegisterPin7;
extern uint8_t pin7Mask;
extern volatile uint8_t* portInputRegisterPin20;
extern uint8_t pin20Mask;

// Временные массивы для текущей группы
extern volatile int currentGroupLatency[GROUP_SIZE];
extern volatile int currentGroupJitter[GROUP_SIZE];

// Функции
void checkSerialCommands();
void startMeasurement(unsigned long session_id, int groups);

#endif