from abc import ABC, abstractmethod


class InstanceInitializer(ABC):
    """Protocol for components that need one-time setup on each model instance.

    Called exactly once per instance, after the project copy is created and
    before any run is executed.  Writers that write *static* file structure
    (headers, record skeletons, etc.) implement this so the per‑run phase
    only writes dynamic values.
    """

    @abstractmethod
    def initialize(self, instance_path: str) -> None:
        """Run one-time initialization on a single instance directory."""
