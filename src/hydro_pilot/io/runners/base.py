from collections.abc import Sequence
from abc import ABC, abstractmethod


class ModelRunner(ABC):
    """Abstract interface for executing a model."""

    @abstractmethod
    def run(self, work_path: str, command: str | Sequence[str], timeout: int) -> int:
        """Execute the model in the given working directory.

        Args:
            work_path: Working directory for the model run.
            command: Command string or list to execute.
            timeout: Timeout in seconds (-1 for no timeout).

        Returns:
            Process return code.

        Raises:
            RunError: On timeout or non-zero exit.
        """
