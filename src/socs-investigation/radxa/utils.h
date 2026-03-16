#ifndef UTILS_H
#define UTILS_H

#include <sched.h>
#include <sys/mman.h>
#include <pthread.h>
#include "shared_data.h"

// Настройка real-time приоритетов для процесса
void setup_rt(int pid);

// Настройка real-time приоритетов для текущего потока
void set_current_thread_rt(const char* thread_name);

// Очистка ресурсов
void cleanup_resources(SharedData *shared);

#endif // UTILS_H