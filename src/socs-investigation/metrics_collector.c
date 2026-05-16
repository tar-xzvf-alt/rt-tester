#define _GNU_SOURCE
#include "metrics_collector.h"
#include "utils.h"
#include "log_writer.h"
#include "shared_data.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <time.h>
#include <errno.h>
#include <pthread.h>

// Cleanup handler for thread cancellation
void metrics_cleanup_handler(void *arg)
{
    (void)arg;
    printf("Metrics collector thread cleaning up\n");
}

void update_cpu_metrics(SharedData *shared)
{
    if (!shared->stat_file) {
        shared->stat_file = fopen("/proc/stat", "r");
        if (!shared->stat_file) {
            perror("fopen /proc/stat");
            return;
        }
    }
    
    // Rewind to beginning of file
    rewind(shared->stat_file);
    fflush(shared->stat_file);
    
    unsigned long long user, nice, system, idle, iowait, irq, softirq;
    int ret = fscanf(shared->stat_file, "cpu %llu %llu %llu %llu %llu %llu %llu",
        &user, &nice, &system, &idle, &iowait, &irq, &softirq);
    
    if (ret < 7) return;
    
    unsigned long long total = user + nice + system + idle + iowait + irq + softirq;
    unsigned long long idle_all = idle + iowait;
    
    // Lock mutex BEFORE reading prev_* variables
    pthread_mutex_lock(&shared->stats_mutex);
        
    if (shared->prev_total != 0) {
        unsigned long long total_diff = total - shared->prev_total;
        unsigned long long idle_diff = idle_all - (shared->prev_idle + shared->prev_iowait);
        
        if (total_diff > 0) {
            float cpu_usage = 100.0 * (1.0 - (float)idle_diff / total_diff);

            if (cpu_usage < 0) cpu_usage = 0;
            if (cpu_usage > 100) cpu_usage = 100;
            
            if (cpu_usage > shared->current_stats.max_cpu) {
                shared->current_stats.max_cpu = cpu_usage;
            }
            shared->current_stats.total_cpu += cpu_usage;
        }
    }

    // Update prev_* variables inside the same critical section
    shared->prev_user = user;
    shared->prev_system = system;
    shared->prev_idle = idle;
    shared->prev_iowait = iowait;
    shared->prev_total = total;
    
    pthread_mutex_unlock(&shared->stats_mutex);
}

void update_memory_metrics(SharedData *shared)
{
    if (!shared->meminfo_file) {
        shared->meminfo_file = fopen("/proc/meminfo", "r");
        if (!shared->meminfo_file) {
            perror("fopen /proc/meminfo");
            return;
        }
    }
    
    // Rewind to beginning of file
    rewind(shared->meminfo_file);
    fflush(shared->meminfo_file);
    
    unsigned long mem_total = 0, mem_available = 0, mem_free = 0;
    char line[256];
    
    while (fgets(line, sizeof(line), shared->meminfo_file)) {
        if (sscanf(line, "MemTotal: %lu kB", &mem_total) == 1) continue;
        if (sscanf(line, "MemAvailable: %lu kB", &mem_available) == 1) continue;
        if (sscanf(line, "MemFree: %lu kB", &mem_free) == 1) continue;
    }
    
    // Fallback to MemFree if MemAvailable not present (older kernels)
    unsigned long mem_avail = mem_available > 0 ? mem_available : mem_free;
    
    if (mem_total > 0 && mem_avail > 0) {
        float mem_usage = 100.0 * (1.0 - (float)mem_avail / mem_total);
        
        if (mem_usage < 0) mem_usage = 0;
        if (mem_usage > 100) mem_usage = 100;
        
        pthread_mutex_lock(&shared->stats_mutex);
        
        if (mem_usage > shared->current_stats.max_mem) {
            shared->current_stats.max_mem = mem_usage;
        }
        shared->current_stats.total_mem += mem_usage;
        
        pthread_mutex_unlock(&shared->stats_mutex);
    }
}

void* metrics_collector_thread(void* arg)
{
    SharedData *shared = (SharedData*)arg;
    
    // Set cleanup handler
    pthread_cleanup_push(metrics_cleanup_handler, shared);
    
    printf("Metrics collector thread started\n");
    set_current_thread_rt("metrics_collector");
    
    // Enable thread cancellation
    pthread_setcancelstate(PTHREAD_CANCEL_ENABLE, NULL);
    pthread_setcanceltype(PTHREAD_CANCEL_DEFERRED, NULL);
    
    struct timespec timeout;
    int local_pulse_counter = 0;
    int measurement_counter = 0;
    
    while (__atomic_load_n(&shared->running, __ATOMIC_SEQ_CST)) {
        pthread_mutex_lock(&shared->stats_mutex);
        
        // Wait for signal from GPIO thread with timeout
        clock_gettime(CLOCK_REALTIME, &timeout);
        timeout.tv_sec += 1;  // 1 second timeout
        
        int ret = pthread_cond_timedwait(&shared->measurement_cond, 
                                         &shared->stats_mutex, &timeout);
        
        if (ret == 0) {
            // Received signal - new pulse
            local_pulse_counter++;
            measurement_counter++;
            
            pthread_mutex_unlock(&shared->stats_mutex);
            
            // Take measurements every 100 pulses (instead of every pulse)
            if (measurement_counter >= 100) {
                update_cpu_metrics(shared);
                update_memory_metrics(shared);
                
                // Increment sample count for this measurement cycle
                pthread_mutex_lock(&shared->stats_mutex);
                shared->current_stats.samples++;
                pthread_mutex_unlock(&shared->stats_mutex);
                
                measurement_counter = 0;
            }
            
            pthread_mutex_lock(&shared->stats_mutex);
            
            // Check if we've completed a group
            if (local_pulse_counter >= PULSES_PER_GROUP) {
                shared->group_counter++;
                
                pthread_mutex_unlock(&shared->stats_mutex);
                
                // Cancellation point inside write_group_to_log
                write_group_to_log(shared);
                
                pthread_mutex_lock(&shared->stats_mutex);
                
                // Reset for next group
                local_pulse_counter = 0;
                measurement_counter = 0;
                shared->pulse_counter = 0;
                
                // Reset group statistics
                shared->current_stats.max_cpu = 0;
                shared->current_stats.max_mem = 0;
                shared->current_stats.total_cpu = 0;
                shared->current_stats.total_mem = 0;
                shared->current_stats.samples = 0;
                gettimeofday(&shared->current_stats.group_start, NULL);
            }
        }
        
        pthread_mutex_unlock(&shared->stats_mutex);
        
        // Check cancellation point
        pthread_testcancel();
    }
    
    pthread_cleanup_pop(1);
    printf("Metrics collector thread stopped\n");
    return NULL;
}