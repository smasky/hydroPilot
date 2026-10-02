from dataclasses import asdict, dataclass


@dataclass
class RunError(Exception):
    stage: str
    code: str
    target: str
    message: str
    severity: str = "fatal"
    traceback: str = ""

    def __str__(self):
        return f"[{self.severity}] {self.stage}:{self.code}:{self.target}: {self.message}"

    def to_dict(self) -> dict:
        return asdict(self)

    def __deepcopy__(self, memo):
        result = type(self)(**self.to_dict())
        memo[id(self)] = result
        return result
