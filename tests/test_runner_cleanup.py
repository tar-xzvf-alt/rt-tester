#!/usr/bin/env python3
import argparse
import configparser
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_gpio_measurement as gpio
import run_linux_benchmark as linux
import run_stand_measurement as stand


@contextlib.contextmanager
def gpio_measurement():
    with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
        args = argparse.Namespace(
            config=str(ROOT / "configs/stands/examples/visionfive2-gpio-basic.conf"),
            session_id=123, groups=1, db=str(Path(tmp) / "result.db"),
            warmup_seconds=0, stop_observability=False, dry_run=False,
            deploy=False, build=False, prepare_only=False, skip_time_sync=True,
            no_prometheus=True, no_grafana=True, keep_target=False,
        )
        stack.enter_context(mock.patch.object(gpio.tempfile, "gettempdir", return_value=tmp))
        mocked = {}
        for name in ("check_prerequisites", "check_arduino", "cleanup_target", "stop_target",
                     "stop_local_receivers", "start_stress", "pin_node_exporter", "warm_up_stress",
                     "start_handler", "pin_handler", "run_receiver", "print_target_diagnostics",
                     "print_prometheus_diagnostics", "print_db_summary"):
            mocked[name] = stack.enter_context(mock.patch.object(gpio, name, return_value=True))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        yield args, mocked


@contextlib.contextmanager
def receiver_child(script):
    processes = []
    popen = subprocess.Popen

    def launch(*args, **kwargs):
        child = popen([sys.executable, "-u", "-c", script], **kwargs)
        processes.append(child)
        return child

    try:
        with mock.patch.object(stand.subprocess, "Popen", side_effect=launch), \
             mock.patch.object(stand, "RECEIVER_STOP_TIMEOUT", 0.1), \
             mock.patch.object(stand, "VERBOSE", False):
            yield processes
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)
            for stream in (child.stdin, child.stdout):
                if stream is not None:
                    stream.close()


class GpioCleanupTest(unittest.TestCase):
    def test_unwritable_warning_output_cannot_skip_cleanup_or_replace_startup_error(self):
        original = RuntimeError("handler failed")
        with gpio_measurement() as (args, mocked):
            mocked["start_handler"].side_effect = original
            mocked["print_target_diagnostics"].side_effect = OSError("diagnostics failed")
            broken_stderr = mock.Mock()
            broken_stderr.write.side_effect = OSError("stderr unavailable")
            with mock.patch.object(sys, "stderr", broken_stderr):
                with self.assertRaises(RuntimeError) as caught:
                    gpio.run_measurement(args)
            self.assertIs(caught.exception, original)
            mocked["stop_target"].assert_called_once()

    def test_signal_failure_retains_pidfile_and_fails_normal_stop(self):
        real_stop = gpio.stop_target
        with gpio_measurement() as (args, mocked):
            pidfile = Path(args.db).parent / "handler.pid"
            pidfile.write_text("424242\n")
            cfg = gpio.load_config(Path(args.config))
            cfg["target"]["pid-path"] = str(pidfile)
            mocked["stop_target"].side_effect = real_stop

            def remote(host, command, **kwargs):
                return subprocess.run([
                    "sh", "-c",
                    "kill() { return 1; }; ps() { printf '424242 424242 S\\n'; }; "
                    "sleep() { :; }; " + command,
                ], check=True, timeout=5, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            with mock.patch.object(gpio, "load_config", return_value=cfg), \
                 mock.patch.object(gpio, "ssh", side_effect=remote):
                with self.assertRaises(subprocess.CalledProcessError):
                    gpio.run_measurement(args)
            self.assertTrue(pidfile.exists(), "failed stop must retain its ownership handle")

    def test_group_stop_handles_live_workers_after_leader_exit_and_ignores_zombies(self):
        real_stop = gpio.stop_target
        with gpio_measurement() as (args, mocked):
            root = Path(args.db).parent
            handler_pid = root / "handler.pid"
            stress_pid = root / "stress.pid"
            signals = root / "signals.log"
            handler_pid.write_text("424242\n")
            stress_pid.write_text("424243\n")
            cfg = gpio.load_config(Path(args.config))
            cfg["target"]["pid-path"] = str(handler_pid)
            cfg["measurement"]["target-stress"] = "on"
            cfg["stress"] = {"pid": str(stress_pid)}
            mocked["stop_target"].side_effect = real_stop

            def remote(host, command, **kwargs):
                stub = (
                    "state=S; kill() { "
                    f"printf '%s\\n' \"$*\" >> {gpio.q(signals)}; "
                    "[ \"$*\" = '-TERM -424243' ] && state=Z; return 0; }; "
                    "ps() { printf '424244 424243 %s\\n' \"$state\"; }; sleep() { :; }; "
                )
                return subprocess.run(["sh", "-c", stub + command], check=True, timeout=5,
                                      text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            with mock.patch.object(gpio, "load_config", return_value=cfg), \
                 mock.patch.object(gpio, "ssh", side_effect=remote):
                gpio.run_measurement(args)
            self.assertFalse(handler_pid.exists())
            self.assertFalse(stress_pid.exists())
            self.assertIn("-TERM -424243", signals.read_text())
            self.assertNotIn("-KILL", signals.read_text())

    def test_each_measurement_stage_failure_still_stops_target(self):
        for stage in ("start_stress", "pin_node_exporter", "warm_up_stress",
                      "start_handler", "pin_handler", "run_receiver"):
            with self.subTest(stage=stage), gpio_measurement() as (args, mocked):
                original = RuntimeError(stage)
                mocked[stage].side_effect = original
                with self.assertRaises(RuntimeError) as caught:
                    gpio.run_measurement(args)
                self.assertIs(caught.exception, original)
                mocked["stop_target"].assert_called_once()
                mocked["print_db_summary"].assert_not_called()

    def test_interrupt_and_system_exit_survive_cleanup_error(self):
        for original in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(error=type(original).__name__), gpio_measurement() as (args, mocked):
                mocked["run_receiver"].side_effect = original
                mocked["stop_target"].side_effect = OSError("stop failed")
                with self.assertRaises(type(original)) as caught:
                    gpio.run_measurement(args)
                self.assertIs(caught.exception, original)
                mocked["stop_target"].assert_called_once()

    def test_keep_target_and_dry_run_retain_their_cleanup_policy(self):
        for keep, dry in ((True, False), (False, True)):
            with self.subTest(keep=keep, dry=dry), gpio_measurement() as (args, mocked):
                args.keep_target = keep
                args.dry_run = dry
                gpio.run_measurement(args)
                if keep:
                    mocked["stop_target"].assert_not_called()
                else:
                    self.assertTrue(mocked["stop_target"].call_args.kwargs["dry_run"])
                if dry:
                    mocked["print_prometheus_diagnostics"].assert_not_called()
                    mocked["print_db_summary"].assert_not_called()

    def test_startup_error_survives_diagnostic_and_cleanup_errors(self):
        original = RuntimeError("handler startup failed")
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            args = argparse.Namespace(
                config=str(ROOT / "configs/stands/examples/visionfive2-gpio-basic.conf"),
                session_id=123, groups=1, db=str(Path(tmp) / "result.db"),
                warmup_seconds=0, stop_observability=False, dry_run=False,
                deploy=False, build=False, prepare_only=False, skip_time_sync=True,
                no_prometheus=True, no_grafana=True, keep_target=False,
            )
            stack.enter_context(mock.patch.object(gpio.tempfile, "gettempdir", return_value=tmp))
            for name in ("check_prerequisites", "check_arduino", "stop_local_receivers",
                         "start_stress", "pin_node_exporter", "warm_up_stress"):
                stack.enter_context(mock.patch.object(gpio, name))
            cleanup = stack.enter_context(mock.patch.object(
                gpio, "cleanup_target"))
            stop = stack.enter_context(mock.patch.object(
                gpio, "stop_target", side_effect=OSError("cleanup unavailable")))
            stack.enter_context(mock.patch.object(gpio, "start_handler", side_effect=original))
            stack.enter_context(mock.patch.object(
                gpio, "print_target_diagnostics", side_effect=OSError("diagnostics unavailable")))
            metrics = stack.enter_context(mock.patch.object(gpio, "print_prometheus_diagnostics"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(errors))

            with self.assertRaises(RuntimeError) as caught:
                gpio.run_measurement(args)

            self.assertIs(caught.exception, original)
            cleanup.assert_called_once()
            stop.assert_called_once()
            metrics.assert_called_once()
            self.assertIn("diagnostics unavailable", errors.getvalue())
            self.assertIn("cleanup unavailable", errors.getvalue())

    def test_normal_stop_is_scoped_and_failed_ssh_does_not_report_success(self):
        failure = subprocess.CalledProcessError(255, ["ssh", "target"])
        output = io.StringIO()
        cfg = gpio.load_config(ROOT / "configs/stands/examples/visionfive2-gpio-basic.conf")
        cfg["measurement"]["target-stress"] = "on"
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            args = argparse.Namespace(
                config="unused", session_id=123, groups=1, db=str(Path(tmp) / "result.db"),
                warmup_seconds=0, stop_observability=False, dry_run=False,
                deploy=False, build=False, prepare_only=False, skip_time_sync=True,
                no_prometheus=True, no_grafana=True, keep_target=False,
            )
            stack.enter_context(mock.patch.object(gpio, "load_config", return_value=cfg))
            stack.enter_context(mock.patch.object(gpio.tempfile, "gettempdir", return_value=tmp))
            for name in ("check_prerequisites", "check_arduino", "stop_local_receivers",
                         "start_stress", "pin_node_exporter", "warm_up_stress", "start_handler",
                         "pin_handler", "run_receiver", "print_target_diagnostics",
                         "print_prometheus_diagnostics", "print_db_summary"):
                stack.enter_context(mock.patch.object(gpio, name, return_value=True))
            ssh = stack.enter_context(mock.patch.object(gpio, "ssh", side_effect=[None, failure, None]))
            stack.enter_context(contextlib.redirect_stdout(output))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

            with self.assertRaises(subprocess.CalledProcessError) as caught:
                gpio.run_measurement(args)

            self.assertIs(caught.exception, failure)
            self.assertEqual(ssh.call_count, 3, "stress cleanup must run after handler stop error")
            self.assertIn("pkill", ssh.call_args_list[0].args[1], "pre-run recovery stays available")
            for call in ssh.call_args_list[1:]:
                self.assertNotIn("pkill", call.args[1])
                self.assertNotIn("systemctl stop", call.args[1])
                self.assertTrue(call.kwargs.get("check", True))
                self.assertIsNotNone(call.kwargs.get("timeout"))
            self.assertNotIn("completed successfully", output.getvalue())


class StandCleanupTest(unittest.TestCase):
    def test_each_start_stage_stops_targets_unless_keep_targets_is_requested(self):
        for stage in ("start_runtime_stress", "start_supervisor", "start_controller",
                      "collect_network_snapshots", "arm_controller"):
            for keep in (False, True):
                with self.subTest(stage=stage, keep=keep), tempfile.TemporaryDirectory() as tmp, \
                     contextlib.ExitStack() as stack:
                    args = stand.build_parser().parse_args([
                        "--config", str(ROOT / "configs/stands/rockpi-plc-visionfive2-controller-stress.conf"),
                        "--session-id", "123", "--groups", "1", "--no-prometheus", "--no-grafana",
                    ])
                    args.keep_targets = keep
                    stack.enter_context(mock.patch.object(stand.tempfile, "gettempdir", return_value=tmp))
                    mocked = {}
                    for name in ("check_prerequisites", "cleanup_before_run", "start_trace_exporter",
                                 "start_runtime_stress", "start_supervisor", "start_controller",
                                 "collect_network_snapshots", "arm_controller", "stop_targets"):
                        mocked[name] = stack.enter_context(mock.patch.object(stand, name, return_value=None))
                    stack.enter_context(mock.patch.object(
                        stand, "run_receiver", side_effect=lambda *a, on_ready, **kw: on_ready()))
                    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                    original = RuntimeError(stage)
                    mocked[stage].side_effect = original

                    with self.assertRaises(RuntimeError) as caught:
                        stand.run_measurement(args)

                    self.assertIs(caught.exception, original)
                    self.assertEqual(mocked["stop_targets"].call_count, 0 if keep else 1)

    def test_receiver_error_survives_snapshot_and_supervisor_stop_errors(self):
        original = RuntimeError("receiver failed")
        errors = io.StringIO()
        args = stand.build_parser().parse_args([
            "--config", str(ROOT / "configs/stands/rockpi-plc-visionfive2-controller-stress.conf"),
            "--session-id", "123", "--groups", "1", "--no-prometheus", "--no-grafana",
        ])

        def receive(*args, on_ready, **kwargs):
            on_ready()
            raise original

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(stand.tempfile, "gettempdir", return_value=tmp))
            for name in ("check_prerequisites", "cleanup_before_run", "start_trace_exporter",
                         "start_runtime_stress", "start_supervisor", "start_controller", "arm_controller"):
                stack.enter_context(mock.patch.object(stand, name))
            snapshots = stack.enter_context(mock.patch.object(
                stand, "collect_network_snapshots", side_effect=[{}, OSError("snapshot unavailable")]))
            ssh = stack.enter_context(mock.patch.object(
                stand, "ssh", side_effect=[OSError("supervisor unavailable"), None, None]))
            stack.enter_context(mock.patch.object(stand, "run_receiver", side_effect=receive))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            stack.enter_context(contextlib.redirect_stderr(errors))

            with self.assertRaises(RuntimeError) as caught:
                stand.run_measurement(args)

            self.assertIs(caught.exception, original)
            self.assertEqual(snapshots.call_count, 2)
            self.assertEqual(ssh.call_count, 3, "controller and stress must stop after supervisor error")
            self.assertIn("snapshot unavailable", errors.getvalue())
            self.assertIn("supervisor unavailable", errors.getvalue())

    def test_supervised_stop_targets_started_process_groups_not_global_names(self):
        cfg = stand.load_config(ROOT / "configs/stands/rockpi-plc-visionfive2-controller-stress.conf")
        args = stand.build_parser().parse_args([
            "--config", "unused", "--session-id", "123", "--groups", "1",
            "--no-prometheus", "--no-grafana",
        ])
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(stand, "load_config", return_value=cfg))
            stack.enter_context(mock.patch.object(stand.tempfile, "gettempdir", return_value=tmp))
            for name in ("check_prerequisites", "cleanup_before_run", "start_trace_exporter",
                         "print_trace_counts", "print_target_log_summary", "import_trace_metrics",
                         "print_db_summary", "check_trace_group_alignment", "check_latency_trace_consistency"):
                stack.enter_context(mock.patch.object(stand, name, return_value=True))
            stack.enter_context(mock.patch.object(stand, "collect_network_snapshots", return_value=None))
            stack.enter_context(mock.patch.object(stand, "run_receiver", side_effect=lambda *a, on_ready, **kw: on_ready()))
            ssh = stack.enter_context(mock.patch.object(stand, "ssh"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))

            stand.run_measurement(args)

            commands = [call.args[1] for call in ssh.call_args_list]
            supervisor_start = next(cmd for cmd in commands if "RT_TRACE_PATH=" in cmd and " -r " in cmd)
            stress_start = next(cmd for cmd in commands if "stress-ng --cpu" in cmd)
            self.assertIn("setsid", supervisor_start)
            self.assertIn("setsid", stress_start)
            stops = ssh.call_args_list[-3:]
            for call in stops:
                self.assertNotIn("pkill", call.args[1])
                self.assertIsNotNone(call.kwargs.get("timeout"))
            self.assertIn("kill -TERM -$pid", stops[0].args[1])
            self.assertIn("kill -TERM -$pid", stops[2].args[1])


class LinuxCleanupTest(unittest.TestCase):
    def test_remote_directory_cleanup_retains_failed_stress_stop_handle(self):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_dict({
            "target": {"host": "root@board"},
            "benchmark": {"engine": "cyclictest", "duration": "1"},
        })
        original = RuntimeError("benchmark failed")
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            remote = Path(tmp) / "remote"
            remote.mkdir()
            (remote / "stress.pid").write_text("424242\n")
            remote_dir = None
            calls = 0

            def ssh(host, command, **kwargs):
                nonlocal remote_dir, calls
                calls += 1
                if calls == 1:
                    remote_dir = command.split()[2]
                    return subprocess.CompletedProcess([], 0)
                if calls == 2:
                    raise original
                return subprocess.run(["sh", "-c", command.replace(remote_dir, str(remote))],
                                      check=True, timeout=5, text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stack.enter_context(mock.patch.object(linux, "preflight", return_value={}))
            stack.enter_context(mock.patch.object(linux, "start_stress"))
            stack.enter_context(mock.patch.object(linux, "stop_stress", side_effect=OSError("stop failed")))
            stack.enter_context(mock.patch.object(linux, "ssh", side_effect=ssh))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            with self.assertRaises(RuntimeError) as caught:
                linux.execute(cfg, Path(tmp) / "results")
            self.assertIs(caught.exception, original)
            self.assertEqual(calls, 3, "directory cleanup must still be attempted")
            self.assertTrue((remote / "stress.pid").exists())

    def test_partial_stress_start_failure_still_attempts_both_cleanup_actions(self):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_dict({
            "target": {"host": "root@board"},
            "benchmark": {"engine": "cyclictest", "duration": "1"},
        })
        original = RuntimeError("stress warmup failed")
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(linux, "preflight", return_value={}))
            stack.enter_context(mock.patch.object(linux, "start_stress", side_effect=original))
            stop = stack.enter_context(mock.patch.object(linux, "stop_stress"))
            ssh = stack.enter_context(mock.patch.object(linux, "ssh"))
            with self.assertRaises(RuntimeError) as caught:
                linux.execute(cfg, Path(tmp))
            self.assertIs(caught.exception, original)
            stop.assert_called_once()
            self.assertEqual(ssh.call_count, 2)
            self.assertIn("rm -rf", ssh.call_args.args[1])

    def test_finalized_bundle_is_retained_but_cleanup_failure_is_reported(self):
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_dict({
            "stand": {"name": "cleanup-test"},
            "target": {"host": "root@board", "label": "board"},
            "benchmark": {"engine": "cyclictest", "duration": "1"},
            "workload": {"engine": "idle"},
        })
        payload = {"file_version": 1, "return_code": 0, "num_threads": 1, "thread": {
            "0": {"cycles": 1, "min": 1, "max": 1, "avg": 1, "cpu": 0,
                  "histogram": {"1": 1}},
        }}
        original = OSError("remote cleanup unavailable")
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            def copy(cmd, **kwargs):
                (Path(cmd[-1]) / "cyclictest.json").write_text(json.dumps(payload))

            stack.enter_context(mock.patch.object(linux, "preflight", return_value={}))
            stack.enter_context(mock.patch.object(linux, "start_stress"))
            stack.enter_context(mock.patch.object(linux, "stop_stress"))
            stack.enter_context(mock.patch.object(linux, "run", side_effect=copy))
            ssh = stack.enter_context(mock.patch.object(linux, "ssh", side_effect=[
                None, subprocess.CompletedProcess([], 0), original,
            ]))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))

            with self.assertRaises(OSError) as caught:
                linux.execute(cfg, Path(tmp))

            self.assertIs(caught.exception, original)
            bundles = list(Path(tmp).iterdir())
            self.assertEqual(len(bundles), 1)
            self.assertFalse(bundles[0].name.startswith("."))
            manifest = json.loads((bundles[0] / "manifest.json").read_text())
            self.assertEqual(manifest["completion_status"], "complete")
            self.assertIsNotNone(ssh.call_args.kwargs.get("timeout"))

    def test_benchmark_error_survives_stress_stop_and_remote_cleanup_errors(self):
        original = RuntimeError("benchmark failed")
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read_dict({
            "stand": {"name": "cleanup-test"},
            "target": {"host": "root@board", "label": "board"},
            "benchmark": {"engine": "cyclictest", "duration": "1"},
            "workload": {"engine": "idle"},
        })
        errors = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(linux, "preflight", return_value={}))
            stack.enter_context(mock.patch.object(linux, "start_stress"))
            stop = stack.enter_context(mock.patch.object(
                linux, "stop_stress", side_effect=OSError("stress stop unavailable")))
            ssh = stack.enter_context(mock.patch.object(
                linux, "ssh", side_effect=[None, original, OSError("remote cleanup unavailable")]))
            stack.enter_context(contextlib.redirect_stderr(errors))

            with self.assertRaises(RuntimeError) as caught:
                linux.execute(cfg, Path(tmp))

            self.assertIs(caught.exception, original)
            stop.assert_called_once()
            self.assertEqual(ssh.call_count, 3)
            self.assertIn("stress stop unavailable", errors.getvalue())
            self.assertIn("remote cleanup unavailable", errors.getvalue())


class ReceiverCleanupTest(unittest.TestCase):
    def test_interrupt_during_term_wait_still_kills_and_reaps_receiver(self):
        script = (
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('Arduino ready for target start', flush=True); time.sleep(60)"
        )
        original = RuntimeError("controller failed")
        with receiver_child(script) as processes, contextlib.redirect_stderr(io.StringIO()):
            def interrupt_cleanup():
                child = processes[0]
                real_wait = child.wait
                interrupted = False

                def wait(*args, **kwargs):
                    nonlocal interrupted
                    if not interrupted:
                        interrupted = True
                        raise KeyboardInterrupt()
                    return real_wait(*args, **kwargs)

                child.wait = wait
                raise original

            with self.assertRaises(RuntimeError) as caught:
                stand.run_receiver(mock.Mock(), 123, Path("/unused.conf"), 1,
                                   dry_run=False, on_ready=interrupt_cleanup)
            self.assertIs(caught.exception, original)
            self.assertIsNotNone(processes[0].poll(), "interrupted cleanup must still reap the receiver")
            self.assertTrue(processes[0].stdout.closed)

    def test_callback_failure_reaps_receiver_even_when_it_ignores_term(self):
        script = (
            "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "print('Arduino ready for target start', flush=True); time.sleep(60)"
        )
        for original in (RuntimeError("controller startup failed"), KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(error=type(original).__name__), receiver_child(script) as processes, \
                 contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(type(original)) as caught:
                    stand.run_receiver(mock.Mock(), 123, Path("/unused.conf"), 1,
                                       dry_run=False, on_ready=mock.Mock(side_effect=original))

                self.assertIs(caught.exception, original)
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll(), "receiver must exit before runner returns")
                self.assertTrue(processes[0].stdout.closed)
                self.assertTrue(processes[0].stdin.closed)

    def test_broken_gate_pipe_reaps_receiver(self):
        script = (
            "import os,time; os.close(0); "
            "print('Arduino ready for target start', flush=True); time.sleep(60)"
        )
        with receiver_child(script) as processes, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(BrokenPipeError):
                stand.run_receiver(mock.Mock(), 123, Path("/unused.conf"), 1,
                                   dry_run=False, on_ready=lambda: None)
            self.assertIsNotNone(processes[0].poll())
            self.assertTrue(processes[0].stdout.closed)

    def test_successful_receiver_closes_pipes_and_reports_progress(self):
        script = (
            "import sys; print('Arduino ready for target start', flush=True); "
            "assert sys.stdin.readline() == 'start\\n'; "
            "print('Group 1/1 stored (index 0, 100.0%)', flush=True)"
        )
        output = io.StringIO()
        with receiver_child(script) as processes, contextlib.redirect_stdout(output):
            stand.run_receiver(mock.Mock(), 123, Path("/unused.conf"), 1,
                               dry_run=False, on_ready=lambda: None)
            self.assertEqual(processes[0].returncode, 0)
            self.assertTrue(processes[0].stdin.closed)
            self.assertTrue(processes[0].stdout.closed)
            self.assertIn("Progress: 1/1 groups", output.getvalue())


if __name__ == "__main__":
    unittest.main()
