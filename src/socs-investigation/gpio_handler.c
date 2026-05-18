#include "gpio_handler.h"
#include "utils.h"
#include "shared_data.h"
#include "gpio_config.h"
#include <gpiod.h>
#include <stdbool.h>
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <pthread.h>

void* gpio_handler_thread(void* arg)
{
    SharedData *shared = (SharedData*)arg;

    printf("GPIO handler thread started\n");
    set_current_thread_rt("gpio_handler");

    pthread_setcancelstate(PTHREAD_CANCEL_ENABLE, NULL);
    pthread_setcanceltype(PTHREAD_CANCEL_DEFERRED, NULL);

    struct gpiod_chip *chip;
    struct gpiod_line_request *req;
    struct gpiod_line_settings *in_cfg, *out_cfg;
    struct gpiod_line_config *line_cfg;
    struct gpiod_request_config *req_cfg;
    unsigned int offsets[2];

    offsets[0] = GPIO_OFFSET_IN;
    offsets[1] = GPIO_OFFSET_OUT;

    chip = gpiod_chip_open(GPIO_CHIP);
    if (!chip) {
        perror("gpiod_chip_open");
        return NULL;
    }

    in_cfg = gpiod_line_settings_new();
    gpiod_line_settings_set_direction(in_cfg, GPIOD_LINE_DIRECTION_INPUT);
    gpiod_line_settings_set_edge_detection(in_cfg, GPIO_EDGE);

    out_cfg = gpiod_line_settings_new();
    gpiod_line_settings_set_direction(out_cfg, GPIOD_LINE_DIRECTION_OUTPUT);
    gpiod_line_settings_set_output_value(out_cfg, 0);

    line_cfg = gpiod_line_config_new();
    gpiod_line_config_add_line_settings(line_cfg, &offsets[0], 1, in_cfg);
    gpiod_line_config_add_line_settings(line_cfg, &offsets[1], 1, out_cfg);

    req_cfg = gpiod_request_config_new();
    gpiod_request_config_set_consumer(req_cfg, GPIO_CONSUMER);

    req = gpiod_chip_request_lines(chip, req_cfg, line_cfg);
    if (!req) {
        perror("gpiod_chip_request_lines");
        gpiod_chip_close(chip);
        return NULL;
    }

    struct gpiod_edge_event_buffer *evbuf;
    evbuf = gpiod_edge_event_buffer_new(1);

    int wait_status = 0;
    struct gpiod_edge_event *ev;

    if (!evbuf) {
        perror("gpiod_edge_event_buffer_new");
        gpiod_line_request_release(req);
        gpiod_chip_close(chip);
        return NULL;
    }

    printf("GPIO handler waiting for interrupts...\n");

#ifdef GPIO_MODE_TOGGLE
    bool toggle = false;
#endif

    while (__atomic_load_n(&shared->running, __ATOMIC_SEQ_CST)) {
        wait_status = gpiod_line_request_read_edge_events(req, evbuf, 1);

        if (wait_status < 0) {
            if (errno == EINTR) {
                break;
            }
            perror("gpiod_line_request_read_edge_events");
            usleep(10000);
            continue;
        }

        if (wait_status == 0) {
            continue;
        }

        ev = gpiod_edge_event_buffer_get_event(evbuf, 0);
        if (!ev) {
            continue;
        }

#ifdef GPIO_MODE_TOGGLE
        if (toggle) {
            gpiod_line_request_set_value(req, offsets[1], 1);
        } else {
            gpiod_line_request_set_value(req, offsets[1], 0);
        }
        toggle = !toggle;

        pthread_mutex_lock(&shared->stats_mutex);
        shared->pulse_counter++;
        pthread_cond_signal(&shared->measurement_cond);
        pthread_mutex_unlock(&shared->stats_mutex);
#else
        if (gpiod_edge_event_get_event_type(ev) == GPIOD_EDGE_EVENT_RISING_EDGE) {
            gpiod_line_request_set_value(req, offsets[1], 1);
        } else {
            gpiod_line_request_set_value(req, offsets[1], 0);
        }

        pthread_mutex_lock(&shared->stats_mutex);
        shared->pulse_counter++;
        pthread_cond_signal(&shared->measurement_cond);
        pthread_mutex_unlock(&shared->stats_mutex);
#endif

        pthread_testcancel();
    }

    printf("\nGPIO handler stopping...\n");

    if (evbuf) gpiod_edge_event_buffer_free(evbuf);
    if (req) gpiod_line_request_release(req);
    if (chip) gpiod_chip_close(chip);

    if (in_cfg) gpiod_line_settings_free(in_cfg);
    if (out_cfg) gpiod_line_settings_free(out_cfg);
    if (line_cfg) gpiod_line_config_free(line_cfg);
    if (req_cfg) gpiod_request_config_free(req_cfg);

    pthread_testcancel();
    printf("GPIO handler thread stopped\n");
    return NULL;
}
