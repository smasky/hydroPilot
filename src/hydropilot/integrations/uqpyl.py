from UQPyL.problem import Eval, Problem
from ..api.sim_model import SimModel


class UQPyLAdapter(Problem):
    """Wraps SimModel as a UQPyL Problem via composition."""

    def __init__(self, cfgPath: str):
        self.model = SimModel(cfgPath)

        super().__init__(
            nInput=self.model.nInput,
            nObj=self.model.nOutput,
            nCon=self.model.nConstraints,
            varType=self.model.varType,
            varSet=self.model.varSet,
            ub=self.model.ub,
            lb=self.model.lb,
            xLabels=self.model.xLabels,
            optType=self.model.optType,
            evaluate=self._evaluate,
        )

    def _evaluate(self, X):
        result = self.model.run(X)
        return Eval(objs=result.objs, cons=result.cons)

    def close(self):
        self.model.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
