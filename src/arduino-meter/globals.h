#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include "config.h"

// Global variables
extern volatile bool active;
extern volatile unsigned long t_start;
extern volatile int groupIndex;
extern volatile int measurementInGroup;
extern volatile int sendingInGroup;
extern volatile bool collectingData;
extern volatile unsigned long sessionId;
extern volatile int maxGroups;

// Timer variables
extern volatile unsigned long lastMeasurementTime;

// Measurement parameters (configurable via START command)
extern volatile int worstCount;              // Number of worst latencies to report
extern volatile unsigned int measurementIntervalUs;  // Interval between measurements

// For direct port access
extern volatile uint8_t* portOutputRegisterPin7;
extern uint8_t pin7Mask;
extern volatile uint8_t* portInputRegisterPin20;
extern uint8_t pin20Mask;

// Temporary arrays for current group
extern volatile int currentGroupLatency[GROUP_SIZE];

// Functions
void checkSerialCommands();
void startMeasurement(unsigned long session_id, int groups, int worst_cnt, unsigned int interval_us);

#endif
