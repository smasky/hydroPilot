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

        pLabels = self._physical_parameter_labels(self.cfg)
        self.reporter = RunReporter(self.workspace.archivePath, self.xLabels, pLabels, self.cfg)
        self.reporter.start()
        self.executor.reporter = self.reporter

        atexit.register(self._cleanup_on_exit)
        try:
            signal.signal(signal.SIGINT, self._handle_termination)
            signal.signal(signal.SIGTERM, self._handle_termination)
        except Exception:
            pass

    @property
    def nInput(self):
        return self.executor.nInput

    @property
    def xLabels(self):
        return self.executor.xLabels

    @property
    def varType(self):
        return self.executor.varType

    @property
    def varSet(self):
        return self.executor.varSet

    @property
    def ub(self):
        return self.executor.ub

    @property
    def lb(self):
        return self.executor.lb

    @property
    def nOutput(self):
        return self.executor.nOutput

    @property
    def optType(self):
        return self.executor.optType

    @property
    def nConstraints(self):
        return self.executor.nConstraints

    @property
    def optSign(self):
        return self.executor.optSign

    @property
    def runPath(self):
        return self.workspace.runPath

    @property
    def archivePath(self):
        return self.workspace.archivePath

    @staticmethod
    def _physical_parameter_labels(cfg):
        return [p.name for p in cfg.parameters.physical]

    def run(self, X):
        return self.executor.run(X)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.reporter is not None:
            try:
                self.reporter.close()
            except Exception as e:
                print(f"[Session.close] reporter.close() failed: {e}")
        if not self.cfg.basic.keepInstances:
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
