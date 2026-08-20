# Arduino Meter

[Код для Arduino](../../src/arduino-meter)

Код на Arduino C измеряет задержки в системе связи с SoC. Он отправляет импульсы через пин 7 и принимает ответные сигналы через пин 20 (на Arduino Mega). Для каждого импульса измеряется **время отклика системы** (разница между отправкой сигнала на SoC и получением ответа).

## Параметры измерения (настраиваются через START команду)

- `measurements_per_group` — количество измерений в группе (1-1500, по умолчанию 1500)
- `worst_count` — количество худших задержек (авто 5% от `measurements_per_group`)
- `measurement_interval_us` — интервал между измерениями (мкс, по умолчанию 300)
- `response_timeout_us` — deadline ожидания ответа на один импульс

Firmware ограничивает `response_timeout_us` диапазоном 1-65535 µs.

## Подготовка Firmware

Firmware предназначен для Arduino Mega 2560 и находится в
`src/arduino-meter/arduino-meter.ino`. Он требует Arduino AVR core и библиотеку
ArduinoJson. Репозиторий пока не содержит автоматизированного build/upload
script, поэтому используйте Arduino IDE или настроенный Arduino CLI, выберите
board Mega 2560 и serial port, затем убедитесь, что receiver обнаруживает порт и
отвечает на status/START protocol до подключения GPIO стенда.

## Режим работы

- Arduino начинает следующий request не раньше `measurement_interval_us` и
  только после response или истечения `response_timeout_us`; одновременно
  существует не более одного outstanding request
- Прерывание `CHANGE` на входном пине фиксирует момент получения ответа от SoC
- В каждый момент ожидается ответ только на один request; отсутствие ответа до
  `response_timeout_us` увеличивает timeout counter и не блокирует всю группу
- По команде `START {"session_id":123,"groups":100,"worst_count":75,"interval_us":300,"measurements_per_group":1500,"response_timeout_us":10000}` начинается сбор данных
- После заполнения группы (заданного числа измерений) формируется JSON-пакет со статистикой
- Данные отправляются на ПК через Serial

После каждой завершенной группы firmware формирует и отправляет отдельный JSON.
После N групп session автоматически останавливается.

Управление осуществляется через последовательный порт командами START и STOP. Каждая сессия измерений имеет уникальный идентификатор для последующего анализа данных на компьютере.

Supervised stand runner открывает serial и выполняет reset/STOP до запуска
controller. После readiness barrier он запускает paused controller, разрешает
обработку GPIO через `SIGUSR1` и только затем разрешает receiver отправить START.
Поэтому GPIO-переходы при reset и настройке line не входят в trace sequence
измерительной сессии.

## JSON формат данных о группе измерений

```json
{
  "session_id": 123456789,
  "group_index": 5,
  "timestamp": 12345678,
  "mean_latency_us": 325.6,
  "avg_latency_us": 312.4,
  "min_latency_us": 223,
  "max_latency_us": 487,
  "jitter_us": 12.34,
  "requests_sent": 1500,
  "responses_received": 1499,
  "timeouts": 1,
  "worst_count": 75,
  "worst_latencies_us": [487, 476, ...],
  "parameters": {
    "interval_us": 300,
    "measurements_per_group": 1500,
    "max_groups": 10,
    "response_timeout_us": 10000
  }
}
```
