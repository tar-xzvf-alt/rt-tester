Name: rt-tester-tools
Version: 0.4.1
Release: alt1
Summary: PC-side measurement tools for RT latency stands
License: GPLv3
Group: Development/Tools
Url: https://altlinux.space/besogon1238/rt-tester
BuildArch: noarch
AutoReq: no

BuildRequires: python3 rpm-build-python3 python3-module-serial python3-module-requests
Requires: python3, python3-module-serial, python3-module-requests
Requires: /bin/sh, openssh-clients, rsync, coreutils

Source0: %name-%version.tar

%description
rt-tester-tools contains PC-side measurement runners, the Arduino receiver,
stand configuration examples and observability assets for standalone GPIO,
cyclictest and supervised raw-Ethernet RT latency stands.

%prep
%setup

%build

%install
root=%buildroot%_datadir/%name
install -d "$root/scripts" "$root/src/pc-receiver"
install -d "$root/configs/stands" "$root/configs/server" \
    "$root/grafana" "$root/prometheus"

install -m755 scripts/run_stand_measurement.py scripts/run_gpio_measurement.py \
    scripts/run_linux_benchmark.py scripts/publish_cyclictest.py "$root/scripts/"
install -m644 scripts/central_observability.py "$root/scripts/"
install -m755 src/pc-receiver/receiver.py \
    src/pc-receiver/import_trace_metrics.py src/pc-receiver/trace_summary.py \
    "$root/src/pc-receiver/"
install -m644 src/pc-receiver/config.py src/pc-receiver/config_loader.py \
    src/pc-receiver/database.py src/pc-receiver/serial_comm.py \
    src/pc-receiver/logging_utils.py src/pc-receiver/arduino_monitor.py \
    src/pc-receiver/metrics_server.py src/pc-receiver/prometheus_client.py \
    src/pc-receiver/measurement-supervised-smoke.conf \
    "$root/src/pc-receiver/"
cp -a configs/stands/. "$root/configs/stands/"
cp -a configs/server/. "$root/configs/server/"
cp -a grafana/dashboards grafana/provisioning "$root/grafana/"
install -m644 prometheus/trace-prometheus-local-tunnel.yml "$root/prometheus/"

install -d %buildroot%_bindir
for entry in \
    'rt-tester-run-stand scripts/run_stand_measurement.py' \
    'rt-tester-run-gpio scripts/run_gpio_measurement.py' \
    'rt-tester-run-linux-benchmark scripts/run_linux_benchmark.py' \
    'rt-tester-publish-cyclictest scripts/publish_cyclictest.py' \
    'rt-tester-receiver src/pc-receiver/receiver.py' \
    'rt-tester-import-trace src/pc-receiver/import_trace_metrics.py' \
    'rt-tester-trace-summary src/pc-receiver/trace_summary.py'; do
    set -- $entry
    cat > %buildroot%_bindir/$1 <<EOF
#!/bin/sh
root=\${RT_TESTER_ROOT:-/usr/share/rt-tester-tools}
export PYTHONDONTWRITEBYTECODE=1
exec /usr/bin/python3 "\$root/$2" "\$@"
EOF
    chmod 755 %buildroot%_bindir/$1
done

%check
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_stand_measurement.py --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_gpio_measurement.py --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 scripts/run_linux_benchmark.py --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 scripts/publish_cyclictest.py --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 src/pc-receiver/receiver.py --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 src/pc-receiver/import_trace_metrics.py --help >/dev/null
PYTHONDONTWRITEBYTECODE=1 python3 src/pc-receiver/trace_summary.py --help >/dev/null
for command in rt-tester-run-stand rt-tester-run-gpio \
    rt-tester-run-linux-benchmark rt-tester-publish-cyclictest \
    rt-tester-receiver rt-tester-import-trace rt-tester-trace-summary; do
    RT_TESTER_ROOT=%buildroot%_datadir/%name \
    %buildroot%_bindir/$command --help >/dev/null
done
test ! -e %buildroot%_datadir/%name/src/pc-receiver/logs
test ! -e %buildroot%_datadir/%name/src/pc-receiver/__pycache__
test -z "$(find %buildroot%_datadir/%name -type f \( -name '*.db' -o -name '*.pyc' \) -print -quit)"

%files
%_bindir/rt-tester-*
%_datadir/%name/
%doc README.md LICENSE.md docs/

%changelog
* Thu Aug 20 2026 Taran Evgeniy <taranev@basealt.ru> 0.4.1-alt1
- Restructure documentation by measurement mode and usage scenario
- Add complete cyclictest publication and fixed-frequency workflows
- Package the full nested documentation tree

* Thu Aug 20 2026 Taran Evgeniy <taranev@basealt.ru> 0.4.0-alt1
- Add validated, idempotent cyclictest bundle publication over SSH
- Keep failed publications in a retryable sidecar queue
- Add optional automatic publication after successful measurements

* Thu Aug 20 2026 Taran Evgeniy <taranev@basealt.ru> 0.3.1-alt1
- Document fixed-frequency idle and stressed cyclictest comparisons
- Record the stress-ng package version in stressed result bundles

* Thu Aug 20 2026 Taran Evgeniy <taranev@basealt.ru> 0.3.0-alt1
- Add remote cyclictest runner with idle and stress-ng profiles
- Preserve native JSON, histograms and versioned bundle manifests
- Validate per-CPU results and use scoped stress process cleanup

* Wed Aug 19 2026 Taran Evgeniy <taranev@basealt.ru> 0.2.0-alt1
- Add centralized Prometheus remote write and Grafana provisioning
- Add standalone userspace and kernelspace GPIO experiment workflows
- Validate measurement integrity and preserve timeout statistics
- Keep Arduino response timeout independent from measurement interval

* Tue Jul 21 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.9-alt1
- Wait for target shutdown before removing shared memory or restarting.

* Tue Jul 21 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.8-alt1
- Arm controller GPIO processing immediately before Arduino START.

* Tue Jul 21 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.7-alt1
- Gate Arduino START until controller startup completes.

* Tue Jul 21 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.6-alt1
- Pass the expected measurement group count to controller trace diagnostics.

* Tue Jul 21 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.5-alt1
- Report host-wide softnet time squeeze as a per-CPU warning, not packet loss.
- Ignore local SQLite sidecar files for the merged measurement database.

* Mon Jul 20 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.4-alt1
- Keep the generated merged measurement database out of version control.

* Mon Jul 20 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.3-alt1
- Add the RockPI Beremiz and VisionFive 2 controller stand configuration.
- Add concise stand progress, early Grafana links and optional verbose diagnostics.
- Improve public command help and cover output behavior during package checks.

* Fri Jul 17 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.2-alt1
- Document the separate rt-supervisor runtime example package.

* Thu Jul 16 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.1-alt1
- Update README and package deployment documentation.

* Thu Jul 16 2026 Taran Evgeniy <taranev@basealt.ru> 0.1.0-alt1
- Initial package with PC-side measurement tools.
