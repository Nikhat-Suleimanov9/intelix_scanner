"""
config.py - Load and validate runtime configuration.

Credentials are read from environment variables.
All other settings (region, output directory, poll timing) come from CLI arguments.

Required environment variables
-------------------------------
INTELIX_CLIENT_ID      - OAuth2 client ID issued by SophosLabs Intelix.
INTELIX_CLIENT_SECRET  - Matching client secret.

CLI arguments (defined in main.py)
------------------------------------
--region               - API region: us-east | de | au  (default: de)
--reports-dir          - Output directory for report files  (default: reports)
"""
import os
import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    region: str
    reports_dir: str


def load_config(args: argparse.Namespace) -> Config:
    """
    Build the full runtime config — credentials from env, rest from CLI args.

    Raises:
        EnvironmentError: If a required environment variable is missing or empty.
    """
    client_id = os.environ.get("INTELIX_CLIENT_ID", "").strip()
    client_secret = os.environ.get("INTELIX_CLIENT_SECRET", "").strip()

    missing = [name for name, val in [
        ("INTELIX_CLIENT_ID", client_id),
        ("INTELIX_CLIENT_SECRET", client_secret),
    ] if not val]

    if missing:
        raise EnvironmentError(
            f"Missing required environment variable(s): {', '.join(missing)}\n"
            "Set them before running:\n"
            "  export INTELIX_CLIENT_ID=<your-id>\n"
            "  export INTELIX_CLIENT_SECRET=<your-secret>"
        )

    return Config(
        client_id=client_id,
        client_secret=client_secret,
        region=args.region,
        reports_dir=args.reports_dir,
    )