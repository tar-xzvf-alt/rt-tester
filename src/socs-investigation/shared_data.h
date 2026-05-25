#ifndef SHARED_DATA_H
#define SHARED_DATA_H

#include <pthread.h>
#include <sys/time.h>
#include <stdio.h>

#define PULSES_PER_GROUP 1500
#define LOG_PATH "/var/log/soc_metrics.log"

// Structure for peak values per group
typedef struct {
    float max_cpu;           // Maximum CPU per measurement in group
    float max_mem;           // Maximum memory per measurement in group
    float total_cpu;         // Sum of CPU for calculating average
    float total_mem;         // Sum of memory for calculating average
    int samples;             // Number of measurements in group
    int group_number;        // Current group number
    struct timeval group_start; // Group start time
} GroupStats;

// Shared data between threads
typedef struct {
    // Control
    volatile int running;
    volatile int pulse_counter;     // Pulse counter in current group
    volatile int group_counter;      // Group counter
    
    // Synchronization
    pthread_mutex_t stats_mutex;
    pthread_cond_t measurement_cond;
    
    // Current group statistics
    GroupStats current_stats;
    
    // Log file
    FILE *log_file;
    
    // Thread IDs for forceful termination
    pthread_t gpio_thread;
} SharedData;

#endif // SHARED_DATA_H