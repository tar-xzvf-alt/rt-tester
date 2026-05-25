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
    
    // Timer-based measurement with configurable interval
    unsigned long now = micros();
    if ((now - lastMeasurementTime >= measurementIntervalUs)&&(measurementInGroup==sendingInGroup)||((now - lastMeasurementTime >= measurementIntervalUs*2))) {
      lastMeasurementTime = now;

      sendingInGroup = measurementInGroup+1;
      
      // Send pulse
      t_start = micros();
      active = !active;
      if (active) {
        *portOutputRegisterPin7 |= pin7Mask;
      } else {
        *portOutputRegisterPin7 &= ~pin7Mask;
      }

      // If group is complete - send statistics
      if (measurementInGroup >= GROUP_SIZE) {
        sendGroupData();
        groupIndex++;
        measurementInGroup = 0;
        sendingInGroup = 0;
        
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
      }
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
        unsigned long interval_us = doc["interval_us"] | DEFAULT_MEASUREMENT_INTERVAL_US;
        
        // Validate parameters
        if (worst_cnt < 1) worst_cnt = 1;
        if (worst_cnt > GROUP_SIZE) worst_cnt = GROUP_SIZE;
        if (interval_us < 10) interval_us = 10;  // Minimum 10 microseconds
        
        if (new_session_id != 0) {
          startMeasurement(new_session_id, groups, worst_cnt, interval_us);
        } else {
          randomSeed(micros());
          startMeasurement(random(100000, 999999), groups, worst_cnt, interval_us);
        }
      } else {
        Serial.print(F("{\"error\":\"Invalid parameters: "));
        Serial.print(params);
        Serial.println(F("\"}"));
      }
    }
    else if (command == "STOP") {
      collectingData = false;
      
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
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "RESET") {
      groupIndex = 0;
      measurementInGroup = 0;
      sendingInGroup = 0;
      collectingData = false;
      maxGroups = 0;
      sessionId = 0;
      
      Serial.println(F("{\"status\":\"reset\"}"));
    }
  }
}

void startMeasurement(unsigned long new_session_id, int groups, 
                      int worst_cnt, unsigned long interval_us) {
  noInterrupts();
  
  sessionId = new_session_id;
  groupIndex = 0;
  measurementInGroup = 0;
  sendingInGroup = 0;
  collectingData = true;
  maxGroups = groups;
  worstCount = worst_cnt;
  measurementIntervalUs = interval_us;
  lastMeasurementTime = micros();
  
  interrupts();
  
  StaticJsonDocument<192> doc;
  doc["status"] = "started";
  doc["session_id"] = sessionId;
  doc["max_groups"] = maxGroups;
  doc["worst_count"] = worstCount;
  doc["interval_us"] = measurementIntervalUs;
  if (maxGroups > 0) {
    doc["auto_stop"] = true;
  }
  serializeJson(doc, Serial);
  Serial.println();
}
