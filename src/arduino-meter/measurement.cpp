#include "measurement.h"
#include <ArduinoJson.h>

// Определения глобальных переменных
volatile bool active = false;
volatile unsigned long t_start = 0;
volatile int groupIndex = 0;
volatile int measurementInGroup = 0;
volatile bool collectingData = false;
volatile unsigned long sessionId = 0;
volatile int maxGroups = 0;

volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

volatile int currentGroupLatency[GROUP_SIZE];
volatile int currentGroupJitter[GROUP_SIZE];

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
  if (collectingData && measurementInGroup < GROUP_SIZE) {
    unsigned long currentTime = micros();
    unsigned long latency = currentTime - t_start;

    unsigned long jitter = 0;
    if (measurementInGroup > 0) {
      if (latency > currentGroupLatency[measurementInGroup-1]) {
        jitter = latency - currentGroupLatency[measurementInGroup-1];
      } else {
        jitter = currentGroupLatency[measurementInGroup-1] - latency;
      }
    }

    currentGroupLatency[measurementInGroup] = latency;
    currentGroupJitter[measurementInGroup] = jitter;
    measurementInGroup++;
  }
}

void sendGroupData() {
  if (GROUP_SIZE == 0) return;

  const int WORST_COUNT = 25;
  unsigned long worstLatencies[WORST_COUNT] = {0};
  int worstIndices[WORST_COUNT] = {-1};
  
  // Находим 25 худших значений latency
  for (int i = 0; i < GROUP_SIZE; i++) {
    unsigned long currentLatency = currentGroupLatency[i];
    
    for (int j = 0; j < WORST_COUNT; j++) {
      if (currentLatency > worstLatencies[j]) {
        // Сдвигаем меньшие значения вправо
        for (int k = WORST_COUNT - 1; k > j; k--) {
          worstLatencies[k] = worstLatencies[k-1];
          worstIndices[k] = worstIndices[k-1];
        }
        worstLatencies[j] = currentLatency;
        worstIndices[j] = i;
        break;
      }
    }
  }
  
  // Вычисляем статистику для худших значений latency
  unsigned long sumLatency = 0;
  unsigned long minLatency = worstLatencies[WORST_COUNT-1];
  unsigned long maxLatency = worstLatencies[0];
  
  for (int i = 0; i < WORST_COUNT; i++) {
    sumLatency += worstLatencies[i];
  }
  
  float avgLatency = (float)sumLatency / WORST_COUNT;
  
  // Джиттер считаем по всем измерениям (не только по худшим)
  unsigned long sumJitter = 0;
  for (int i = 1; i < GROUP_SIZE; i++) {
    sumJitter += currentGroupJitter[i];
  }
  float avgJitter = (float)sumJitter / (GROUP_SIZE - 1);
  
  // Формируем JSON
  StaticJsonDocument<512> doc;
  
  // Используем session_id, полученный с ПК
  doc["session_id"] = sessionId;
  doc["group_index"] = groupIndex;
  doc["timestamp"] = millis();
  doc["avg_latency_us"] = avgLatency;
  doc["min_latency_us"] = minLatency;
  doc["max_latency_us"] = maxLatency;
  doc["jitter_us"] = avgJitter;
  doc["worst_count"] = WORST_COUNT;
  
  // Добавляем массив худших значений
  JsonArray worstArray = doc.createNestedArray("worst_latencies_us");
  for (int i = 0; i < WORST_COUNT; i++) {
    worstArray.add(worstLatencies[i]);
  }
  
  // Параметры измерений
  JsonObject params = doc.createNestedObject("parameters");
  params["delay_us"] = DELAY_MICROSECONDS;
  params["measurements_per_group"] = GROUP_SIZE;
  params["max_groups"] = maxGroups;
  
  serializeJson(doc, Serial);
  Serial.println();
}