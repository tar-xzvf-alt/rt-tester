#include "measurement.h"
#include <ArduinoJson.h>
#include <math.h>

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
    
    measurementInGroup++;
  }
}

// Функция для поиска N наибольших значений
void findNLargest(unsigned long* source, int sourceSize, unsigned long* dest, int destSize) 
{
  for (int i = 0; i < destSize; i++) {
    dest[i] = 0;
  }

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
  
  unsigned long sumLatency = 0;
  for (int i = 0; i < GROUP_SIZE; i++) {
    sumLatency += currentGroupLatency[i];
  }
  float meanLatency = (float)sumLatency / GROUP_SIZE;
  
  double sumSquaredDiff = 0;  // используем double для большей точности
  for (int i = 0; i < GROUP_SIZE; i++) {
    double diff = (double)currentGroupLatency[i] - meanLatency;
    sumSquaredDiff += diff * diff;
  }
  

  float variance = sumSquaredDiff / GROUP_SIZE;
  float jitter = sqrt(variance);
  
  return jitter;
}

void sendGroupData() {
    if (GROUP_SIZE == 0) return;
        
    unsigned long worstLatency[WORST_COUNT];
    
    findNLargest((unsigned long*)currentGroupLatency, GROUP_SIZE, 
                 worstLatency, WORST_COUNT);
    
    float jitter = calculateJitter();

    //Serial.print("\n Джиттер группы: ");Serial.print(jitter);
    
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
