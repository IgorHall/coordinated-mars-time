# Coordinated Mars Time

Convert an Earth UTC instant into Coordinated Mars Time (CMT / MTC) and the
local mean solar time at any Mars longitude. Pure Python, standard library
only.

```python
from datetime import datetime, timezone
from coordinated_mars_time import utc_to_cmt, CoordinatedMarsTime, LocalMarsSolarTime
from coordinated_mars_time.core import local_mean_solar_time

dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
cmt = utc_to_cmt(dt)
print(cmt)                       # "Sol N HH:MM:SS MTC"
print(cmt.hours, cmt.minutes, cmt.seconds, cmt.sol_number)

lmst = local_mean_solar_time(dt, 137.4)   # east-positive longitude in degrees
print(lmst.as_lmst_string())     # "HH:MM:SS"
print(lmst.hours, lmst.minutes, lmst.seconds, lmst.longitude_east)
```

## Why this exists

Mission planning for Mars surface assets needs a single, reproducible mapping
from UTC to the Mars clock face, plus a per-longitude local solar time for
power and thermal reasoning. The authoritative algorithm (Allison & McEwen,
2000) is simple enough to implement in a few dozen lines, but the small
constants matter and it is easy to get them subtly wrong. This library is a
single, auditable implementation of that algorithm with no external
dependencies.

The trade-off: UTC leap seconds are ignored. Every Earth day is treated as
exactly 86 400 seconds, so the Mars clock can drift by up to a few tens of
seconds relative to the physical planet over the long term. This is deliberate
— it makes the mapping deterministic and keeps the library from depending on a
leap-second table that itself needs maintaining.

## The awkward edge

Two awkward edges the reader will hit:

1. **Naive datetimes are treated as UTC.** The library does not guess your
   local timezone. If you pass a naive `datetime`, it is read as if it already
   carried `tzinfo=timezone.utc`. Pass an aware datetime if you mean anything
   else.

2. **Sol numbering is arbitrary.** `CoordinatedMarsTime.sol_number` counts
   whole Mars sols from the library's internal reference epoch
   (JD 2441499.5), not from any particular mission's landing. If you need a
   mission-relative sol, subtract the mission's landing sol from this value.

## Exported names

- `CoordinatedMarsTime` — dataclass with `hours`, `minutes`, `seconds`,
  `sol_number`.
- `LocalMarsSolarTime` — dataclass with `hours`, `minutes`, `seconds`,
  `longitude_east`, and an `as_lmst_string()` method.
- `utc_to_cmt(dt)` — returns a `CoordinatedMarsTime`.
- `coordinated_mars_time.core.local_mean_solar_time(dt, longitude_east)` —
  returns a `LocalMarsSolarTime`.
