#include "statistics.h"
#include <ArduinoJson.h>

void sendAveragedJsonData() {
  DynamicJsonDocument doc(3072);

  doc["session_id"] = sessionId;
  doc["groups_count"] = NUM_GROUPS;
  doc["measurements_per_group"] = GROUP_SIZE;
  doc["total_measurements"] = NUM_GROUPS * GROUP_SIZE;
  doc["timestamp"] = millis();
  doc["device"] = "Arduino Mega";

  JsonArray avgLatencyArray = doc.createNestedArray("avg_latency_us");
  JsonArray minLatencyArray = doc.createNestedArray("min_latency_us");
  JsonArray maxLatencyArray = doc.createNestedArray("max_latency_us");
  JsonArray avgJitterArray = doc.createNestedArray("avg_jitter_us");

  float totalAvgLatency = 0;
  float totalMinLatency = groupMinLatency[0];
  float totalMaxLatency = groupMaxLatency[0];
  float totalAvgJitter = 0;

  for (int i = 0; i < NUM_GROUPS; i++) {
    avgLatencyArray.add(groupAvgLatency[i]);
    minLatencyArray.add(groupMinLatency[i]);
    maxLatencyArray.add(groupMaxLatency[i]);
    avgJitterArray.add(groupAvgJitter[i]);

    totalAvgLatency += groupAvgLatency[i];
    totalAvgJitter += groupAvgJitter[i];

    if (groupMinLatency[i] < totalMinLatency) totalMinLatency = groupMinLatency[i];
    if (groupMaxLatency[i] > totalMaxLatency) totalMaxLatency = groupMaxLatency[i];
  }

  totalAvgLatency /= NUM_GROUPS;
  totalAvgJitter /= NUM_GROUPS;

  JsonObject stats = doc.createNestedObject("statistics");
  JsonObject latencyStats = stats.createNestedObject("latency");
  latencyStats["overall_avg_us"] = totalAvgLatency;
  latencyStats["overall_min_us"] = totalMinLatency;
  latencyStats["overall_max_us"] = totalMaxLatency;
  latencyStats["variation_us"] = totalMaxLatency - totalMinLatency;

  JsonObject jitterStats = stats.createNestedObject("jitter");
  jitterStats["overall_avg_us"] = totalAvgJitter;

  JsonObject params = doc.createNestedObject("parameters");
  params["delay_between_pulses_us"] = DELAY_MICROSECONDS;
  params["groups"] = NUM_GROUPS;
  params["measurements_per_group"] = GROUP_SIZE;

  serializeJson(doc, Serial);
  Serial.println();
}
