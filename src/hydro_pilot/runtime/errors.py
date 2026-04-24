from dataclasses import dataclass


@dataclass
class RunError(Exception):
    stage: str       # params / subprocess / series / derived / evaluator / unknown
    code: str        # TIMEOUT / NONZERO_EXIT / SIZE_MISMATCH / EXPR_EVAL_FAILED / CLAMPED ...
    target: str      # simulation / tn / tn_r2 / objective_xxx
    message: str
    severity: str = "fatal"   # "fatal" / "warning"
    traceback: str = ""       # original exception traceback (optional)

    def __str__(self):
        return f"[{self.severity}] {self.stage}:{self.code}:{self.target}: {self.message}"
