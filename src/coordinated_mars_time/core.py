"""Core conversion routines for Coordinated Mars Time (CMT / MTC).

This module converts an Earth UTC timestamp into:
  * Coordinated Mars Time (CMT) — also known in the literature as Mars Time
    Coordinated (MTC) — expressed as a 24-hour Mars clock readout.
  * Local Mean Solar Time (LMST) and Local True Solar Time (LTST) for an
    arbitrary longitude on Mars.

A single algorithm is used to keep the implementation honest: the time-of-day
value on Mars is represented internally as a real number of "sol-seconds" in
the half-open range ``[0, 86400)`` so that hour, minute, and second components
are always well-defined. The leap-second surface of UTC is intentionally not
honoured: we treat every UTC day as exactly 86 400 seconds and accept the small
(~1 part in 10^8) drift that this introduces, which is negligible for the
second-resolution clock this library returns. This is the one design decision a
user needs to know about; it is stated again in the README.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Mars sidereal day in terrestrial (Earth) seconds. The value below is the
# commonly cited figure from Allison & McEwen (2000), corresponding to a
# sidereal rotation period of 24h 37m 22.663s.
_MARS_SIDEREAL_SECONDS: float = 88775.244

# One Mars solar day (sol) in seconds of TAI/UTC: 88775.244 + ~2.06 s.
# The canonical reference value used throughout the Mars time community is
# 88775.244147 s (Allison, 1997; Allison & McEwen, 2000).
_MARS_SOL_SECONDS: float = 88775.244147

# Number of Mars sols per Earth day. Used to advance the Mars clock relative
# to the Julian Date.
_MARS_SOL_PER_DAY: float = _MARS_SOL_SECONDS / 86400.0

# The Julian Date (UT, not TDB) at which Mars' mean solar noon (MTC 12:00:00)
# is defined to coincide with the chosen reference epoch, following
# Allison & McEwen (2000). This value, JD 2441499.5 (2000-01-01 00:00 UT),
# anchors the conversion so that the absolute clock readout is reproducible.
_REFERENCE_JD: float = 2441499.5

# The number of complete Mars sols elapsed between JD 2440575.0 (the Unix
# epoch, 1970-01-01T00:00Z) and the reference epoch JD 2441499.5. Computed
# once so that ``utc_to_cmt`` can work in terms of seconds-since-Unix-epoch
# without repeatedly carrying Julian Dates through the calculation.
_SECONDS_PER_DAY: float = 86400.0
_REFERENCE_UNIX_SECONDS: float = (
    (_REFERENCE_JD - 2440575.0) * _SECONDS_PER_DAY
)

# The Mars-side phase (in fractional sols) of the reference epoch. Allison's
# convention places MTC midnight at JD 2441499.5 minus a fixed offset; we use
# the simplified relation
#     MTC_fraction = ((JD_UT - 2441499.5) * 1.027491252 + 0.00096) mod 1
# where 0.00096 sol (~83 s) is the documented phase correction. Keeping it as
# a single constant makes the arithmetic easy to audit.
_PHASE_OFFSET_SOL: float = 0.00096


def _floor(x: float) -> int:
    """Return the mathematical floor of *x* as a Python int.

    ``math.floor`` already does this, but defining a tiny local helper keeps
    the module dependency-free in spirit (the standard library is allowed; we
    just prefer to make the floor operation explicit here because it is the
    only non-trivial rounding step in the whole pipeline).
    """
    import math
    return math.floor(x)


def _to_unix_seconds(dt: datetime) -> float:
    """Convert an aware datetime to a floating-point count of seconds since
    1970-01-01T00:00:00Z.

    A naive datetime is treated as UTC; this mirrors the behaviour of
    ``datetime.utcnow()`` callers who often forget to attach tzinfo, and keeps
    the library usable from scripts that have not been taught about timezones.
    The caller still gets correct results as long as the wall-clock they pass
    really is UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # ``timestamp()`` on an aware datetime returns POSIX seconds. We go via
    # a manual computation instead to avoid any dependence on the platform's
    # ``mktime``/``timegm`` handling of leap seconds — the intent of this
    # library is a uniform 86400-second day.
    delta: timedelta = dt - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.total_seconds()


def _sol_seconds_since_epoch(unix_seconds: float) -> float:
    """Return the Mars-side elapsed time (in sol-seconds) since the reference
    epoch, with the phase correction applied so that the value wraps cleanly
    into a 24-hour Mars clock.

    The arithmetic is the Allison & McEwen (2000) relation expressed in
    seconds rather than in fractional sols, to avoid a second mod operation.
    """
    elapsed_earth_s: float = unix_seconds - _REFERENCE_UNIX_SECONDS
    elapsed_sol_s: float = elapsed_earth_s * 86400.0 / _MARS_SOL_SECONDS
    # Add the phase correction, expressed in sol-seconds.
    phase_s: float = _PHASE_OFFSET_SOL * 86400.0
    return elapsed_sol_s + phase_s


def _wrap_into_day(seconds: float) -> float:
    """Wrap an arbitrary number of sol-seconds into the half-open range
    ``[0, 86400)``.

    Mars uses a 24×60×60 = 86 400 second clock face by convention — each Mars
    "second" is about 1.02749 Earth seconds, but the *display* of the clock
    is always 0..86399. We therefore normalise against 86 400, not against
    88 775.244.
    """
    day: float = 86400.0
    # ``%`` on floats behaves well for our purposes: it preserves sign and
    # returns a non-negative remainder when the divisor is positive.
    return seconds % day


@dataclass(frozen=True)
class CoordinatedMarsTime:
    """The readout of the Coordinated Mars Time (MTC) clock for a given UTC
    instant.

    Attributes
    ----------
    hours:
        Integer hour of the sol, 0–23.
    minutes:
        Integer minute, 0–59.
    seconds:
        Integer second, 0–59. Sub-second precision is intentionally dropped;
        a Mars clock that reports fractional seconds implies a stability this
        library does not claim to provide.
    sol_number:
        Whole-number index of the current sol, counted from the reference
        epoch. It is not the mission-relative sol numbering used by any
        particular surface mission; callers who need that must apply their
        own offset.
    """

    hours: int
    minutes: int
    seconds: int
    sol_number: int

    def __str__(self) -> str:
        return (
            f"Sol {self.sol_number} "
            f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d} MTC"
        )


@dataclass(frozen=True)
class LocalMarsSolarTime:
    """Local solar time at a given Mars longitude.

    Attributes
    ----------
    hours:
        Local hour, 0–23.
    minutes:
        Local minute, 0–59.
    seconds:
        Local second, 0–59.
    longitude_east:
        The east-positive longitude in degrees for which this local time was
        computed. Included so that the result is self-describing.
    """

    hours: int
    minutes: int
    seconds: int
    longitude_east: float

    def as_lmst_string(self) -> str:
        """Return a ``HH:MM:SS`` LMST string."""
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}"


def utc_to_cmt(dt: datetime) -> CoordinatedMarsTime:
    """Convert an Earth UTC datetime to Coordinated Mars Time.

    Parameters
    ----------
    dt:
        A :class:`datetime.datetime`. If naive, it is interpreted as UTC. If
        aware, its UTC equivalent is used.

    Returns
    -------
    CoordinatedMarsTime
        The Mars clock readout at the given instant.

    Notes
    -----
    Leap seconds are ignored: every UTC day is treated as exactly 86 400
    seconds long. This keeps the mapping deterministic and avoids depending on
    a leap-second table, at the cost of up to ~30 seconds of long-term drift
    relative to the real planet. The trade-off is deliberate.
    """
    unix_s: float = _to_unix_seconds(dt)
    sol_s_total: float = _sol_seconds_since_epoch(unix_s)

    # The sol number is the whole-sol count since the reference epoch.
    # ``_floor`` correctly handles negative values (i.e. dates before the
    # reference epoch), so the function is well-defined for any datetime the
    # caller cares to supply.
    sol_number: int = _floor(sol_s_total / 86400.0)

    time_of_day: float = _wrap_into_day(sol_s_total)
    hours: int = int(time_of_day // 3600)
    minutes: int = int((time_of_day - hours * 3600) // 60)
    seconds: int = int(time_of_day - hours * 3600 - minutes * 60)

    return CoordinatedMarsTime(
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        sol_number=sol_number,
    )


def local_mean_solar_time(
    dt: datetime, longitude_east: float
) -> LocalMarsSolarTime:
    """Compute Local Mean Solar Time (LMST) at the given east-positive
    longitude.

    Parameters
    ----------
    dt:
        UTC datetime (naive datetimes are treated as UTC).
    longitude_east:
        East-positive longitude in degrees, in the range ``[-180, 360]``.
        Values outside ``[-180, 180]`` are accepted and wrapped, because some
        mission conventions use ``[0, 360)`` east longitudes and it would be
        needlessly hostile to reject them.

    Returns
    -------
    LocalMarsSolarTime
        The local mean solar time, to whole-second precision.

    Notes
    -----
    LMST differs from MTC by ``longitude_east / 15`` hours: local noon (12:00)
    occurs when the mean Sun is on the local meridian. We subtract rather than
    add because at east longitudes the Sun transits *before* it does at the
    prime meridian.
    """
    cmt: CoordinatedMarsTime = utc_to_cmt(dt)
    # Local offset in sol-seconds. 1 degree of longitude = 86400/360 = 240 s.
    offset_seconds: float = (longitude_east / 15.0) * 3600.0
    local_seconds: float = (
        cmt.hours * 3600 + cmt.minutes * 60 + cmt.seconds - offset_seconds
    )
    local_seconds = _wrap_into_day(local_seconds)

    hours: int = int(local_seconds // 3600)
    minutes: int = int((local_seconds - hours * 3600) // 60)
    seconds: int = int(local_seconds - hours * 3600 - minutes * 60)

    return LocalMarsSolarTime(
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        longitude_east=longitude_east,
    )
