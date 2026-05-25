#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <pthread.h>
#include <string.h>
#include <sys/time.h>
#include <errno.h>
#include <sys/stat.h>  
#include <time.h>
#include "shared_data.h"
#include "utils.h"
#include "gpio_handler.h"
#include "log_writer.h"

static SharedData *shared = NULL;

void signal_handler(int sig)
{
    printf("\nReceived signal %d (%s), cleaning up...\n", 
           sig, strsignal(sig));

    if (sig == SIGUSR1) {
        printf("\nReceived SIGUSR1, resetting group counter to 0\n");
        if (shared) {
            pthread_mutex_lock(&shared->stats_mutex);
            shared->group_counter = 0;
            shared->current_stats.group_number = 0;
            gettimeofday(&shared->current_stats.group_start, NULL);
            
            pthread_mutex_unlock(&shared->stats_mutex);
            
            printf("Group counter reset to 0\n");
        }
        return;
    }
    
    if (shared) {
        // Set stop flag
        __atomic_store_n(&shared->running, 0, __ATOMIC_SEQ_CST);
        
        // Wake up waiting threads
        pthread_mutex_lock(&shared->stats_mutex);
        pthread_cond_broadcast(&shared->measurement_cond);
        pthread_mutex_unlock(&shared->stats_mutex);
        
        // Give threads a moment to exit
        usleep(100000); // 100ms
        
        // Force cancel threads if they're still running
        pthread_cancel(shared->gpio_thread);
    }
}

int is_log_file_empty(const char *log_path) {
    struct stat st;
    if (stat(log_path, &st) != 0) {
        // File doesn't exist - consider empty
        return 1;
    }
    return st.st_size == 0;
}

int main(int argc, char *argv[])
{
    const char *log_path = LOG_PATH;
    
    if (argc > 1) {
        log_path = argv[1];
    }
    
    // Setup real-time for main process
    //setup_rt(0);
    
    // Set signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGQUIT, signal_handler);
    signal(SIGUSR1, signal_handler);  // For external reset
    
    // Ignore SIGPIPE
    signal(SIGPIPE, SIG_IGN);
    
    // Allocate memory for shared data
    shared = calloc(1, sizeof(SharedData));
    if (!shared) {
        perror("calloc");
        return 1;
    }
    
    // Initialize synchronization
    pthread_mutex_init(&shared->stats_mutex, NULL);
    pthread_cond_init(&shared->measurement_cond, NULL);
    
    __atomic_store_n(&shared->running, 1, __ATOMIC_SEQ_CST);
    shared->pulse_counter = 0;
    shared->group_counter = 0;
    
    // Initialize current group statistics
    gettimeofday(&shared->current_stats.group_start, NULL);
    shared->current_stats.max_cpu = 0;
    shared->current_stats.max_mem = 0;
    shared->current_stats.total_cpu = 0;
    shared->current_stats.total_mem = 0;
    shared->current_stats.samples = 0;
    
    // Check log file state at startup
    if (is_log_file_empty(log_path)) {
        printf("Log file is empty, starting with fresh counter\n");
    } else {
        // If file is not empty, we need to determine last group number
        // This is difficult without reading entire file, so just warn
        printf("Log file already exists with content. Group numbers may continue from previous run.\n");
        printf("To start fresh, clear the log file manually.\n");
    }
    
    // Open log file
    if (init_log_file(shared, log_path) != 0) {
        free(shared);
        return 1;
    }
    
    printf("========================================\n");
    printf("SoC Metrics Monitor started\n");
    printf("Log file: %s\n", log_path);
    printf("Pulses per group: %d\n", PULSES_PER_GROUP);
    printf("Current group counter: %d\n", shared->group_counter);
    printf("Press Ctrl+C to stop\n");
    printf("========================================\n");
    
    // Create threads and store their IDs
    if (pthread_create(&shared->gpio_thread, NULL, gpio_handler_thread, shared) != 0) {
        perror("pthread_create gpio_thread");
        cleanup_resources(shared);
        free(shared);
        return 1;
    }

    // Try to set IRQ thread priority (requires root)
    // Must be called from main process before creating threads
    printf("Setting IRQ thread priority...\n");
    if (set_irq_thread_priority() != 0) {
        printf("Note: IRQ priority setting failed (run as root for maximum performance)\n");
    }
    

    // Wait for threads to finish
    pthread_join(shared->gpio_thread, NULL);
    
    // Cleanup resources
    cleanup_resources(shared);
    free(shared);
    
    printf("SoC Metrics Monitor stopped normally\n");
    return 0;
}