# Arduino meter

[Русский](../ru/hardware/arduino.md)

The Arduino Mega 2560 sends a request transition on **D7** and receives the target
response on **D20**. It times the elapsed request/response interval in
microseconds. This includes the physical GPIO path and target handling, not just
Linux scheduler wake-up latency. Firmware belongs to this repository under
`src/arduino-meter/`.

## Firmware and electrical preparation

Open `src/arduino-meter/arduino-meter.ino` using Arduino IDE or a configured
Arduino CLI. Install Arduino AVR core and ArduinoJson, select Mega 2560 and the
actual serial port, then build/upload. There is no repository-provided automated
build/upload script. Firmware is not included as an installed target program in
the PC tools RPM. Record firmware revision and library/tool versions.

Mega GPIO uses 5 V logic; VisionFive 2 GPIO uses 3.3 V logic. Do not directly
drive the target input with a 5 V request. Use suitable, direction-correct level
adaptation and ensure the return signal meets the Arduino input thresholds.
Firmware configures D20 as `INPUT_PULLUP`: account for that pull-up in the
electrical design so it cannot expose the target output to unsafe voltage.
Connect a common GND. GPIO chip/line offsets are not physical header pin numbers.
Use the [complete wiring walkthrough](../usage/standalone-gpio-walkthrough.md)
and verify the board/adapter datasheets.

## Measurement parameters

| Parameter | Meaning |
|---|---|
| `measurements_per_group` | Requests per group, 1–1500; default 1500 |
| `worst_count` | Number of retained largest response latencies; receiver normally chooses 5% |
| `interval_us` | Minimum request interval; default 300 µs |
| `response_timeout_us` | Deadline for one response, clamped by firmware to 1–65535 µs |
| `groups` | Automatic session stop count |

Arduino waits until both the minimum interval has elapsed and the previous
request has responded or timed out. At most one request is outstanding. The
D20 `CHANGE` interrupt records a response only while one is pending. A timeout
increments a counter; it is not a retry with a new timestamp and is not a latency
sample. Groups are based on attempted requests, so received sample counts can
be lower than the requested group size.

The receiver sends protocol commands over serial, for example:

```text
START {"session_id":123,"groups":100,"worst_count":75,"interval_us":300,"measurements_per_group":1500,"response_timeout_us":10000}
STOP
```

Every completed group produces JSON. The finite session stops after its configured
group count. Before connecting a full stand, confirm serial discovery and command
handling with the prepared firmware. Let the runner own serial/reset/START during
measurement; do not open another serial application simultaneously.

## Group JSON

Illustrative valid JSON, showing three retained samples:

```json
{
  "session_id": 123456789,
  "group_index": 5,
  "timestamp": 12345678,
  "mean_latency_us": 250.0,
  "avg_latency_us": 479.67,
  "min_latency_us": 476,
  "max_latency_us": 487,
  "jitter_us": 12.34,
  "requests_sent": 1500,
  "responses_received": 1499,
  "timeouts": 1,
  "worst_count": 3,
  "worst_latencies_us": [487, 476, 476],
  "parameters": {
    "interval_us": 300,
    "measurements_per_group": 1500,
    "max_groups": 10,
    "response_timeout_us": 10000
  }
}
```

This illustrates fields, not a recorded measurement. `timestamp` is Arduino
`millis()`. `mean_latency_us` is whole-received-group mean; `avg_latency_us` and
`min_latency_us` refer to the retained worst tail; `max_latency_us` is the largest
received response. `jitter_us` is population standard deviation around the
whole-group mean, not standard deviation of the tail or max-minus-min. See
[statistics](../reference/measurement-statistics.md) and
[SQLite storage](../reference/sqlite-schema.md) for what survives in the database.

For supervised runs, the runner resets/stops Arduino before controller startup.
It resumes the paused controller after readiness, then permits receiver START.
This keeps reset/setup transitions out of the measurement trace sequence.
