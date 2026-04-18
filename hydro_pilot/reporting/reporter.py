import atexit
import csv
import json
import queue
import sqlite3
import threading
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np


class RunReporter:
    def __init__(self, backupPath, xLabels, pLabels, cfg):
        self.cfg = cfg
        self.backupPath = Path(backupPath)
        self.backupPath.mkdir(parents=True, exist_ok=True)

        self.xLabels = self._sanitizeLabels(xLabels)
        self.pLabels = self._sanitizeLabels(pLabels) if pLabels else []

        self.dbPath = self.backupPath / "results.db"
        self.summaryCsv = self.backupPath / "summary.csv"
        self.errorJsonl = self.backupPath / "error.jsonl"
        self.errorLog = self.backupPath / "error.log"

        self._parseIds()
        self.startRunId = 1

        # Reporter config
        repCfg = getattr(self.cfg, "reporter", None)
        self.flushInterval = int(getattr(repCfg, "flushInterval", 50)) if repCfg else 50
        self.holdingPenLimit = int(getattr(repCfg, "holdingPenLimit", 20)) if repCfg else 20
        if self.flushInterval <= 0:
            self.flushInterval = 50
        if self.holdingPenLimit <= 0:
            self.holdingPenLimit = 20

        # Thread infrastructure
        self._q = queue.Queue()
        self._stop = object()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._batchNo = 0
        self._lock = threading.Lock()
        self._crashEvent = threading.Event()
        self._stopped = False
        self._started = False

        atexit.register(self.close)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _sanitizeLabels(self, labels):
        cleaned = []
        seen = set()
        for i, x in enumerate(labels):
            name = str(x)
            name = name.replace("[", "_").replace("]", "_").replace(".", "_").strip()
            if not name:
                name = f"x_{i+1}"
            base = name
            suffix = 1
            while name in seen:
                suffix += 1
                name = f"{base}_{suffix}"
            seen.add(name)
            cleaned.append(name)
        return cleaned

    def _parseIds(self):
        # Series ids for DB storage
        self.allSeriesIds = [f"{k}_sim" for k in self.cfg.series_index.keys()]

        # Scalar ids: objectives + constraints + diagnostics + derived (ordered, deduplicated)
        orderedScalars = []
        seen = set()
        for oid in self.cfg.objectives.use:
            if oid not in seen:
                orderedScalars.append(oid)
                seen.add(oid)
        for cid in self.cfg.constraints.use:
            if cid not in seen:
                orderedScalars.append(cid)
                seen.add(cid)
        for did in self.cfg.diagnostics.use:
            if did not in seen:
                orderedScalars.append(did)
                seen.add(did)
        for d in self.cfg.derived:
            if d.id not in seen:
                orderedScalars.append(d.id)
                seen.add(d.id)
        self.allScalarIds = orderedScalars

        # Series CSV export list
        repCfg = getattr(self.cfg, "reporter", None)
        if repCfg:
            rawOutSeries = list(getattr(repCfg, "series", []))
            self.outSeriesIds = []
            for s in rawOutSeries:
                s = str(s)
                self.outSeriesIds.append(f"{s}_sim" if not s.endswith("_sim") else s)
        else:
            self.outSeriesIds = []

    def _buildCsvFields(self):
        """Build unified column list for summary CSV and DB."""
        fields = ["batch_id", "run_id", "status"]
        fields += self.allScalarIds
        fields += [f"X_{x}" for x in self.xLabels]
        if self.pLabels:
            fields += [f"P_{p}" for p in self.pLabels]
        return fields

    def _toScalarOrNan(self, value):
        if value is None:
            return np.nan
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                pass
        if isinstance(value, (list, tuple, np.ndarray)):
            arr = np.asarray(value)
            if arr.size == 0:
                return np.nan
            if arr.size == 1:
                return arr.reshape(-1)[0].item() if hasattr(arr.reshape(-1)[0], "item") else arr.reshape(-1)[0]
            raise ValueError(f"Expected scalar-compatible value, but got shape {arr.shape}")
        return value

    def _to1dFloatList(self, value):
        if value is None:
            return []
        arr = np.asarray(value, dtype=float).ravel()
        return arr.tolist()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        if self._stopped:
            raise RuntimeError("RunReporter is already closed and cannot be restarted.")
        if not self._started:
            self._thread.start()
            self._started = True

    def submit(self, record):
        if self._crashEvent.is_set():
            raise RuntimeError("RunReporter has crashed; cannot submit new records.")
        if self._stopped:
            raise RuntimeError("RunReporter is closed; cannot submit new records.")
        if not self._started:
            self.start()
        self._q.put(record)

    def newBatchId(self):
        with self._lock:
            self._batchNo += 1
            return self._batchNo

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        if self._stopped:
            return
        self._stopped = True
        if self._started:
            self._q.put(self._stop)
            self._thread.join()

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _worker(self):
        conn = None
        csvFile = None
        seriesCsvHandlers = {}
        jsonlFile = None
        logFile = None

        try:
            # --- DB setup ---
            conn = sqlite3.connect(self.dbPath)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")

            csvFields = self._buildCsvFields()

            # Summary table
            cols = ["batch_id INTEGER", "run_id INTEGER", "status TEXT"]
            cols += [f'"{sk}" REAL' for sk in self.allScalarIds]
            cols += [f'"X_{x}" REAL' for x in self.xLabels]
            if self.pLabels:
                cols += [f'"P_{p}" REAL' for p in self.pLabels]
            cursor.execute(f"CREATE TABLE IF NOT EXISTS summary ({', '.join(cols)})")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_summary_batch ON summary(batch_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_summary_status ON summary(status)")

            # Errors table
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS errors (
                    batch_id INTEGER, run_id INTEGER,
                    severity TEXT, stage TEXT, code TEXT, target TEXT, message TEXT
                )"""
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_errors_batch ON errors(batch_id)")

            # Series table
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS series (
                    batch_id INTEGER, run_id INTEGER,
                    series_id TEXT, data BLOB
                )"""
            )
            conn.commit()

            # --- CSV setup ---
            csvFile = open(self.summaryCsv, "a", newline="", encoding="utf-8-sig")
            csvWriter = csv.writer(csvFile)
            if csvFile.tell() == 0:
                csvWriter.writerow(csvFields)
                csvFile.flush()

            for sk in self.outSeriesIds:
                f = open(self.backupPath / f"{sk}.csv", "a", newline="", encoding="utf-8-sig")
                w = csv.writer(f)
                seriesCsvHandlers[sk] = {"file": f, "writer": w, "headerWritten": f.tell() > 0}

            # --- Error log setup ---
            jsonlFile = open(self.errorJsonl, "a", encoding="utf-8")
            logFile = open(self.errorLog, "a", encoding="utf-8")

            # --- Buffers ---
            summaryDbBuf = []
            summaryCsvBuf = []
            seriesDbBuf = []
            seriesCsvBuf = {sk: [] for sk in self.outSeriesIds}
            errorsDbBuf = []

            holdingPen = {}
            nextExpectedId = self.startRunId
            currentBatchId = -1

            # --- Main loop ---
            while True:
                item = self._q.get()
                try:
                    if item is self._stop:
                        remaining = sorted(holdingPen.keys())
                        self._processHoldingPen(
                            holdingPen, remaining, conn, csvFile, csvWriter,
                            summaryDbBuf, summaryCsvBuf,
                            seriesDbBuf, seriesCsvHandlers, seriesCsvBuf,
                            errorsDbBuf, jsonlFile, logFile,
                            forceFlush=True,
                        )
                        return

                    rid = item.get("i", -1)
                    rid = rid.item() if hasattr(rid, "item") else rid
                    rid = int(rid) + 1

                    bid = item.get("batch_id", -1)
                    bid = bid.item() if hasattr(bid, "item") else bid
                    bid = int(bid)

                    if bid > currentBatchId:
                        if holdingPen:
                            remaining = sorted(holdingPen.keys())
                            self._processHoldingPen(
                                holdingPen, remaining, conn, csvFile, csvWriter,
                                summaryDbBuf, summaryCsvBuf,
                                seriesDbBuf, seriesCsvHandlers, seriesCsvBuf,
                                errorsDbBuf, jsonlFile, logFile,
                                forceFlush=True,
                            )
                        currentBatchId = bid
                        nextExpectedId = self.startRunId
                        holdingPen.clear()

                    holdingPen[rid] = item

                    # Flush consecutive ready ids
                    readyIds = []
                    while nextExpectedId in holdingPen:
                        readyIds.append(nextExpectedId)
                        nextExpectedId += 1

                    # Holding pen overflow: flush all arrived records
                    if not readyIds and len(holdingPen) >= self.holdingPenLimit:
                        readyIds = sorted(holdingPen.keys())
                        nextExpectedId = readyIds[-1] + 1

                    if readyIds:
                        self._processHoldingPen(
                            holdingPen, readyIds, conn, csvFile, csvWriter,
                            summaryDbBuf, summaryCsvBuf,
                            seriesDbBuf, seriesCsvHandlers, seriesCsvBuf,
                            errorsDbBuf, jsonlFile, logFile,
                            forceFlush=False,
                        )
                finally:
                    self._q.task_done()

        except Exception:
            self._crashEvent.set()
            print("\nRUN REPORTER CRASHED")
            traceback.print_exc()
        finally:
            for f in [csvFile, jsonlFile, logFile]:
                try:
                    if f is not None:
                        f.close()
                except Exception:
                    pass
            for h in seriesCsvHandlers.values():
                try:
                    h["file"].close()
                except Exception:
                    pass
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Record processing
    # ------------------------------------------------------------------

    def _processHoldingPen(
        self, holdingPen, readyIds, conn, csvFile, csvWriter,
        sDbBuf, sCsvBuf, serDbBuf, serCsvH, serCsvBuf,
        errDbBuf, jsonlFile, logFile,
        forceFlush=False,
    ):
        for rid in readyIds:
            item = holdingPen.pop(rid)
            batchId = item.get("batch_id", -1)
            if hasattr(batchId, "item"):
                batchId = batchId.item()
            batchId = int(batchId)
            runId = item.get("i", -1)
            if hasattr(runId, "item"):
                runId = runId.item()
            runId = int(runId) + 1

            status = "ok"
            if "error" in item:
                status = "error"
            elif item.get("warnings"):
                status = "warning"

            # --- Build summary row ---
            baseInfo = [batchId, runId, status]

            # Scalar values
            scalarVals = []
            for key in self.allScalarIds:
                try:
                    val = self._toScalarOrNan(item.get(key, np.nan))
                except Exception:
                    val = np.nan
                scalarVals.append(val)

            # X parameters
            rawX = item.get("X", [])
            xVals = self._to1dFloatList(rawX)

            # P parameters
            pVals = []
            if self.pLabels:
                rawP = item.get("P", [])
                pArr = self._to1dFloatList(rawP) if rawP is not None else []
                for idx in range(len(self.pLabels)):
                    if idx < len(pArr):
                        pVals.append(pArr[idx])
                    else:
                        pVals.append(np.nan)

            dbRow = baseInfo + scalarVals + xVals + pVals
            sDbBuf.append(dbRow)
            sCsvBuf.append(list(dbRow))

            # --- Errors / warnings ---
            self._writeErrorEntries(
                batchId, runId, item.get("error"), item.get("warnings", []),
                errDbBuf, jsonlFile, logFile,
            )

            # --- Series data ---
            if status != "error":
                for sk in self.allSeriesIds:
                    if sk in item:
                        simData = np.asarray(item[sk], dtype=np.float32).ravel()
                        serDbBuf.append((batchId, runId, sk, sqlite3.Binary(simData.tobytes())))
                        if sk in self.outSeriesIds and sk in serCsvBuf:
                            serCsvBuf[sk].append([batchId, runId] + simData.tolist())

        if (len(sDbBuf) >= self.flushInterval) or (forceFlush and len(sDbBuf) > 0):
            self._flush(
                conn, csvFile, csvWriter,
                sDbBuf, sCsvBuf, serDbBuf, serCsvH, serCsvBuf,
                errDbBuf, jsonlFile, logFile,
            )

    def _writeErrorEntries(self, batchId, runId, error, warnings,
                           errDbBuf, jsonlFile, logFile):
        entries = []
        if error:
            entries.append(error)
        for w in warnings:
            if isinstance(w, dict):
                entries.append(w)
            else:
                # RunError object from warning collector
                entries.append({
                    "stage": w.stage, "code": w.code,
                    "target": w.target, "message": w.message,
                    "severity": w.severity, "traceback": getattr(w, "traceback", ""),
                })

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for e in entries:
            severity = e.get("severity", "fatal")
            stage = e.get("stage", "")
            code = e.get("code", "")
            target = e.get("target", "")
            msg = e.get("message", "")
            tb = e.get("traceback", "")

            # DB buffer
            errDbBuf.append((batchId, runId, severity, stage, code, target, msg))

            # JSON Lines
            jsonObj = {
                "ts": ts, "batch": batchId, "run": runId,
                "severity": severity, "stage": stage, "code": code,
                "target": target, "msg": msg,
            }
            if tb:
                jsonObj["tb"] = tb
            jsonlFile.write(json.dumps(jsonObj, ensure_ascii=False) + "\n")

            # Human-readable log
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

    # ------------------------------------------------------------------
    # Flush buffers to disk
    # ------------------------------------------------------------------

    def _flush(
        self, conn, csvFile, csvWriter,
        summaryDbBuf, summaryCsvBuf,
        seriesDbBuf, seriesCsvHandlers, seriesCsvBuf,
        errorsDbBuf, jsonlFile, logFile,
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
        # Flush error log files
        jsonlFile.flush()
        logFile.flush()
        conn.commit()

