"""Lossless V2 cutover verification for the actual game's economic shadow columns.

This module is READ ONLY. It does not enable V2, run a migration, or mutate balances.
Require an independently restored backup, frozen legacy writers, and a successful
full scan before a separate, deliberately coordinated cutover can be considered.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping

from sparse_exact_v1 import SparseExact
from v2_numeric_lossless_backfill import numeric_text_to_sparse


@dataclass(frozen=True)
class AuditSummary:
    rows: int
    columns: int
    values_checked: int


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not value or not value[0].isalpha():
        raise ValueError("Invalid SQL identifier")
    if not all(c.isascii() and (c.isalnum() or c == "_") for c in value):
        raise ValueError("Invalid SQL identifier")
    return '"' + value + '"'


def inspect_shadow_consistency(conn, columns: Mapping[str, tuple[str, ...]],
                               *, schema="hare_factory", batch_size=250):
    """Exhaustively compare legacy NUMERIC and S1 shadow values without floats.

    Uses small batches to avoid fetching a full production table into memory.
    Raises with a bounded description of the FIRST mismatch; never logs values,
    passwords, identifiers or user balances. An empty table is not proof of a
    populated migration; callers must also verify expected row counts.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 10000:
        raise ValueError("Invalid batch size")
    if not isinstance(columns, Mapping) or not columns:
        raise ValueError("No economic columns supplied")
    schema_sql=_identifier(schema)
    table_count=0
    row_count=0
    value_count=0
    for table, names in columns.items():
        table_sql=_identifier(table)
        if not isinstance(names, (tuple, list)) or not names:
            raise ValueError("Missing numeric column manifest")
        if len(set(names)) != len(names):
            raise ValueError("Duplicate numeric column")
        table_count += 1
        select_parts=[]
        for name in names:
            n=_identifier(name)
            select_parts.extend((n+"::text",_identifier(name+"_v2")))
        # Explicit ordering prevents a positional schema modification from
        # silently changing which numeric value is compared to its shadow.
        query="SELECT "+", ".join(select_parts)+" FROM "+schema_sql+"."+table_sql
        cursor=conn.execute(query)
        local_rows=0
        while True:
            batch=cursor.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                if len(row) != 2*len(names):
                    raise RuntimeError("Unexpected shadow audit query shape")
                local_rows += 1
                for index, name in enumerate(names):
                    legacy, shadow=row[2*index:2*index+2]
                    if legacy is None or shadow is None:
                        raise RuntimeError(
                            f"V2 shadow missing: {table}.{name} at scan row {local_rows}")
                    try:
                        old=numeric_text_to_sparse(legacy)
                        new=SparseExact.deserialize(shadow)
                        equal=old.compare(new)==0
                    except (ValueError,TypeError,OverflowError) as error:
                        raise RuntimeError(
                            f"V2 shadow invalid: {table}.{name} at scan row {local_rows}"
                        ) from error
                    if not equal:
                        raise RuntimeError(
                            f"V2 shadow drift: {table}.{name} at scan row {local_rows}")
                    value_count += 1
        row_count += local_rows
    return AuditSummary(rows=row_count,columns=table_count,values_checked=value_count)


def require_cutover_ready(conn, columns, *, backup_restored=False,
                          legacy_writers_frozen=False, expected_rows=None):
    """Fail closed; this check NEVER changes the live authoritative format.

    A passing audit is a precondition, NOT a production deployment approval.
    The caller must still test settlement, all writers, replay and rollback.
    """
    if backup_restored is not True:
        raise RuntimeError("Verified restored backup is required")
    if legacy_writers_frozen is not True:
        raise RuntimeError("Legacy writers must be frozen for cutover verification")
    if type(expected_rows) is not int or expected_rows <= 0:
        raise RuntimeError("Positive expected row count must be supplied")
    summary=inspect_shadow_consistency(conn,columns)
    if summary.rows != expected_rows:
        raise RuntimeError("V2 shadow row count changed during verification")
    return summary
