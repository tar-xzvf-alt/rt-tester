#ifndef MEASUREMENT_H
#define MEASUREMENT_H

#include "globals.h"

void initPins();                     // настройка пинов и прерывания
void onResponse();                    // обработчик прерывания (ISR)
void processGroupStatistics();        // расчёт статистики по завершённой группе

#endif
