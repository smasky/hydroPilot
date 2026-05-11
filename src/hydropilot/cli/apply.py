import argparse

from hydropilot.api.apply import apply_from_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply HydroPilot parameters to a project copy")
    parser.add_argument("apply_yaml", help="Path to apply YAML")
    args = parser.parse_args()

    mode, target = apply_from_yaml(args.apply_yaml)
    print(f"Applied {mode} parameters to: {target}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())