from .apply import apply_design_params, apply_physical_params
from ..config.loader import load_config
from ..runtime.session import Session


class SimModel:
    def __init__(self, cfgPath: str):
        self.cfgPath = cfgPath
        self.cfg = load_config(cfgPath)
        self.session = Session(self.cfg, cfgPath)

    @property
    def nInput(self):
        return self.session.nInput

    @property
    def xLabels(self):
        return self.session.xLabels

    @property
    def varType(self):
        return self.session.varType

    @property
    def varSet(self):
        return self.session.varSet

    @property
    def ub(self):
        return self.session.ub

    @property
    def lb(self):
        return self.session.lb

    @property
    def nOutput(self):
        return self.session.nOutput

    @property
    def optType(self):
        return self.session.optType

    @property
    def nConstraints(self):
        return self.session.nConstraints

    @property
    def optSign(self):
        return self.session.optSign

    @property
    def runPath(self):
        return self.session.runPath

    @property
    def archivePath(self):
        return self.session.archivePath

    def run(self, X):
        return self.session.run(X)

    def apply_design(self, X, out_dir):
        return apply_design_params(self.cfg, X, out_dir)

    def apply_params(self, P, out_dir):
        return apply_physical_params(self.cfg, P, out_dir)

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
