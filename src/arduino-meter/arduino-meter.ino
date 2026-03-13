#include <ArduinoJson.h>
#include "config.h"
#include "globals.h"
#include "measurement.h"

int GROUPS_COUNT = 1000; 

void setup() {
  Serial.begin(115200);
  initPins();
  interrupts();
  
  Serial.println(F("{\"status\":\"ready\",\"message\":\"Continuous measurement mode\"}"));
}

void loop() {
  checkSerialCommands();

  if(groupIndex < GROUPS_COUNT)
  {
    if (collectingData) {
      // Send pulse to SoC
      t_start = micros();
      active = !active;
      if (active) {
        *portOutputRegisterPin7 |= pin7Mask;
      } else {
        *portOutputRegisterPin7 &= ~pin7Mask;
      }
      delayMicroseconds(DELAY_MICROSECONDS);
  
      // If group is complete - send statistics
      if (measurementInGroup >= GROUP_SIZE) {
        sendGroupData();
        groupIndex++;
        measurementInGroup = 0;
        
        // Continue indefinitely, don't stop
        if (groupIndex % 10 == 0) {
          // Optional progress output every 10 groups
          Serial.print(F("{\"progress\":\""));
          Serial.print(groupIndex);
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
    
    if (command.startsWith("START")) {
      // Parse groups count if provided
      int spaceIndex = command.indexOf(' ');
      if (spaceIndex > 0) {
        // Extract the number after START
        String groupsStr = command.substring(spaceIndex + 1);
        groupsStr.trim();
        int newGroupsCount = groupsStr.toInt();
        
        // Update GROUPS_COUNT if valid number provided
        if (newGroupsCount > 0) {
          GROUPS_COUNT = newGroupsCount;
        }
      } else {
        // Если число не передано, используем значение по умолчанию (1000)
        GROUPS_COUNT = 1000;
      }
      
      // Generate new session ID
      randomSeed(analogRead(0));
      sessionId = random(100000, 999999);
      
      // Reset counters
      groupIndex = 0;
      measurementInGroup = 0;
      collectingData = true;
      
      // Send confirmation
      StaticJsonDocument<128> doc;
      doc["status"] = "started";
      doc["session_id"] = sessionId;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "STOP") {
      collectingData = false;
      
      // Send confirmation with collected groups count
      StaticJsonDocument<64> doc;
      doc["status"] = "stopped";
      doc["groups_collected"] = groupIndex;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "STATUS") {
      // Report current status
      StaticJsonDocument<128> doc;
      doc["status"] = "status";
      doc["collecting"] = collectingData;
      doc["groups"] = groupIndex;
      doc["measurements"] = measurementInGroup;
      doc["session_id"] = sessionId;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "RESET") {
      // Reset to initial state
      groupIndex = 0;
      measurementInGroup = 0;
      collectingData = false;
      
      Serial.println(F("{\"status\":\"reset\"}"));
    }
  }
}
