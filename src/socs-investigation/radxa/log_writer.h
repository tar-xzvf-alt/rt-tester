#ifndef LOG_WRITER_H
#define LOG_WRITER_H

#include "shared_data.h"

// Initialize log file
int init_log_file(SharedData *shared, const char *log_path);

// Write group statistics to log
void write_group_to_log(SharedData *shared);

#endif // LOG_WRITER_H