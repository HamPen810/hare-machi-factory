"""Read-only enforcement: server-observed tap pattern monitoring (no punishment).

Only successful non-replayed tap actions are sampled, within the existing game
transaction. Batch arrival timing is NOT individual finger timing; scores are
heuristics and do not prove automated input.
"""
import json
import logging
import math

MAX_GAPS=36
BREAK_MS=15000

def classify(now, started, last, calls, taps, gaps, current_count):
    """Return next session and cautious indicators, all integer-safe."""
    count=int(current_count)
    if not 1<=count<=20:
        raise ValueError("invalid tap count")
    delta=now-last if last else None
    if delta is None or delta<0 or delta>BREAK_MS:
        started=now
        calls=0
        taps=0
        gaps=[]
    else:
        gaps=list(gaps[-(MAX_GAPS-1):])
        # Zero gaps happen with concurrent actions and must not imply bot timing.
        if delta>=50:
            gaps.append(delta)
    calls+=1
    taps+=count
    duration=max(0,now-started)
    rate=taps*1000/duration if duration>=1000 else 0
    good=[int(x) for x in gaps if isinstance(x,int) and 50<=x<=BREAK_MS]
    mean=sum(good)/len(good) if good else 0
    cv=(math.sqrt(sum((x-mean)**2 for x in good)/len(good))/mean
        if mean>0 and len(good)>=20 else None)
    score=0
    reasons=[]
    # Distinct features required: a client can be extremely fast or regular
    # without conclusively using automation.
    if len(good)>=32 and cv is not None and cv<0.04 and 120<=mean<=5000 and duration>=120000:
        score+=40
        reasons.append("通信間隔が長時間ほぼ一定")
    if duration>=180000 and taps>=4000 and rate>=20:
        score+=40
        reasons.append("長時間にわたる高いタップ処理速度")
    if duration>=1800000 and taps>=15000 and rate>=7:
        score+=30
        reasons.append("休止の少ない長時間の連続操作")
    return {
        "started_at":started,"last_at":now,"request_count":calls,
        "tap_count":taps,"gaps":good[-MAX_GAPS:],
        "score":min(score,100),"reasons":"、".join(reasons),
        "duration_ms":duration,"rate":round(rate,2),
        "avg_interval_ms":round(mean,1) if mean else None,
        "cv":round(cv,4) if cv is not None else None
    }

def record(db,player,now,count):
    """Best-effort observability; never change the economic transaction outcome."""
    db.execute("SAVEPOINT tap_monitor_safe")
    try:
        row=db.execute(
            "SELECT started_at,last_at,request_count,tap_count,gaps_json,"
            "flagged_at FROM tap_monitor_state WHERE player=?",(player,)
        ).fetchone()
        if row:
            d=dict(row)
            try:
                prior=json.loads(d["gaps_json"])
                if not isinstance(prior,list):prior=[]
            except (ValueError,TypeError):
                prior=[]
            started=int(d["started_at"])
            last=int(d["last_at"])
            calls=int(d["request_count"])
            taps=int(d["tap_count"])
            flagged=d["flagged_at"]
        else:
            prior=[]
            started=now
            last=0
            calls=taps=0
            flagged=None
        result=classify(int(now),started,last,calls,taps,prior,int(count))
        if result["score"]>=60 and flagged is None:
            flagged=now
        db.execute(
            "INSERT INTO tap_monitor_state("
            "player,started_at,last_at,request_count,tap_count,gaps_json,"
            "score,reasons,flagged_at,avg_interval_ms,cv,rate"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(player) DO UPDATE SET "
            "started_at=excluded.started_at,last_at=excluded.last_at,"
            "request_count=excluded.request_count,tap_count=excluded.tap_count,"
            "gaps_json=excluded.gaps_json,score=excluded.score,"
            "reasons=excluded.reasons,flagged_at=excluded.flagged_at,"
            "avg_interval_ms=excluded.avg_interval_ms,cv=excluded.cv,"
            "rate=excluded.rate",
            (player,result["started_at"],result["last_at"],result["request_count"],
             result["tap_count"],json.dumps(result["gaps"],separators=(",",":")),
             result["score"],result["reasons"],flagged,result["avg_interval_ms"],
             result["cv"],result["rate"])
        )
        db.execute("RELEASE SAVEPOINT tap_monitor_safe")
    except Exception:
        # PostgreSQL requires rollback-to-savepoint after any SQL exception.
        try:
            db.execute("ROLLBACK TO SAVEPOINT tap_monitor_safe")
            db.execute("RELEASE SAVEPOINT tap_monitor_safe")
        except Exception:
            logging.exception("Tap monitoring savepoint recovery failed")
        logging.warning("Tap monitor sampling unavailable; preserving game action")
