#include "utils.h"
#include "shared_data.h"
#include "consumer_names.h"
#include <stdio.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>

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
    int priority = RT_PRIORITY;
    
    struct sched_param sp = {
        .sched_priority = priority
    };
    
    int policy = SCHED_FIFO;
    int ret = pthread_setschedparam(self, policy, &sp);
    if (ret != 0) {
        fprintf(stderr, "pthread_setschedparam for %s (priority %d): %s\n", 
                thread_name, priority, strerror(ret));
    }
    
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0) {
        perror("mlockall");
    }
}


// Find and set priority for IRQ thread by trying all known consumer names
// Returns 0 on success, -1 on error
int set_irq_thread_priority(void)
{
    const char* consumer_names[] = {
        CONSUMER_LICHEE,
        CONSUMER_RADXA,
        CONSUMER_STARFIVE,
        CONSUMER_BCVM,
        CONSUMER_BVCARM,
        CONSUMER_MANGOPI,
        CONSUMER_ROCKPI4,
        CONSUMER_REPKAPI4
    };
    int num_names = sizeof(consumer_names) / sizeof(consumer_names[0]);

    for (int i = 0; i < num_names; i++) {
        const char* consumer_name = consumer_names[i];
        char command[512];
        char result[256];
        FILE *fp;
        int pid = -1;
        
        // Build search pattern: irq thread containing consumer name
        // Example: [irq/136-lichee-monitor] contains "lichee-monitor"
        snprintf(command, sizeof(command),
                 "ps -eLo pid,cls,rtprio,cmd | grep 'irq/' | grep '%s' | grep -v grep | awk '{print $1}'",
                 consumer_name);
        
        fp = popen(command, "r");
        if (!fp) {
            perror("popen");
            continue;
        }
        
        if (fgets(result, sizeof(result), fp)) {
            pid = atoi(result);
        }
        pclose(fp);
        
        if (pid == -1) {
            // Try alternative search without brackets
            snprintf(command, sizeof(command),
                     "ps -eLo pid,cls,rtprio,cmd | grep 'irq/' | grep -i '%s' | grep -v grep | awk '{print $1}'",
                     consumer_name);
            
            fp = popen(command, "r");
            if (!fp) {
                perror("popen");
                continue;
            }
            
            if (fgets(result, sizeof(result), fp)) {
                pid = atoi(result);
            }
            pclose(fp);
        }
        
        if (pid == -1) {
            continue;
        }
        
        printf("Found IRQ thread for '%s': PID %d\n", consumer_name, pid);
        
        // Set priority using sched_setscheduler
        struct sched_param sp = {
            .sched_priority = 99  // Maximum priority
        };
        
        int ret = sched_setscheduler(pid, SCHED_FIFO, &sp);
        if (ret != 0) {
            fprintf(stderr, "sched_setscheduler for IRQ thread %d (priority 99): %s\n", 
                    pid, strerror(errno));
            return -1;
        }
        
        printf("Set priority 99 for IRQ thread %d (consumer: %s)\n", pid, consumer_name);
        return 0;
    }
    
    fprintf(stderr, "Could not find IRQ thread for any known consumer\n");
    return -1;
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