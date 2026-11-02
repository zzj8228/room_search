"""Refresh yesterday, today and tomorrow using the saved official session."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from room_search.model import today
from room_search.sync import sync_day

for offset in (-1, 0, 1):
    day = today() + dt.timedelta(days=offset)
    result = sync_day(day)
    print(f"{day}: {result['accepted']} lessons", flush=True)
