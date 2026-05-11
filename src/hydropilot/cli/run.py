import argparse

from hydropilot.api.run import format_run_summary, run_from_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HydroPilot once from a run YAML")
    parser.add_argument("run_yaml", help="Path to run YAML")
    args = parser.parse_args()

    _mode, result = run_from_yaml(args.run_yaml)
    print(format_run_summary(result))
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
