# Центральные Prometheus и Grafana

[English](../../observability/central.md)

Приёмник на ПК и экспортёры целевой системы находятся в частных измерительных
сетях. Локальный Prometheus опрашивает их и отправляет временные ряды в реальном
времени в **ваш** центральный Prometheus через перенаправление SSH (защищённого
удалённого соединения). Серверная Grafana запрашивает центральное хранилище.

```text
Arduino → приёмник на ПК :9101 ─┐
целевой node_exporter :9100 ────┼→ Prometheus на ПК :9092 → remote_write → SSH :19090
необязательные экспортёры трасс ┘                                           │
                                           серверный Prometheus 127.0.0.1:9090
                                                                          │
                                           серверная Grafana 127.0.0.1:3000
                                                                          │ перенаправление SSH
                                                браузер ПК 127.0.0.1:3002
```

Локальный Prometheus остаётся необходимым: приёмник запрашивает его API
(программный интерфейс) для метрик SoC (системы на кристалле), а запуски с
супервизором импортируют агрегаты трассировок после сбора. Remote write
(удалённая запись метрик) **не** публикует базу SQLite сеанса, исходные трассировки
или заметки эксперимента. Более простой вариант только на ПК описан в
[локальном мониторинге](local.md).

## 1. Подготовьте свой сервер

Установите версию Prometheus с поддержкой `--web.enable-remote-write-receiver`,
Grafana и сервер SSH из пакетов своего дистрибутива. На ALT Linux, если они
доступны в настроенных репозиториях:

```bash
apt-get install prometheus grafana openssh-server
```

Перед изменением конфигурации службы проверьте установленные юниты и параметры
(`systemctl cat prometheus`, `prometheus --help`). Имена служб, расположение
файлов окружения и доступность пакетов зависят от установки. Сценарий запуска
ожидает серверные назначения **127.0.0.1:9090** и **127.0.0.1:3000**; эти адреса
фиксированы в его коде перенаправления SSH.

Настройте центральный Prometheus с доступной для записи постоянной TSDB
(базой временных рядов) и следующими параметрами:

```text
--config.file=/etc/prometheus/prometheus.yml
--storage.tsdb.path=/var/lib/prometheus
--storage.tsdb.retention.time=365d
--web.listen-address=127.0.0.1:9090
--web.enable-remote-write-receiver
```

365 дней — пример срока хранения; выберите его с учётом сборщиков и диска.
Служба ALT может читать `OPTIONS` из файла sysconfig; подтвердите, что юнит
действительно его использует. Минимальная серверная конфигурация:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ['127.0.0.1:9090']
```

Используйте служебную учётную запись пакета и права записи в хранилище.
Проверьте через `promtool check config /etc/prometheus/prometheus.yml`,
перезапустите/включите фактическую службу, затем проверьте на сервере:

```bash
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:9090/api/v1/status/flags
```

Ответ с флагами должен показывать включённый приёмник remote write. Одна готовность
не доказывает приём записи. Обеспечьте доступ к точке записи через SSH;
пример не требует публичного приёма без аутентификации.

Настройте Grafana на прослушивание `127.0.0.1:3000` через `[server] http_addr`
и `http_port`. Задайте эти источники данных Prometheus в установленном каталоге
автоматической настройки Grafana:

```yaml
apiVersion: 1
datasources:
  - name: RT GPIO Prometheus
    uid: rt-gpio-prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    jsonData:
      timeInterval: 500ms
  - name: RT Trace Prometheus
    uid: rt-trace-prometheus
    type: prometheus
    access: proxy
    url: http://127.0.0.1:9090
    jsonData:
      timeInterval: 500ms
```

Скопируйте нужный JSON панели из установленного на ПК каталога
`/usr/share/rt-tester-tools/grafana/dashboards/` (или рабочей копии исходников)
в читаемый серверный каталог панелей, например `/var/lib/grafana/dashboards`.
Настройте файловый поставщик:

```yaml
apiVersion: 1
providers:
  - name: RT Tester Dashboards
    orgId: 1
    folder: RT Tester
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

Перезапустите фактическую службу Grafana, проверьте её журналы и
`curl -fsS http://127.0.0.1:3000/api/health`, затем источники данных в интерфейсе.
Существующие ресурсы `configs/server/wetgrape-*` фиксируют развёртывание проекта
и служат примерами, а не установочным сценарием для вашего сервера. В частности,
не предполагайте необходимость его широкого переопределения ограничений службы.

## 2. Настройте перенаправление SSH

Создайте серверную учётную запись и разрешите ключ ПК для неинтерактивного
перенаправления. Доступ к файлам TSDB ей не нужен. Пример ограниченной записи
`authorized_keys` разрешает только два необходимых назначения:

```text
restrict,port-forwarding,command="/bin/false",permitopen="127.0.0.1:9090",permitopen="127.0.0.1:3000" ssh-ed25519 YOUR_PUBLIC_KEY
```

Политика серверного SSH должна разрешать локальное перенаправление. Задайте
учётную запись, порт SSH и ключ в собственном профиле. Перед сбором проверьте
доверие к ключу узла и аутентификацию. Для независимой проверки с ПК:

```bash
ssh -N -T -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -i ~/.ssh/rt-observability -p 22 \
  -L 127.0.0.1:19090:127.0.0.1:9090 \
  -L 127.0.0.1:3002:127.0.0.1:3000 prometheus-writer@CENTRAL_HOST
```

В другом терминале запросите `http://127.0.0.1:19090/-/ready` и
`http://127.0.0.1:3002/api/health`. Остановите ручной туннель перед запуском
управляемого сценария туннеля, чтобы освободить порты.

## 3. Адаптируйте и запустите центральный профиль

Скопируйте установленный пример в сохранённый каталог эксперимента:

```text
/usr/share/rt-tester-tools/configs/stands/examples/visionfive2-gpio-central.conf
```

Измените `root@TARGET_HOST`, метаданные, аппаратную конфигурацию и центральную
передачу; отдельно подтвердите обнаружение/доступ к последовательному порту Arduino:

```ini
[observability]
collector-label = my-measurement-pc
prometheus-port = 9092
receiver-port = 9101
remote-write-url = http://127.0.0.1:19090/api/v1/write
central-ssh-host = prometheus-writer@CENTRAL_HOST
central-ssh-port = 22
central-ssh-identity = ~/.ssh/rt-observability
central-prometheus-local-port = 19090
central-grafana-local-port = 3002
central-tunnel-pid = .rt-tester-example/central-tunnel.pid
central-tunnel-log = .rt-tester-example/central-tunnel.log
grafana-managed = false
grafana-url = http://127.0.0.1:3002/d/rt-standalone-gpio
```

Сохраните остальные поля полного примера и используйте абсолютные пути,
подготовленные в пошаговой процедуре; фрагмент INI показывает шаблонные пути
до адаптации. Сценарий запускает один процесс SSH с обоими перенаправлениями
и проверяет готовность центральных служб. Он запускает локальный Prometheus,
а не локальную Grafana. Запускайте после физической подготовки стенда:

```bash
rt-tester-run-gpio --config ./visionfive2-gpio-central.conf --groups 10
```

Стенды с супервизором используют те же поля передачи, но свои локальные
Prometheus/задания и панель `rt-trace-stages`. Не копируйте конфигурацию опроса
автономного режима в профиль с супервизором.

## 4. Проверьте каждый этап во время сбора

1. **Приёмник:** `http://127.0.0.1:9101/metrics` содержит `arduino_latency_mean`,
   `arduino_latency_avg` и `arduino_jitter` после завершённой группы.
   `avg` — среднее хвоста (наибольших сохранённых задержек); `mean` и джиттер
   (разброс задержек) охватывают все полученные ответы. До первой группы ответ
   может быть пустым.
2. **Локальный опрос:** откройте `http://127.0.0.1:9092/targets`. Во время сбора
   `up{job="arduino_latency"}` и `up{job="runtime_node_exporter"}` должны быть `1`.
   Запросите `arduino_latency_avg{session_id="SESSION_ID"}` на
   `http://127.0.0.1:9092/graph` (страница запросов; новые версии могут перенаправлять).
   После выхода приёмника его `up` может стать `0`; используйте диапазон времени сбора.
3. **Очередь записи:** изучите локальный `http://127.0.0.1:9092/metrics` и журнал
   Prometheus. Если собственные метрики опрашиваются, используйте
   `prometheus_remote_storage_samples_pending` и
   `rate(prometheus_remote_storage_samples_failed_total[5m])` для диагностики
   накопления очереди или ошибок. Имена метрик зависят от версии Prometheus;
   отсутствие ряда не доказывает успех, а генерируемая конфигурация сценария
   не добавляет опрос самого Prometheus.
4. **Центральный приём:** на `http://127.0.0.1:19090/graph` запросите:

   ```promql
   arduino_latency_avg{collector="my-measurement-pc",session_id="SESSION_ID"}
   up{job="runtime_node_exporter",collector="my-measurement-pc"}
   count by (collector, stand) (arduino_session_info)
   ```

   Стабильный HTTP API запросов также позволяет проверить доставку с ПК:

   ```bash
   curl -fsSG http://127.0.0.1:19090/api/v1/query \
     --data-urlencode 'query=arduino_latency_avg{collector="my-measurement-pc",session_id="SESSION_ID"}'
   ```

   Успешное получение соответствующего сеанса — проверка доставки. Исправного
   туннеля без данных недостаточно. Для завершённого запуска выберите его
   временной диапазон или используйте
   `max_over_time(arduino_latency_avg{session_id="SESSION_ID"}[1h])`.
5. **Панель:** откройте
   `http://127.0.0.1:3002/d/rt-standalone-gpio?var-session_id=SESSION_ID`, выберите
   плату/сеанс и диапазон сбора, подтвердите задержку, джиттер и нагрузку.
   Если пусто, используйте Grafana Explore с `rt-gpio-prometheus` и центральным
   запросом выше, проверьте UID (уникальный идентификатор) источника данных и
   автоматическую настройку перед изменением измерения.

Сценарий создаёт `monitor`, `collector` и `stand` как **внешние метки**.
Они добавляются к удалённо доставленным рядам, **не сохраняются как метки
локально опрошенных рядов**. Не фильтруйте локальные запросы по `collector` или
`stand`; локально используйте сеанс/плату. Задавайте различные значения сборщика
и стенда на разных ПК/стендах для различения центральных рядов. Существующие
панели преимущественно выбирают плату/сеанс; при диагностике нескольких
сборщиков используйте Explore с фильтрами сборщика/стенда.

Экспортируемые приёмником метрики текущих значений описывают последнюю завершённую
группу. Remote write не гарантирует архивный образец для каждой группы Arduino,
особенно в коротких запусках. Сохраняйте и проверяйте SQLite независимо.

## 5. Остановите управляемый мониторинг и сохраните результаты

Используйте тот же профиль и сохранённый каталог эксперимента:

```bash
rt-tester-run-gpio --config ./visionfive2-gpio-central.conf --stop-observability
# For a supervised profile:
rt-tester-run-stand --config ./supervised.conf --stop-observability
```

Дождитесь опустошения очереди и подтвердите центральный приём перед остановкой
локального Prometheus/туннеля. Это останавливает управляемые сценарием процессы,
а не серверные службы. Архивируйте базу и профиль собственным способом хранения
артефактов. Cyclictest использует [публикацию комплектов](../usage/publish-cyclictest.md)
независимо от Prometheus. [Протокол проверки](../reference/validation.md) отделяет
проверки документации от фактически выполненных серверных/аппаратных процедур.
