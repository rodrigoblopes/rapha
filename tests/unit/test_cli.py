"""CLI smoke tests — the parser must build and format help without crashing.

A raw `%` in an argparse help string (e.g. `%RAPHA_HOME%`) makes `--help` raise
ValueError at format time. That is invisible until someone runs --help, so it gets
its own test.
"""

import pytest

from rapha.cli import build_parser


def test_the_parser_builds():
    assert build_parser() is not None


@pytest.mark.parametrize(
    "command",
    ["login", "sync", "extract", "assess", "plan", "push", "report", "serve"],
)
def test_top_level_and_each_subcommand_format_help(command, capsys):
    parser = build_parser()

    # Top-level --help
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    capsys.readouterr()

    # Each subcommand's --help — this is what a raw % in a help string breaks.
    with pytest.raises(SystemExit):
        parser.parse_args([command, "--help"])
    out = capsys.readouterr().out
    assert command in out or "usage" in out.lower()


def test_a_missing_command_errors_cleanly():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
