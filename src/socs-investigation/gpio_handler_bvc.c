#include "gpio_handler.h"
#include "utils.h"
#include "shared_data.h"
#include "consumer_names.h"
#include <gpiod.h>
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <pthread.h>

#define GPIO_CHIP      "/dev/gpiochip0"
#define GPIO_IN_LINE   0
#define GPIO_OUT_LINE  4


void* gpio_handler_thread(void* arg)
{
    SharedData *shared = (SharedData*)arg;
    
    printf("GPIO handler thread started\n");
    set_current_thread_rt("gpio_handler");
    
    pthread_setcancelstate(PTHREAD_CANCEL_ENABLE, NULL);
    pthread_setcanceltype(PTHREAD_CANCEL_DEFERRED, NULL);
    
    struct gpiod_chip *chip;
    struct gpiod_line *in_line, *out_line;
    int ret;

    chip = gpiod_chip_open(GPIO_CHIP);
    if (!chip) {
        perror("gpiod_chip_open");
        return NULL;
    }

    in_line = gpiod_chip_get_line(chip, GPIO_IN_LINE);
    if (!in_line) {
        perror("gpiod_chip_get_line (input)");
        gpiod_chip_close(chip);
        return NULL;
    }

    out_line = gpiod_chip_get_line(chip, GPIO_OUT_LINE);
    if (!out_line) {
        perror("gpiod_chip_get_line (output)");
        gpiod_chip_close(chip);
        return NULL;
    }

    ret = gpiod_line_request_both_edges_events(in_line, CONSUMER_BVCARM);
    if (ret < 0) {
        perror("gpiod_line_request_both_edges_events");
        gpiod_chip_close(chip);
        return NULL;
    }

    ret = gpiod_line_request_output(out_line, CONSUMER_BVCARM, 0);
    if (ret < 0) {
        perror("gpiod_line_request_output");
        gpiod_line_release(in_line);
        gpiod_chip_close(chip);
        return NULL;
    }

    struct gpiod_line_event event;
    struct timespec timeout = { .tv_sec = 0, .tv_nsec = 100000000 }; // 100ms

    printf("GPIO handler waiting for interrupts...\n");
    printf("(will be canceled on shutdown)\n");

    while (__atomic_load_n(&shared->running, __ATOMIC_SEQ_CST)) {
        
        ret = gpiod_line_event_wait(in_line, &timeout);
        
        if (ret < 0) {
            if (errno == EINTR) {
                break;
            }
            perror("gpiod_line_event_wait");
            usleep(10000);
            continue;
        }
        
        if (ret == 0) {
            continue;
        }
        
        ret = gpiod_line_event_read(in_line, &event);
        if (ret < 0) {
            perror("gpiod_line_event_read");
            continue;
        }

        if (event.event_type == GPIOD_LINE_EVENT_RISING_EDGE) {
            gpiod_line_set_value(out_line, 1);
            
            pthread_mutex_lock(&shared->stats_mutex);
            shared->pulse_counter++;
            pthread_cond_signal(&shared->measurement_cond);
            pthread_mutex_unlock(&shared->stats_mutex);
            
        } else {
            gpiod_line_set_value(out_line, 0);

            pthread_mutex_lock(&shared->stats_mutex);
            shared->pulse_counter++;
            pthread_cond_signal(&shared->measurement_cond);
            pthread_mutex_unlock(&shared->stats_mutex);
        }
        
        pthread_testcancel();
    }

    printf("\nGPIO handler stopping...\n");
    
    gpiod_line_release(in_line);
    gpiod_line_release(out_line);
    gpiod_chip_close(chip);
    
    pthread_testcancel();
    printf("GPIO handler thread stopped\n");
    return NULL;
}
