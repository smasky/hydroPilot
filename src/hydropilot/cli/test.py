import argparse
from pathlib import Path

from hydropilot.testing.report import format_terminal_summary
from hydropilot.testing.runner import run_config_test


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a full HydroPilot config smoke test")
    parser.add_argument("config", help="Path to config YAML")
    args = parser.parse_args()

    result = run_config_test(Path(args.config))
    print(format_terminal_summary(result))
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
