from typing import Dict, Type

from .base import ModelTemplate

TEMPLATE_REGISTRY: Dict[str, Type[ModelTemplate]] = {}


def register_template(version: str, template_cls: Type[ModelTemplate]):
    """Register a model template for a given version string."""
    TEMPLATE_REGISTRY[version] = template_cls


def get_template(version: str) -> ModelTemplate:
    """Instantiate and return a template for the given version."""
    if version not in TEMPLATE_REGISTRY:
        available = ", ".join(sorted(TEMPLATE_REGISTRY.keys())) or "(none)"
        raise ValueError(
            f"Unknown model version '{version}'. "
            f"Available templates: {available}. "
            f"Use version='general' for manual configuration."
        )
    return TEMPLATE_REGISTRY[version]()


# Register built-in templates
from .swat.template import SwatTemplate
register_template("swat", SwatTemplate)
