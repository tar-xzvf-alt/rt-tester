#include "prometheus_exporter.h"
#include "utils.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <microhttpd.h>

static PrometheusExporter *exporter = NULL;
static struct MHD_Daemon *mhd_daemon = NULL;
static pthread_mutex_t metrics_mutex = PTHREAD_MUTEX_INITIALIZER;

static int format_prometheus_metrics(char *buffer, size_t buffer_size)
{
    if (!exporter || !exporter->shared) {
        return 0;
    }

    SharedData *shared = exporter->shared;
    pthread_mutex_lock(&shared->stats_mutex);

    float cpu_avg = 0;
    float mem_avg = 0;
    int samples = shared->current_stats.samples;
    
    if (samples > 0) {
        cpu_avg = shared->current_stats.total_cpu / samples;
        mem_avg = shared->current_stats.total_mem / samples;
    }

    float max_cpu = shared->current_stats.max_cpu;
    float max_mem = shared->current_stats.max_mem;
    int group_counter = shared->group_counter;

    pthread_mutex_unlock(&shared->stats_mutex);

    pthread_mutex_lock(&metrics_mutex);
    
    int len = snprintf(buffer, buffer_size,
        "# TYPE soc_cpu_percent gauge\n"
        "soc_cpu_percent{board=\"%s\",session_id=\"%s\"} %.2f\n"
        "# TYPE soc_cpu_max gauge\n"
        "soc_cpu_max{board=\"%s\",session_id=\"%s\"} %.2f\n"
        "# TYPE soc_memory_percent gauge\n"
        "soc_memory_percent{board=\"%s\",session_id=\"%s\"} %.2f\n"
        "# TYPE soc_memory_max gauge\n"
        "soc_memory_max{board=\"%s\",session_id=\"%s\"} %.2f\n"
        "# TYPE soc_group_counter gauge\n"
        "soc_group_counter{board=\"%s\",session_id=\"%s\"} %d\n"
        "# TYPE soc_samples gauge\n"
        "soc_samples{board=\"%s\",session_id=\"%s\"} %d\n",
        exporter->board_name, exporter->session_id, cpu_avg,
        exporter->board_name, exporter->session_id, max_cpu,
        exporter->board_name, exporter->session_id, mem_avg,
        exporter->board_name, exporter->session_id, max_mem,
        exporter->board_name, exporter->session_id, group_counter,
        exporter->board_name, exporter->session_id, samples
    );

    pthread_mutex_unlock(&metrics_mutex);

    return len;
}

static enum MHD_Result handle_metrics_request(void *cls, struct MHD_Connection *connection,
                                  const char *url, const char *method,
                                  const char *version, const char *upload_data,
                                  size_t *upload_data_size, void **con_cls)
{
    (void)cls;
    (void)url;
    (void)method;
    (void)version;
    (void)upload_data;
    (void)upload_data_size;
    (void)con_cls;

    char buffer[EXPORTER_BUFFER_SIZE];
    int len = format_prometheus_metrics(buffer, sizeof(buffer));

    struct MHD_Response *response = MHD_create_response_from_buffer(
        len, buffer, MHD_RESPMEM_MUST_COPY);
    
    if (!response) {
        return MHD_NO;
    }

    MHD_add_response_header(response, "Content-Type", "text/plain; version=0.0.4; charset=utf-8");
    enum MHD_Result ret = MHD_queue_response(connection, MHD_HTTP_OK, response);
    MHD_destroy_response(response);

    return ret;
}

static void* exporter_thread(void *arg)
{
    (void)arg;
    
    printf("Prometheus exporter thread started on port %d\n", PROMETHEUS_PORT);
    
    mhd_daemon = MHD_start_daemon(
        MHD_USE_SELECT_INTERNALLY | MHD_USE_ERROR_LOG,
        PROMETHEUS_PORT,
        NULL, NULL,
        &handle_metrics_request, NULL,
        MHD_OPTION_END
    );

    if (!mhd_daemon) {
        printf("ERROR: Failed to start Prometheus exporter on port %d\n", PROMETHEUS_PORT);
        return NULL;
    }

    printf("Prometheus exporter listening on http://0.0.0.0:%d/metrics\n", PROMETHEUS_PORT);

    while (exporter && exporter->running) {
        sleep(1);
    }

    printf("Prometheus exporter thread stopping\n");
    return NULL;
}

int start_prometheus_exporter(SharedData *shared, const char *board_name, const char *session_id)
{
    if (exporter) {
        printf("Exporter already running\n");
        return 0;
    }

    exporter = calloc(1, sizeof(PrometheusExporter));
    if (!exporter) {
        perror("calloc");
        return -1;
    }

    exporter->shared = shared;
    strncpy(exporter->board_name, board_name, sizeof(exporter->board_name) - 1);
    strncpy(exporter->session_id, session_id, sizeof(exporter->session_id) - 1);
    exporter->running = 1;

    pthread_t thread;
    if (pthread_create(&thread, NULL, exporter_thread, NULL) != 0) {
        perror("pthread_create");
        free(exporter);
        exporter = NULL;
        return -1;
    }

    pthread_detach(thread);
    return 0;
}

void stop_prometheus_exporter(void)
{
    if (exporter) {
        exporter->running = 0;
        
        if (mhd_daemon) {
            MHD_stop_daemon(mhd_daemon);
            mhd_daemon = NULL;
        }
        
        free(exporter);
        exporter = NULL;
        printf("Prometheus exporter stopped\n");
    }
}

int is_exporter_running(void)
{
    return exporter != NULL && mhd_daemon != NULL;
}

void update_exporter_session_id(const char *session_id)
{
    if (exporter) {
        pthread_mutex_lock(&metrics_mutex);
        strncpy(exporter->session_id, session_id, sizeof(exporter->session_id) - 1);
        pthread_mutex_unlock(&metrics_mutex);
    }
}