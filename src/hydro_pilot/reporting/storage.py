import csv
import json
import sqlite3


def setup_storage(conn, csvFile, csvFields, allScalarIds, xLabels, pLabels):
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA temp_store=MEMORY")

    cols = ["batch_id INTEGER", "run_id INTEGER", "status TEXT"]
    cols += [f'"{sk}" REAL' for sk in allScalarIds]
    cols += [f'"X_{x}" REAL' for x in xLabels]
    if pLabels:
        cols += [f'"P_{p}" REAL' for p in pLabels]
    cursor.execute(f"CREATE TABLE IF NOT EXISTS summary ({', '.join(cols)})")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summary_batch ON summary(batch_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_summary_status ON summary(status)")

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS errors (
            batch_id INTEGER, run_id INTEGER,
            severity TEXT, stage TEXT, code TEXT, target TEXT, message TEXT
        )"""
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_batch ON errors(batch_id)")

    cursor.execute(
        """CREATE TABLE IF NOT EXISTS series (
            batch_id INTEGER, run_id INTEGER,
            series_id TEXT, data BLOB
        )"""
    )
    conn.commit()

    csvWriter = csv.writer(csvFile)
    if csvFile.tell() == 0:
        csvWriter.writerow(csvFields)
        csvFile.flush()
    return csvWriter


def flush_buffers(
    conn,
    csvFile,
    csvWriter,
    summaryDbBuf,
    summaryCsvBuf,
    seriesDbBuf,
    seriesCsvHandlers,
    seriesCsvBuf,
    errorsDbBuf,
    jsonlFile,
    logFile,
):
    if summaryDbBuf:
        placeholders = ",".join(["?"] * len(summaryDbBuf[0]))
        conn.executemany(f"INSERT INTO summary VALUES ({placeholders})", summaryDbBuf)
        summaryDbBuf.clear()
    if summaryCsvBuf:
        csvWriter.writerows(summaryCsvBuf)
        csvFile.flush()
        summaryCsvBuf.clear()
    if seriesDbBuf:
        conn.executemany("INSERT INTO series VALUES (?, ?, ?, ?)", seriesDbBuf)
        seriesDbBuf.clear()
    for sk, rows in seriesCsvBuf.items():
        if rows:
            h = seriesCsvHandlers.get(sk)
            if h:
                if not h["headerWritten"]:
                    size = len(rows[0]) - 2
                    header = ["batch_id", "run_id"] + [f"V_{i+1}" for i in range(size)]
                    h["writer"].writerow(header)
                    h["headerWritten"] = True
                h["writer"].writerows(rows)
                h["file"].flush()
            rows.clear()
    if errorsDbBuf:
        conn.executemany(
            "INSERT INTO errors VALUES (?, ?, ?, ?, ?, ?, ?)", errorsDbBuf
        )
        errorsDbBuf.clear()
    jsonlFile.flush()
    logFile.flush()
    conn.commit()


def write_jsonl(jsonlFile, jsonObj):
    jsonlFile.write(json.dumps(jsonObj, ensure_ascii=False) + "\n")


def write_error_log(logFile, ts, batchId, runId, entry):
    severity = entry.get("severity", "fatal")
    stage = entry.get("stage", "")
    code = entry.get("code", "")
    target = entry.get("target", "")
    msg = entry.get("message", "")
    tb = entry.get("traceback", "")

    logFile.write(
        f"[{ts}] batch={batchId} run={runId} severity={severity.upper()} "
        f"stage={stage} code={code} target={target}\n"
        f"  message: {msg}\n"
    )
    if tb:
        logFile.write("  traceback:\n")
        for line in tb.strip().splitlines():
            logFile.write(f"    {line}\n")
    logFile.write("\n")
