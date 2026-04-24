import argparse
from pathlib import Path

from hydro_pilot.validation.entry import validate_config
from hydro_pilot.validation.diagnostics import has_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a hydroPilot config file")
    parser.add_argument("config", help="Path to config YAML")
    args = parser.parse_args()

    diagnostics = validate_config(Path(args.config))
    for item in diagnostics:
        line = f"{item.level.upper()} {item.path}: {item.message}"
        if item.suggestion:
            line += f" Suggestion: {item.suggestion}"
        print(line)

    failed = has_error(diagnostics)
    if not diagnostics:
        print(f"Validation passed: {args.config}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
