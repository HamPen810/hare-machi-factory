"""Fail-closed readiness audit for actual economic V2 schema.

Read-only validation, not a migration and not an authorization to cut over.
Every required legacy NUMERIC field must retain its original type and have
an additional TEXT field before the full shadow-value audit can run.
"""
from v2_shadow_schema_manifest import ECONOMIC_COLUMNS


def assess_schema(columns):
    """Return deterministic blockers from {(table,column): data_type} metadata."""
    if not isinstance(columns,dict):
        raise TypeError("Expected verified database column metadata")
    blockers=[]
    for table, names in ECONOMIC_COLUMNS.items():
        for name in names:
            old=columns.get((table,name))
            new=columns.get((table,name+"_v2"))
            if old is None:
                blockers.append("missing legacy column: "+table+"."+name)
            elif old.lower() != "numeric":
                blockers.append("legacy type changed: "+table+"."+name)
            if new is None:
                blockers.append("missing V2 column: "+table+"."+name+"_v2")
            elif new.lower() != "text":
                blockers.append("V2 column not TEXT: "+table+"."+name+"_v2")
    return blockers


def require_schema_ready(columns):
    blockers=assess_schema(columns)
    if blockers:
        raise RuntimeError("V2 schema cutover blocked: "+str(len(blockers))+
                           " requirement(s) unmet. First: "+blockers[0])
    return True


# Execute this statement using a restricted read-only account. Never include
# credentials, row values, or passwords in audit reports.
READ_ONLY_COLUMNS_SQL = (
    "SELECT table_name,column_name,data_type "
    "FROM information_schema.columns "
    "WHERE table_schema='hare_factory'"
)


def rows_to_columns(rows):
    result={}
    for row in rows:
        if isinstance(row,dict):
            table,name,kind=(row["table_name"],row["column_name"],row["data_type"])
        else:
            table,name,kind=row
        key=(table,name)
        if key in result:
            raise ValueError("Duplicate database column entry")
        result[key]=kind
    return result
