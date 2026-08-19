#include "measurement.h"
#include <ArduinoJson.h>

// Global variables definitions
volatile bool active = false;
volatile unsigned long t_start = 0;
volatile int groupIndex = 0;
volatile int measurementInGroup = 0;
volatile int sendingInGroup = 0;
volatile int timeoutsInGroup = 0;
volatile bool responsePending = false;
volatile bool collectingData = false;
volatile unsigned long sessionId = 0;
volatile int maxGroups = 0;

volatile unsigned long lastMeasurementTime = 0;

// Measurement parameters
volatile int worstCount = DEFAULT_WORST_COUNT;
volatile unsigned long measurementIntervalUs = DEFAULT_MEASUREMENT_INTERVAL_US;
volatile unsigned long responseTimeoutUs = 10000;
volatile int measurementsPerGroup = GROUP_SIZE;

volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

volatile uint16_t currentGroupLatency[GROUP_SIZE];

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
  if (collectingData && responsePending &&
      measurementInGroup < measurementsPerGroup) {
    unsigned long currentTime = micros();
    unsigned long latency = currentTime - t_start;

    currentGroupLatency[measurementInGroup] =
        latency > UINT16_MAX ? UINT16_MAX : (uint16_t)latency;
    measurementInGroup++;
    responsePending = false;
  }
}

void sendGroupData() {
  int requestedPerGroup = measurementsPerGroup;
  int responsesReceived = measurementInGroup;
  if (requestedPerGroup == 0) requestedPerGroup = GROUP_SIZE;

  int actualWorstCount = worstCount;
  if (actualWorstCount > responsesReceived) {
    actualWorstCount = responsesReceived;
  }
  if (actualWorstCount < 1) {
    actualWorstCount = 1;
  }

  // Calculate whole-group statistics before selecting the tail in-place.
  unsigned long sumAllLatency = 0;
  for (int i = 0; i < responsesReceived; i++) {
    sumAllLatency += currentGroupLatency[i];
  }
  float meanLatency = responsesReceived ?
      (float)sumAllLatency / responsesReceived : 0;
  
  // Calculate RMS jitter (standard deviation)
  float sumSquaredDiff = 0;
  for (int i = 0; i < responsesReceived; i++) {
    float diff = currentGroupLatency[i] - meanLatency;
    sumSquaredDiff += diff * diff;
  }
  float rmsJitter = responsesReceived ?
      sqrt(sumSquaredDiff / responsesReceived) : 0;

  // Put the N largest values at the front of the existing global buffer.
  for (int i = 0; i < actualWorstCount && responsesReceived; i++) {
    int maxIndex = i;
    for (int j = i + 1; j < responsesReceived; j++) {
      if (currentGroupLatency[j] > currentGroupLatency[maxIndex]) {
        maxIndex = j;
      }
    }
    uint16_t tmp = currentGroupLatency[i];
    currentGroupLatency[i] = currentGroupLatency[maxIndex];
    currentGroupLatency[maxIndex] = tmp;
  }

  unsigned long sumLatency = 0;
  for (int i = 0; i < actualWorstCount && responsesReceived; i++) {
    sumLatency += currentGroupLatency[i];
  }
  unsigned long minLatency = responsesReceived ?
      currentGroupLatency[actualWorstCount - 1] : 0;
  unsigned long maxLatency = responsesReceived ? currentGroupLatency[0] : 0;
  float avgLatency = responsesReceived ?
      (float)sumLatency / actualWorstCount : 0;
  
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
  doc["requests_sent"] = sendingInGroup;
  doc["responses_received"] = responsesReceived;
  doc["timeouts"] = timeoutsInGroup;
  
  JsonArray worstArray = doc.createNestedArray("worst_latencies_us");
  for (int i = 0; i < actualWorstCount && responsesReceived; i++) {
    worstArray.add(currentGroupLatency[i]);
  }
  
  JsonObject params = doc.createNestedObject("parameters");
  params["interval_us"] = measurementIntervalUs;
  params["measurements_per_group"] = requestedPerGroup;
  params["max_groups"] = maxGroups;
  params["response_timeout_us"] = responseTimeoutUs;
  
  serializeJson(doc, Serial);
  Serial.println();
}
