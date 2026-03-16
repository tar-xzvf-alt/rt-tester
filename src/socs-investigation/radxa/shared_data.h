#ifndef SHARED_DATA_H
#define SHARED_DATA_H

#include <pthread.h>
#include <sys/time.h>
#include <stdio.h>

#define PULSES_PER_GROUP 1500
#define LOG_PATH "/var/log/soc_metrics.log"

// Структура для пиковых значений за группу
typedef struct {
    float max_cpu;           // Максимальный CPU за одно измерение в группе
    float max_mem;           // Максимальная память за одно измерение в группе
    float total_cpu;         // Сумма CPU для вычисления среднего
    float total_mem;         // Сумма памяти для вычисления среднего
    int samples;             // Количество измерений в группе
    int group_number;        // Номер текущей группы
    struct timeval group_start; // Время начала группы
} GroupStats;

// Разделяемые данные между потоками
typedef struct {
    // Управление
    volatile int running;
    volatile int pulse_counter;     // Счетчик импульсов в текущей группе
    volatile int group_counter;      // Счетчик групп
    
    // Синхронизация
    pthread_mutex_t stats_mutex;
    pthread_cond_t measurement_cond;
    
    // Статистика текущей группы
    GroupStats current_stats;
    
    // Для измерения CPU (предыдущие значения)
    unsigned long long prev_user;
    unsigned long long prev_system;
    unsigned long long prev_idle;
    unsigned long long prev_iowait;
    unsigned long long prev_total;
    
    // Лог-файл
    FILE *log_file;
    
    // Идентификаторы потоков для принудительного завершения
    pthread_t gpio_thread;
    pthread_t metrics_thread;
} SharedData;

#endif // SHARED_DATA_H