#!/usr/bin/env python3
"""Run an AKS command and fail when the remote command fails."""

import argparse
import json
import re
import subprocess
import sys

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SENSITIVE_VALUE = re.compile(r"(?i)\b(token|password|secret)(\s*[:=]\s*)(\S+)")
AUTHORIZATION_VALUE = re.compile(r"(?i)\b(authorization)(\s*[:=]\s*)([^\r\n]+)")
MAX_LOG_LENGTH = 4000


def sanitize(value):
    text = ANSI_ESCAPE.sub("", str(value))
    text = "".join(
        character
        for character in text
        if character in "\n\r\t" or character.isprintable()
    )
    text = SENSITIVE_VALUE.sub(r"\1\2***", text)
    text = AUTHORIZATION_VALUE.sub(r"\1\2***", text)
    if len(text) > MAX_LOG_LENGTH:
        return text[:MAX_LOG_LENGTH] + "\n[logs truncated]"
    return text


def invoke(args):
    command = [
        "az",
        "aks",
        "command",
        "invoke",
        "--resource-group",
        args.resource_group,
        "--name",
        args.name,
        "--command",
        args.command,
        "--output",
        "json",
    ]
    if args.subscription:
        command.extend(["--subscription", args.subscription])
    for path in args.file:
        command.extend(["--file", path])

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        print("Azure CLI failed to invoke the AKS command.", file=sys.stderr)
        if result.stderr:
            print(sanitize(result.stderr), file=sys.stderr)
        return 1

    try:
        response = json.loads(result.stdout)
        exit_code = int(response["exitCode"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        print("Azure CLI returned an invalid AKS command response.", file=sys.stderr)
        return 1

    provisioning_state = response.get("provisioningState")
    logs = sanitize(response.get("logs", ""))
    if provisioning_state != "Succeeded" or exit_code != 0:
        print(
            "AKS command failed: "
            f"provisioningState={provisioning_state!r}, exitCode={exit_code}.",
            file=sys.stderr,
        )
        if logs:
            print(logs, file=sys.stderr)
        return 1

    if args.print_logs and logs:
        print(logs)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--subscription")
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--print-logs", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(invoke(parse_args()))
