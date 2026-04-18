#define _GNU_SOURCE
#include "utils.h"
#include "shared_data.h"
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>

#define RT_PRIORITY 80

void setup_rt(int pid)
{
    struct sched_param sp = {
        .sched_priority = RT_PRIORITY
    };

    if (sched_setscheduler(pid, SCHED_FIFO, &sp) < 0)
        perror("sched_setscheduler");

    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0)
        perror("mlockall");
}

void set_current_thread_rt(const char* thread_name)
{
    pthread_t self = pthread_self();
    struct sched_param sp = {
        .sched_priority = RT_PRIORITY
    };
    
    int policy = SCHED_FIFO;
    int ret = pthread_setschedparam(self, policy, &sp);
    if (ret != 0) {
        fprintf(stderr, "pthread_setschedparam for %s: %s\n", 
                thread_name, strerror(ret));
    }
    
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0) {
        perror("mlockall");
    }
}

void cleanup_resources(SharedData *shared)
{
    if (!shared) return;
    
    printf("Cleaning up resources...\n");
    
    if (shared->log_file) {
        fflush(shared->log_file);
        fclose(shared->log_file);
        shared->log_file = NULL;
        printf("Log file closed\n");
    }
    
    pthread_mutex_destroy(&shared->stats_mutex);
    pthread_cond_destroy(&shared->measurement_cond);
    printf("Mutex and condition destroyed\n");
}