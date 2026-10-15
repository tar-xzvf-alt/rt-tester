import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StandDashboardTest(unittest.TestCase):
    def setUp(self):
        self.dashboard = json.loads(
            (ROOT / 'grafana/dashboards/rt-supervised-overview.json').read_text())

    def test_overview_starts_with_full_width_latency_and_rms(self):
        first, second = self.dashboard['panels'][:2]
        self.assertEqual(first['id'], 6)
        self.assertEqual(second['id'], 12)
        self.assertEqual(first['gridPos']['w'], 24)
        self.assertEqual(second['gridPos']['w'], 24)
        self.assertLess(first['gridPos']['y'], second['gridPos']['y'])

    def test_each_stage_has_session_and_statistic_selection(self):
        variables = {v['name']: v for v in self.dashboard['templating']['list']}
        self.assertEqual(variables['stage_stat']['query'], 'min,avg,max')
        expected = {
            'gpio_to_send', 'request_send', 'ethernet_recv', 'shmem_input',
            'runtime_wait', 'shmem_output', 'ethernet_send', 'response_recv',
            'response_to_gpio', 'response_wait',
        }
        for stage in expected:
            matching = [p for p in self.dashboard['panels'] if 21 <= p['id'] <= 30 and any(
                f'stage="{stage}"' in t.get('expr', '') for t in p.get('targets', []))]
            self.assertEqual(len(matching), 1, stage)
            expression = matching[0]['targets'][0]['expr']
            self.assertIn('session_id=~"${session_id:regex}"', expression)
            self.assertIn('stat=~"${stage_stat:regex}"', expression)

    def test_runtime_board_drives_session_and_load_selection(self):
        variables = {v['name']: v for v in self.dashboard['templating']['list']}
        self.assertIn('role="supervisor"', variables['runtime_board']['query'])
        self.assertIn('stage="runtime_wait"', variables['runtime_board']['query'])
        for name in ('kernel', 'stress', 'session_id'):
            self.assertIn('board=~"${runtime_board:regex}"', variables[name]['query'])
        self.assertEqual(variables['stand']['allValue'], '.*')
        for panel in self.dashboard['panels']:
            if panel['id'] not in (2, 3, 4, 5, 14):
                continue
            for target in panel['targets']:
                self.assertIn('board=~"${runtime_board:regex}"', target['expr'])
                self.assertIn('role=~"runtime|supervisor"', target['expr'])

    def test_arduino_and_controller_are_bound_to_runtime_sessions(self):
        for panel in self.dashboard['panels']:
            if panel['id'] not in (6, 7, 8, 11, 12, 13, 21, 22, 28, 29, 30):
                continue
            for target in panel['targets']:
                self.assertIn('and on(stand,session_id)', target['expr'])
                self.assertIn('board=~"${runtime_board:regex}"', target['expr'])

    def test_no_lab_specific_names_addresses_or_interfaces(self):
        body = json.dumps(self.dashboard)
        for value in ('repka', 'spacemit', '10.64.', 'end0', 'K3'):
            self.assertNotIn(value, body)
        network = next(p for p in self.dashboard['panels'] if p['id'] == 5)
        for target in network['targets']:
            self.assertIn('device!="lo"', target['expr'])
            self.assertNotIn('network_iface', target['expr'])

    def test_only_measurement_filters_are_visible(self):
        variables = self.dashboard['templating']['list']
        visible = [v['name'] for v in variables if v.get('hide', 0) == 0]
        self.assertEqual(visible, ['runtime_board', 'kernel', 'stress',
                                   'session_id', 'stage_stat'])
        names = {v['name'] for v in variables}
        self.assertNotIn('controller_board', names)
        self.assertNotIn('network_iface', names)
        for name in ('datasource', 'stand', 'freshness_seconds'):
            variable = next(v for v in variables if v['name'] == name)
            self.assertEqual(variable['hide'], 2)

    def test_kernel_and_stress_are_chained_session_metadata_filters(self):
        variables = {v['name']: v for v in self.dashboard['templating']['list']}
        self.assertIn('arduino_session_info', variables['kernel']['query'])
        self.assertNotIn('${kernel:regex}', variables['kernel']['query'])
        self.assertIn('kernel=~"${kernel:regex}"', variables['stress']['query'])
        self.assertNotIn('${stress:regex}', variables['stress']['query'])
        for selector in ('kernel=~"${kernel:regex}"', 'stress=~"${stress:regex}"'):
            self.assertIn(selector, variables['session_id']['query'])
        for panel in self.dashboard['panels']:
            if panel['id'] in (2, 3, 4, 5, 14):
                continue  # node_exporter is host/time data, not session metadata.
            for target in panel['targets']:
                self.assertIn('kernel=~"${kernel:regex}"', target['expr'])
                self.assertIn('stress=~"${stress:regex}"', target['expr'])
                self.assertIn('max_over_time(arduino_session_info', target['expr'])

    def test_freshness_is_configurable_and_stage_means_are_not_tail_means(self):
        variables = {v['name']: v for v in self.dashboard['templating']['list']}
        self.assertIn('freshness_seconds', variables)
        for panel in self.dashboard['panels']:
            if panel['id'] in (6, 12) or 21 <= panel['id'] <= 30:
                for target in panel['targets']:
                    self.assertIn('< $freshness_seconds', target['expr'])
        plc = next(p for p in self.dashboard['panels'] if p['id'] == 25)
        self.assertIn('not pure PLC CPU', plc['description'])
        self.assertIn('not worst-tail', plc['description'])

    def test_panel_rectangles_do_not_overlap(self):
        panels = self.dashboard['panels']
        for i, first in enumerate(panels):
            a = first['gridPos']
            for second in panels[i + 1:]:
                b = second['gridPos']
                overlap = (a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w']
                           and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h'])
                self.assertFalse(overlap, (first['id'], second['id']))

    @unittest.skipUnless(shutil.which('promtool'), 'promtool is not installed')
    def test_queries_isolate_boards_kernels_and_stress_including_expired_metadata(self):
        panels = {p['id']: p for p in self.dashboard['panels']}
        substitutions = {
            '${stand:regex}': '.*', '${runtime_board:regex}': 'runtime-a',
            '${session_id:regex}': '.*', '${kernel:regex}': 'kernel-a',
            '${stress:regex}': 'off', '${stage_stat:regex}': 'avg',
            '$freshness_seconds': '60', '$__rate_interval': '1m', '$__range': '1m',
        }
        cases = []
        for labelled, expired in ((False, False), (False, True),
                                  (True, False), (True, True)):
            suffix_a = ',stand="stand-a"' if labelled else ''
            suffix_b = ',stand="stand-b"' if labelled else ''
            # Central collectors may share session IDs; stand must disambiguate.
            session_b = '123' if labelled else '456'
            series = []
            for board, session, suffix, value, kernel, stress in [
                ('runtime-a', '123', suffix_a, 20, 'kernel-a', 'off'),
                ('runtime-b', session_b, suffix_b, 900, 'kernel-a', 'off'),
                ('runtime-a', '789', suffix_a, 600, 'kernel-b', 'off'),
                ('runtime-a', '987', suffix_a, 700, 'kernel-a', 'on'),
            ]:
                context = (f'board="{board}",role="supervisor",'
                           f'session_id="{session}",stage="runtime_wait"{suffix}')
                series.extend([
                    {'series': 'rt_trace_stage_latest_group_index{' + context + '}',
                     'values': '0 0 stale stale' if expired else '0 0 0 0'},
                    {'series': 'rt_trace_stage_latest_timestamp_seconds{' + context + '}', 'values': '60 60'},
                    {'series': 'rt_trace_stage_latest_us{' + context + ',stat="avg"}', 'values': f'{value} {value}'},
                ])
                series.append({
                    'series': 'arduino_session_info{session_id="' + session + '",'
                              f'kernel="{kernel}",stress="{stress}"' + suffix + '}',
                    'values': '1 1 stale stale' if expired else '1 1 1 1',
                })
                for metric, number in [('arduino_latency_mean', value),
                                       ('arduino_last_group_timestamp_seconds', 60),
                                       ('arduino_group_responses_received', 20)]:
                    series.append({'series': metric + '{session_id="' + session + '"' + suffix + '}',
                                   'values': f'{number} {number}'})
                controller_context = (f'board="controller-{board}",role="controller",'
                                      f'session_id="{session}",stage="gpio_to_send"{suffix}')
                series.extend([
                    {'series': 'rt_trace_stage_latest_timestamp_seconds{' + controller_context + '}', 'values': '60 60'},
                    {'series': 'rt_trace_stage_latest_us{' + controller_context + ',stat="avg"}', 'values': f'{value} {value}'},
                ])
            evaluations = []
            variable_labels = {
                'kernel': ['{kernel="kernel-a"}', '{kernel="kernel-b"}'],
                'stress': ['{stress="off"}', '{stress="on"}'],
                'session_id': ['{session_id="123"}'],
            }
            for variable in self.dashboard['templating']['list']:
                if variable['name'] not in variable_labels:
                    continue
                expression = variable['query']
                self.assertTrue(expression.startswith('query_result('))
                expression = expression[len('query_result('):-1]
                for old, new in substitutions.items():
                    expression = expression.replace(old, new)
                evaluations.append({
                    'expr': expression, 'eval_time': '1m',
                    'exp_samples': [{'labels': label, 'value': 1}
                                    for label in variable_labels[variable['name']]],
                })
            for panel_id, expected in [
                (6, 'arduino_latency_mean{session_id="123"' + suffix_a + '}'),
                (25, 'rt_trace_stage_latest_us{board="runtime-a",role="supervisor",session_id="123",stage="runtime_wait",stat="avg"' + suffix_a + '}'),
                (21, 'rt_trace_stage_latest_us{board="controller-runtime-a",role="controller",session_id="123",stage="gpio_to_send",stat="avg"' + suffix_a + '}'),
            ]:
                expression = panels[panel_id]['targets'][0]['expr']
                for old, new in substitutions.items():
                    expression = expression.replace(old, new)
                evaluations.append({'expr': expression, 'eval_time': '1m',
                                    'exp_samples': [{'labels': expected, 'value': 20}]})
                evaluations.append({
                    'expr': expression.replace('kernel-a', 'not-recorded'),
                    'eval_time': '1m', 'exp_samples': [],
                })
            # Parse and evaluate every panel query, not just the three with expected data.
            populated = {(6, 'A'), (21, 'A'), (25, 'A'), (7, 'A'),
                         (8, 'B'), (11, 'B')}
            if expired:
                populated.remove((11, 'B'))  # Current group gauge has gone stale.
            for panel in panels.values():
                for target in panel['targets']:
                    expression = target['expr']
                    for old, new in substitutions.items():
                        expression = expression.replace(old, new)
                    evaluations.append({'expr': 'count(' + expression + ') or vector(0)',
                                        'eval_time': '1m',
                                        'exp_samples': [{'labels': '{}', 'value':
                                            int((panel['id'], target['refId']) in populated)}]})
            cases.append({'interval': '20s', 'input_series': series,
                          'promql_expr_test': evaluations})
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'dashboard-tests.yml'
            fixture.write_text(json.dumps({'evaluation_interval': '1m', 'tests': cases}))
            result = subprocess.run(['promtool', 'test', 'rules', str(fixture)],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
