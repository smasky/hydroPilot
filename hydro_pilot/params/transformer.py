from typing import Optional

import numpy as np

from ..errors import RunError


class Transformer:
    """Handles X → P parameter transformation, decoupled from file writing."""

    def __init__(self, func_manager, transform_func: Optional[str] = None):
        self.func_manager = func_manager
        self.transform_func = transform_func

    def transform(self, X) -> np.ndarray:
        """Transform design variables X to physical parameters P.

        In direct mode (no transform_func), returns X as-is.
        In transform mode, calls the registered function.
        """
        X_flat = np.ravel(np.asarray(X, dtype=float))

        if not self.transform_func:
            return X_flat

        try:
            result = self.func_manager.call(self.transform_func, X_flat)

            if result is None:
                raise RunError(
                    stage="subprocess",
                    code="TRANSFORM_FUNC_ERROR",
                    target="transformation",
                    message="Transform function returned None."
                )
            if isinstance(result, dict):
                raise RunError(
                    stage="subprocess",
                    code="TRANSFORM_FUNC_ERROR",
                    target="transformation",
                    message="Transform function returned a dict, but configuration expects an array-like result."
                )

            return np.ravel(np.asarray(result, dtype=float))

        except RunError:
            raise
        except Exception as e:
            raise RunError(
                stage="subprocess",
                code="TRANSFORM_FUNC_EXCEPTION",
                target="transformation",
                message=f"Error during transformation: {str(e)}"
            )
