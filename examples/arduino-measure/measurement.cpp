#include "measurement.h"
#include "config.h"

// Определения глобальных переменных
volatile bool active = false;
volatile unsigned long t_start = 0;
volatile uint8_t groupIndex = 0;
volatile int measurementInGroup = 0;
volatile bool collectingData = false;
volatile bool sendDataFlag = false;
volatile unsigned long sessionId = 0;

volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

float groupAvgLatency[NUM_GROUPS];
float groupMinLatency[NUM_GROUPS];
float groupMaxLatency[NUM_GROUPS];
float groupAvgJitter[NUM_GROUPS];

volatile unsigned long currentGroupLatency[GROUP_SIZE];
volatile unsigned long currentGroupJitter[GROUP_SIZE];

// Реализация функций
void initPins() {
  pinMode(PIN_OUT, OUTPUT);
  portOutputRegisterPin7 = portOutputRegister(digitalPinToPort(PIN_OUT));
  pin7Mask = digitalPinToBitMask(PIN_OUT);

  pinMode(PIN_IN, INPUT);
  portInputRegisterPin20 = portInputRegister(digitalPinToPort(PIN_IN));
  pin20Mask = digitalPinToBitMask(PIN_IN);

  attachInterrupt(digitalPinToInterrupt(PIN_IN), onResponse, FALLING);
}

void onResponse() {
  if (collectingData && groupIndex < NUM_GROUPS && measurementInGroup < GROUP_SIZE) {
    unsigned long currentTime = micros();
    unsigned long latency = currentTime - t_start;

    unsigned long jitter = 0;
    if (measurementInGroup > 0) {
      jitter = abs((long)(latency - currentGroupLatency[measurementInGroup-1]));
    }

    currentGroupLatency[measurementInGroup] = latency;
    currentGroupJitter[measurementInGroup] = jitter;
    measurementInGroup++;
  }
}

void processGroupStatistics() {
  if (GROUP_SIZE == 0) return;

  unsigned long minLatency = currentGroupLatency[0];
  unsigned long maxLatency = currentGroupLatency[0];
  unsigned long sumLatency = currentGroupLatency[0];
  unsigned long sumJitter = currentGroupJitter[0];

  for (int i = 1; i < GROUP_SIZE; i++) {
    unsigned long latency = currentGroupLatency[i];
    if (latency < minLatency) minLatency = latency;
    if (latency > maxLatency) maxLatency = latency;
    sumLatency += latency;
    sumJitter += currentGroupJitter[i];
  }

  groupAvgLatency[groupIndex] = (float)sumLatency / GROUP_SIZE;
  groupMinLatency[groupIndex] = (float)minLatency;
  groupMaxLatency[groupIndex] = (float)maxLatency;
  groupAvgJitter[groupIndex] = (float)sumJitter / (GROUP_SIZE - 1);
}
