#include "measurement.h"
#include <ArduinoJson.h>
#include <math.h>

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
volatile unsigned long currentGroupJitter[GROUP_SIZE];  // больше не используется для расчёта, но оставим для совместимости

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

    // Сохраняем задержку
    currentGroupLatency[measurementInGroup] = latency;
    
    // Для обратной совместимости можно не заполнять jitter массив
    // или заполнять чем-то, но он больше не используется в расчётах
    
    measurementInGroup++;
  }
}

// Функция для поиска N наибольших значений
void findNLargest(unsigned long* source, int sourceSize, 
                  unsigned long* dest, int destSize) {
  // Инициализируем массив назначения нулями
  for (int i = 0; i < destSize; i++) {
    dest[i] = 0;
  }
  
  // Проходим по всем исходным значениям
  for (int i = 0; i < sourceSize; i++) {
    unsigned long currentValue = source[i];
    //Serial.print("\nЗадержка №");Serial.print(i);Serial.print(" равна ");Serial.print(currentValue);

    
    // Вставляем в dest, если значение больше минимального в нём
    for (int j = 0; j < destSize; j++) {
      if (currentValue > dest[j]) {
        // Сдвигаем меньшие значения вправо
        for (int k = destSize - 1; k > j; k--) {
          dest[k] = dest[k-1];
        }
        dest[j] = currentValue;
        break;
      }
    }
  }
}

// Функция для вычисления стандартного отклонения (джеттер)
float calculateJitter() {
  if (GROUP_SIZE <= 1) return 0.0;
  
  // 1. Вычисляем среднее арифметическое всех задержек в группе
  unsigned long sumLatency = 0;
  for (int i = 0; i < GROUP_SIZE; i++) {
    sumLatency += currentGroupLatency[i];
  }
  float meanLatency = (float)sumLatency / GROUP_SIZE;
  
  // 2. Вычисляем сумму квадратов отклонений от среднего
  double sumSquaredDiff = 0;  // используем double для большей точности
  for (int i = 0; i < GROUP_SIZE; i++) {
    double diff = (double)currentGroupLatency[i] - meanLatency;
    sumSquaredDiff += diff * diff;
  }
  
  // 3. Стандартное отклонение (джеттер)
  // Для генеральной совокупности делим на GROUP_SIZE
  // Для выборки обычно делят на GROUP_SIZE-1, но здесь вся группа - это и есть наша совокупность
  float variance = sumSquaredDiff / GROUP_SIZE;
  float jitter = sqrt(variance);
  
  return jitter;
}

void sendGroupData() {
    if (GROUP_SIZE == 0) return;
        
    // Массив для хранения WORST_COUNT самых больших значений latency
    unsigned long worstLatency[WORST_COUNT];
    
    // Находим 25 худших задержек
    findNLargest((unsigned long*)currentGroupLatency, GROUP_SIZE, 
                 worstLatency, WORST_COUNT);
    
    // Вычисляем джиттер по стандартной формуле (стандартное отклонение)
    float jitter = calculateJitter();

    //Serial.print("\n Джиттер группы: ");Serial.print(jitter);
    
    // Отправляем JSON
    StaticJsonDocument<1024> doc;
    
    doc["session_id"] = sessionId;
    doc["group_index"] = groupIndex;
    doc["timestamp"] = millis();
    doc["jitter_us"] = jitter; 
    doc["total_measurements"] = GROUP_SIZE;
    doc["worst_count"] = WORST_COUNT;
    
    // Добавляем массив худших задержек
    JsonArray worstLatencies = doc.createNestedArray("worst_latencies_us");
    for (int i = 0; i < WORST_COUNT; i++) {
        worstLatencies.add(worstLatency[i]);
        //Serial.print("\nХудшая задержка ранга ");Serial.print(i);Serial.print(" равна ");Serial.print(worstLatency[i]);
    }
    
    JsonObject params = doc.createNestedObject("parameters");
    params["delay_us"] = DELAY_MICROSECONDS;
    params["measurements_per_group"] = GROUP_SIZE;
    
    serializeJson(doc, Serial);
    Serial.println();
}
