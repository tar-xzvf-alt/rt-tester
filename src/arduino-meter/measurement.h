#ifndef MEASUREMENT_H
#define MEASUREMENT_H

#include "globals.h"

void initPins();        // Pin initialization
void onResponse();      // Interrupt handler
void sendGroupData();   // Send data to PC

#endif
