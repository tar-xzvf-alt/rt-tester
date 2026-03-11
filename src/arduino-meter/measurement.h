#ifndef MEASUREMENT_H
#define MEASUREMENT_H

#include "globals.h"

void initPins();        // pin initialization
void onResponse();      // intrerrupt handler
void sendGroupData();   // sending data into pc

#endif
