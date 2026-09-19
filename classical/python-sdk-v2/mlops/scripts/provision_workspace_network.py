from __future__ import annotations

import argparse
import subprocess
import time

TRANSIENT_PERMISSION_MESSAGES = (
    "required permissions to read and approve private endpoint connections",
    "permissions were recently granted",
)


def provision_network(
    resource_group: str,
    workspace_name: str,
    attempts: int,
    interval_seconds: int,
) -> None:
    command = [
        "az",
        "ml",
        "workspace",
        "provision-network",
        "--resource-group",
        resource_group,
        "--name",
        workspace_name,
        "--only-show-errors",
    ]
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if completed.returncode == 0:
            print("Workspace managed network provisioned successfully.")
            return
        diagnostic = "\n".join((completed.stdout, completed.stderr)).strip()
        normalized = diagnostic.lower()
        transient = any(
            message in normalized for message in TRANSIENT_PERMISSION_MESSAGES
        )
        if not transient or attempt == attempts:
            raise RuntimeError(
                "Workspace managed network provisioning failed"
                f" after {attempt} attempt(s):\n{diagnostic}"
            )
        print(
            "Workspace network approver roles are not effective yet; "
            f"retrying in {interval_seconds} seconds "
            f"({attempt}/{attempts})."
        )
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--interval-seconds", type=int, default=30)
    args = parser.parse_args()
    if args.attempts < 1 or args.interval_seconds < 0:
        raise SystemExit("attempts must be positive and interval-seconds nonnegative")
    try:
        provision_network(
            args.resource_group,
            args.workspace_name,
            args.attempts,
            args.interval_seconds,
        )
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        raise SystemExit(error) from error


if __name__ == "__main__":
    main()
