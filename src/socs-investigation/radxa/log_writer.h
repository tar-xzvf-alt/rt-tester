#ifndef LOG_WRITER_H
#define LOG_WRITER_H

#include "shared_data.h"

// Инициализация лог-файла
int init_log_file(SharedData *shared, const char *log_path);

// Запись статистики группы в лог
void write_group_to_log(SharedData *shared);

#endif // LOG_WRITER_H