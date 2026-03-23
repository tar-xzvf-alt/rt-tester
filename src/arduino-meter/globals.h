#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include "config.h"

// Global variables
extern volatile bool active;
extern volatile unsigned long t_start;
extern volatile int groupIndex;
extern volatile int measurementInGroup;
extern volatile int measurementInGroupLast;
extern volatile bool collectingData;
extern volatile unsigned long sessionId;  // Received from PC
extern volatile int maxGroups;

// For direct port access
extern volatile uint8_t* portOutputRegisterPin7;
extern uint8_t pin7Mask;
extern volatile uint8_t* portInputRegisterPin20;
extern uint8_t pin20Mask;

// Temporary arrays for current group
extern volatile int currentGroupLatency[GROUP_SIZE];
extern volatile int currentGroupJitter[GROUP_SIZE];

// Functions
void checkSerialCommands();
void startMeasurement(unsigned long session_id, int groups);

#endif