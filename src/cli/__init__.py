"""CLI entry points for operator tooling.

The ``therapyrag-admin`` script dispatches to the subcommands in
:mod:`src.cli.admin` — access reviews, retention purges, and related
SOC 2 / HIPAA operator flows. Kept separate from the main FastAPI
entry point so the app image doesn't drag argparse into request paths.
"""
