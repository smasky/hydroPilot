import atexit
import signal

from ..reporting.reporter import RunReporter
from .executor import Executor
from .workspace import Workspace


class Session:
    def __init__(self, cfg, cfg_path: str):
        self.cfg = cfg
        self.cfgPath = cfg_path
        self._closed = False

        self.workspace = Workspace(cfg, cfg_path)
        self.executor = Executor(cfg, self.workspace, reporter=None)

        pLabels = []
        if self.cfg.parameters.transformer:
            pLabels = [p.name for p in self.cfg.parameters.physical]
        self.nInput = self.executor.nInput
        self.xLabels = self.executor.xLabels
        self.varType = self.executor.varType
        self.varSet = self.executor.varSet
        self.ub = self.executor.ub
        self.lb = self.executor.lb
        self.nOutput = self.executor.nOutput
        self.optType = self.executor.optType
        self.nConstraints = self.executor.nConstraints
        self.optSign = self.executor.optSign
        self.runPath = self.workspace.runPath
        self.backupPath = self.workspace.backupPath

        self.reporter = RunReporter(self.workspace.backupPath, self.xLabels, pLabels, self.cfg)
        self.reporter.start()
        self.executor.reporter = self.reporter

        atexit.register(self._cleanup_on_exit)
        try:
            signal.signal(signal.SIGINT, self._handle_termination)
            signal.signal(signal.SIGTERM, self._handle_termination)
        except Exception:
            pass

    def evaluate(self, X):
        return self.executor.evaluate(X)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.reporter is not None:
            try:
                self.reporter.close()
            except Exception as e:
                print(f"[Session.close] reporter.close() failed: {e}")
        try:
            self.workspace.cleanup_instances()
        except Exception as e:
            print(f"[Session.close] instance cleanup failed: {e}")
            print("Please clean instance folders manually if needed.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _cleanup_on_exit(self):
        try:
            self.close()
        except Exception as e:
            print(f"[Session._cleanup_on_exit] cleanup failed: {e}")

    def _handle_termination(self, signum, frame):
        try:
            print(f"[Session] Received signal {signum}, cleaning instance folders...")
            self.close()
        except Exception as e:
            print(f"[Session._handle_termination] cleanup failed: {e}")
        raise SystemExit(128 + signum)
