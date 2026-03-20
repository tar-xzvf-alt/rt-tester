#include "log_writer.h"
#include "shared_data.h"
#include <stdio.h>
#include <sys/file.h>
#include <time.h>
#include <sys/time.h>
#include <unistd.h>
#include <sys/stat.h>


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
    
    struct timeval now;
    gettimeofday(&now, NULL);
    
    float group_duration = (now.tv_sec - shared->current_stats.group_start.tv_sec) * 1000.0 +
                          (now.tv_usec - shared->current_stats.group_start.tv_usec) / 1000.0;
    
    // Set cleanup handler for safe writing
    pthread_cleanup_push((void(*)(void*))flock, 
                         (void*)(intptr_t)fileno(shared->log_file));
    
    flock(fileno(shared->log_file), LOCK_EX);
    
    
    fprintf(shared->log_file, 
            "GROUP=%d CPU_MAX=%.2f MEM_MAX=%.2f CPU_AVG=%.2f MEM_AVG=%.2f SAMPLES=%d DURATION_MS=%.2f TIMESTAMP=%ld\n",
            shared->group_counter,
            shared->current_stats.max_cpu,
            shared->current_stats.max_mem,
            shared->current_stats.total_cpu / shared->current_stats.samples,
            shared->current_stats.total_mem / shared->current_stats.samples,
            shared->current_stats.samples,
            group_duration,
            time(NULL));
    
    fflush(shared->log_file);
    flock(fileno(shared->log_file), LOCK_UN);
    
    pthread_cleanup_pop(0);
    
    printf("Group %d written to log (CPU_MAX=%.2f%%, MEM_MAX=%.2f%%, samples=%d)\n",
           shared->group_counter,
           shared->current_stats.max_cpu,
           shared->current_stats.max_mem,
           shared->current_stats.samples);
}