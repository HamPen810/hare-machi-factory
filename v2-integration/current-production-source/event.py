"""Event times in Japan, confirmed by the organizer."""
from datetime import datetime

OPEN_AT='2026-11-09T08:00:00+09:00'
DEPARTURE_DAY='2026-11-16T00:00:00+09:00'  # Date boundary, not actual flight time.
OPEN_MS=int(datetime.fromisoformat(OPEN_AT).timestamp()*1000)
DEPARTURE_MS=int(datetime.fromisoformat(DEPARTURE_DAY).timestamp()*1000)
