import subprocess
import sys
from pathlib import Path


def test_qmtl_init_after_wheel_install(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "dist"
    wheel_dir.mkdir()
    build_py = Path(sys.base_prefix) / "bin" / "python3"
    subprocess.run([build_py, "-m", "pip", "wheel", ".", "-w", str(wheel_dir)], check=True)

    wheel = next(wheel_dir.glob("qmtl-*.whl"))
    env_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(env_dir)], check=True)
    env_python = env_dir / "bin" / "python"
    if not env_python.exists():
        env_python = env_dir / "Scripts" / "python.exe"
    subprocess.run([env_python, "-m", "pip", "install", str(wheel)], check=True)

    proj = tmp_path / "proj"
    qmtl_cli = env_dir / ("Scripts" if env_python.name.endswith("python.exe") else "bin") / "qmtl"
    subprocess.run([qmtl_cli, "init", "--path", str(proj)], check=True)
    assert (proj / "qmtl.yml").is_file()
    assert (proj / "strategy.py").is_file()
