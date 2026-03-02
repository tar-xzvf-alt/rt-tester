#include "measurement.h"
#include <ArduinoJson.h>

// Определения глобальных переменных
volatile bool active = false;
volatile unsigned long t_start = 0;
volatile uint8_t groupIndex = 0;
volatile int measurementInGroup = 0;
volatile bool collectingData = false;
volatile unsigned long sessionId = 0;

volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

volatile unsigned long currentGroupLatency[GROUP_SIZE];
volatile unsigned long currentGroupJitter[GROUP_SIZE];

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
      jitter = abs((long)(latency - currentGroupLatency[measurementInGroup-1]));
    }

    currentGroupLatency[measurementInGroup] = latency;
    currentGroupJitter[measurementInGroup] = jitter;
    measurementInGroup++;
  }
}

void sendGroupStatistics() {
    if (GROUP_SIZE == 0) return;
    
    const int WORST_COUNT = 5;  // Количество худших значений для анализа latency
    
    // Массив для хранения WORST_COUNT самых больших значений latency
    unsigned long worstLatency[WORST_COUNT] = {0};
    
    // Проходим по всем измерениям и находим WORST_COUNT самых больших задержек
    for (int i = 0; i < GROUP_SIZE; i++) {
        unsigned long currentLatency = currentGroupLatency[i];
        
        // Вставляем в массив worstLatency, если значение больше минимального в нём
        for (int j = 0; j < WORST_COUNT; j++) {
            if (currentLatency > worstLatency[j]) {
                // Сдвигаем меньшие значения вправо
                for (int k = WORST_COUNT - 1; k > j; k--) {
                    worstLatency[k] = worstLatency[k-1];
                }
                worstLatency[j] = currentLatency;
                break;
            }
        }
    }
    
    // Вычисляем статистику latency по худшим значениям
    unsigned long minLatency = worstLatency[WORST_COUNT-1];
    unsigned long maxLatency = worstLatency[0];
    unsigned long sumLatency = 0;
    
    for (int i = 0; i < WORST_COUNT; i++) {
        sumLatency += worstLatency[i];
        // Обновляем min/max (хотя они уже отсортированы, но для надёжности)
        if (worstLatency[i] < minLatency) minLatency = worstLatency[i];
        if (worstLatency[i] > maxLatency) maxLatency = worstLatency[i];
    }
    
    float avgLatency = (float)sumLatency / WORST_COUNT;
    
    // Вычисляем джиттер по ВСЕМ измерениям (как в оригинале)
    unsigned long sumJitter = 0;
    for (int i = 1; i < GROUP_SIZE; i++) {
        sumJitter += currentGroupJitter[i];
    }
    float avgJitter = (float)sumJitter / (GROUP_SIZE - 1);
    
    // Отправляем JSON
    StaticJsonDocument<384> doc;
    doc["session_id"] = sessionId;
    doc["group_index"] = groupIndex;
    doc["timestamp"] = millis();
    doc["avg_latency_us"] = avgLatency;
    doc["min_latency_us"] = minLatency;
    doc["max_latency_us"] = maxLatency;
    doc["avg_jitter_us"] = avgJitter;
    
    // Добавляем информацию о том, что статистика latency только по худшим
    doc["latency_stats_type"] = "worst_25";
    doc["jitter_stats_type"] = "all_measurements";
    doc["total_measurements"] = GROUP_SIZE;
    doc["worst_count"] = WORST_COUNT;
    
    JsonObject params = doc.createNestedObject("parameters");
    params["delay_us"] = DELAY_MICROSECONDS;
    params["measurements_per_group"] = GROUP_SIZE;
    
    serializeJson(doc, Serial);
    Serial.println();
}
