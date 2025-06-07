import sys
from qmtl.sdk.runner import Runner
from tests.sample_strategy import SampleStrategy


def test_backtest(capsys):
    strategy = Runner.backtest(SampleStrategy, start_time="s", end_time="e")
    captured = capsys.readouterr().out
    assert "[BACKTEST] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)


def test_dryrun(capsys):
    strategy = Runner.dryrun(SampleStrategy)
    captured = capsys.readouterr().out
    assert "[DRYRUN] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)


def test_live(capsys):
    strategy = Runner.live(SampleStrategy)
    captured = capsys.readouterr().out
    assert "[LIVE] SampleStrategy" in captured
    assert isinstance(strategy, SampleStrategy)
