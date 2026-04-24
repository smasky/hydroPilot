from ..config.loader import load_config
from ..runtime.session import Session


class SimModel:
    def __init__(self, cfgPath: str):
        self.cfgPath = cfgPath
        self.cfg = load_config(cfgPath)
        self.session = Session(self.cfg, cfgPath)

        self.nInput = self.session.nInput
        self.xLabels = self.session.xLabels
        self.varType = self.session.varType
        self.varSet = self.session.varSet
        self.ub = self.session.ub
        self.lb = self.session.lb
        self.nOutput = self.session.nOutput
        self.optType = self.session.optType
        self.nConstraints = self.session.nConstraints
        self.optSign = self.session.optSign
        self.runPath = self.session.runPath
        self.backupPath = self.session.backupPath

    def evaluate(self, X):
        return self.session.evaluate(X)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
