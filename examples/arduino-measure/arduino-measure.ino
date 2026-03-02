#include <ArduinoJson.h>
#include "config.h"
#include "globals.h"
#include "measurement.h"

void setup() {
  Serial.begin(115200);
  initPins();
  interrupts();
  randomSeed(analogRead(0));
  sessionId = random(100000, 999999);
  
  Serial.println(F("{\"status\":\"ready\",\"message\":\"Continuous measurement mode\"}"));
}

void loop() {
  // Обработка команд из Serial (оставлена в основном файле)
  checkSerialCommands();

  if (collectingData) {
    // Отправка импульса на Lichee
    t_start = micros();
    active = !active;
    if (active) {
      *portOutputRegisterPin7 |= pin7Mask;
    } else {
      *portOutputRegisterPin7 &= ~pin7Mask;
    }
    delayMicroseconds(DELAY_MICROSECONDS);

    // Если группа завершена – отправляем статистику
    if (measurementInGroup >= GROUP_SIZE) {
      sendGroupStatistics();
      groupIndex++;
      measurementInGroup = 0;
      
      // Не останавливаемся, продолжаем бесконечно
      if (groupIndex % 10 == 0) {
        // Можно выводить прогресс раз в 10 групп
        Serial.print(F("{\"progress\":\""));
        Serial.print(groupIndex);
        Serial.println(F("\"}"));
      }
    }
  }
}

// Обработка команд из Serial
void checkSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command == "START") {
      groupIndex = 0;
      measurementInGroup = 0;
      collectingData = true;
      
      StaticJsonDocument<128> doc;
      doc["status"] = "started";
      doc["session_id"] = sessionId;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "STOP") {
      collectingData = false;
      
      StaticJsonDocument<64> doc;
      doc["status"] = "stopped";
      doc["groups_collected"] = groupIndex;
      serializeJson(doc, Serial);
      Serial.println();
    }
    else if (command == "STATUS") {
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
      groupIndex = 0;
      measurementInGroup = 0;
      collectingData = false;
      
      Serial.println(F("{\"status\":\"reset\"}"));
    }
  }
}
