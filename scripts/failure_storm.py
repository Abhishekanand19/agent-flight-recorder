"""Trip the failure-rate alert on demand: run the (deterministically
failing) demo request several times in a row so the issue_refund error
ratio pins at 100% inside the alert's evaluation window.

Usage: python -m scripts.failure_storm [runs]
"""

import sys
import time

from dotenv import load_dotenv

from agent.main import DEMO_QUERY, run_request
from agent.telemetry import init_telemetry, shutdown_telemetry


def main() -> None:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    load_dotenv()
    init_telemetry()
    for i in range(1, runs + 1):
        trace_id, _ = run_request(DEMO_QUERY)
        print(f"storm run {i}/{runs}: trace {trace_id}")
        if i < runs:
            time.sleep(3)
    shutdown_telemetry()
    print("storm complete — the alert should fire within its 1m evaluation cycle")


if __name__ == "__main__":
    main()
