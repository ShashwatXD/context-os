"""CLI shim supporting `python -m app.cli demo seed` and `python -m app.cli demo run`."""

import sys
from app.interfaces.cli.demo_cli import seed_demo, run_scenario
import asyncio


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "demo":
        print("Usage: python -m app.cli demo [seed|run]")
        sys.exit(1)

    subcmd = sys.argv[2].lower()
    if subcmd == "seed":
        asyncio.run(seed_demo())
    elif subcmd == "run":
        asyncio.run(run_scenario())
    else:
        print(f"Unknown subcommand: '{subcmd}'. Choose 'seed' or 'run'.")


if __name__ == "__main__":
    main()

