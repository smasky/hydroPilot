from UQPyL.problem import Problem
from ..api.sim_model import SimModel


class UQPyLAdapter(Problem):
    """Wraps SimModel as a UQPyL Problem via composition."""

    def __init__(self, cfgPath: str):
        self.model = SimModel(cfgPath)

        super().__init__(
            nInput=self.model.nInput,
            nOutput=self.model.nOutput,
            varType=self.model.varType,
            varSet=self.model.varSet,
            ub=self.model.ub,
            lb=self.model.lb,
            xLabels=self.model.xLabels,
            optType=self.model.optType,
        )

    def evaluate(self, X):
        result = self.model.run(X)
        return {"objs": result.objs, "cons": result.cons}

    def objFunc(self, X):
        return self.evaluate(X)["objs"]

    def conFunc(self, X):
        return self.evaluate(X)["cons"]

    def close(self):
        self.model.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
