"""vbench — the vmem experiment harness.

Config-driven, one job per module: config (discovery/schema), server (vmem_server
lifecycle), footprint (measure peak vpages), runner (run one bench x condition),
collect (aggregate). The CLI (cli.py) composes them into verbs. No monolith.
"""
__version__ = "0.1"
