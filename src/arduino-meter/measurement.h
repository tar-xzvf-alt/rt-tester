#ifndef MEASUREMENT_H
#define MEASUREMENT_H

#include "globals.h"

void initPins();        // инициализация пинов
void onResponse();      // обработчик прерывания
void sendGroupData();   // отправка джиттера группы и худших задержек ПК

#endif
