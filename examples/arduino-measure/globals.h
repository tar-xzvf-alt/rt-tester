#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include "config.h"

// Глобальные переменные
extern volatile bool active;
extern volatile unsigned long t_start;
extern volatile uint8_t groupIndex;
extern volatile int measurementInGroup;
extern volatile bool collectingData;
extern volatile unsigned long sessionId;

// Для прямого доступа к портам
extern volatile uint8_t* portOutputRegisterPin7;
extern uint8_t pin7Mask;
extern volatile uint8_t* portInputRegisterPin20;
extern uint8_t pin20Mask;

// Временные массивы для текущей группы
extern volatile unsigned long currentGroupLatency[GROUP_SIZE];
extern volatile unsigned long currentGroupJitter[GROUP_SIZE];

#endif
