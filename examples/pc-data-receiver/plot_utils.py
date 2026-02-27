import matplotlib
matplotlib.use('Agg')           # Используем неинтерактивный бэкенд (без GUI)
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from datetime import datetime
import os
import time

def generate_mixed_plots(data):
    try:
        if "avg_latency_us" not in data:
            print("No data for plotting")
            return

        avg_latency = data['avg_latency_us']
        min_latency = data['min_latency_us']
        max_latency = data['max_latency_us']
        avg_jitter = data['avg_jitter_us']

        stats = data.get('statistics', {})
        total_avg_latency = stats.get('latency', {}).get('overall_avg_us', 0)
        total_avg_jitter = stats.get('jitter', {}).get('overall_avg_us', 0)

        params = data.get('parameters', {})
        delay = params.get('delay_between_pulses_us', 0)
        groups = data.get('groups_count', 0)
        per_group = data.get('measurements_per_group', 0)

        data_dir = "arduino_measurements"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        session_id = data.get('session_id', 'unknown')
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        fig.suptitle(f'Latency & Jitter Analysis | Session: {session_id}\n'
                     f'Delay: {delay:,} µs | {timestamp}',
                     fontsize=14, fontweight='bold')

        groups_list = list(range(1, len(avg_latency) + 1))

        # Latency plot
        axes[0].plot(groups_list, avg_latency, 'b.-', markersize=8, linewidth=2,
                     label=f'Average latency per group')
        axes[0].fill_between(groups_list, min_latency, max_latency,
                             alpha=0.2, color='blue', label='Min-max range')
        axes[0].scatter(groups_list, min_latency, color='green', s=20,
                        marker='^', alpha=0.6, label=f'Min: {min(min_latency):.1f} µs')
        axes[0].scatter(groups_list, max_latency, color='red', s=20,
                        marker='v', alpha=0.6, label=f'Max: {max(max_latency):.1f} µs')
        axes[0].axhline(y=total_avg_latency, color='black', linestyle='--',
                        linewidth=2, alpha=0.7,
                        label=f'Overall avg: {total_avg_latency:.1f} µs')
        axes[0].xaxis.set_major_locator(MaxNLocator(integer=True))
        axes[0].set_xticks(groups_list)
        axes[0].set_title(f'Latency per group ({groups}×{per_group} measurements)', fontsize=12)
        axes[0].set_xlabel('Group number')
        axes[0].set_ylabel('Latency (µs)')
        axes[0].grid(True, alpha=0.3)
        axes[0].legend(loc='best', fontsize=9)

        # Jitter plot
        axes[1].plot(groups_list, avg_jitter, 'g.-', markersize=8, linewidth=2,
                     label='Average jitter per group')
        axes[1].axhline(y=total_avg_jitter, color='black', linestyle='--',
                        linewidth=2, alpha=0.7,
                        label=f'Overall avg: {total_avg_jitter:.1f} µs')
        axes[1].xaxis.set_major_locator(MaxNLocator(integer=True))
        axes[1].set_xticks(groups_list)
        axes[1].set_title(f'Jitter per group ({groups}×{per_group} measurements)', fontsize=12)
        axes[1].set_xlabel('Group number')
        axes[1].set_ylabel('Jitter (µs)')
        axes[1].grid(True, alpha=0.3)
        axes[1].legend(loc='best', fontsize=9)

        plt.tight_layout(rect=[0, 0, 1, 0.93])

        timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")
        plot_filename = f"{data_dir}/latency_jitter_session_{session_id}_{timestamp_file}.png"
        plt.savefig(plot_filename, dpi=150)
        print(f"✓ Plots saved: {plot_filename}")

        plt.show(block=False)
        plt.pause(0.1)
        time.sleep(3)
        plt.close(fig)

    except Exception as e:
        print(f"Error generating plots: {e}")

def create_summary_plot(sessions_data):
    try:
        if not sessions_data:
            print("No data for summary plot")
            return

        fig, axes = plt.subplots(1, 2, figsize=(14, 6))

        for i, session in enumerate(sessions_data):
            session_id = session.get('session_id', f'Session_{i}')
            if 'avg_latency_us' in session:
                avg_latency = session['avg_latency_us']
                avg_jitter = session['avg_jitter_us']
                groups = list(range(1, len(avg_latency) + 1))
                axes[0].plot(groups, avg_latency, '.-', label=session_id, alpha=0.7)
                axes[1].plot(groups, avg_jitter, '.-', label=session_id, alpha=0.7)

        axes[0].xaxis.set_major_locator(MaxNLocator(integer=True))
        axes[1].xaxis.set_major_locator(MaxNLocator(integer=True))

        axes[0].set_title('Average Latency Comparison Between Sessions')
        axes[0].set_xlabel('Group number')
        axes[0].set_ylabel('Latency (µs)')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        axes[1].set_title('Average Jitter Comparison Between Sessions')
        axes[1].set_xlabel('Group number')
        axes[1].set_ylabel('Jitter (µs)')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()

        data_dir = "arduino_measurements"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plt.savefig(f"{data_dir}/summary_comparison_{timestamp}.png", dpi=150)
        plt.show(block=False)
        print("✓ Summary plot saved")
        time.sleep(3)
        plt.close()

    except Exception as e:
        print(f"Error generating summary plot: {e}")