#ifndef METRICS_COLLECTOR_H
#define METRICS_COLLECTOR_H

#include "shared_data.h"

// Функция потока сборщика метрик
void* metrics_collector_thread(void* arg);

// Обновление метрик CPU
void update_cpu_metrics(SharedData *shared);

// Обновление метрик памяти
void update_memory_metrics(SharedData *shared);

#endif // METRICS_COLLECTOR_H