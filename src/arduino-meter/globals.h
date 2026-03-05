#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include "config.h"

extern volatile bool active;
extern volatile unsigned long t_start;
extern volatile uint8_t groupIndex;
extern volatile int measurementInGroup;
extern volatile bool collectingData;
extern volatile unsigned long sessionId;

extern volatile uint8_t* portOutputRegisterPin7;
extern uint8_t pin7Mask;
extern volatile uint8_t* portInputRegisterPin20;
extern uint8_t pin20Mask;

extern volatile unsigned long currentGroupLatency[GROUP_SIZE];

#endif
