#include "gpio_handler.h"
#include "utils.h"
#include "shared_data.h"
#include <gpiod.h>
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <pthread.h>

#define GPIO_CHIP      "/dev/gpiochip0"
#define GPIO_LINE 4
#define GPIO_IN_LINE   15
#define GPIO_OUT_LINE  12


void* gpio_handler_thread(void* arg)
{
    SharedData *shared = (SharedData*)arg;
    
    printf("GPIO handler thread started\n");
    set_current_thread_rt("gpio_handler");
    
    // Enable thread cancellation
    pthread_setcancelstate(PTHREAD_CANCEL_ENABLE, NULL);
    pthread_setcanceltype(PTHREAD_CANCEL_DEFERRED, NULL);
    
    struct gpiod_chip *chip;
    struct gpiod_line_request *req;
    struct gpiod_line_settings *in_cfg, *out_cfg;
    struct gpiod_line_config *line_cfg;
    struct gpiod_request_config *req_cfg;
    unsigned int offsets[2];

    offsets[0] = (GPIO_LINE * 32) + GPIO_IN_LINE;   // Input
    offsets[1] = (GPIO_LINE * 32) + GPIO_OUT_LINE;  // Output

    chip = gpiod_chip_open(GPIO_CHIP);
    if (!chip) {
        perror("gpiod_chip_open");
        return NULL;
    }

    in_cfg = gpiod_line_settings_new();
    gpiod_line_settings_set_direction(in_cfg, GPIOD_LINE_DIRECTION_INPUT);
    gpiod_line_settings_set_edge_detection(in_cfg, GPIOD_LINE_EDGE_BOTH);

    out_cfg = gpiod_line_settings_new();
    gpiod_line_settings_set_direction(out_cfg, GPIOD_LINE_DIRECTION_OUTPUT);
    gpiod_line_settings_set_output_value(out_cfg, 0);

    line_cfg = gpiod_line_config_new();
    gpiod_line_config_add_line_settings(line_cfg, &offsets[0], 1, in_cfg);
    gpiod_line_config_add_line_settings(line_cfg, &offsets[1], 1, out_cfg);

    req_cfg = gpiod_request_config_new();
    gpiod_request_config_set_consumer(req_cfg, "lichee-monitor");

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
    printf("(will be canceled on shutdown)\n");

    while (shared->running) {
        
        
        wait_status = gpiod_line_request_read_edge_events(req, evbuf,1);;

        ev = gpiod_edge_event_buffer_get_event(evbuf, 0);

        // Process event
            
        if (gpiod_edge_event_get_event_type(ev) == GPIOD_EDGE_EVENT_RISING_EDGE) {
            gpiod_line_request_set_value(req, offsets[1], 1);
            
            pthread_mutex_lock(&shared->stats_mutex);
            shared->pulse_counter++;
            pthread_cond_signal(&shared->measurement_cond);
            pthread_mutex_unlock(&shared->stats_mutex);
            //printf("\nRising event!");
            
        } else {
            gpiod_line_request_set_value(req, offsets[1], 0);

            pthread_mutex_lock(&shared->stats_mutex);
            shared->pulse_counter++;
            pthread_cond_signal(&shared->measurement_cond);
            pthread_mutex_unlock(&shared->stats_mutex);

            //printf("\nFalling event!");
        }
        
        
        // Check cancellation point
        pthread_testcancel();
    }

    printf("\nGPIO handler stopping...\n");
    
    // Cleanup GPIO resources
    if (evbuf) gpiod_edge_event_buffer_free(evbuf);
    if (req) gpiod_line_request_release(req);
    if (chip) gpiod_chip_close(chip);
    
    if (in_cfg) gpiod_line_settings_free(in_cfg);
    if (out_cfg) gpiod_line_settings_free(out_cfg);
    if (line_cfg) gpiod_line_config_free(line_cfg);
    if (req_cfg) gpiod_request_config_free(req_cfg);
    
    printf("GPIO handler thread stopped\n");
    return NULL;
}
