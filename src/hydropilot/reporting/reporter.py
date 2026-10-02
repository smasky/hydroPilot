import atexit
from copy import deepcopy
import csv
from datetime import datetime
import hashlib
import json
import logging
from pathlib import Path
import queue
import sqlite3
import threading
import time

from .records import build_csv_fields, parse_report_ids, sanitize_labels
from .storage import exportStorage, setupStorage, writeRecord


logger = logging.getLogger(__name__)


class _FlushRequest:
    def __init__(self):
        self.done = threading.Event()


class RunReporter:
    """Persist stage snapshots in SQLite, then export committed data."""

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
        self.allSeriesIds, self.allScalarIds, self.outSeriesIds = parse_report_ids(cfg)
        self.derivedIds = [item.id for item in cfg.derived]
        self.fields = build_csv_fields(self.allScalarIds, self.xLabels, self.pLabels)
        self._reset_if_schema_changed()
        self.configJson = None
        self.configId = None
        if hasattr(cfg, "model_dump"):
            functionHashes = {
                name: hashlib.sha256(spec.file.read_bytes()).hexdigest()
                for name, spec in cfg.functions.items() if spec.file is not None
            }
            self.configJson = json.dumps({"config": cfg.model_dump(mode="json"),
                                          "functionHashes": functionHashes}, sort_keys=True)
            self.configId = hashlib.sha256(self.configJson.encode()).hexdigest()
        repCfg = getattr(cfg, "reporter", None)
        self.flushInterval = int(getattr(repCfg, "flushInterval", 50)) if repCfg else 50
        self.holdingPenLimit = int(getattr(repCfg, "holdingPenLimit", 20)) if repCfg else 20
        if self.flushInterval <= 0:
            self.flushInterval = 50
        if self.holdingPenLimit <= 0:
            self.holdingPenLimit = 20
        self._q = queue.Queue()
        self._stop = object()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._lock = threading.Lock()
        self._crashEvent = threading.Event()
        self._stopped = False
        self._started = False
        atexit.register(self.close)

    def _reset_if_schema_changed(self):
        actual = None
        if self.dbPath.exists():
            try:
                with sqlite3.connect(self.dbPath) as connection:
                    actual = [row[1] for row in connection.execute("PRAGMA table_info(summary)")]
            except sqlite3.Error:
                return
        elif self.summaryCsv.exists():
            with self.summaryCsv.open(newline="", encoding="utf-8-sig") as stream:
                actual = next(csv.reader(stream), [])
        if actual is not None and actual != self.fields:
            for path in (self.dbPath, self.summaryCsv, self.errorJsonl, self.errorLog):
                path.unlink(missing_ok=True)

    def _buildCsvFields(self):
        return list(self.fields)

    def start(self):
        with self._lock:
            if self._stopped:
                raise RuntimeError("RunReporter is already closed and cannot be restarted.")
            if not self._started:
                self._started = True
                self._thread.start()

    def submit(self, record):
        if record.get("archive_stage") == "post":
            allowed = set(self.allScalarIds + self.fields + ["i", "X", "P", "error", "postErrors", "warnings", "archive_stage"])
            record = {key: value for key, value in record.items() if key in allowed}
        snapshot = deepcopy(record)
        snapshot["config_id"] = self.configId
        with self._lock:
            if self._crashEvent.is_set():
                raise RuntimeError("RunReporter has crashed; cannot submit new records.")
            if self._stopped:
                raise RuntimeError("RunReporter is closed; cannot submit new records.")
            if not self._started:
                self._started = True
                self._thread.start()
            self._q.put(snapshot)

    def flush(self, timeout=30):
        request = _FlushRequest()
        with self._lock:
            if self._crashEvent.is_set() or self._stopped:
                raise RuntimeError("RunReporter is closed or has crashed.")
            if not self._started:
                self._started = True
                self._thread.start()
            self._q.put(request)
        deadline = time.monotonic() + timeout
        while not request.done.wait(0.05):
            if self._crashEvent.is_set():
                raise RuntimeError("RunReporter has crashed.")
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out flushing RunReporter.")
        if self._crashEvent.is_set():
            raise RuntimeError("RunReporter has crashed.")

    def close(self):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            if self._started:
                self._q.put(self._stop)
        if self._started:
            self._thread.join()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _export(self, connection):
        try:
            exportStorage(connection, self.archivePath, self.fields, self.outSeriesIds)
        except Exception as error:
            message = f"Could not export committed archive data: {error}"
            logger.warning("REPORTER_EXPORT_FAILED: %s", message)
            connection.execute("INSERT OR IGNORE INTO errors VALUES (?,?,?,?,?,?,?,?,?)", (
                -1, -1, "warning", "reporter", "REPORTER_EXPORT_FAILED", str(self.archivePath), message, "",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ))
            connection.commit()

    def _worker(self):
        connection = None
        try:
            connection = sqlite3.connect(self.dbPath)
            setupStorage(connection, self.fields)
            if self.configJson is not None:
                connection.execute("INSERT OR REPLACE INTO metadata VALUES (?,?)",
                                   (self.configId, self.configJson))
                connection.commit()
            updates = 0
            while True:
                try:
                    item = self._q.get(timeout=1)
                except queue.Empty:
                    if updates:
                        connection.commit()
                        self._export(connection)
                        updates = 0
                    continue
                try:
                    if item is self._stop or isinstance(item, _FlushRequest):
                        connection.commit()
                        self._export(connection)
                        updates = 0
                        if item is self._stop:
                            return
                    else:
                        writeRecord(connection, item, self.fields, self.allScalarIds, self.allSeriesIds, self.derivedIds)
                        updates += 1
                        if updates >= min(self.flushInterval, self.holdingPenLimit):
                            connection.commit()
                            self._export(connection)
                            updates = 0
                except Exception:
                    self._crashEvent.set()
                    raise
                finally:
                    if isinstance(item, _FlushRequest):
                        item.done.set()
                    self._q.task_done()
        except Exception:
            self._crashEvent.set()
            logger.exception("RUN REPORTER CRASHED")
        finally:
            if connection is not None:
                connection.close()
