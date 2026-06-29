# Prometheus и Grafana

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
