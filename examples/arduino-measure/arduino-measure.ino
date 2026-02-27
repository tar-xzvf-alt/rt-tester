// Основной файл arduino-example.ino
#include "config.h"
#include "globals.h"
#include "measurement.h"
#include "statistics.h"
#include <ArduinoJson.h>

void setup() {
  Serial.begin(115200);
  initPins();                     // из measurement.h
  interrupts();
  randomSeed(analogRead(0));
  sessionId = random(100000, 999999);
}

void loop() {
  checkSerialCommands();          // обработка команд (определена ниже)

  if (sendDataFlag && (groupIndex == NUM_GROUPS)) {
    sendAveragedJsonData();       // из statistics.h
    sendDataFlag = false;
    collectingData = false;
  }

  if (collectingData && (groupIndex < NUM_GROUPS)) {
    // Отправка импульса на Lichee
    t_start = micros();
    active = !active;
    if (active) {
      *portOutputRegisterPin7 |= pin7Mask;
    } else {
      *portOutputRegisterPin7 &= ~pin7Mask;
    }
    delayMicroseconds(DELAY_MICROSECONDS);

    // Если группа завершена – обработать статистику
    if (measurementInGroup >= GROUP_SIZE) {
      processGroupStatistics();   // из measurement.h
      groupIndex++;
      measurementInGroup = 0;

      if (groupIndex == NUM_GROUPS) {
        Serial.println(F("{\"status\":\"data_ready\",\"message\":\"All groups collected\"}"));
        collectingData = false;
      }
    }
  }
}

// Обработка команд из Serial (оставлена в основном файле)
void checkSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "START") {
      groupIndex = 0;
      measurementInGroup = 0;
      sendDataFlag = false;
      collectingData = true;
      Serial.println(F("{\"status\":\"started\",\"message\":\"Measurement started\"}"));
    }
    else if (command == "SEND") {
      if (groupIndex == NUM_GROUPS) {
        Serial.println(F("{\"status\":\"sending\",\"message\":\"Preparing to send averaged data\"}"));
        sendDataFlag = true;
      } else {
        Serial.println(F("{\"status\":\"error\",\"message\":\"Data not ready yet\"}"));
      }
    }
    else if (command == "STATUS") {
      StaticJsonDocument<200> doc;
      doc["status"] = "status_report";
      doc["groups_collected"] = groupIndex;
      doc["measurements_in_current_group"] = measurementInGroup;
      doc["session_id"] = sessionId;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "RESET") {
      groupIndex = 0;
      measurementInGroup = 0;
      sendDataFlag = false;
      collectingData = false;
      Serial.println(F("{\"status\":\"reset\",\"message\":\"Measurements reset\"}"));
    }
    else {
      Serial.print(F("{\"status\":\"error\",\"message\":\"Unknown command: "));
      Serial.print(command);
      Serial.println(F("\"}"));
    }
  }
}
