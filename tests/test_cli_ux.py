import subprocess
import sys


def test_cli_run_directory_conflict_is_actionable_without_traceback(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "existing.txt").write_text("occupied", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness.cli",
            "--profile",
            "demo",
            "--run-dir",
            str(run_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "use --resume" in result.stderr
    assert "choose a fresh --run-dir" in result.stderr
    assert "Traceback" not in result.stderr
