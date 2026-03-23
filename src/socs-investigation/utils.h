#ifndef UTILS_H
#define UTILS_H

#include <sched.h>
#include <sys/mman.h>
#include <pthread.h>
#include "shared_data.h"

// Setup real-time priority for process
void setup_rt(int pid);

// Setup real-time priority for current thread
void set_current_thread_rt(const char* thread_name);

// Cleanup resources
void cleanup_resources(SharedData *shared);

#endif // UTILS_H