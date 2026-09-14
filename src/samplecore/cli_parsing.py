from __future__ import annotations

import argparse


class DefaultsHelpFormatter(argparse.HelpFormatter):
    """Help that names each option's default beside it, wherever leaving the option out picks a value."""

    def _get_help_string(self, action: argparse.Action) -> str | None:
        unstated = action.default is None or action.default is False or action.default == argparse.SUPPRESS
        if action.help is None or unstated or not action.option_strings or "%(default)" in action.help:
            return action.help
        return f"{action.help} (default: %(default)s)"


def command_parser(*, prog: str, description: str) -> argparse.ArgumentParser:
    """A command's own parser, whose help names the default of every option that has one."""
    return argparse.ArgumentParser(prog=prog, description=description, formatter_class=DefaultsHelpFormatter)


def add_subcommand(
    commands: argparse._SubParsersAction[argparse.ArgumentParser], name: str, *, summary: str
) -> argparse.ArgumentParser:
    """A subcommand's parser, its summary shown in the listing and atop its own help, which names every default."""
    return commands.add_parser(name, help=summary, description=summary, formatter_class=DefaultsHelpFormatter)
