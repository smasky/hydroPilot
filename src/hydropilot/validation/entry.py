from pathlib import Path

import yaml

from hydropilot.config.loader import ConfigPreparationError, prepare_config
from hydropilot.validation.diagnostics import Diagnostic, error


def validate_config(config_path: Path) -> list[Diagnostic]:
    yaml_file = Path(config_path).resolve()
    if not yaml_file.exists():
        return [error("config", f"Config file not found: {yaml_file}")]

    try:
        prepared = prepare_config(yaml_file)
    except ConfigPreparationError as exc:
        return exc.diagnostics
    except yaml.YAMLError as exc:
        return [error("config", f"Failed to parse YAML: {exc}")]
    except ValueError as exc:
        return [error("config", str(exc))]
    except FileNotFoundError as exc:
        return [error("config", str(exc))]
    return prepared.diagnostics
