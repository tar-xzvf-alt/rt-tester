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
    SharedData *shared = (SharedData*)arg;
    printf("Metrics collector thread cleaning up\n");
}

void update_cpu_metrics(SharedData *shared)
{
    FILE *stat = fopen("/proc/stat", "r");
    if (!stat) {
        perror("fopen /proc/stat");
        return;
    }
    
    unsigned long long user, nice, system, idle, iowait, irq, softirq;
    int ret = fscanf(stat, "cpu %llu %llu %llu %llu %llu %llu %llu",
           &user, &nice, &system, &idle, &iowait, &irq, &softirq);
    fclose(stat);
    
    if (ret < 7) return;
    
    unsigned long long total = user + nice + system + idle + iowait + irq + softirq;
    unsigned long long idle_all = idle + iowait;
    
    if (shared->prev_total != 0) {
        unsigned long long total_diff = total - shared->prev_total;
        unsigned long long idle_diff = idle_all - (shared->prev_idle + shared->prev_iowait);
        
        if (total_diff > 0) {
            float cpu_usage = 100.0 * (1.0 - (float)idle_diff / total_diff);
            
            pthread_mutex_lock(&shared->stats_mutex);
            
            if (cpu_usage > shared->current_stats.max_cpu) {
                shared->current_stats.max_cpu = cpu_usage;
            }
            shared->current_stats.total_cpu += cpu_usage;
            
            pthread_mutex_unlock(&shared->stats_mutex);
        }
    }
    
    shared->prev_user = user;
    shared->prev_system = system;
    shared->prev_idle = idle;
    shared->prev_iowait = iowait;
    shared->prev_total = total;
}

void update_memory_metrics(SharedData *shared)
{
    FILE *meminfo = fopen("/proc/meminfo", "r");
    if (!meminfo) {
        perror("fopen /proc/meminfo");
        return;
    }
    
    unsigned long mem_total = 0, mem_available = 0;
    char line[256];
    
    while (fgets(line, sizeof(line), meminfo)) {
        if (sscanf(line, "MemTotal: %lu kB", &mem_total) == 1) continue;
        if (sscanf(line, "MemAvailable: %lu kB", &mem_available) == 1) continue;
    }
    fclose(meminfo);
    
    if (mem_total > 0 && mem_available > 0) {
        float mem_usage = 100.0 * (1.0 - (float)mem_available / mem_total);
        
        pthread_mutex_lock(&shared->stats_mutex);
        
        if (mem_usage > shared->current_stats.max_mem) {
            shared->current_stats.max_mem = mem_usage;
        }
        shared->current_stats.total_mem += mem_usage;
        shared->current_stats.samples++;
        
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
    
    while (shared->running) {
        pthread_mutex_lock(&shared->stats_mutex);
        
        // Wait for signal from GPIO thread with timeout
        clock_gettime(CLOCK_REALTIME, &timeout);
        timeout.tv_sec += 1;  // 1 second timeout
        
        int ret = pthread_cond_timedwait(&shared->measurement_cond, 
                                         &shared->stats_mutex, &timeout);
        
        if (ret == 0) {
            // Received signal - new pulse
            local_pulse_counter++;
            
            pthread_mutex_unlock(&shared->stats_mutex);
            
            // Take measurements (cancellation points inside these functions)
            update_cpu_metrics(shared);
            update_memory_metrics(shared);
            
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