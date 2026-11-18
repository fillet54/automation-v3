"""The crew, when a script doesn't fly the LM itself

``nominal`` flies the procedure: PRO at ignition, V16 N68 to monitor the
braking phase, V57 once the landing radar's data is good, the master
alarm and RSET after an alarm, KEY REL in P64, P66 at low gate with
rate-of-descent clicks down to contact, and ENGINE STOP after contact.
After three program alarms it stops selecting V16 N68 again, as Apollo
11's crew did once they knew the alarms were safe to fly through.

``hands-off`` gives PRO and V57 only: guidance lands in P65.

``manual`` does nothing: the script is the crew.

The nominal crew watches the rate the computer holds, clicks once and
waits; clicking on the measured rate makes it swing (a lesson from the
heddle model in ~/Work/apollo11).
"""

from . import lgc as L


def fresh(kind):
    return {"kind": kind, "pro_at": None, "monitor_at": None, "v57_at": None,
            "alarm_at": None, "keyrel_at": None, "stop_at": None, "rod_at": 0}


def keys(s, text):
    for k in text:
        L.key(s, k)


def target_rate(h):
    return -max(0.6, min(3.0, h / 20.0))


def act(s):
    c, lgc, tick = s["crew"], s["lgc"], s["tick"]
    if c["kind"] == "manual":
        return
    if lgc["awaiting_pro"]:
        if c["pro_at"] is None:
            c["pro_at"] = tick + 30
        elif tick >= c["pro_at"]:
            c["pro_at"] = None
            L.proceed(s)
    if not lgc["lr_incorporate"] and s["lr"]["alt_good"] and lgc["ignited"] is not None:
        if c["v57_at"] is None:
            c["v57_at"] = tick + 40
        elif tick >= c["v57_at"]:
            keys(s, "V57E")
    if c["kind"] != "nominal":
        return
    flying = lgc["ignited"] is not None
    if flying and lgc["program"] == 63 and lgc["monitor"] is None and len(lgc["alarms"]) < 3:
        if c["monitor_at"] is None:
            c["monitor_at"] = tick + (200 if lgc["alarms"] else 100)
        elif tick >= c["monitor_at"]:
            c["monitor_at"] = None
            keys(s, "V16N68E")
    if s["cwea"]["master_alarm"]:
        if c["alarm_at"] is None:
            c["alarm_at"] = tick + 30
        elif tick >= c["alarm_at"]:
            c["alarm_at"] = None
            s["cwea"]["master_alarm"] = False
            if lgc["lights"]["prog"] or lgc["lights"]["restart"]:
                keys(s, "R")
    if lgc["lights"]["key-rel"] and lgc["program"] != 63:
        if c["keyrel_at"] is None:
            c["keyrel_at"] = tick + 20
        elif tick >= c["keyrel_at"]:
            c["keyrel_at"] = None
            keys(s, "K")
    if lgc["program"] == 64 and (L.nav(s)["h"] <= 150.0 or lgc["phase_tgo"] <= 6.0):
        L.click_rod(s, 1)
        c["rod_at"] = tick + 20
    elif lgc["program"] == 66 and not s["contact"] and tick >= c["rod_at"]:
        c["rod_at"] = tick + 20
        diff = target_rate(L.nav(s)["h"]) - lgc["vz_cmd"]
        clicks = max(-3, min(3, round(diff / L.FT)))
        if clicks:
            L.click_rod(s, clicks)
    if s["contact"] and not s["panel"]["engine_stop"]:
        if c["stop_at"] is None:
            c["stop_at"] = tick + 10
        elif tick >= c["stop_at"]:
            s["panel"]["engine_stop"] = True
