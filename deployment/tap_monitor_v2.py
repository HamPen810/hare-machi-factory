"""Low-bandwidth stage 3/4 tap heuristics; observation only, never punitive.

Single current-state row per player. 1-minute buckets retained for 30 minutes.
Client stats are untrusted supporting evidence and sampled only periodically.
No additional HTTP requests. Event history recorded at most once per 6 hours
per high-scoring player. No raw tap events or IPs are retained.
"""
import json
import logging
import math
import tap_monitor_v1

BUCKET_MS=60000
MAX_BUCKETS=30
EVENT_COOLDOWN_MS=21600000

def _rollup(now, previous, count):
    minute=int(now)//BUCKET_MS
    parsed=[]
    if isinstance(previous,list):
        for item in previous:
            if (isinstance(item,list) and len(item)==3 and
                all(type(n) is int for n in item) and
                minute-29<=item[0]<=minute and 0<=item[1]<=100000
                and 0<=item[2]<=2000000):
                parsed.append(item)
    by_minute={r[0]:r[1:] for r in parsed}
    calls,taps=by_minute.get(minute,(0,0))
    by_minute[minute]=(calls+1,taps+count)
    return [[m,*by_minute[m]] for m in sorted(by_minute) if m>=minute-29]

def _window(rows,now,minutes):
    since=int(now)//BUCKET_MS-(minutes-1)
    chosen=[r for r in rows if r[0]>=since]
    return sum(r[1] for r in chosen),sum(r[2] for r in chosen)

def _client_meta(meta,count):
    # Sampled per-batch statistics, never trusted as proof of automation.
    if not isinstance(meta,list) or len(meta)!=4:
        return None
    if not all(type(x) is int for x in meta):
        return None
    n,mean,cv,trusted=meta
    if not (n==count and 1<=n<=20 and
            0<=mean<=30000 and 0<=cv<=10000 and 0<=trusted<=count):
        return None
    return [n,mean,cv,trusted]

def record(db,player,now,count,client_meta=None):
    # Only called after an accepted game tap, never on idempotent replays.
    db.execute("SAVEPOINT tap_monitor_v2_safe")
    try:
        r=db.execute(
            "SELECT started_at,last_at,request_count,tap_count,gaps_json,"
            "score,reasons,flagged_at,rollups_json,client_samples,client_regular_samples,"
            "last_event_at FROM tap_monitor_state WHERE player=?",(player,)
        ).fetchone()
        d=dict(r) if r else {}
        def parsed(name):
            try:
                v=json.loads(d.get(name) or "[]")
                return v if isinstance(v,list) else []
            except (ValueError,TypeError):
                return []
        old_gaps=parsed('gaps_json')
        old_rollups=parsed('rollups_json')
        previous_score=int(d.get('score') or 0)
        old_reason=str(d.get('reasons') or '')
        last_event=int(d.get('last_event_at') or 0)
        now=int(now)
        count=int(count)
        current=tap_monitor_v1.classify(
            now,int(d.get('started_at') or now),int(d.get('last_at') or 0),
            int(d.get('request_count') or 0),int(d.get('tap_count') or 0),
            old_gaps,count)
        rollups=_rollup(now,old_rollups,count)
        calls1,taps1=_window(rollups,now,1)
        calls5,taps5=_window(rollups,now,5)
        calls30,taps30=_window(rollups,now,30)
        # Use full window denominators, not bursty instant arrival rates.
        rate1=taps1/60.0
        rate5=taps5/300.0
        rate30=taps30/1800.0
        samples=int(d.get('client_samples') or 0)
        regular=int(d.get('client_regular_samples') or 0)
        meta=_client_meta(client_meta,count)
        if meta is not None:
            # Non-authoritative supplementary signal: very low jitter.
            samples=min(1000000,samples+1)
            if meta[0]>=5 and 50<=meta[1]<=2500 and meta[2]<25:
                regular=min(1000000,regular+1)
        score=0
        reasons=[]
        # Server-side independent indicators.
        if calls5>=70 and taps5>=7500 and rate5>=25:
            score+=35
            reasons.append("5分間の高頻度タップ")
        if calls30>=150 and taps30>=27000 and rate30>=15:
            score+=35
            reasons.append("30分間の継続的な高頻度タップ")
        if (current['cv'] is not None and current['cv']<0.035 and
            current['request_count']>=75 and current['duration_ms']>=120000):
            score+=20
            reasons.append("サーバー通信間隔の周期性")
        if samples>=8 and regular>=6 and regular/samples>=0.7:
            score+=15
            reasons.append("参考:ブラウザからの操作間隔の周期性")
        score=min(score,100)
        if current['score']>score:
            score=current['score']
            reasons=current['reasons'].split('、') if current['reasons'] else []
        reason_text='、'.join(reasons)
        peak=max(score,previous_score)
        peak_reason=reason_text if score>previous_score else old_reason
        flagged=now if score>=60 else d.get('flagged_at')
        # Event history is tiny and sparse: one event per 6h at most.
        if score>=60 and (not last_event or now-last_event>=EVENT_COOLDOWN_MS):
            db.execute(
                "INSERT INTO tap_monitor_events(player,detected_at,score,reasons,"
                "taps_1m,taps_5m,taps_30m,rate_5m,rate_30m,client_samples)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (player,now,score,reason_text,taps1,taps5,taps30,
                 round(rate5,2),round(rate30,2),samples))
            last_event=now
        db.execute(
            "INSERT INTO tap_monitor_state("
            "player,started_at,last_at,request_count,tap_count,gaps_json,"
            "score,reasons,flagged_at,avg_interval_ms,cv,rate,"
            "rollups_json,client_samples,client_regular_samples,last_event_at"
            ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(player) DO UPDATE SET "
            "started_at=excluded.started_at,last_at=excluded.last_at,"
            "request_count=excluded.request_count,tap_count=excluded.tap_count,"
            "gaps_json=excluded.gaps_json,score=excluded.score,"
            "reasons=excluded.reasons,flagged_at=excluded.flagged_at,"
            "avg_interval_ms=excluded.avg_interval_ms,cv=excluded.cv,"
            "rate=excluded.rate,rollups_json=excluded.rollups_json,"
            "client_samples=excluded.client_samples,"
            "client_regular_samples=excluded.client_regular_samples,"
            "last_event_at=excluded.last_event_at",
            (player,current['started_at'],current['last_at'],
             current['request_count'],current['tap_count'],
             json.dumps(current['gaps'],separators=(',',':')),
             peak,peak_reason,flagged,current['avg_interval_ms'],
             current['cv'],current['rate'],
             json.dumps(rollups,separators=(',',':')),samples,regular,last_event))
        db.execute("RELEASE SAVEPOINT tap_monitor_v2_safe")
    except Exception:
        try:
            db.execute("ROLLBACK TO SAVEPOINT tap_monitor_v2_safe")
            db.execute("RELEASE SAVEPOINT tap_monitor_v2_safe")
        except Exception:
            logging.exception("Tap monitor v2 savepoint recovery failed")
        logging.warning("Tap monitor v2 unavailable; legitimate tap remains unaffected")
