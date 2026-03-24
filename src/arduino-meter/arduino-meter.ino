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
    
    // NEW: Timer-based measurement instead of delayMicroseconds
    unsigned long now = micros();
    if (now - lastMeasurementTime >= MEASUREMENT_INTERVAL_US) {
      lastMeasurementTime = now;
      
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
      
      StaticJsonDocument<128> doc;
      DeserializationError error = deserializeJson(doc, params);
      
      if (!error) {
        unsigned long new_session_id = doc["session_id"].as<unsigned long>();
        int groups = doc["groups"] | 0;

        if (new_session_id != 0) {
          startMeasurement(new_session_id, groups);
        } else {
          randomSeed(analogRead(0));
          startMeasurement(random(100000, 999999), groups);
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
      collectingData = false;
      maxGroups = 0;
      sessionId = 0;
      
      Serial.println(F("{\"status\":\"reset\"}"));
    }
  }
}

void startMeasurement(unsigned long new_session_id, int groups) {
  sessionId = new_session_id;
  groupIndex = 0;
  measurementInGroup = 0;
  collectingData = true;
  maxGroups = groups;
  lastMeasurementTime = micros();  // Initialize timer
  
  StaticJsonDocument<128> doc;
  doc["status"] = "started";
  doc["session_id"] = sessionId;
  doc["max_groups"] = maxGroups;
  if (maxGroups > 0) {
    doc["auto_stop"] = true;
  }
  serializeJson(doc, Serial);
  Serial.println();
}
