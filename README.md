# Тестирование различных плат

[Тестирование Lichee RV Dock](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/lichee_tests.md) 

[Тестирование Radxa rk3588 5b](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/radxa_tests.md) 

[Тестирование Starfive Visionfive 2](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/visionfive_tests.md) 

[Тестирование БЦВМ АРМ](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/bcvmarm_tests.md) 

[Тестирование БВЦ АРМ](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/bvcarm_tests.md) 

**Сводные таблицы результатов можно найти по ссылкам выше.**

## Код для ПК

[Код для ПК](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/pc-receiver)

Код на Python управляет измерениями задержек между Arduino Mega и одноплатником. Подключается к Arduino через последовательный порт, отправляет команды управления и принимает обработанные данные в формате JSON. Программа работает в интерактивном режиме с консольным управлением. Метрики CPU/памяти собираются через Prometheus (node_exporter) и сохраняются в SQLite базу.

После запуска код автоматически ищет подключенную Arduino Mega по доступным COM-портам или запрашивает порт вручную. Установив соединение, программа переходит в режим командной строки, где пользователь может управлять измерениями: запускать сбор данных, останавливать сбор и проверять статус.

[Пример конфигурационного файла](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/pc-receiver/measurement.conf)

Конфигурационный файл поддерживает следующие параметры:

| Параметр | Описание | Значение по умолчанию |
|----------|----------|---------------------|
| `db` | Путь к файлу базы данных SQLite | `./arduino_data.db` |
| `measurements-per-group` | Количество измерений в группе (200-1500) | `1500` |
| `measurement-interval-us` | Интервал между измерениями (мкс) | `300` |
| `auto-stop-groups` | Автоостановка после N групп (0 = бесконечно) | `2500` |
| `target-board` | Название тестируемой платы | `unknown` |
| `target-kernel` | Версия ядра на тестируемой плате | `unknown` |
| `target-stress` | Наличие системной нагрузки на плате (`on`/`off`) | `off` |
| `target-payload` | Полезная нагрузка между импульсами (`on`/`off`) | `off` |

**Автоматически рассчитываемые параметры:**

| Параметр | Формула | Пример (1500 × 300 µs) |
|----------|---------|----------------------|
| `worst-count` | 5% от `measurements-per-group` (мин. 1) | 75 |
| `timeout-us` | `group_duration × 2` | 900,000 µs (0.9 сек) |
| `check-interval-us` | `group_duration` | 450,000 µs (0.45 сек) |

где `group_duration = measurements-per-group × measurement-interval-us`.

Если `timeout-us` или `check-interval-us` **явно указаны** в конфигурации — используются ручные значения вместо авто-расчёта.

Секция `[soc]` больше не используется — метрики CPU/памяти собираются через node_exporter.

Когда Arduino отправляет обработанные данные, скрипт [receiver](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/pc-receiver/receiver.py) парсит JSON, и сохраняет данные в SQLite базу, из которой может быть выгружена для визуализации отдельным скриптом [plot_statistics](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/pc-receiver/plot_statistics.py).

Стандартный сценарий использования:


Сбор данных:
```bash
# связь с Arduino и одноплатником с параметрами указанными в /path/to/params.conf

./receiver.py --params /path/to/params.conf

start # запуск сессии сбора N

stop # остановка сессии сбора N

# повторный вызов 'start' - новая сессия

exit # завершение сбора
```

Анализ данных:

```bash
# Список всех сессий с информацией о плате, ядре и превышениях порога
./plot_statistics.py arduino_data.db sessions --limit 250

# Детальная информация о конкретной сессии
./plot_statistics.py arduino_data.db details 123456 --limit 250

# Комплексный график (латентность, джиттер, превышения порога, загрузка SoC)
./plot_statistics.py arduino_data.db all --session 123456 --limit 250

# График латентности с наложением загрузки SoC и гистограммой превышений
./plot_statistics.py arduino_data.db latency+soc --session 123456 --limit 250 --output plot.png

# График джиттера с наложением загрузки SoC и гистограммой превышений
./plot_statistics.py arduino_data.db jitter+soc --session 123456 --limit 250

# Автоматическое именование файла: sessionid_board_kernel_interval_worstcount_avg_latency_stress.png
./plot_statistics.py arduino_data.db all --session 123456

# Сравнение максимальной латентности и джиттера между двумя сессиями
./plot_statistics.py --output lichee_radxa_rt_stress_on.png  arduino.db compare 228465 362956 
```

### Структура базы данных SQLite

База данных `arduino_data.db` содержит следующие таблицы:

#### Таблица `groups`
Хранит информацию о группах измерений:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `session_id` | INTEGER | ID сессии |
| `group_index` | INTEGER | Номер группы |
| `pc_timestamp` | TEXT | Время получения на ПК |
| `jitter_us` | REAL | RMS джиттер (мкс) |
| `delay_us` | INTEGER | Интервал между измерениями (мкс) |
| `measurements_per_group` | INTEGER | Количество измерений в группе |
| `worst_count` | INTEGER | Количество сохраненных худших задержек |
| `target_board` | TEXT | Название тестируемой платы |
| `target_kernel` | TEXT | Версия ядра |
| `target_stress` | TEXT | Наличие нагрузки (`on`/`off`) |

#### Таблица `latencies`
Хранит худшие задержки для каждой группы:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `group_id` | INTEGER | Ссылка на `groups.id` |
| `latency_us` | INTEGER | Значение задержки (мкс) |
| `rank_in_group` | INTEGER | Ранг (1 = худшая) |

#### Таблица `soc_metrics`
Хранит метрики загрузки одноплатника:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `session_id` | INTEGER | ID сессии |
| `group_index` | INTEGER | Номер группы |
| `cpu_percent` | REAL | Средняя загрузка CPU (%) |
| `memory_percent` | REAL | Средняя загрузка памяти (%) |
| `cpu_max` | REAL | Максимальная загрузка CPU (%) |
| `mem_max` | REAL | Максимальная загрузка памяти (%) |
| `samples_in_group` | INTEGER | Количество измерений в группе |
| `duration_ms` | REAL | Фактическая длительность группы (мс) |

#### Таблица `events`
Хранит события сессии (старт, стоп, падения, восстановления):

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER | Первичный ключ |
| `session_id` | INTEGER | ID сессии |
| `event_type` | TEXT | Тип события (`start`/`stop`/`fall`/`recovery`) |
| `event_time` | TEXT | Время события |
| `group_index` | INTEGER | Номер группы на момент события |
| `details` | TEXT | Дополнительная информация |


## Код для Arduino

[Код для Arduino](https://altlinux.space/besogon1238/rt-tester/src/branch/main/src/arduino-meter)

Код на Arduino C измеряет задержки в системе связи с SoC. Он отправляет импульсы через пин 7 и принимает ответные сигналы через пин 20 (на Arduino Mega). Для каждого импульса измеряется **время отклика системы** (разница между отправкой сигнала на SoC и получением ответа).

**Параметры измерения (настраиваются через START команду):**
- `measurements_per_group` — количество измерений в группе (200-1500, по умолчанию 1500)
- `worst_count` — количество худших задержек (авто 5% от `measurements_per_group`)
- `measurement_interval_us` — интервал между измерениями (мкс, по умолчанию 300)

**Режим работы:**
- Arduino генерирует меандр с переключением каждые `measurement_interval_us` мкс
- Прерывание `CHANGE` на входном пине фиксирует момент получения ответа от SoC
- По команде `START {"session_id":123,"groups":100,"worst_count":75,"interval_us":300,"measurements_per_group":1500}` начинается сбор данных
- После заполнения группы (заданного числа измерений) формируется JSON-пакет со статистикой
- Данные отправляются на ПК через Serial

После сбора всех N групп программа формирует JSON-пакет со статистикой о группе, который отправляется на ПК автоматически после того как группа из 1500 измерений была проведена.

Управление осуществляется через последовательный порт командами START и STOP. Каждая сессия измерений имеет уникальный идентификатор для последующего анализа данных на компьютере.

### JSON формат данных о группе измерений

```json
{
  "session_id": 123456789,           // Уникальный идентификатор сессии
  "group_index": 5,                  // Номер группы (начиная с 0)
  "timestamp": 12345678,             // Время отправки (мс от старта Arduino)
  "mean_latency_us": 325.6,          // Среднее по ВСЕМ 1500 измерениям
  "avg_latency_us": 312.4,           // Среднее по N худшим задержкам
  "min_latency_us": 223,             // Минимальная среди N худших
  "max_latency_us": 487,             // Максимальная среди N худших
  "jitter_us": 12.34,            // Среднеквадратичное отклонение (RMS jitter)
  "worst_count": 25,                 // Количество худших значений (N)
  "worst_latencies_us": [487, 476, ...], // Массив N худших задержек (от большего к меньшему)
  "parameters": {
    "interval_us": 300,              // Интервал между измерениями (мкс)
    "measurements_per_group": 1500,  // Количество измерений в группе
    "max_groups": 10                 // Максимальное количество групп (0 = бесконечно)
  }
}
```



## Код на одноплатнике (SoC) 

Код на C работает на тестируемой плате (Radxa/Lichee/Raspberry Pi) и реализует:
- Ответную логику на импульсы от Arduino
- Сбор метрик загрузки CPU и памяти
- Логирование статистики в файл

**Архитектура программы:**
- `gpio_handler_thread` — обработчик GPIO-событий (реагирует на фронты от Arduino)
- Для Ethernet round-trip тестирования используется `controller-emu` из проекта [rt-supervisor](https://altlinux.space/besogon1238/rt-supervisor) (ветка `polygon`)

**Конфигурация GPIO (различается для разных плат):**

| Платформа | GPIO Chip | Вход (от Arduino) | Выход (ответ) |
|-----------|-----------|-------------------|---------------|
| Radxa RK3588 | `/dev/gpiochip3` | BANK=1, LINE=2 | BANK=1, LINE=3 |
| Lichee RV Dock | `/dev/gpiochip0` | BANK=4, LINE=12 | BANK=4, LINE=16 |
| Visionfive Starfive v2 | `/dev/gpiochip0` | LINE=60 | LINE=61 |
| БЦВМ АРМ | `/dev/gpiochip0` | LINE=15 | LINE=9 |
| БВЦ АРМ | `/dev/gpiochip0` | LINE=0 | LINE=4 |
| RepkaPI4 | `/dev/gpiochip1` | BANK=6, LINE=13 | BANK=6, LINE=12 |
| MangoPI | `/dev/gpiochip0` | BANK=1, LINE=3 | BANK=1, LINE=4 |
| RockPI4 | `/dev/gpiochip4` | LINE=6 | LINE=7 |

## Утилиты для тестирования

```
chrt -f -p value pid # изменить приоритет процесса pid на value

ps -eLo pid,cls,rtprio,cmd | grep SoC # узнать текущий приоритет процесса/прерывания на SoC

stress-ng --cpu $(nproc) --vm $(nproc) --vm-bytes 100% & # нагрузка на процессор и память
```

## Prometheus и Grafana

**Запуск Prometheus (systemd):**

```bash
sudo cp prometheus/prometheus.yml /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus
```

Конфигурация в `prometheus/prometheus.yml`:
- Scrape interval: 500ms
- node_exporter на SoC: `<IP_SOC>:9100`
- receiver metrics server: `localhost:9101`
- Retention: размерный (10GB) в systemd override

**Импорт дашборда Grafana:**

```bash
curl -X POST http://admin:admin@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\":$(cat grafana/rt-tester-dashboard.json),\"overwrite\":true}"
```

## Методика испытаний

На текущий момент методику испытаний можно описать так:

0. Прошивка Arduino
1. Запуск `controller-emu` + `alt-rt-supervisor` на одноплатнике (через `cmake --build Build --target run` в rt-supervisor)
2. (Опциональный) Нагрузка системы с помощью stress-ng
3. Конфигурация настроечного файла:
   - `measurements-per-group` — количество измерений в группе (200-1500)
   - `measurement-interval-us` — интервал между импульсами
   - `auto-stop-groups` — количество групп до автоостановки
   - `worst-count` рассчитывается автоматически (5% от группы)
   - временной порог ответов для ненагруженной системы 75 мкс, для нагруженной 250
4. Запуск *receiver.py* с указанием параметра --params
5. Цикл сбора данных:
  - Подача команды start
  - Ожидание автоматического завершения сессии
  - Фиксация номера сессии для дальнейшей визуализации
  - Подача команды exit
6. Запуск *plot_statistics* для получения результатов сессии, указывая --limit 75 для сессий без нагрузок и --limit 250 для сессий с нагрузкой.
7. Данные доступны в Grafana (в реальном времени) и через plot_statistics (post-hoc анализ)

[Пример артефактов после обработки одной сессии](https://altlinux.space/besogon1238/rt-tester/src/branch/main/tests/examples/)