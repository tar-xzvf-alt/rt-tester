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
    
    // For CPU measurement (previous values)
    unsigned long long prev_user;
    unsigned long long prev_nice;      // Added
    unsigned long long prev_system;
    unsigned long long prev_idle;
    unsigned long long prev_iowait;
    unsigned long long prev_irq;       // Added
    unsigned long long prev_softirq;   // Added
    unsigned long long prev_steal;     // Added
    unsigned long long prev_total;
    
    // Log file
    FILE *log_file;
    
    // Thread IDs for forceful termination
    pthread_t gpio_thread;
    pthread_t metrics_thread;
} SharedData;

#endif // SHARED_DATA_H