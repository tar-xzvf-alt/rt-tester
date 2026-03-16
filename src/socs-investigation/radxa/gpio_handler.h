#ifndef GPIO_HANDLER_H
#define GPIO_HANDLER_H

#include "shared_data.h"

// Функция потока обработчика GPIO
void* gpio_handler_thread(void* arg);

#endif // GPIO_HANDLER_H