#include "log_writer.h"
#include "shared_data.h"
#include <stdio.h>
#include <sys/file.h>
#include <time.h>
#include <sys/time.h>
#include <unistd.h>
#include <sys/stat.h>
#include <stdint.h>

// Wrapper for pthread_cleanup_push — flock() has incompatible signature (int, int)
static void flock_unlock(void *arg)
{
    flock((int)(intptr_t)arg, LOCK_UN);
}


int init_log_file(SharedData *shared, const char *log_path)
{
    shared->log_file = fopen(log_path, "a");
    if (!shared->log_file) {
        perror("fopen log file");
        return -1;
    }
    
    // Check if log was cleared externally
    struct stat st;
    if (stat(log_path, &st) == 0 && st.st_size == 0) {
        fprintf(shared->log_file, "# SoC Metrics Log Started at %ld\n", time(NULL));
        fflush(shared->log_file);
        printf("New log session started, counter reset to 0\n");
    }
    
    return 0;
}

void write_group_to_log(SharedData *shared)
{
    if (!shared->log_file) return;
    
    // Local copies for thread safety
    int group_counter;
    float max_cpu, max_mem, total_cpu, total_mem;
    int samples;
    struct timeval group_start;
    
    // Make copies inside critical section
    pthread_mutex_lock(&shared->stats_mutex);
    group_counter = shared->group_counter;
    max_cpu = shared->current_stats.max_cpu;
    max_mem = shared->current_stats.max_mem;
    total_cpu = shared->current_stats.total_cpu;
    total_mem = shared->current_stats.total_mem;
    samples = shared->current_stats.samples;
    group_start = shared->current_stats.group_start;
    pthread_mutex_unlock(&shared->stats_mutex);
    
    // Check for division by zero
    float cpu_avg = 0.0;
    float mem_avg = 0.0;
    if (samples > 0) {
        cpu_avg = total_cpu / samples;
        mem_avg = total_mem / samples;
    }
    
    struct timeval now;
    gettimeofday(&now, NULL);
    
    float group_duration = (now.tv_sec - group_start.tv_sec) * 1000.0 +
                          (now.tv_usec - group_start.tv_usec) / 1000.0;
    
    int log_fd = fileno(shared->log_file);
    
    // Set cleanup handler for safe writing
    pthread_cleanup_push(flock_unlock, (void*)(intptr_t)log_fd);
    
    flock(log_fd, LOCK_EX);
    
    
    fprintf(shared->log_file, 
            "GROUP=%d CPU_MAX=%.2f MEM_MAX=%.2f CPU_AVG=%.2f MEM_AVG=%.2f SAMPLES=%d DURATION_MS=%.2f TIMESTAMP=%ld\n",
            group_counter,
            max_cpu,
            max_mem,
            cpu_avg,
            mem_avg,
            samples,
            group_duration,
            time(NULL));
    
    fflush(shared->log_file);
    flock(log_fd, LOCK_UN);
    
    pthread_cleanup_pop(0);
}