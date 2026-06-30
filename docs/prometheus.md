# Prometheus и Grafana

## Стандартный запуск измерения

Основной пользовательский путь для raw-Ethernet стенда — один конфиг и одна
команда из корня `rt-tester`:

```bash
scripts/run_stand_measurement.py \
    --config configs/stands/rockpi-plc-visionfive2-controller.conf
```

Этот конфиг описывает текущую роль плат:

```text
rockpi      = Beremiz runtime + alt-rt-supervisor
visionfive2 = GPIO controller side
```

Скрипт выполняет полный цикл:

1. проверяет сеть ПК через `rt-supervisor/scripts/check_pc_network.sh`;
2. запускает `preflight_stand.sh` на `rockpi` и `visionfive2`;
3. стартует trace exporters на обеих платах;
4. стартует локальный Prometheus на `127.0.0.1:9091`;
5. стартует локальную Grafana на `127.0.0.1:3001` с provisioning из `grafana/`;
6. запускает `alt-rt-supervisor` + Beremiz на `rockpi`;
7. запускает `controller-emu -b visionfive2` на `visionfive2`;
8. запускает `receiver.py --start --exit-on-stop`;
9. после auto-stop импортирует trace metrics в SQLite и печатает ссылку Grafana.

Полезные опции:

```bash
# Короткий smoke на 10 групп
scripts/run_stand_measurement.py \
    --config configs/stands/rockpi-plc-visionfive2-controller.conf \
    --groups 10

# Проверить команды без запуска стенда
scripts/run_stand_measurement.py \
    --config configs/stands/rockpi-plc-visionfive2-controller.conf \
    --dry-run

# Пересобрать удаленные деревья перед запуском
scripts/run_stand_measurement.py \
    --config configs/stands/rockpi-plc-visionfive2-controller.conf \
    --build
```

После завершения measurement target-процессы (`alt-rt-supervisor`, Beremiz,
`controller-emu`) останавливаются автоматически. Prometheus, Grafana и remote
trace exporters остаются запущенными, чтобы Grafana продолжала видеть результаты.
Остановить их можно так:

```bash
scripts/run_stand_measurement.py \
    --config configs/stands/rockpi-plc-visionfive2-controller.conf \
    --stop-observability
```

Скрипт печатает итоговые URL, например:

```text
Prometheus: http://127.0.0.1:9091
Grafana: http://127.0.0.1:3001/d/rt-trace-stages?var-session_id=1782751117
```

Если measurement завершился, но в SQLite появились события кроме `start`/`stop`,
в логах target-процессов есть `ERR`/`WARN`/CRC/timeout, trace group count не
совпадает с receiver group count или trace-метрики противоречат Arduino latency,
скрипт печатает
`Measurement completed with anomalies` и завершает работу с кодом `2`. При этом
БД, Prometheus и ссылка Grafana остаются доступными для разбора причины.

Сообщение `Arduino latency contradicts imported trace metrics` означает, что
один обязательный trace stage уже дольше максимальной задержки, измеренной
Arduino. Обычно это указывает на неверную проводку, прямой loopback/crosstalk
между Arduino `D7` и `D20` или отсутствие общего GND.

Сообщение `trace group count does not match receiver groups` означает, что
controller/supervisor увидели больше или меньше GPIO/Ethernet cycles, чем
Arduino/receiver сохранили как measurement groups. Частая причина — лишние edges
на controller GPIO input или trace, стартовавший до фактического measurement
window Arduino.

В `[transport]` stand config параметр `payload-size = 64` передаётся как
`RT_TRANSPORT_PAYLOAD_SIZE=64`. BETH v2 использует только начало 96 KiB
supervisor slot, поэтому компактный raw-Ethernet payload уменьшает число
Ethernet frames на cycle и предотвращает `packet sequence gap` на текущем стенде.

## Зависимости

### ПК (receiver + Prometheus + Grafana)

```bash
apt-get install python3-module-serial \
    python3-module-requests python3-module-prometheus_client \
    python3-module-pandas python3-module-numpy python3-module-matplotlib \
    python3-module-paramiko prometheus grafana openssh-clients rsync
```

| Пакет | Назначение |
|-------|-----------|
| `python3-module-serial` | Связь с Arduino по COM-порту |
| `python3-module-requests` | Запросы к Prometheus API |
| `python3-module-prometheus_client` | Prometheus client library |
| `python3-module-pandas` / `python3-module-numpy` / `python3-module-matplotlib` | Построение графиков и анализ БД |
| `python3-module-paramiko` | Legacy SSH SoC monitor tooling |
| `prometheus` | Сервер сбора метрик |
| `grafana` | Визуализация (опционально) |

### Одноплатник (SoC)

```bash
apt-get install libgpiod2 libgpiod-devel gcc make glibc-devel pkg-config \
    prometheus-node_exporter stress-ng openssh-server
```

| Пакет | Назначение |
|-------|-----------|
| `libgpiod2` | GPIO-библиотека |
| `libgpiod-devel` | Заголовки GPIO для сборки |
| `gcc` / `make` | Компиляция C-кода |
| `glibc-devel` | Заголовки libc для сборки C-кода |
| `pkg-config` | Проверка/поиск установленных библиотек |
| `prometheus-node_exporter` | Экспорт метрик CPU/памяти |
| `stress-ng` | Нагрузочное тестирование |

### Arduino

```bash
apt-get install arduino-core avr-gcc
```

| Пакет | Назначение |
|-------|-----------|
| `arduino-core` | Ядро Arduino |
| `avr-gcc` | Компилятор для AVR (Arduino Mega) |

## Запуск Prometheus (systemd)

```bash
sudo cp prometheus/prometheus.yml /etc/prometheus/prometheus.yml
sudo systemctl restart prometheus
```

Конфигурация в `prometheus/prometheus.yml`:
- Scrape interval: 500ms
- node_exporter на SoC: `<IP_SOC>:9100`
- receiver metrics server: `localhost:9101`
- Retention: размерный (10GB) в systemd override

## Импорт дашборда Grafana

```bash
curl -X POST http://admin:admin@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\":$(cat grafana/rt-tester-dashboard.json),\"overwrite\":true}"
```
