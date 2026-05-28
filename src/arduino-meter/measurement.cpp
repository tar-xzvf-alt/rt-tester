#include "measurement.h"
#include <ArduinoJson.h>

// Global variables definitions
volatile bool active = false;
volatile unsigned long t_start = 0;
volatile int groupIndex = 0;
volatile int measurementInGroup = 0;
volatile int sendingInGroup = 0;
volatile bool collectingData = false;
volatile unsigned long sessionId = 0;
volatile int maxGroups = 0;

volatile unsigned long lastMeasurementTime = 0;

// Measurement parameters
volatile int worstCount = DEFAULT_WORST_COUNT;
volatile unsigned long measurementIntervalUs = DEFAULT_MEASUREMENT_INTERVAL_US;
volatile int measurementsPerGroup = GROUP_SIZE;

volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

volatile unsigned long currentGroupLatency[GROUP_SIZE];

void initPins() {
  pinMode(PIN_OUT, OUTPUT);
  portOutputRegisterPin7 = portOutputRegister(digitalPinToPort(PIN_OUT));
  pin7Mask = digitalPinToBitMask(PIN_OUT);

  pinMode(PIN_IN, INPUT_PULLUP);
  portInputRegisterPin20 = portInputRegister(digitalPinToPort(PIN_IN));
  pin20Mask = digitalPinToBitMask(PIN_IN);

  attachInterrupt(digitalPinToInterrupt(PIN_IN), onResponse, CHANGE);
}

void onResponse() {
  if (collectingData && measurementInGroup < measurementsPerGroup) {
    unsigned long currentTime = micros();
    unsigned long latency = currentTime - t_start;

    currentGroupLatency[measurementInGroup] = latency;
    measurementInGroup++;
  }
}

void sendGroupData() {
  int msrPerGroup = measurementsPerGroup;
  if (msrPerGroup == 0) msrPerGroup = GROUP_SIZE;

  int actualWorstCount = worstCount;
  if (actualWorstCount > msrPerGroup) {
    actualWorstCount = msrPerGroup;
  }
  if (actualWorstCount < 1) {
    actualWorstCount = 1;
  }

  unsigned long worstLatencies[actualWorstCount];
  for (int i = 0; i < actualWorstCount; i++) {
    worstLatencies[i] = 0;
  }
  
  // Find N worst latency values
  for (int i = 0; i < msrPerGroup; i++) {
    unsigned long currentLatency = currentGroupLatency[i];
    
    for (int j = 0; j < actualWorstCount; j++) {
      if (currentLatency > worstLatencies[j]) {
        for (int k = actualWorstCount - 1; k > j; k--) {
          worstLatencies[k] = worstLatencies[k-1];
        }
        worstLatencies[j] = currentLatency;
        break;
      }
    }
  }
  
  // Calculate statistics for worst latency values
  unsigned long sumLatency = 0;
  unsigned long minLatency = worstLatencies[actualWorstCount-1];
  unsigned long maxLatency = worstLatencies[0];
  
  for (int i = 0; i < actualWorstCount; i++) {
    sumLatency += worstLatencies[i];
  }
  
  float avgLatency = (float)sumLatency / actualWorstCount;
  
  // Calculate mean latency for jitter
  unsigned long sumAllLatency = 0;
  for (int i = 0; i < msrPerGroup; i++) {
    sumAllLatency += currentGroupLatency[i];
  }
  float meanLatency = (float)sumAllLatency / msrPerGroup;
  
  // Calculate RMS jitter (standard deviation)
  float sumSquaredDiff = 0;
  for (int i = 0; i < msrPerGroup; i++) {
    float diff = currentGroupLatency[i] - meanLatency;
    sumSquaredDiff += diff * diff;
  }
  float rmsJitter = sqrt(sumSquaredDiff / msrPerGroup);
  
  // Form JSON
  StaticJsonDocument<1024> doc;  // Increased size for variable worst count
  
  doc["session_id"] = sessionId;
  doc["group_index"] = groupIndex;
  doc["timestamp"] = millis();
  doc["mean_latency_us"] = meanLatency;
  doc["avg_latency_us"] = avgLatency;
  doc["min_latency_us"] = minLatency;
  doc["max_latency_us"] = maxLatency;
  doc["jitter_us"] = rmsJitter;
  doc["worst_count"] = actualWorstCount;
  
  JsonArray worstArray = doc.createNestedArray("worst_latencies_us");
  for (int i = 0; i < actualWorstCount; i++) {
    worstArray.add(worstLatencies[i]);
  }
  
  JsonObject params = doc.createNestedObject("parameters");
  params["interval_us"] = measurementIntervalUs;
  params["measurements_per_group"] = msrPerGroup;
  params["max_groups"] = maxGroups;
  
  serializeJson(doc, Serial);
  Serial.println();
}
