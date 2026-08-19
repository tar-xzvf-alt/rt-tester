#include <ArduinoJson.h>
#include "config.h"
#include "globals.h"
#include "measurement.h"

void setup() {
  Serial.begin(115200);
  initPins();
  interrupts();
  
  Serial.println(F("{\"status\":\"ready\",\"message\":\"Continuous measurement mode\"}"));
}

void loop() {
  checkSerialCommands();

  if (collectingData) {
    // Check if group limit reached
    if (maxGroups > 0 && groupIndex >= maxGroups) {
      collectingData = false;

      StaticJsonDocument<64> doc;
      doc["status"] = "auto_stopped";
      doc["session_id"] = sessionId;
      doc["groups_collected"] = groupIndex;
      serializeJson(doc, Serial);
      Serial.println();
      
      return;
    }
    
    // Finish after exactly measurementsPerGroup requests, including timeouts.
    if (sendingInGroup >= measurementsPerGroup && !responsePending) {
      sendGroupData();
      groupIndex++;
      measurementInGroup = 0;
      sendingInGroup = 0;
      timeoutsInGroup = 0;
      // Optional progress output
      if (groupIndex % 10 == 0) {
        Serial.print(F("{\"progress\":\""));
        Serial.print(groupIndex);
        if (maxGroups > 0) {
          Serial.print(F("/"));
          Serial.print(maxGroups);
        }
        Serial.println(F("\"}"));
      }
      return;
    }

    // Do not resend a pending request. A timeout is accounted as a lost sample.
    unsigned long now = micros();
    noInterrupts();
    bool pending = responsePending;
    unsigned long requestStart = t_start;
    interrupts();
    if (pending && now - requestStart >= responseTimeoutUs) {
      noInterrupts();
      if (responsePending && micros() - t_start >= responseTimeoutUs) {
        responsePending = false;
        timeoutsInGroup++;
      }
      interrupts();
    }

    if (!responsePending && sendingInGroup < measurementsPerGroup &&
        now - lastMeasurementTime >= measurementIntervalUs) {
      // Publish pending state and timestamp atomically with the GPIO edge.
      noInterrupts();
      t_start = micros();
      lastMeasurementTime = t_start;
      sendingInGroup++;
      responsePending = true;
      active = !active;
      if (active) {
        *portOutputRegisterPin7 |= pin7Mask;
      } else {
        *portOutputRegisterPin7 &= ~pin7Mask;
      }
      interrupts();
    }
  }
}

void checkSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command.startsWith("START ")) {
      String params = command.substring(6);
      
      StaticJsonDocument<256> doc;  // Increased size for new parameters
      DeserializationError error = deserializeJson(doc, params);
      
      if (!error) {
        unsigned long new_session_id = doc["session_id"].as<unsigned long>();
        int groups = doc["groups"] | 0;
        int worst_cnt = doc["worst_count"] | DEFAULT_WORST_COUNT;
        unsigned long interval_us = doc["interval_us"].is<unsigned long>()
          ? doc["interval_us"].as<unsigned long>()
          : DEFAULT_MEASUREMENT_INTERVAL_US;
        int msr_per_group = doc["measurements_per_group"] | GROUP_SIZE;
        unsigned long response_timeout_us =
          doc["response_timeout_us"] | 10000UL;
        
        // Validate parameters
        if (worst_cnt < 1) worst_cnt = 1;
        if (interval_us < 10) interval_us = 10;
        if (msr_per_group < 1) msr_per_group = 1;
        if (msr_per_group > GROUP_SIZE) msr_per_group = GROUP_SIZE;
        if (response_timeout_us < 1) response_timeout_us = 1;
        if (response_timeout_us > UINT16_MAX) {
          response_timeout_us = UINT16_MAX;
        }
        
        if (new_session_id != 0) {
          startMeasurement(new_session_id, groups, worst_cnt, interval_us,
                           msr_per_group, response_timeout_us);
        } else {
          randomSeed(micros());
          startMeasurement(random(100000, 999999), groups, worst_cnt,
                           interval_us, msr_per_group, response_timeout_us);
        }
      } else {
        Serial.print(F("{\"error\":\"Invalid parameters: "));
        Serial.print(params);
        Serial.println(F("\"}"));
      }
    }
    else if (command == "STOP") {
      collectingData = false;
      responsePending = false;
      
      StaticJsonDocument<64> doc;
      doc["status"] = "stopped";
      doc["session_id"] = sessionId;
      doc["groups_collected"] = groupIndex;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "STATUS") {
      StaticJsonDocument<128> doc;
      doc["status"] = "status";
      doc["session_id"] = sessionId;
      doc["collecting"] = collectingData;
      doc["groups"] = groupIndex;
      doc["max_groups"] = maxGroups;
      doc["measurements"] = measurementInGroup;
      doc["requests"] = sendingInGroup;
      doc["timeouts"] = timeoutsInGroup;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "RESET") {
      groupIndex = 0;
      measurementInGroup = 0;
      sendingInGroup = 0;
      timeoutsInGroup = 0;
      responsePending = false;
      collectingData = false;
      maxGroups = 0;
      sessionId = 0;
      
      Serial.println(F("{\"status\":\"reset\"}"));
    }
  }
}

void startMeasurement(unsigned long new_session_id, int groups,
                      int worst_cnt, unsigned long interval_us,
                      int msr_per_group,
                      unsigned long response_timeout_us) {
  noInterrupts();
  collectingData = false;
  responsePending = false;
  active = false;
  *portOutputRegisterPin7 &= ~pin7Mask;
  sessionId = new_session_id;
  groupIndex = 0;
  measurementInGroup = 0;
  sendingInGroup = 0;
  timeoutsInGroup = 0;
  collectingData = true;
  maxGroups = groups;
  worstCount = worst_cnt;
  measurementIntervalUs = interval_us;
  responseTimeoutUs = response_timeout_us;
  measurementsPerGroup = msr_per_group;
  lastMeasurementTime = micros();
  
  interrupts();
  
  StaticJsonDocument<224> doc;
  doc["status"] = "started";
  doc["session_id"] = sessionId;
  doc["max_groups"] = maxGroups;
  doc["worst_count"] = worstCount;
  doc["interval_us"] = measurementIntervalUs;
  doc["measurements_per_group"] = measurementsPerGroup;
  doc["response_timeout_us"] = responseTimeoutUs;
  if (maxGroups > 0) {
    doc["auto_stop"] = true;
  }
  serializeJson(doc, Serial);
  Serial.println();
}
