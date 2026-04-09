#ifndef PROMETHEUS_EXPORTER_H
#define PROMETHEUS_EXPORTER_H

#include "shared_data.h"
#include <microhttpd.h>

#define PROMETHEUS_PORT 9100
#define EXPORTER_BUFFER_SIZE 65536

typedef struct {
    SharedData *shared;
    char board_name[64];
    char session_id[32];
    volatile int running;
} PrometheusExporter;

int start_prometheus_exporter(SharedData *shared, const char *board_name, const char *session_id);
void stop_prometheus_exporter(void);
int is_exporter_running(void);
void update_exporter_session_id(const char *session_id);

#endif // PROMETHEUS_EXPORTER_H