"""Exact V2 read projections for rankings, admin dashboard, and time-series.

No writes and no monetary floating-point conversion. This only adapts legacy
numeric results to the versioned S1 wire format; V2-native settlement has not
yet been switched on.
"""
from v2_numeric_lossless_backfill import numeric_text_to_sparse

METRICS=("manufactured","revenue","net_profit")
CASH_FIELDS=("cash","manufactured","revenue","net_profit")
MARKET_FIELDS=("offered","sold","revenue","inventory","cost")
DATA_FIELDS=("amount",)


def _s1(value):
    if value is None:
        return None
    if type(value) in (int,str) or value.__class__.__name__=="Decimal":
        return numeric_text_to_sparse(str(value)).serialize()
    raise ValueError("Unexpected financial data type; refuse lossy conversion")


def _fields(row,columns):
    copied=dict(row)
    for key in columns:
        if key in copied and copied[key] is not None:
            copied[key]=_s1(copied[key])
    return copied


def rankings_projection(source):
    result={}
    for metric in METRICS:
        if metric not in source:
            raise ValueError("Ranking metric not supplied: "+metric)
        board=source[metric]
        result[metric]={
            "metric":metric,
            "individual":[_fields(row,(metric,)) for row in board["individual"]],
            "classes":[_fields(row,(metric,)) for row in board["classes"]],
        }
    return {"format":"S1","authoritative":"legacy_numeric","rankings":result}


def dashboard_projection(source):
    result=dict(source)
    result["format"]="S1"
    result["authoritative"]="legacy_numeric"
    result["players"]=[]
    for player in source["players"]:
        row=_fields(player,CASH_FIELDS)
        row["stock"]=[_fields(stock,("quantity",)) for stock in player.get("stock",[])]
        result["players"].append(row)
    result["pending"]=[_fields(listing,("quantity","price")) for listing in source["pending"]]
    result["market"]=[_fields(row,MARKET_FIELDS) for row in source["market"]]
    result["summary"]=_fields(source["summary"],("manufactured","revenue","net_profit"))
    result["rankings"]=rankings_projection(source["rankings"])["rankings"]
    return result


def data_projection(source):
    result=dict(source)
    result["format"]="S1"
    result["authoritative"]="legacy_numeric"
    result["timeline"]=[_fields(row,MARKET_FIELDS) for row in source.get("timeline",[])]
    if "breakdown" in source:
        breakdown=dict(source["breakdown"])
        for category in ("income","expense"):
            if category in breakdown:
                breakdown[category]=[_fields(row,DATA_FIELDS) for row in breakdown[category]]
        result["breakdown"]=breakdown
    return result
