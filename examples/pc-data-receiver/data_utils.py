import json
import pandas as pd
from datetime import datetime
import os

class DataManager:
    def __init__(self):
        self.data = []               # все сессии
        self.last_data_received = None
        self.session_id = None

    def process_mixed_data(self, data):
        if "session_id" in data:
            self.session_id = data["session_id"]
        self.last_data_received = data

        measurements = {
            'session_id': data.get('session_id', 'unknown'),
            'timestamp': datetime.now(),
            'avg_latency_us': data.get('avg_latency_us', []),
            'min_latency_us': data.get('min_latency_us', []),
            'max_latency_us': data.get('max_latency_us', []),
            'avg_jitter_us': data.get('avg_jitter_us', []),
            'statistics': data.get('statistics', {})
        }
        self.data.append(measurements)

        self._display_stats(data)
        from plot_utils import generate_mixed_plots
        generate_mixed_plots(data)
        self.save_mixed_data_to_file(data)
        return True

    def _display_stats(self, data):
        params = data.get('parameters', {})
        delay = params.get('delay_between_pulses_us', 0)
        groups = data.get('groups_count', 0)
        per_group = data.get('measurements_per_group', 0)
        stats = data.get('statistics', {})

        print("\n" + "="*60)
        print(f"SESSION: {data.get('session_id', 'N/A')}")
        print(f"CONFIGURATION: {groups} groups × {per_group} measurements")
        print(f"PULSE DELAY: {delay:,} µs")
        print(f"TIME: {datetime.now().strftime('%H:%M:%S')}")
        print("-"*60)
        latency_stats = stats.get('latency', {})
        if latency_stats:
            print("LATENCY STATISTICS (µs):")
            print(f"  OVERALL AVG: {latency_stats.get('overall_avg_us', 0):.2f}")
            print(f"  OVERALL MIN: {latency_stats.get('overall_min_us', 0):.2f}")
            print(f"  OVERALL MAX: {latency_stats.get('overall_max_us', 0):.2f}")
            print(f"  VARIATION: {latency_stats.get('variation_us', 0):.2f}")
        jitter_stats = stats.get('jitter', {})
        if jitter_stats:
            print(f"\nJITTER STATISTICS (µs):")
            print(f"  OVERALL AVG: {jitter_stats.get('overall_avg_us', 0):.2f}")
        print("="*60 + "\n")

    def save_mixed_data_to_file(self, data):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = data.get('session_id', 'unknown')
            data_dir = "arduino_measurements"
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)

            # JSON
            json_filename = f"{data_dir}/latency_jitter_session_{session_id}_{timestamp}.json"
            with open(json_filename, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ JSON saved: {json_filename}")

            # CSV
            if all(k in data for k in ['avg_latency_us', 'min_latency_us', 'max_latency_us', 'avg_jitter_us']):
                groups = len(data['avg_latency_us'])
                df_data = {
                    'group_num': list(range(1, groups + 1)),
                    'avg_latency_us': data['avg_latency_us'],
                    'min_latency_us': data['min_latency_us'],
                    'max_latency_us': data['max_latency_us'],
                    'latency_variation_us': [m - n for m, n in zip(data['max_latency_us'], data['min_latency_us'])],
                    'avg_jitter_us': data['avg_jitter_us']
                }
                df = pd.DataFrame(df_data)
                csv_filename = f"{data_dir}/latency_jitter_session_{session_id}_{timestamp}.csv"
                df.to_csv(csv_filename, index=False)
                print(f"✓ CSV saved: {csv_filename}")
        except Exception as e:
            print(f"Error saving files: {e}")