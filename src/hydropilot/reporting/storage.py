import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

import numpy as np

from .records import collect_error_entries, normalize_batch_run, record_status, to_scalar_or_nan
from .serializers import decodeArray, encodeArray


STATE_FIELDS = ("sim_status", "obj_state", "con_state", "diag_state")


def quoteColumn(name):
    return '"' + name.replace('"', '""') + '"'


def readLastBatchId(archivePath):
    archive = Path(archivePath)
    database = archive / "results.db"
    if database.exists():
        try:
            with sqlite3.connect(database) as connection:
                value = connection.execute("SELECT MAX(batch_id) FROM summary").fetchone()[0]
                return int(value) if value is not None else 0
        except sqlite3.Error:
            pass
    summary = archive / "summary.csv"
    if not summary.exists():
        return 0
    try:
        with summary.open(newline="", encoding="utf-8-sig") as stream:
            values = []
            for row in csv.DictReader(stream):
                try:
                    values.append(int(row.get("batch_id", 0)))
                except (TypeError, ValueError):
                    continue
            return max(values, default=0)
    except OSError:
        return 0


def setupStorage(connection, fields):
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    columns = []
    for name in fields:
        kind = "INTEGER" if name in ("batch_id", "run_id") else "TEXT" if name in STATE_FIELDS + ("status",) else "REAL"
        columns.append(f"{quoteColumn(name)} {kind}")
    connection.execute(f"CREATE TABLE IF NOT EXISTS summary ({','.join(columns)}, PRIMARY KEY(batch_id, run_id))")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_summary_status ON summary(status)")
    connection.execute("""CREATE TABLE IF NOT EXISTS errors (
        batch_id INTEGER, run_id INTEGER, severity TEXT, stage TEXT, code TEXT,
        target TEXT, message TEXT, traceback TEXT, ts TEXT,
        UNIQUE(batch_id, run_id, severity, stage, code, target, message))""")
    for table in ("series", "derived"):
        connection.execute(f"""CREATE TABLE IF NOT EXISTS {table} (
            batch_id INTEGER, run_id INTEGER, series_id TEXT, dtype TEXT, shape TEXT, data BLOB,
            PRIMARY KEY(batch_id, run_id, series_id))""")
    connection.execute("""CREATE TABLE IF NOT EXISTS observations (
        obs_id TEXT PRIMARY KEY, series_id TEXT, dtype TEXT, shape TEXT, data BLOB)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS observation_refs (
        batch_id INTEGER, run_id INTEGER, series_id TEXT, obs_id TEXT,
        PRIMARY KEY(batch_id, run_id, series_id))""")
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
    connection.execute("""CREATE TABLE IF NOT EXISTS run_metadata (
        batch_id INTEGER, run_id INTEGER, value TEXT, PRIMARY KEY(batch_id, run_id))""")
    connection.commit()


def _scalar(value):
    try:
        result = to_scalar_or_nan(value)
        return None if np.isnan(result) else float(result)
    except (TypeError, ValueError):
        return None


def writeRecord(connection, item, fields, scalarIds, seriesIds, derivedIds):
    batchId, runId = normalize_batch_run(item)
    values = {key: _scalar(item[key]) if key in item else None for key in scalarIds}
    values.update(batch_id=batchId, run_id=runId, status=record_status(item))
    for prefix in ("X", "P"):
        array = np.asarray(item.get(prefix, []), dtype=float).ravel() if item.get(prefix) is not None else []
        labels = [key for key in fields if key.startswith(prefix + "_")]
        values.update({key: _scalar(array[i]) if i < len(array) else None for i, key in enumerate(labels)})
    values.update({key: item.get(key, "ok" if key == "sim_status" else "pending") for key in STATE_FIELDS})
    names = ','.join(map(quoteColumn, fields))
    updates = ','.join(f"{quoteColumn(key)}=excluded.{quoteColumn(key)}" for key in fields[2:])
    placeholders = ','.join('?' for _ in fields)
    connection.execute(f"INSERT INTO summary ({names}) VALUES ({placeholders}) "
                       f"ON CONFLICT(batch_id,run_id) DO UPDATE SET {updates}", [values[key] for key in fields])

    if item.get("archive_stage") != "post":
        for sid in seriesIds:
            if sid in item:
                dtype, shape, data = encodeArray(item[sid])
                connection.execute("INSERT OR REPLACE INTO series VALUES (?,?,?,?,?,?)",
                                   (batchId, runId, sid, dtype, shape, data))
            obsKey = sid.removesuffix(".sim") + ".obs"
            if obsKey in item and item[obsKey] is not None:
                dtype, shape, data = encodeArray(item[obsKey])
                obsId = hashlib.sha256(obsKey.encode() + dtype.encode() + shape.encode() + data).hexdigest()
                connection.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?)", (obsId, obsKey, dtype, shape, data))
                connection.execute("INSERT OR REPLACE INTO observation_refs VALUES (?,?,?,?)", (batchId, runId, obsKey, obsId))
        details = {"config_id": item.get("config_id"), "params": {
            key: value for key, value in item.items() if key.startswith("param.")
        }}
        connection.execute("INSERT OR REPLACE INTO run_metadata VALUES (?,?,?)",
                           (batchId, runId, json.dumps(details, default=lambda value: value.tolist() if isinstance(value, np.ndarray) else str(value))))
    for sid in derivedIds:
        if sid in item:
            dtype, shape, data = encodeArray(item[sid])
            connection.execute("INSERT OR REPLACE INTO derived VALUES (?,?,?,?,?,?)", (batchId, runId, sid, dtype, shape, data))
    entries = collect_error_entries(item.get("error"), item.get("warnings", []))
    for error in item.get("postErrors", []):
        entries.extend(collect_error_entries(error, []))
    for entry in entries:
        connection.execute("INSERT OR IGNORE INTO errors VALUES (?,?,?,?,?,?,?,?,?)", (
            batchId, runId, entry.get("severity", "fatal"), entry.get("stage", ""),
            entry.get("code", ""), entry.get("target", ""), entry.get("message", ""),
            entry.get("traceback", ""), datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))


def _atomicWrite(path, write):
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("w", newline="", encoding="utf-8") as stream:
            write(stream)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def exportStorage(connection, archive, fields, outSeriesIds):
    def summary(stream):
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(connection.execute(
            f"SELECT {','.join(map(quoteColumn, fields))} FROM summary ORDER BY batch_id, run_id"))
    _atomicWrite(archive / "summary.csv", summary)
    for sid in outSeriesIds:
        rows = connection.execute("SELECT batch_id,run_id,dtype,shape,data FROM series WHERE series_id=? ORDER BY batch_id,run_id", (sid,)).fetchall()
        width = max((decodeArray(data, dtype, shape).size for _, _, dtype, shape, data in rows), default=0)
        def series(stream):
            writer = csv.writer(stream)
            writer.writerow(["batch_id", "run_id"] + [f"V_{i+1}" for i in range(width)])
            for batchId, runId, dtype, shape, data in rows:
                values = decodeArray(data, dtype, shape).ravel().tolist()
                writer.writerow([batchId, runId] + values + [""] * (width - len(values)))
        _atomicWrite(archive / (sid + ".csv"), series)
    errors = connection.execute("SELECT batch_id,run_id,severity,stage,code,target,message,traceback,ts FROM errors ORDER BY rowid").fetchall()
    def errorJson(stream):
        for batchId, runId, severity, stage, code, target, message, traceback, timestamp in errors:
            row = dict(ts=timestamp, batch=batchId, run=runId, severity=severity, stage=stage, code=code, target=target, msg=message)
            if traceback:
                row["tb"] = traceback
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    def errorLog(stream):
        for batchId, runId, severity, stage, code, target, message, traceback, timestamp in errors:
            stream.write(f"[{timestamp}] batch={batchId} run={runId} severity={severity.upper()} stage={stage} code={code} target={target}\n  message: {message}\n")
            if traceback:
                stream.write("  traceback:\n" + "".join("    " + line + "\n" for line in traceback.splitlines()))
            stream.write("\n")
    _atomicWrite(archive / "error.jsonl", errorJson)
    _atomicWrite(archive / "error.log", errorLog)
