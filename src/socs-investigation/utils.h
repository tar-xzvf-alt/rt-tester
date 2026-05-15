#ifndef UTILS_H
#define UTILS_H

#include <sched.h>
#include <sys/mman.h>
#include <pthread.h>
#include "shared_data.h"

// Setup real-time priority for process
void setup_rt(int pid);

// Setup real-time priority for current thread
// GPIO handler gets priority 80, metrics collector gets priority 79
void set_current_thread_rt(const char* thread_name);

// Set maximum priority (99) for current thread
void set_max_priority(const char* thread_name);

// Find and set priority for IRQ thread by trying all known consumer names
// Returns 0 on success, -1 on error
int set_irq_thread_priority(void);

// Cleanup resources
void cleanup_resources(SharedData *shared);

#endif // UTILS_H