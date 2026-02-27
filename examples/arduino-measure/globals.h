#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include "config.h"

extern volatile bool active;
extern volatile unsigned long t_start;
extern volatile uint8_t groupIndex;
extern volatile int measurementInGroup;
extern volatile bool collectingData;
extern volatile bool sendDataFlag;
extern volatile unsigned long sessionId;

// Для прямого доступа к портам
extern volatile uint8_t* portOutputRegisterPin7;
extern uint8_t pin7Mask;
extern volatile uint8_t* portInputRegisterPin20;
extern uint8_t pin20Mask;

// Массивы статистики (будут заполняться в processGroupStatistics)
extern float groupAvgLatency[NUM_GROUPS];
extern float groupMinLatency[NUM_GROUPS];
extern float groupMaxLatency[NUM_GROUPS];
extern float groupAvgJitter[NUM_GROUPS];

// Временные массивы для текущей группы (используются в прерывании)
extern volatile unsigned long currentGroupLatency[GROUP_SIZE];
extern volatile unsigned long currentGroupJitter[GROUP_SIZE];

#endif
