from dataclasses import dataclass

from ..evaluation.evaluator import Evaluator
from ..evaluation.func_manager import FunctionManager
from ..io.runners.base import ModelRunner
from ..io.runners.subprocess_runner import SubprocessRunner
from ..params import ParamApplier, ParamSpace, ParamWritePlan
from ..series import ObsStore, SeriesExtractor, SeriesPlan


@dataclass
class ExecutionServices:
    functionManager: FunctionManager
    paramSpace: ParamSpace
    paramWritePlan: ParamWritePlan
    paramApplier: ParamApplier
    seriesPlan: SeriesPlan
    obsStore: ObsStore
    runner: ModelRunner
    seriesExtractor: SeriesExtractor
    evaluator: Evaluator

    @classmethod
    def from_config(cls, cfg) -> "ExecutionServices":
        function_manager = FunctionManager(cfg)
        param_space = ParamSpace(cfg.parameters.design)
        param_write_plan = ParamWritePlan(cfg)
        param_applier = ParamApplier(cfg, function_manager, param_write_plan)
        series_plan = SeriesPlan(cfg.series)
        obs_store = ObsStore(series_plan)
        runner: ModelRunner = SubprocessRunner()
        series_extractor = SeriesExtractor(cfg, function_manager, series_plan, obs_store)
        evaluator = Evaluator(cfg, function_manager)
        return cls(
            functionManager=function_manager,
            paramSpace=param_space,
            paramWritePlan=param_write_plan,
            paramApplier=param_applier,
            seriesPlan=series_plan,
            obsStore=obs_store,
            runner=runner,
            seriesExtractor=series_extractor,
            evaluator=evaluator,
        )
