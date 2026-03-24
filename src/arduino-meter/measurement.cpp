#include "measurement.h"
#include <ArduinoJson.h>

// Global variables definitions
volatile bool active = false;
volatile unsigned long t_start = 0;
volatile int groupIndex = 0;
volatile int measurementInGroup = 0;
volatile bool collectingData = false;
volatile unsigned long sessionId = 0;
volatile int maxGroups = 0;

volatile unsigned long lastMeasurementTime = 0;

volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

volatile int currentGroupLatency[GROUP_SIZE];

void initPins() {
  pinMode(PIN_OUT, OUTPUT);
  portOutputRegisterPin7 = portOutputRegister(digitalPinToPort(PIN_OUT));
  pin7Mask = digitalPinToBitMask(PIN_OUT);

  pinMode(PIN_IN, INPUT);
  portInputRegisterPin20 = portInputRegister(digitalPinToPort(PIN_IN));
  pin20Mask = digitalPinToBitMask(PIN_IN);

  attachInterrupt(digitalPinToInterrupt(PIN_IN), onResponse, CHANGE);
}

void onResponse() {
  if (collectingData && measurementInGroup < GROUP_SIZE) {
    unsigned long currentTime = micros();
    unsigned long latency = currentTime - t_start;

    currentGroupLatency[measurementInGroup] = latency;
    measurementInGroup++;
  }
}

void sendGroupData() {
  if (GROUP_SIZE == 0) return;

  const int WORST_COUNT = 25;
  unsigned long worstLatencies[WORST_COUNT] = {0};
  
  // Find 25 worst latency values
  for (int i = 0; i < GROUP_SIZE; i++) {
    unsigned long currentLatency = currentGroupLatency[i];
    
    for (int j = 0; j < WORST_COUNT; j++) {
      if (currentLatency > worstLatencies[j]) {
        // Shift smaller values to the right
        for (int k = WORST_COUNT - 1; k > j; k--) {
          worstLatencies[k] = worstLatencies[k-1];
        }
        worstLatencies[j] = currentLatency;
        break;
      }
    }
  }
  
  // Calculate statistics for worst latency values
  unsigned long sumLatency = 0;
  unsigned long minLatency = worstLatencies[WORST_COUNT-1];
  unsigned long maxLatency = worstLatencies[0];
  
  for (int i = 0; i < WORST_COUNT; i++) {
    sumLatency += worstLatencies[i];
  }
  
  float avgLatency = (float)sumLatency / WORST_COUNT;
  
  
  float sumSquaredDiff = 0;
  for (int i = 0; i < GROUP_SIZE; i++) {
    float diff = currentGroupLatency[i] - avgLatency;
    sumSquaredDiff += diff * diff;
  }
  float rmsJitter = sqrt(sumSquaredDiff / GROUP_SIZE);
  
  // Form JSON
  StaticJsonDocument<512> doc;
  
  // Use session_id received from PC
  doc["session_id"] = sessionId;
  doc["group_index"] = groupIndex;
  doc["timestamp"] = millis();
  doc["avg_latency_us"] = avgLatency;
  doc["min_latency_us"] = minLatency;
  doc["max_latency_us"] = maxLatency;
  doc["jitter_us"] = rmsJitter;
  doc["worst_count"] = WORST_COUNT;
  
  // Add array of worst values
  JsonArray worstArray = doc.createNestedArray("worst_latencies_us");
  for (int i = 0; i < WORST_COUNT; i++) {
    worstArray.add(worstLatencies[i]);
  }
  
  JsonObject params = doc.createNestedObject("parameters");
  params["delay_us"] = MEASUREMENT_INTERVAL_US;
  params["measurements_per_group"] = GROUP_SIZE;
  params["max_groups"] = maxGroups;
  
  serializeJson(doc, Serial);
  Serial.println();
}
