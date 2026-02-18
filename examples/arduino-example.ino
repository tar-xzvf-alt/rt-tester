#include <ArduinoJson.h>

const int PIN_OUT = 7;        // Arduino → Lichee (signal "start")
const int PIN_IN  = 20;       // Lichee → Arduino (response pulse)

const int GROUP_SIZE = 500;       // Number of pulses per group
const int NUM_GROUPS = 50;        // Number of groups

volatile bool active = false;
const unsigned int DELAY_MICROSECONDS = 300;

// Arrays for statistics
float groupAvgLatency[NUM_GROUPS];     // Average latency per group
float groupMinLatency[NUM_GROUPS];     // Minimum latency per group
float groupMaxLatency[NUM_GROUPS];     // Maximum latency per group
float groupAvgJitter[NUM_GROUPS];      // ONLY AVERAGE jitter per group

// Temporary arrays for current group
volatile unsigned long currentGroupLatency[GROUP_SIZE];
volatile unsigned long currentGroupJitter[GROUP_SIZE];

volatile uint8_t groupIndex = 0;            // Current group (0-9)
volatile int measurementInGroup = 0;    // Measurement in current group
volatile unsigned long t_start = 0;

// For synchronization
volatile unsigned long sessionId = 0;
volatile bool sendDataFlag = false;
volatile bool collectingData = false;

// For direct port access
volatile uint8_t* portOutputRegisterPin7;
uint8_t pin7Mask;
volatile uint8_t* portInputRegisterPin20;
uint8_t pin20Mask;

void setup() {
  Serial.begin(115200);
  
  // Initialize direct port access for PIN_OUT (pin 7)
  pinMode(PIN_OUT, OUTPUT);
  portOutputRegisterPin7 = portOutputRegister(digitalPinToPort(PIN_OUT));
  pin7Mask = digitalPinToBitMask(PIN_OUT);
  
  // Initialize direct port access for PIN_IN (pin 20)
  pinMode(PIN_IN, INPUT);
  portInputRegisterPin20 = portInputRegister(digitalPinToPort(PIN_IN));
  pin20Mask = digitalPinToBitMask(PIN_IN);
  
  attachInterrupt(digitalPinToInterrupt(PIN_IN), onResponse, FALLING);
  interrupts();
  
  // Generate unique session ID
  randomSeed(analogRead(0));
  sessionId = random(100000, 999999);
}

void loop() {
  // Check commands from PC
  checkSerialCommands();

  // If flag is set, send data
  if (sendDataFlag && (groupIndex == NUM_GROUPS)) {
    sendAveragedJsonData();
    sendDataFlag = false;
    collectingData = false;
  }
  
  // Send pulses if collecting data
  if (collectingData && (groupIndex < NUM_GROUPS)) {
    // Send pulse to Lichee
    t_start = micros();
    active = !active;
    if (active) {
      *portOutputRegisterPin7 |= pin7Mask;   // Set HIGH
    } else {
      *portOutputRegisterPin7 &= ~pin7Mask;  // Set LOW
    }
    delayMicroseconds(DELAY_MICROSECONDS);
    
    // If group is complete, process statistics
    if (measurementInGroup >= GROUP_SIZE) {
      processGroupStatistics();
      groupIndex++;      
      measurementInGroup = 0;

      if (groupIndex == NUM_GROUPS) {
        Serial.println(F("{\"status\":\"data_ready\",\"message\":\"All groups collected\"}"));
        collectingData = false;
      }
    }
  }
}

void onResponse() {
  if (collectingData && groupIndex < NUM_GROUPS && measurementInGroup < GROUP_SIZE) {
    unsigned long currentTime = micros();
    
    // Calculate latency
    unsigned long latency = currentTime - t_start;
    
    // Calculate jitter (difference between current and previous latency)
    unsigned long jitter = 0;
    if (measurementInGroup > 0) {
      jitter = abs((long)(latency - currentGroupLatency[measurementInGroup-1]));
    }
  
    currentGroupLatency[measurementInGroup] = latency;
    currentGroupJitter[measurementInGroup] = jitter;
    measurementInGroup++;
  }
}

void processGroupStatistics() {
  if (GROUP_SIZE == 0) return;
  
  // For latency calculate min, max and average
  unsigned long minLatency = currentGroupLatency[0];
  unsigned long maxLatency = currentGroupLatency[0];
  unsigned long sumLatency = currentGroupLatency[0];
  
  // For jitter calculate only average
  unsigned long sumJitter = currentGroupJitter[0];
  
  // Process remaining measurements
  for (int i = 1; i < GROUP_SIZE; i++) {
    unsigned long latency = currentGroupLatency[i];
    
    // Update min/max for latency
    if (latency < minLatency) minLatency = latency;
    if (latency > maxLatency) maxLatency = latency;
    
    sumLatency += latency;
    sumJitter += currentGroupJitter[i];
  }
  
  // Save group statistics
  groupAvgLatency[groupIndex] = (float)sumLatency / GROUP_SIZE;
  groupMinLatency[groupIndex] = (float)minLatency;
  groupMaxLatency[groupIndex] = (float)maxLatency;
  groupAvgJitter[groupIndex] = (float)sumJitter / (GROUP_SIZE-1);
}

void checkSerialCommands() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command == "START") {
      // Start data collection
      groupIndex = 0;
      measurementInGroup = 0;
      sendDataFlag = false;
      collectingData = true;
      
      Serial.println(F("{\"status\":\"started\",\"message\":\"Measurement started 20 groups 50 pulses\"}"));
    }
    else if (command == "SEND") {
      // Request data sending
      if (groupIndex == NUM_GROUPS) {
        Serial.println(F("{\"status\":\"sending\",\"message\":\"Preparing to send averaged data\"}"));
        sendDataFlag = true;
      } else {
        Serial.println(F("{\"status\":\"error\",\"message\":\"Data not ready yet\"}"));
      }
    }
    else if (command == "STATUS") {
      // Send current status
      StaticJsonDocument<200> doc;
      doc["status"] = "status_report";
      doc["groups_collected"] = groupIndex;
      doc["measurements_in_current_group"] = measurementInGroup;
      doc["session_id"] = sessionId;
      serializeJson(doc, Serial);
    }
    else if (command == "RESET") {
      // Reset measurements
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

void sendAveragedJsonData() {
  // Create JSON document
  DynamicJsonDocument doc(3072);
  
  // Basic information
  doc["session_id"] = sessionId;
  doc["groups_count"] = NUM_GROUPS;
  doc["measurements_per_group"] = GROUP_SIZE;
  doc["total_measurements"] = NUM_GROUPS * GROUP_SIZE;
  doc["timestamp"] = millis();
  doc["device"] = "Arduino Mega";
  
  // Arrays with per-group statistics
  JsonArray avgLatencyArray = doc.createNestedArray("avg_latency_us");
  JsonArray minLatencyArray = doc.createNestedArray("min_latency_us");
  JsonArray maxLatencyArray = doc.createNestedArray("max_latency_us");
  JsonArray avgJitterArray = doc.createNestedArray("avg_jitter_us");
  
  // Overall statistics across all groups
  float totalAvgLatency = 0;
  float totalMinLatency = groupMinLatency[0];
  float totalMaxLatency = groupMaxLatency[0];
  float totalAvgJitter = 0;
  
  // Fill arrays and calculate overall statistics
  for (int i = 0; i < NUM_GROUPS; i++) {
    avgLatencyArray.add(groupAvgLatency[i]);
    minLatencyArray.add(groupMinLatency[i]);
    maxLatencyArray.add(groupMaxLatency[i]);
    avgJitterArray.add(groupAvgJitter[i]);
    
    totalAvgLatency += groupAvgLatency[i];
    totalAvgJitter += groupAvgJitter[i];
    
    // Update overall min and max for latency
    if (groupMinLatency[i] < totalMinLatency) totalMinLatency = groupMinLatency[i];
    if (groupMaxLatency[i] > totalMaxLatency) totalMaxLatency = groupMaxLatency[i];
  }
  
  // Average values across all groups
  totalAvgLatency /= NUM_GROUPS;
  totalAvgJitter /= NUM_GROUPS;
  
  // Statistics
  JsonObject stats = doc.createNestedObject("statistics");
  
  JsonObject latencyStats = stats.createNestedObject("latency");
  latencyStats["overall_avg_us"] = totalAvgLatency;
  latencyStats["overall_min_us"] = totalMinLatency;
  latencyStats["overall_max_us"] = totalMaxLatency;
  latencyStats["variation_us"] = totalMaxLatency - totalMinLatency;
  
  JsonObject jitterStats = stats.createNestedObject("jitter");
  jitterStats["overall_avg_us"] = totalAvgJitter;
  
  // Parameter information
  JsonObject params = doc.createNestedObject("parameters");
  params["delay_between_pulses_us"] = DELAY_MICROSECONDS;
  params["groups"] = NUM_GROUPS;
  params["measurements_per_group"] = GROUP_SIZE;

  // Serialize and send
  serializeJson(doc, Serial);
  Serial.println();
}
