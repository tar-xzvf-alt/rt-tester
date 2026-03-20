#ifndef METRICS_COLLECTOR_H
#define METRICS_COLLECTOR_H

#include "shared_data.h"

// Metrics collector thread function
void* metrics_collector_thread(void* arg);

// Update CPU metrics
void update_cpu_metrics(SharedData *shared);

// Update memory metrics
void update_memory_metrics(SharedData *shared);

#endif // METRICS_COLLECTOR_H