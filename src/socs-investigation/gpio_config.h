#ifndef GPIO_CONFIG_H
#define GPIO_CONFIG_H

#include "consumer_names.h"

#if defined(BOARD_bcvm)
  #define GPIO_CHIP         "/dev/gpiochip0"
  #define GPIO_BANK         0
  #define GPIO_BANK_MULT    0
  #define GPIO_LINE_IN      15
  #define GPIO_LINE_OUT     9
  #define GPIO_EDGE         GPIOD_LINE_EDGE_FALLING
  #define GPIO_MODE_TOGGLE
  #define GPIO_CONSUMER     CONSUMER_BCVM

#elif defined(BOARD_bvc) || defined(BOARD_bvc_arm)
  #define GPIO_CHIP         "/dev/gpiochip0"
  #define GPIO_BANK         0
  #define GPIO_BANK_MULT    0
  #define GPIO_LINE_IN      0
  #define GPIO_LINE_OUT     4
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_BVCARM

#elif defined(BOARD_lichee)
  #define GPIO_CHIP         "/dev/gpiochip0"
  #define GPIO_BANK         4
  #define GPIO_BANK_MULT    32
  #define GPIO_LINE_IN      12
  #define GPIO_LINE_OUT     16
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_LICHEE

#elif defined(BOARD_radxa)
  #define GPIO_CHIP         "/dev/gpiochip3"
  #define GPIO_BANK         1
  #define GPIO_BANK_MULT    8
  #define GPIO_LINE_IN      2
  #define GPIO_LINE_OUT     3
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_RADXA

#elif defined(BOARD_starfive)
  #define GPIO_CHIP         "/dev/gpiochip0"
  #define GPIO_BANK         0
  #define GPIO_BANK_MULT    0
  #define GPIO_LINE_IN      60
  #define GPIO_LINE_OUT     61
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_STARFIVE

#elif defined(BOARD_mangopi)
  #define GPIO_CHIP         "/dev/gpiochip0"
  #define GPIO_BANK         1
  #define GPIO_BANK_MULT    32
  #define GPIO_LINE_IN      3
  #define GPIO_LINE_OUT     4
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_MANGOPI

#elif defined(BOARD_rockpi4)
  #define GPIO_CHIP         "/dev/gpiochip4"
  #define GPIO_BANK         0
  #define GPIO_BANK_MULT    0
  #define GPIO_LINE_IN      6
  #define GPIO_LINE_OUT     7
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_ROCKPI4

#elif defined(BOARD_repkapi4)
  #define GPIO_CHIP         "/dev/gpiochip1"
  #define GPIO_BANK         6
  #define GPIO_BANK_MULT    32
  #define GPIO_LINE_IN      13
  #define GPIO_LINE_OUT     12
  #define GPIO_EDGE         GPIOD_LINE_EDGE_BOTH
  #define GPIO_CONSUMER     CONSUMER_REPKAPI4

#else
  #error "No BOARD_xxx defined. Use -DBOARD_lichee or similar in CFLAGS"
#endif

#define GPIO_OFFSET_IN   (GPIO_BANK * GPIO_BANK_MULT + GPIO_LINE_IN)
#define GPIO_OFFSET_OUT  (GPIO_BANK * GPIO_BANK_MULT + GPIO_LINE_OUT)

#endif // GPIO_CONFIG_H
