#ifndef MEASUREMENT_H
#define MEASUREMENT_H

#include "globals.h"

void initPins();
void onResponse();           // обработчик прерывания
void sendGroupStatistics();   // отправка статистики группы на ПК

#endif
