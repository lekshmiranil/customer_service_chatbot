"""Checks for src\\tickets\\config.py and src\\tickets\\business_time.py.

Uses only temporary files; it never touches the real config, uploads or logs.
"""
import copy
import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.tickets.business_time import (
    add_business_seconds,
    business_seconds_between,
    elapsed_seconds,
    evaluate_sla,
    is_business_open,
    next_business_open,
)
from src.tickets.config import (
    DEFAULT_CONFIG,
    ConfigError,
    get_config,
    last_config_error,
    reset_cache,
    write_default_config,
)

IST = ZoneInfo("Asia/Kolkata")
NEW_YORK = ZoneInfo("America/New_York")

total = 0
problems = 0


def check(name, got, expected):
    global total, problems
    total += 1
    if got == expected:
        print(f"ok   {name}")
    else:
        problems += 1
        print(f"FAIL {name}: got {got!r}, expected {expected!r}")


def raises(name, exception_type, function):
    global total, problems
    total += 1
    try:
        function()
    except exception_type:
        print(f"ok   {name}")
    except Exception as error:
        problems += 1
        print(f"FAIL {name}: raised {type(error).__name__} instead of {exception_type.__name__}")
    else:
        problems += 1
        print(f"FAIL {name}: nothing was raised")


def at(year, month, day, hour=0, minute=0, tz=IST):
    return datetime(year, month, day, hour, minute, tzinfo=tz)


def write_config(folder, name, data):
    path = Path(folder) / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


reset_cache()

with tempfile.TemporaryDirectory() as tmp:
    # Calendar used below: Wed 21 Oct 2026 is a working day, Thu 22 Oct is a holiday,
    # Sat 24 and Sun 25 are the weekend, Mon 26 is a working day. Hours 09:00-18:00 IST.
    base = copy.deepcopy(DEFAULT_CONFIG)
    base["holidays"] = [{"date": "2026-10-22", "name": "Test holiday"}]
    ist_path = write_config(tmp, "ist.json", base)
    cfg = get_config(ist_path)

    # ---- business time elapsed
    check("elapsed within one day", business_seconds_between(cfg, at(2026, 10, 21, 10), at(2026, 10, 21, 12)), 7200.0)
    check("elapsed counts only the window", business_seconds_between(cfg, at(2026, 10, 21, 8), at(2026, 10, 21, 20)), 32400.0)
    check("elapsed skips the holiday", business_seconds_between(cfg, at(2026, 10, 21, 17), at(2026, 10, 23, 10)), 7200.0)
    check("elapsed skips the weekend", business_seconds_between(cfg, at(2026, 10, 23, 17), at(2026, 10, 26, 10)), 7200.0)
    check("holiday counts zero", business_seconds_between(cfg, at(2026, 10, 22, 0), at(2026, 10, 22, 23)), 0.0)
    check("weekend counts zero", business_seconds_between(cfg, at(2026, 10, 24, 0), at(2026, 10, 25, 23)), 0.0)
    check("end before start counts zero", business_seconds_between(cfg, at(2026, 10, 21, 12), at(2026, 10, 21, 10)), 0.0)
    check("calendar basis counts everything", elapsed_seconds(cfg, "calendar", at(2026, 10, 21, 17), at(2026, 10, 24, 17)), 259200.0)
    raises("naive datetime is refused", ValueError,
           lambda: business_seconds_between(cfg, datetime(2026, 10, 21, 10), datetime(2026, 10, 21, 11)))
    raises("unknown basis is refused", ValueError,
           lambda: elapsed_seconds(cfg, "lunar", at(2026, 10, 21, 10), at(2026, 10, 21, 11)))

    # ---- adding business time
    check("add across the holiday", add_business_seconds(cfg, at(2026, 10, 21, 17), 7200), at(2026, 10, 23, 10))
    check("add from the weekend", add_business_seconds(cfg, at(2026, 10, 24, 12), 3600), at(2026, 10, 26, 10))
    check("add up to closing time", add_business_seconds(cfg, at(2026, 10, 21, 9), 32400), at(2026, 10, 21, 18))
    check("add with a partial first day", add_business_seconds(cfg, at(2026, 10, 21, 17, 30), 3600), at(2026, 10, 23, 9, 30))
    consistent = True
    for start in (at(2026, 10, 21, 8), at(2026, 10, 21, 17), at(2026, 10, 24, 12), at(2026, 10, 23, 17, 30)):
        for seconds in (1800, 28800, 100000):
            reached = add_business_seconds(cfg, start, seconds)
            if business_seconds_between(cfg, start, reached) != float(seconds):
                consistent = False
    check("add and elapsed agree", consistent, True)

    # ---- opening times
    check("next open from the weekend", next_business_open(cfg, at(2026, 10, 24, 12)), at(2026, 10, 26, 9))
    check("next open before opening", next_business_open(cfg, at(2026, 10, 21, 8)), at(2026, 10, 21, 9))
    check("next open while open", next_business_open(cfg, at(2026, 10, 21, 10)), at(2026, 10, 21, 10))
    check("next open skips the holiday", next_business_open(cfg, at(2026, 10, 21, 19)), at(2026, 10, 23, 9))
    check("closing time is closed", next_business_open(cfg, at(2026, 10, 21, 18)), at(2026, 10, 23, 9))
    check("open at 10:00", is_business_open(cfg, at(2026, 10, 21, 10)), True)
    check("open at 09:00 sharp", is_business_open(cfg, at(2026, 10, 21, 9)), True)
    check("closed at 18:00", is_business_open(cfg, at(2026, 10, 21, 18)), False)
    check("closed on the holiday", is_business_open(cfg, at(2026, 10, 22, 10)), False)
    check("closed on Saturday", is_business_open(cfg, at(2026, 10, 24, 10)), False)

    # ---- SLA clock, business basis (8 working hours)
    target = {"target_minutes": 480, "basis": "business"}
    created = at(2026, 10, 21, 9)
    check("sla ok at 14:59", evaluate_sla(cfg, created, target, at(2026, 10, 21, 14, 59))["state"], "ok")
    at_warning = evaluate_sla(cfg, created, target, at(2026, 10, 21, 15))
    check("sla warning at exactly 75 percent", at_warning["state"], "warning")
    check("sla warning moment", at_warning["warning_at"], at(2026, 10, 21, 15))
    check("sla deadline", at_warning["deadline"], at(2026, 10, 21, 17))
    check("sla consumed fraction", at_warning["consumed_fraction"], 0.75)
    at_breach = evaluate_sla(cfg, created, target, at(2026, 10, 21, 17))
    check("sla breached at the deadline", at_breach["state"], "breached")
    check("sla remaining at the deadline", at_breach["remaining_seconds"], 0.0)
    after = evaluate_sla(cfg, created, target, at(2026, 10, 21, 18))
    check("sla remaining after the deadline is negative", after["remaining_seconds"], -3600.0)
    overnight = evaluate_sla(cfg, at(2026, 10, 21, 17), {"target_minutes": 120, "basis": "business"}, at(2026, 10, 23, 9, 30))
    check("sla warning across the holiday", overnight["state"], "warning")
    check("sla deadline across the holiday", overnight["deadline"], at(2026, 10, 23, 10))

    # ---- SLA clock, calendar basis does not skip weekends
    critical = {"target_minutes": 240, "basis": "calendar"}
    saturday = at(2026, 10, 24, 10)
    check("calendar sla warning on Saturday", evaluate_sla(cfg, saturday, critical, at(2026, 10, 24, 13))["state"], "warning")
    check("calendar sla breach on Saturday", evaluate_sla(cfg, saturday, critical, at(2026, 10, 24, 14))["state"], "breached")

    # ---- daylight saving (New York): offsets change, so real durations change
    ny = copy.deepcopy(DEFAULT_CONFIG)
    ny["timezone"] = "America/New_York"
    ny["holidays"] = []
    ny["business_hours"] = {"start": "01:00", "end": "05:00", "working_days": [6]}
    ny_cfg = get_config(write_config(tmp, "ny.json", ny))
    check("clocks go back: a 01:00-05:00 window is 5 real hours",
          business_seconds_between(ny_cfg, at(2026, 11, 1, 0, 0, NEW_YORK), at(2026, 11, 2, 0, 0, NEW_YORK)), 18000.0)
    check("clocks go forward: a 01:00-05:00 window is 3 real hours",
          business_seconds_between(ny_cfg, at(2027, 3, 14, 0, 0, NEW_YORK), at(2027, 3, 15, 0, 0, NEW_YORK)), 10800.0)
    check("calendar time across the clock change is 25 hours",
          elapsed_seconds(ny_cfg, "calendar", at(2026, 10, 31, 12, 0, NEW_YORK), at(2026, 11, 1, 12, 0, NEW_YORK)), 90000.0)

    # ---- SLA target lookup
    check("payment high uses the override", cfg.sla_target("high", "payment"),
          {"target_minutes": 240, "basis": "business", "source": "override:payment:high"})
    check("order high uses the policy", cfg.sla_target("high", "order"),
          {"target_minutes": 480, "basis": "business", "source": "policy:high"})
    check("critical uses the calendar policy", cfg.sla_target("critical")["basis"], "calendar")
    raises("unknown priority is refused", ValueError, lambda: cfg.sla_target("urgent"))

    # ---- live reload without a restart
    before = get_config(ist_path)
    check("unchanged file reuses the parsed config", before is cfg, True)
    changed = copy.deepcopy(base)
    changed["holidays"].append({"date": "2026-10-23", "name": "Added while running"})
    write_config(tmp, "ist.json", changed)
    reloaded = get_config(ist_path)
    check("edit is picked up", reloaded is not cfg, True)
    check("new holiday applies", reloaded.is_working_day(date(2026, 10, 23)), False)
    check("old config object is unchanged", cfg.is_working_day(date(2026, 10, 23)), True)
    check("calendar fingerprint changes with holidays", reloaded.calendar_fingerprint != cfg.calendar_fingerprint, True)
    check("deadline moves with the new holiday",
          add_business_seconds(reloaded, at(2026, 10, 21, 17), 7200), at(2026, 10, 26, 10))
    agents_changed = copy.deepcopy(changed)
    agents_changed["routing"]["agents"][0]["available"] = False
    write_config(tmp, "ist.json", agents_changed)
    after_agents = get_config(ist_path)
    check("agent change alters the full fingerprint", after_agents.fingerprint != reloaded.fingerprint, True)
    check("agent change leaves the SLA fingerprint alone", after_agents.calendar_fingerprint, reloaded.calendar_fingerprint)

    # ---- a broken edit keeps the last good config
    ist_path.write_text("{ this is not json", encoding="utf-8")
    kept = get_config(ist_path)
    check("broken edit keeps the last good config", kept is after_agents, True)
    check("broken edit is reported", last_config_error(ist_path) is not None, True)
    write_config(tmp, "ist.json", agents_changed)
    get_config(ist_path)
    check("fixed edit clears the report", last_config_error(ist_path), None)

    # ---- defaults and validation
    partial = write_config(tmp, "partial.json", {"timezone": "UTC"})
    partial_cfg = get_config(partial)
    check("partial file keeps the defaults", partial_cfg.data["sla"], DEFAULT_CONFIG["sla"])
    check("partial file applies its own value", partial_cfg.data["timezone"], "UTC")
    default_path = Path(tmp) / "written_default.json"
    write_default_config(default_path)
    check("written default loads back unchanged", get_config(default_path).data, DEFAULT_CONFIG)
    raises("missing file is refused", ConfigError, lambda: get_config(Path(tmp) / "nothing_here.json"))

    counter = [0]

    def broken(change):
        counter[0] += 1
        data = copy.deepcopy(DEFAULT_CONFIG)
        change(data)
        path = write_config(tmp, f"broken_{counter[0]}.json", data)
        return lambda: get_config(path)

    raises("unknown timezone is refused", ConfigError, broken(lambda d: d.update(timezone="Mars/Olympus")))
    raises("start after end is refused", ConfigError,
           broken(lambda d: d["business_hours"].update(start="18:00", end="09:00")))
    raises("bad warning fraction is refused", ConfigError, broken(lambda d: d["sla"].update(warning_fraction=1.5)))
    raises("unknown mandatory field is refused", ConfigError,
           broken(lambda d: d["mandatory_fields"].update(default=["shoe_size"])))
    raises("category with an unknown team is refused", ConfigError,
           broken(lambda d: d["routing"]["categories"]["order"].update(team="ghost_team")))
    raises("unknown SLA basis is refused", ConfigError,
           broken(lambda d: d["sla"]["policies"]["low"].update(basis="weird")))
    raises("duplicate agent id is refused", ConfigError,
           broken(lambda d: d["routing"]["agents"].append(copy.deepcopy(d["routing"]["agents"][0]))))
    raises("thresholds out of order are refused", ConfigError,
           broken(lambda d: d["priority"]["thresholds"].update(critical=10)))
    raises("bad holiday date is refused", ConfigError,
           broken(lambda d: d.update(holidays=[{"date": "2026-13-45", "name": "nonsense"}])))

print(f"checks run: {total}, problems: {problems}")
sys.exit(1 if problems else 0)