"""Tests for the `time` and `datetime` modules that frozen_stdlib_preamble.py registers in a canister.

Neither C module is linked into the template, so the preamble provides both, on
the IC clock (#73). These tests register them from the preamble's
`_register_time` and `_register_datetime`, with a fake `_basilisk_ic` whose clock
is fixed, and compare what they return with CPython's own modules on the same
inputs. The host runs in UTC for the comparison, since a canister's local time
is UTC.
"""

import _strptime  # noqa: F401 -- binds the host's time before the fixture swaps it out
import ast
import datetime as real_datetime
import os
import random
import sys
import time as real_time

import pytest

PREAMBLE = os.path.join(os.path.dirname(__file__), "..", "basilisk", "frozen_stdlib_preamble.py")

# 2027-01-15 08:00:00.123456789 UTC
IC_TIME_NS = 1_800_000_000_123_456_789


class FakeIC:
    @staticmethod
    def time():
        return IC_TIME_NS


@pytest.fixture
def canister(monkeypatch):
    """The preamble's (time, datetime), registered in sys.modules for the test, on a UTC host."""
    monkeypatch.setenv("TZ", "UTC")
    real_time.tzset()
    with open(PREAMBLE) as f:
        source = f.read()
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name in ("_register_time", "_register_datetime")]
    namespace = {"_sys": sys, "_basilisk_ic": FakeIC}
    exec(compile(ast.Module(nodes, []), PREAMBLE, "exec"), namespace)
    # setitem first so that monkeypatch puts the host's modules back afterwards
    monkeypatch.setitem(sys.modules, "time", real_time)
    monkeypatch.setitem(sys.modules, "datetime", real_datetime)
    namespace["_register_time"]()
    namespace["_register_datetime"]()
    yield sys.modules["time"], sys.modules["datetime"]
    monkeypatch.undo()
    real_time.tzset()


def outcome(function, *args, **kwargs):
    """What a call returns or raises, as something comparable across the two modules."""
    try:
        value = function(*args, **kwargs)
    except Exception as e:
        return ("raises", type(e).__name__)
    if isinstance(value, real_time.struct_time) or type(value).__name__ == "struct_time":
        return ("returns", tuple(value))
    return ("returns", repr(value))


def same(make, canister_module, real_module):
    """make(module) evaluated on both modules gives the same outcome."""
    assert outcome(make, canister_module) == outcome(make, real_module)


RNG = random.Random(73)
# A day inside date.min and date.max: CPython's naive fromtimestamp looks a day
# either side for a fold and refuses those first and last days.
FIRST, LAST = -62135596800 + 86400, 253402300799 - 86400
TIMESTAMPS = (
    [0, 1, -1, 86399, 86400, 951782400, 1_700_000_000, 1_800_000_000, FIRST, LAST]
    + [RNG.randint(FIRST, LAST) for _ in range(300)]
    + [RNG.uniform(FIRST, LAST) for _ in range(300)]
    + [1_800_000_000.5, 1_800_000_000.0000005, 1_800_000_000.0000015, -0.5, -1.9999995]
)
OFFSETS = [None, 0, 3600, -3600, 19800, -34200, 86399, -86399, 45, 1.5]


def tz(module, offset):
    if offset is None:
        return None
    if offset == 0:
        return module.timezone.utc
    return module.timezone(module.timedelta(seconds=offset))


def moments():
    """(timestamp, offset) pairs that cover the calendar and the zones above."""
    for i, t in enumerate(TIMESTAMPS):
        yield t, OFFSETS[i % len(OFFSETS)]


# --- the clock -------------------------------------------------------------


def test_time_reads_the_ic_clock(canister):
    time, datetime = canister
    assert time.time_ns() == IC_TIME_NS
    assert time.time() == IC_TIME_NS / 1e9
    assert time.monotonic() == time.perf_counter() == time.time()
    assert time.monotonic_ns() == time.perf_counter_ns() == IC_TIME_NS


def test_now_is_the_ic_time(canister):
    time, datetime = canister
    assert repr(datetime.datetime.now()) == "datetime.datetime(2027, 1, 15, 8, 0, 0, 123457)"
    assert repr(datetime.datetime.now(datetime.timezone.utc)) == (
        "datetime.datetime(2027, 1, 15, 8, 0, 0, 123457, tzinfo=datetime.timezone.utc)")
    assert datetime.datetime.utcnow() == datetime.datetime.now()
    assert repr(datetime.date.today()) == "datetime.date(2027, 1, 15)"


def test_the_issue_73_symptoms_are_gone(canister):
    """What #73 saw: every date 1970, a - b always zero, timestamp() 0, no strptime."""
    time, datetime = canister
    a = datetime.datetime.fromtimestamp(1_800_000_000)
    b = datetime.datetime.fromtimestamp(1_700_000_000)
    assert a.strftime("%Y-%m-%d %H:%M:%S.%f") == "2027-01-15 08:00:00.000000"
    assert str(a - b) == "1157 days, 9:46:40"
    assert a.timestamp() == 1_800_000_000
    assert a + datetime.timedelta(days=1) == datetime.datetime(2027, 1, 16, 8)
    # ic-python-db's SystemTime.format_timestamp
    stamp = datetime.datetime.fromtimestamp(1_800_000_000_123 / 1000).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    assert stamp == "2027-01-15 08:00:00.123"
    assert datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f") == datetime.datetime(
        2027, 1, 15, 8, 0, 0, 123000)


def test_sleep_refuses_to_pretend(canister):
    time, _ = canister
    with pytest.raises(NotImplementedError, match="cannot wait in a canister"):
        time.sleep(1)
    assert time.sleep(0) is None
    with pytest.raises(ValueError):
        time.sleep(-1)


def test_unsupported_directives_raise(canister):
    _, datetime = canister
    moment = datetime.datetime(2027, 1, 15)
    with pytest.raises(ValueError, match="not supported in a canister"):
        moment.strftime("%Q")
    with pytest.raises(ValueError, match="not supported in a canister"):
        moment.strftime("%E")
    with pytest.raises(ValueError, match="not supported in a canister"):
        datetime.datetime.strptime("Fri Jan 15 08:00:00 2027", "%c")


# --- datetime against CPython ----------------------------------------------


def test_fromtimestamp_matches_cpython(canister):
    _, datetime = canister
    for t, offset in moments():
        same(lambda m: m.datetime.fromtimestamp(t), datetime, real_datetime)
        same(lambda m: m.datetime.fromtimestamp(t, tz(m, offset)), datetime, real_datetime)
        same(lambda m: m.date.fromtimestamp(t), datetime, real_datetime)


def test_timestamp_round_trips_like_cpython(canister):
    _, datetime = canister
    for t, offset in moments():
        same(lambda m: m.datetime.fromtimestamp(t).timestamp(), datetime, real_datetime)
        same(lambda m: m.datetime.fromtimestamp(t, tz(m, offset)).timestamp(), datetime, real_datetime)


DIRECTIVES = ("aAbBcdfGHIjmMpSuUVwWxXyYzZ%" "CDeFghklnPrRsTt")
FORMATS = (
    ["%" + d for d in DIRECTIVES]
    + ["%-" + d for d in "dmHIMSj"]
    + ["%:z", "%Y-%m-%d %H:%M:%S.%f", "%A, %d. %B %Y %I:%M%p", "100%% %Y", "%", "no directive"]
)


def test_strftime_matches_cpython(canister):
    _, datetime = canister
    for t, offset in moments():
        if not -30610224000 <= t <= 253402214400:  # %Y pads differently below year 1000
            continue
        for fmt in FORMATS:
            same(lambda m: m.datetime.fromtimestamp(t, tz(m, offset)).strftime(fmt), datetime, real_datetime)
            same(lambda m: m.date.fromtimestamp(t).strftime(fmt), datetime, real_datetime)
            same(lambda m: format(m.datetime.fromtimestamp(t), fmt), datetime, real_datetime)


def test_date_calendar_matches_cpython(canister):
    _, datetime = canister
    ordinals = [1, 2, 365, 366, 719163, 730120, 3652059] + [RNG.randint(1, 3652059) for _ in range(500)]
    for n in ordinals:
        for method in ("toordinal", "weekday", "isoweekday", "isocalendar", "isoformat",
                       "ctime", "timetuple", "__str__", "__repr__"):
            same(lambda m: getattr(m.date.fromordinal(n), method)(), datetime, real_datetime)
        same(lambda m: m.date.fromordinal(n).replace(day=28), datetime, real_datetime)
        same(lambda m: m.date.fromordinal(n) + m.timedelta(days=400), datetime, real_datetime)
        same(lambda m: m.date.fromordinal(n) - m.date(2000, 2, 29), datetime, real_datetime)
        same(lambda m: m.date.fromordinal(n) < m.date(2000, 2, 29), datetime, real_datetime)


def test_constructors_validate_like_cpython(canister):
    _, datetime = canister
    cases = [(2024, 2, 29), (2023, 2, 29), (1900, 2, 29), (2000, 2, 29), (0, 1, 1), (10000, 1, 1),
             (2027, 13, 1), (2027, 0, 1), (2027, 4, 31), (2027, 1, 0), (2027.0, 1, 1), ("2027", 1, 1)]
    for args in cases:
        same(lambda m: m.date(*args), datetime, real_datetime)
        same(lambda m: m.datetime(*args, 23, 59, 59, 999999), datetime, real_datetime)
    for time_args in [(24,), (0, 60), (0, 0, 60), (0, 0, 0, 1000000), (-1,)]:
        same(lambda m: m.datetime(2027, 1, 1, *time_args), datetime, real_datetime)
    same(lambda m: m.datetime(2027, 1, 1, tzinfo="UTC"), datetime, real_datetime)
    same(lambda m: m.timezone(m.timedelta(hours=24)), datetime, real_datetime)
    same(lambda m: m.timezone(m.timedelta(hours=5), "Five"), datetime, real_datetime)


def random_timedelta_args():
    yield (0, 0, 0)
    yield (-1, 0, 0)
    yield (0, 0, -1)
    yield (999999999, 86399, 999999)
    for _ in range(300):
        yield (RNG.randint(-20000, 20000), RNG.randint(-200000, 200000), RNG.randint(-3_000_000, 3_000_000))


def test_timedelta_matches_cpython(canister):
    _, datetime = canister
    others = list(random_timedelta_args())
    for i, args in enumerate(random_timedelta_args()):
        other = others[-1 - i]
        a = lambda m: m.timedelta(*args)
        b = lambda m: m.timedelta(*other)
        for make in (
            lambda m: a(m), lambda m: str(a(m)), lambda m: a(m).total_seconds(),
            lambda m: (a(m).days, a(m).seconds, a(m).microseconds), lambda m: bool(a(m)),
            lambda m: -a(m), lambda m: abs(a(m)), lambda m: a(m) + b(m), lambda m: a(m) - b(m),
            lambda m: a(m) * 3, lambda m: 3 * a(m), lambda m: a(m) * 0.5, lambda m: a(m) * -2.25,
            lambda m: a(m) // 7, lambda m: a(m) / 7, lambda m: a(m) / 0.3, lambda m: a(m) // b(m),
            lambda m: a(m) / b(m), lambda m: a(m) % b(m), lambda m: divmod(a(m), b(m)),
            lambda m: (a(m) < b(m), a(m) <= b(m), a(m) == b(m), a(m) > b(m), a(m) >= b(m)),
            lambda m: a(m) == 5, lambda m: a(m) < 5, lambda m: hash(a(m)) == hash(m.timedelta(*args)),
        ):
            same(make, datetime, real_datetime)
    for kwargs in ({"weeks": 2, "hours": -3, "milliseconds": 1500}, {"days": 1.5}, {"seconds": 0.25},
                   {"minutes": 1e6}, {"days": 1_000_000_000}, {"hours": "1"}):
        same(lambda m: m.timedelta(**kwargs), datetime, real_datetime)
    same(lambda m: (m.timedelta.min, m.timedelta.max, m.timedelta.resolution), datetime, real_datetime)


def test_datetime_arithmetic_matches_cpython(canister):
    _, datetime = canister
    stamps = list(moments())
    for i, (t, offset) in enumerate(stamps):
        u, other_offset = stamps[-1 - i]
        a = lambda m: m.datetime.fromtimestamp(t, tz(m, offset))
        b = lambda m: m.datetime.fromtimestamp(u, tz(m, other_offset))
        step = (RNG.randint(-400000, 400000), RNG.randint(-86400, 86400), RNG.randint(-10**6, 10**6))
        for make in (
            lambda m: a(m) + m.timedelta(*step), lambda m: m.timedelta(*step) + a(m),
            lambda m: a(m) - m.timedelta(*step), lambda m: a(m) - b(m),
            lambda m: (a(m) == b(m), a(m) != b(m)), lambda m: a(m) < b(m), lambda m: a(m) >= b(m),
            lambda m: a(m) == a(m).replace(tzinfo=None), lambda m: a(m) == a(m).date(),
            lambda m: a(m) < a(m).date(),
            lambda m: hash(a(m)) == hash(a(m).astimezone(m.timezone.utc)),
            lambda m: a(m).astimezone(m.timezone(m.timedelta(hours=-5))),
            lambda m: a(m).astimezone(), lambda m: a(m).utcoffset(), lambda m: a(m).tzname(),
            lambda m: a(m).dst(), lambda m: a(m).timetuple(), lambda m: a(m).utctimetuple(),
            lambda m: a(m).date(), lambda m: a(m).ctime(), lambda m: str(a(m)),
            lambda m: a(m).replace(year=2000, microsecond=5), lambda m: a(m).replace(fold=1),
        ):
            same(make, datetime, real_datetime)
    same(lambda m: (m.datetime.min, m.datetime.max, m.date.min, m.date.max), datetime, real_datetime)


ISO_STRINGS = [
    "2027-01-15", "20270115", "2027-01-15T08:00", "2027-01-15 08:00:00", "2027-01-15T08",
    "2027-01-15T08:00:00.123", "2027-01-15T08:00:00,123456", "2027-01-15T08:00:00.1234567",
    "2027-01-15T080000", "2027-01-15T08:00:00Z", "2027-01-15T08:00:00+01:00",
    "2027-01-15T08:00:00-05:30", "2027-01-15T08:00:00+0130", "2027-01-15T08:00:00+01:00:30.5",
    "2027-01-15T08:00:00+00:00", "20270115T080000Z", "2027-01-15X08:00",
    "2027-1-15", "2027-01-15T", "2027-01-15T8:00", "2027-01-15T08:0", "2027-02-30",
    "2027-01-15T25:00", "2027-01-15T08:00:00.", "2027-01-15T08:00+", "", "x" * 12, "2027-01-15T08:00:00+24:00",
    "2027-01-15T08:00:00Z05:00", "2027-01-15T08:00Zjunk", "2027-01-15T08:00:00ZZ",
]


def test_isoformat_round_trips_like_cpython(canister):
    _, datetime = canister
    for t, offset in moments():
        a = lambda m: m.datetime.fromtimestamp(t, tz(m, offset))
        for timespec in ("auto", "hours", "minutes", "seconds", "milliseconds", "microseconds", "days"):
            same(lambda m: a(m).isoformat(timespec=timespec), datetime, real_datetime)
        same(lambda m: m.datetime.fromisoformat(a(m).isoformat()), datetime, real_datetime)
        same(lambda m: m.date.fromisoformat(a(m).date().isoformat()), datetime, real_datetime)
    for text in ISO_STRINGS:
        same(lambda m: m.datetime.fromisoformat(text), datetime, real_datetime)
        same(lambda m: m.date.fromisoformat(text), datetime, real_datetime)


STRPTIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S.%f", "%Y%m%d", "%d/%m/%y %I:%M %p", "%a %b %d %H:%M:%S %Y",
    "%Y-%m-%dT%H:%M:%S%z", "%B %d, %Y", "%j %Y", "%Y-%m-%d %H:%M:%S %Z", "%A %d %B %Y %H%M",
    "%y-%m-%d", "%Y-%m-%d %H:%M:%S%:z",
]


# CPython's own warning about day-of-month parsing without a year (3.13)
@pytest.mark.filterwarnings("ignore:Parsing dates involving a day of month:DeprecationWarning")
def test_strptime_matches_cpython(canister):
    _, datetime = canister
    for t, offset in list(moments())[:200]:
        moment = real_datetime.datetime.fromtimestamp(t, tz(real_datetime, offset or 0))
        if moment.year < 1000:
            continue
        for fmt in STRPTIME_FORMATS:
            text = moment.strftime(fmt)
            same(lambda m: m.datetime.strptime(text, fmt), datetime, real_datetime)
    for text, fmt in [("2027-01-15", "%Y-%m-%d %H"), ("2027-01-15 08", "%Y-%m-%d"),
                      ("2027-13-15", "%Y-%m-%d"), ("2027-02-29", "%Y-%m-%d"), ("15  Jan   2027", "%d %b %Y"),
                      ("15 january 2027", "%d %B %Y"), ("12 AM", "%I %p"), ("12 PM", "%I %p"),
                      ("1:5:9", "%H:%M:%S"), ("2027-01-15T08:00Z", "%Y-%m-%dT%H:%M%z"),
                      ("+05:30", "%z"), ("-0130", "%z"), ("100%", "%d%%"), ("x", "%Y")]:
        same(lambda m: m.datetime.strptime(text, fmt), datetime, real_datetime)


# --- time against CPython --------------------------------------------------


def test_time_functions_match_cpython(canister):
    time, _ = canister
    for t, _offset in moments():
        if not -30610224000 <= t <= 253402214400:
            continue
        same(lambda m: m.gmtime(t), time, real_time)
        same(lambda m: m.localtime(t), time, real_time)
        same(lambda m: m.mktime(m.localtime(t)), time, real_time)
        same(lambda m: m.ctime(t), time, real_time)
        same(lambda m: m.asctime(m.gmtime(t)), time, real_time)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%a %b %d %j %U %W %z %Z", "%c", "%x %X %p"):
            same(lambda m: m.strftime(fmt, m.gmtime(t)), time, real_time)
    for fields in [(2027, 1, 15, 8, 0, 0, 0, 0, 0), (2027, 14, 1, 0, 0, 0, 0, 0, 0),
                   (2027, 0, 1, 0, 0, 0, 0, 0, 0), (2027, 1, 32, 25, 61, 61, 0, 0, 0)]:
        same(lambda m: m.mktime(fields), time, real_time)
    for text, fmt in [("2027-01-15 08:00:00", "%Y-%m-%d %H:%M:%S"), ("Fri Jan 15 08:00:00 2027", None)]:
        same(lambda m: m.strptime(text, fmt) if fmt else m.strptime(text), time, real_time)
    assert (time.timezone, time.altzone, time.daylight, time.tzname) == (0, 0, 0, ("UTC", "UTC"))


def test_gmtime_defaults_to_the_ic_clock(canister):
    time, _ = canister
    assert tuple(time.gmtime()) == tuple(real_time.gmtime(IC_TIME_NS // 10**9))
    assert time.strftime("%Y-%m-%d %H:%M:%S") == "2027-01-15 08:00:00"
    assert (time.gmtime().tm_zone, time.gmtime().tm_gmtoff) == ("GMT", 0)
    assert (time.localtime().tm_zone, time.localtime().tm_gmtoff) == ("UTC", 0)


# --- found in review: each was a wrong answer, not an exception -----------------


def test_timedelta_from_floats_matches_cpython_to_the_microsecond(canister):
    """Float components are split and rounded in CPython's order, or 1 in ~700 is a µs off."""
    _, datetime = canister
    rng = random.Random(76)
    scales = {"days": 1e6, "seconds": 1e7, "microseconds": 1e9, "milliseconds": 1e7,
              "minutes": 1e5, "hours": 1e4, "weeks": 1e5}
    for _ in range(20_000):
        kwargs = {}
        for name in rng.sample(sorted(scales), rng.randint(1, 4)):
            value = rng.uniform(-scales[name], scales[name])
            kwargs[name] = value if rng.random() < 0.8 else int(value)
        same(lambda m: m.timedelta(**kwargs), datetime, real_datetime)


STRPTIME_CASES = [
    ("461", "%j"), ("366", "%j"), ("000", "%j"), ("41 AM", "%I %p"), ("00 PM", "%I %p"),
    ("Jun", "%B"), ("June", "%b"), ("Thu", "%A"), ("Thursday", "%a"), (" 5", "%d"), ("  5", "%d"),
    ("32", "%d"), ("13", "%m"), ("00", "%m"), ("24", "%H"), ("60", "%M"), ("62", "%S"),
    ("1301", "%m%d"), ("2027130", "%Y%m%d"), ("02", "%H%M"), ("12", "%m%d"), ("+0160", "%z"),
    ("+01:30:60", "%z"), ("+0130:5", "%z"), ("z", "%z"), ("2027-01-15  08", "%Y-%m-%d %H"), (" ", "%d"), (" x", "%d"), (" 5", "%H"), (" 0", "%H"),
    (" 0", "%I"), (" 9 PM", "%I %p"), (" 5", "%M"),
]


@pytest.mark.filterwarnings("ignore:Parsing dates involving a day of month:DeprecationWarning")
def test_strptime_refuses_what_cpython_refuses(canister):
    _, datetime = canister
    for text, fmt in STRPTIME_CASES:
        same(lambda m: m.datetime.strptime(text, fmt), datetime, real_datetime)
    rng = random.Random(2)
    formats = ["%j", "%d", "%m", "%H", "%I %p", "%M", "%S", "%y", "%f", "%m%d", "%H%M", "%d/%m/%Y", "%B %d", "%b %d"]
    names = [n for n in ("January", "Jun", "June", "Sept", "May", "Mayo", "dec") if n]
    for _ in range(20_000):
        fmt = rng.choice(formats)
        digits = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 4)))
        if "%B" in fmt or "%b" in fmt:
            text = f"{rng.choice(names)} {digits[:2]}"
        elif "%p" in fmt:
            text = f"{digits[:2]} {rng.choice(['AM', 'PM', 'am', 'XM'])}"
        elif "/" in fmt:
            text = f"{digits[:2]}/{rng.choice(['1', '01', '12', '13'])}/2027"
        else:
            text = digits
        same(lambda m: m.datetime.strptime(text, fmt), datetime, real_datetime)


def test_dates_and_zones_as_keys_match_cpython(canister):
    """Equal dates, datetimes and zones hash alike, so they find each other as dict keys."""
    _, datetime = canister
    for make in (
        lambda m: {m.date(2027, 1, 15): "x"}[m.date(2027, 1, 15)],
        lambda m: m.date(2027, 1, 15) in {m.date(2027, 1, 15), m.date(2027, 1, 16)},
        lambda m: m.date(2027, 1, 15) == m.datetime(2027, 1, 15),
        lambda m: hash(m.date(2027, 1, 15)) == hash(m.date.fromordinal(m.date(2027, 1, 15).toordinal())),
        lambda m: m.timezone(m.timedelta(hours=1)) == m.timezone(m.timedelta(hours=1), "CET"),
        lambda m: hash(m.timezone(m.timedelta(hours=1))) == hash(m.timezone(m.timedelta(hours=1), "CET")),
        lambda m: m.timezone(m.timedelta(0)) is m.timezone.utc,
        lambda m: {m.timezone.utc: "utc"}[m.timezone(m.timedelta(0), "UTC")],
        lambda m: m.timezone(m.timedelta(hours=1)) == m.timezone(m.timedelta(hours=2)),
        lambda m: m.timezone.utc == "UTC",
        lambda m: {m.datetime(2027, 1, 15, 9, tzinfo=m.timezone(m.timedelta(hours=1))): "x"}[
            m.datetime(2027, 1, 15, 8, tzinfo=m.timezone.utc)],
    ):
        same(make, datetime, real_datetime)

