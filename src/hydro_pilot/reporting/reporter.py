import atexit
import csv
import queue
import sqlite3
import threading
import traceback
from pathlib import Path

from .records import (
    build_csv_fields,
    collect_error_entries,
    make_error_json,
    normalize_batch_run,
    parse_report_ids,
    record_status,
    sanitize_labels,
    to_scalar_or_nan,
)
from .serializers import series_blob, to_1d_float_list
from .storage import flush_buffers, setup_storage, write_error_log, write_jsonl


class RunReporter:
    def __init__(self, archivePath, xLabels, pLabels, cfg):
        self.cfg = cfg
        self.archivePath = Path(archivePath)
        self.archivePath.mkdir(parents=True, exist_ok=True)

        self.xLabels = sanitize_labels(xLabels)
        self.pLabels = sanitize_labels(pLabels) if pLabels else []

        self.dbPath = self.archivePath / "results.db"
        self.summaryCsv = self.archivePath / "summary.csv"
        self.errorJsonl = self.archivePath / "error.jsonl"
        self.errorLog = self.archivePath / "error.log"

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

    def _parseIds(self):
        self.allSeriesIds, self.allScalarIds, self.outSeriesIds = parse_report_ids(self.cfg)

    def _buildCsvFields(self):
        return build_csv_fields(self.allScalarIds, self.xLabels, self.pLabels)

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
            conn = sqlite3.connect(self.dbPath)
            csvFields = self._buildCsvFields()
            csvFile = open(self.summaryCsv, "a", newline="", encoding="utf-8-sig")
            csvWriter = setup_storage(
                conn, csvFile, csvFields,
                self.allScalarIds, self.xLabels, self.pLabels,
            )

            for sk in self.outSeriesIds:
                f = open(self.archivePath / f"{sk}.csv", "a", newline="", encoding="utf-8-sig")
                import csv as _csv
                seriesCsvHandlers[sk] = {"file": f, "writer": _csv.writer(f), "headerWritten": f.tell() > 0}

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

    def _processHoldingPen(
        self, holdingPen, readyIds, conn, csvFile, csvWriter,
        sDbBuf, sCsvBuf, serDbBuf, serCsvH, serCsvBuf,
        errDbBuf, jsonlFile, logFile,
        forceFlush=False,
    ):
        import numpy as np
        for rid in readyIds:
            item = holdingPen.pop(rid)
            batchId, runId = normalize_batch_run(item)
            status = record_status(item)

            baseInfo = [batchId, runId, status]
            scalarVals = []
            for key in self.allScalarIds:
                try:
                    val = to_scalar_or_nan(item.get(key, np.nan))
                except Exception:
                    val = np.nan
                scalarVals.append(val)

            xVals = to_1d_float_list(item.get("X", []))
            pVals = []
            if self.pLabels:
                pArr = to_1d_float_list(item.get("P", []) or [])
                for idx in range(len(self.pLabels)):
                    pVals.append(pArr[idx] if idx < len(pArr) else np.nan)

            dbRow = baseInfo + scalarVals + xVals + pVals
            sDbBuf.append(dbRow)
            sCsvBuf.append(list(dbRow))

            self._writeErrorEntries(
                batchId, runId, item.get("error"), item.get("warnings", []),
                errDbBuf, jsonlFile, logFile,
            )

            if status != "error":
                for sk in self.allSeriesIds:
                    if sk in item:
                        simData, blob = series_blob(item[sk])
                        serDbBuf.append((batchId, runId, sk, blob))
                        if sk in self.outSeriesIds and sk in serCsvBuf:
                            serCsvBuf[sk].append([batchId, runId] + simData.tolist())

        if (len(sDbBuf) >= self.flushInterval) or (forceFlush and len(sDbBuf) > 0):
            flush_buffers(
                conn, csvFile, csvWriter,
                sDbBuf, sCsvBuf, serDbBuf, serCsvH, serCsvBuf,
                errDbBuf, jsonlFile, logFile,
            )

    def _writeErrorEntries(self, batchId, runId, error, warnings,
                           errDbBuf, jsonlFile, logFile):
        for entry in collect_error_entries(error, warnings):
            ts, jsonObj = make_error_json(batchId, runId, entry)
            errDbBuf.append((
                batchId, runId,
                entry.get("severity", "fatal"),
                entry.get("stage", ""),
                entry.get("code", ""),
                entry.get("target", ""),
                entry.get("message", ""),
            ))
            write_jsonl(jsonlFile, jsonObj)
            write_error_log(logFile, ts, batchId, runId, entry)

    def _flush(self, conn, csvFile, csvWriter,
               summaryDbBuf, summaryCsvBuf,
               seriesDbBuf, seriesCsvHandlers, seriesCsvBuf,
               errorsDbBuf, jsonlFile, logFile):
        flush_buffers(
            conn, csvFile, csvWriter,
            summaryDbBuf, summaryCsvBuf,
            seriesDbBuf, seriesCsvHandlers, seriesCsvBuf,
            errorsDbBuf, jsonlFile, logFile,
        )

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
