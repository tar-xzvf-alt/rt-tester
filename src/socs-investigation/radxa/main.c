#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <pthread.h>
#include <string.h>
#include <sys/time.h>
#include <errno.h>
#include <sys/stat.h>  
#include "shared_data.h"
#include "utils.h"
#include "gpio_handler.h"
#include "metrics_collector.h"
#include "log_writer.h"

static SharedData *shared = NULL;
static int log_was_cleared = 0;  // Флаг, что лог был очищен извне


void signal_handler(int sig)
{
    printf("\n🚦 Received signal %d (%s), cleaning up...\n", 
           sig, strsignal(sig));

    if (sig == SIGUSR1) {
        printf("\n🚦 Received SIGUSR1, resetting group counter to 0\n");
        if (shared) {
            pthread_mutex_lock(&shared->stats_mutex);
            shared->group_counter = 0;
            shared->current_stats.group_number = 0;
            gettimeofday(&shared->current_stats.group_start, NULL);
            
            // Также сбрасываем предыдущие значения CPU
            shared->prev_total = 0;
            shared->prev_idle = 0;
            shared->prev_iowait = 0;
            pthread_mutex_unlock(&shared->stats_mutex);
            
            printf("✅ Group counter reset to 0\n");
        }
        return;
    }
    
    if (shared) {
        // Устанавливаем флаг остановки
        shared->running = 0;
        
        // Разбудить ожидающие потоки
        pthread_mutex_lock(&shared->stats_mutex);
        pthread_cond_broadcast(&shared->measurement_cond);
        pthread_mutex_unlock(&shared->stats_mutex);
        
        // Даем время на корректное завершение (1 секунда)
        printf("  Waiting for threads to finish (1 sec)...\n");
        sleep(1);
        
        // Проверяем, завершились ли потоки
        int gpio_running = 1;
        int metrics_running = 1;
        
        // Если нет - принудительно отменяем
        if (gpio_running) {
            printf("  ⚠️ GPIO thread still running, cancelling...\n");
            pthread_cancel(shared->gpio_thread);
        }
        
        if (metrics_running) {
            printf("  ⚠️ Metrics thread still running, cancelling...\n");
            pthread_cancel(shared->metrics_thread);
        }
        
        // Ждем завершения после отмены
        pthread_join(shared->gpio_thread, NULL);
        pthread_join(shared->metrics_thread, NULL);

        printf("Threads finished\n");
    }
}

int is_log_file_empty(const char *log_path) {
    struct stat st;
    if (stat(log_path, &st) != 0) {
        // Файл не существует - считаем пустым
        return 1;
    }
    return st.st_size == 0;
}

// Функция для обработки сигнала от внешнего мира (вызывается из main при старте)
void reset_group_counter_if_needed(SharedData *shared, const char *log_path) {
    if (is_log_file_empty(log_path)) {
        printf("📋 Log file is empty, resetting group counter to 0\n");
        pthread_mutex_lock(&shared->stats_mutex);
        shared->group_counter = 0;
        shared->current_stats.group_number = 0;
        gettimeofday(&shared->current_stats.group_start, NULL);
        pthread_mutex_unlock(&shared->stats_mutex);
        
        // Также сбрасываем предыдущие значения CPU для корректного расчета
        shared->prev_total = 0;
        shared->prev_idle = 0;
        shared->prev_iowait = 0;
        
        log_was_cleared = 1;
    } else {
        printf("📋 Log file has content, keeping group counter at %d\n", shared->group_counter);
    }
}

int main(int argc, char *argv[])
{
    const char *log_path = LOG_PATH;
    
    if (argc > 1) {
        log_path = argv[1];
    }
    
    // Настройка real-time для главного процесса
    setup_rt(0);
    
    // Установка обработчиков сигналов
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    signal(SIGQUIT, signal_handler);
    signal(SIGUSR1, signal_handler);  // Для внешнего сброса
    
    // Игнорируем SIGPIPE
    signal(SIGPIPE, SIG_IGN);
    
    // Выделяем память под разделяемые данные
    shared = calloc(1, sizeof(SharedData));
    if (!shared) {
        perror("calloc");
        return 1;
    }
    
    // Инициализация синхронизации
    pthread_mutex_init(&shared->stats_mutex, NULL);
    pthread_cond_init(&shared->measurement_cond, NULL);
    
    shared->running = 1;
    shared->pulse_counter = 0;
    shared->group_counter = 0;
    
    // Инициализация статистики текущей группы
    gettimeofday(&shared->current_stats.group_start, NULL);
    shared->current_stats.max_cpu = 0;
    shared->current_stats.max_mem = 0;
    shared->current_stats.total_cpu = 0;
    shared->current_stats.total_mem = 0;
    shared->current_stats.samples = 0;
    
    // Инициализация предыдущих значений CPU
    shared->prev_total = 0;
    shared->prev_idle = 0;
    shared->prev_iowait = 0;
    
    // Проверяем состояние лог-файла при старте
    if (is_log_file_empty(log_path)) {
        printf("📋 Log file is empty, starting with fresh counter\n");
    } else {
        // Если файл не пустой, нам нужно определить последний номер группы
        // Это сложно сделать без чтения всего файла, поэтому просто предупреждаем
        printf("⚠️ Log file already exists with content. Group numbers may continue from previous run.\n");
        printf("   To start fresh, clear the log file manually.\n");
    }
    
    // Открываем лог-файл
    if (init_log_file(shared, log_path) != 0) {
        free(shared);
        return 1;
    }
    
    printf("========================================\n");
    printf("🚀 SoC Metrics Monitor started\n");
    printf("📁 Log file: %s\n", log_path);
    printf("🔢 Pulses per group: %d\n", PULSES_PER_GROUP);
    printf("📊 Current group counter: %d\n", shared->group_counter);
    printf("🛑 Press Ctrl+C to stop\n");
    printf("========================================\n");
    
    // Создаем потоки и сохраняем их ID
    if (pthread_create(&shared->gpio_thread, NULL, gpio_handler_thread, shared) != 0) {
        perror("pthread_create gpio_thread");
        cleanup_resources(shared);
        free(shared);
        return 1;
    }
    
    if (pthread_create(&shared->metrics_thread, NULL, metrics_collector_thread, shared) != 0) {
        perror("pthread_create metrics_thread");
        shared->running = 0;
        pthread_cond_broadcast(&shared->measurement_cond);
        pthread_cancel(shared->gpio_thread);
        pthread_join(shared->gpio_thread, NULL);
        cleanup_resources(shared);
        free(shared);
        return 1;
    }
    
    // Ждем завершения потоков
    pthread_join(shared->gpio_thread, NULL);
    pthread_join(shared->metrics_thread, NULL);
    
    // Очистка ресурсов
    cleanup_resources(shared);
    free(shared);
    
    printf("✅ SoC Metrics Monitor stopped normally\n");
    return 0;
}