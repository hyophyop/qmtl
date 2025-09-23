import os
import subprocess
import sys
from pathlib import Path


def test_init_wheel(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "dist"
    project_dir = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["uv", "build", "--wheel", str(project_dir), "-o", str(wheel_dir)],
        check=True,
        cwd=project_dir,
    )
    wheel = next(wheel_dir.glob("qmtl-*.whl"))
    env_dir = tmp_path / "venv"
    subprocess.run(["uv", "venv", str(env_dir)], check=True)
    bin_dir = "Scripts" if sys.platform == "win32" else "bin"
    python = env_dir / bin_dir / "python"
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--no-deps",
            str(wheel),
            "--python",
            str(python),
        ],
        check=True,
    )
    qmtl = env_dir / bin_dir / "qmtl"
    dest = tmp_path / "proj"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    extra_paths = [str(Path(path)) for path in sys.path if path]
    if existing:
        extra_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(extra_paths)
    subprocess.run(
        [str(qmtl), "init", "--with-sample-data", "--path", str(dest)],
        check=True,
        env=env,
    )
    assert (dest / "data" / "sample_ohlcv.csv").is_file()
    assert (dest / "notebooks" / "strategy_analysis_example.ipynb").is_file()
