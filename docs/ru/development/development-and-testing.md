# Разработка и тестирование

[English](../../development/development-and-testing.md)

Перед изменением пути измерения прочитайте [архитектуру](architecture.md).
Команды ниже выполняются из корня checkout исходников, если не указано иное.
Установленный RPM — штатный путь эксперимента; офлайн-графики и объединение БД
требуют исходников. См. [зависимости](../reference/dependencies.md).

## Зависимости исходников

Python-инструментам не требуется компиляция. В ALT Linux импорты сборщика
обеспечивают:

```bash
apt-get install python3 python3-module-serial python3-module-requests
```

Графики дополнительно импортируют `pandas`, `numpy`, `matplotlib` (пакеты ALT:
`python3-module-pandas`, `python3-module-numpy`, `python3-module-matplotlib`).
Установленные runner используют стандартную библиотеку и внешние команды,
например SSH/SCP и rsync; реальные запуски требуют зависимостей соответствующей
роли на платах. `metrics_server.py` реализует HTTP-метрики стандартной библиотекой:
сторонний пакет `prometheus-client` не нужен. Локальный файл
`prometheus_client.py` использует `requests`; не путайте его с этим пакетом.
`paramiko` нужен только историческому `soc_monitor.py`.

Другой вариант при наличии поддержки Python venv/pip — отдельное окружение
вне отслеживаемых артефактов:

```bash
python3 -m venv "$HOME/.venvs/rt-tester"
. "$HOME/.venvs/rt-tester/bin/activate"
python3 -m pip install pyserial requests pandas numpy matplotlib
```

Импорт `serial` предоставляет **pyserial**, а не посторонний пакет с именем
`serial`. Устанавливайте `paramiko` только для работы с историческим SSH-
помощником. Сборка прошивки требует Arduino Mega 2560 core, AVR toolchain и
ArduinoJson; сборка обработчика/supervisor относится к внешним репозиториям,
не к этой подготовке ПК. Unittest не проверяет компиляцию или загрузку прошивки.

## Автоматические проверки без стенда

Команда проверки репозитория:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
```

Выборочные примеры используют discovery: `tests/` не является Python-пакетом.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_receiver_integrity.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_run_stand_measurement.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_run_linux_benchmark.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_publish_cyclictest.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_documentation.py'
```

| Тесты | Что проверяют |
|---|---|
| `test_run_gpio_measurement.py` | Генерацию команд backend/приоритетов/очистки и параметры парных профилей |
| `test_receiver_integrity.py` | Хранение во временной SQLite и валидацию полной группы/группы с тайм-аутом |
| `test_run_stand_measurement.py` | Стартовый шлюз/прогресс с mock, команды жизненного цикла, сетевую политику и обработку ошибки импорта trace |
| `test_central_observability.py` | Генерацию идентичности/конфигурации, команды туннелей и выбор удалённой Grafana |
| `test_run_linux_benchmark.py` | Генерацию команд, проверку результатов, изолированный жизненный цикл stress и метаданные |
| `test_publish_cyclictest.py` | Удалённый импорт с mock, состояние повторной отправки и отклонение изменённых артефактов |
| `test_documentation.py` | Структуру, локальные ссылки/ресурсы, переключатели языка, совпадение исполняемых примеров и семантику JSON |
| `test_documentation_profiles.py` | Адаптированные профили через генераторы receiver/Prometheus/Grafana; базовые флаги подавляют запуск мониторинга |

Тесты подменяют границы subprocess/сети либо используют временные данные. Они не
доказывают правильность подключения GPIO, временных характеристик, serial-
совместимости прошивки, модуля ядра, доступа SSH, доставки remote write или
дашбордов. Проверка ссылок не проверяет внешние URL и Markdown-якоря. Выполненные
и ожидающие проверки фиксируйте в [валидации](../reference/validation.md).

Безопасные проверки разбора CLI завершаются до создания сборщика или выполнения
runner:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 src/pc-receiver/receiver.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_gpio_measurement.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_stand_measurement.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_linux_benchmark.py --help
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish_cyclictest.py --help
```

Не используйте полный GPIO/supervised runner для офлайн-smoke, даже с `--dry-run`:
он может подготовить каталоги, конфигурацию receiver и файлы наблюдения.
Предпочитайте изолированный разбор конфигурации, генерацию команд и функции
валидации с подменой внешних вызовов по образцу тестов. Уже конструктор
`ArduinoCollector` создаёт БД и запускает HTTP-сервер.

## Статические исторические данные и изоляция тестов

Статические отслеживаемые БД с завершённым checkpoint открывайте по immutable
read-only URI: это не создаёт WAL/SHM и не меняет настройки журнала.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import sqlite3
from pathlib import Path
path = Path('tests/old_databases/28032026.db').resolve()
with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as conn:
    print(conn.execute('PRAGMA integrity_check').fetchone()[0])
    print(conn.execute('SELECT COUNT(*) FROM groups').fetchone()[0])
PY
```

`immutable=1` предполагает неизменность БД и игнорирует восстановление журнала;
не применяйте его к активному сбору или данным с незавершённым WAL-checkpoint.
Для проверки графиков/объединения используйте временную копию завершённой БД,
вывод направляйте в собственный временный каталог. Текущие инструменты открывают
обычные SQLite-соединения; `database.py` явно включает WAL даже при чтении.
Не инициализируйте отслеживаемые исторические fixtures этим модулем. Ограничения
интерпретации см. в [анализе](../usage/analysis-and-reports.md) и
[статистике](../reference/measurement-statistics.md).

Тесты записи используют `TemporaryDirectory` и сбрасывают `database._db_manager`
до и после каждого случая: кэшированный manager сохраняет первый путь.
Следуйте этому шаблону изоляции в текущих тестах; смена аргумента пути не выбирает
другую БД в одном процессе. Подменяйте subprocess, SSH и HTTP на границе вызова;
проверяйте значимый результат, например отклонение тайм-аутов или открытие
стартового шлюза только после готовности.

## Граница упаковки

`.gear/rt-tester-tools.spec` определяет обёртки, устанавливаемые исходные файлы,
`%doc` и `%check`. Проверка исходников не подтверждает содержимое установленного
RPM или пакетные ссылки. После одобрения документации подготовьте снимок исходников
выпуска, обновите version/release и changelog, затем собирайте с явно заданными
target/APT/workdir hasher. Фиксируйте пакетные проверки и проверку установленного
содержимого отдельно от тестов исходников. `BuildArch: noarch` даёт архитектурно
независимый RPM; пересборка в других целевых окружениях проверяет зависимости и `%check`.

Далее: [руководство по изменениям](change-guide.md).
