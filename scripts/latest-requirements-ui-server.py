"""Disposable UI fixture server; pause the real solver to observe progress polling."""
import runpy
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import algorithm

generate = algorithm.generate_schedule


def delayed_generation(**kwargs):
    time.sleep(2)
    return generate(**kwargs)


algorithm.generate_schedule = delayed_generation
runpy.run_path(str(root / 'scripts/ui-fixture-server.py'), run_name='__main__')
