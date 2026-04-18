from ..params.manager import ParamManager
from ..series.extractor import SeriesExtractor
from ..evaluation.evaluator import Evaluator
from ..evaluation.func_manager import FunctionManager
from ..runner.base import ModelRunner
from ..runner.subprocess_runner import SubprocessRunner


class ModelAdapter:
    """Aggregates Writer, Runner, Reader into a single interface.

    SimModel interacts with this adapter instead of concrete implementations.
    For 'general' mode, components are assembled from config.
    Future model templates (swat, vic, etc.) will provide pre-configured adapters.
    """

    def __init__(self, cfg, backupPath):
        self.cfg = cfg

        # Function manager (shared by params, series, evaluator)
        self.functionManager = FunctionManager(cfg)

        # Params layer (includes Transformer + WriterDispatch)
        self.paramManager = ParamManager(cfg, self.functionManager, backupPath)

        # Runner layer
        self.runner: ModelRunner = SubprocessRunner()

        # Series extraction layer
        self.seriesExtractor = SeriesExtractor(cfg, self.functionManager)

        # Evaluation layer
        self.evaluator = Evaluator(cfg, self.functionManager)

    def write_params(self, workPath: str, X, context: dict) -> None:
        """Write parameter values to model input files."""
        self.paramManager.setValues(workPath, X, context)

    def run_model(self, workPath: str) -> int:
        """Execute the model."""
        return self.runner.run(
            workPath,
            self.cfg.basic.command,
            self.cfg.basic.timeout,
        )

    def read_results(self, workPath: str, context: dict) -> dict:
        """Extract series data from model output."""
        return self.seriesExtractor.extract_all(workPath, context)

    def evaluate(self, context: dict) -> dict:
        """Compute derived metrics, objectives, constraints, diagnostics."""
        return self.evaluator.evaluate_all(context)

    def get_physical_params(self, X):
        """Return the transformed physical parameter array P."""
        return self.paramManager.getPhysicalParams(X)

    def get_param_info(self):
        return self.paramManager.getParamInfo()

    def get_evaluation_info(self):
        return self.evaluator.get_evaluation_info()
