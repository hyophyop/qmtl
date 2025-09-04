# tests/e2e/world_smoke/scripts/run_world.py
import os, subprocess, sys


def main():
    if len(sys.argv) < 3:
        print("usage: run_world.py <WORLD_ID> <DURATION_SEC>", file=sys.stderr)
        sys.exit(2)
    world_id = sys.argv[1]
    duration = sys.argv[2]
    env = os.environ.copy()
    env["WORLD_ID"] = world_id
    env["DURATION_SEC"] = duration
    cmd = [sys.executable, "tests/e2e/world_smoke/strategies/mean_rev.py"]
    subprocess.check_call(cmd, env=env)


if __name__ == "__main__":
    main()

