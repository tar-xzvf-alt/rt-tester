#ifndef CONFIG_H
#define CONFIG_H

const int PIN_OUT = 7;
const int PIN_IN = 20;
const int GROUP_SIZE = 1500;

// Default values (will be overridden by START command)
const int DEFAULT_WORST_COUNT = 75;
const unsigned long DEFAULT_MEASUREMENT_INTERVAL_US = 10000UL;

#endif
