import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "classical"
    / "python-sdk-v2"
    / "runner-bootstrap"
    / "scripts"
    / "invoke_aks_command.py"
)


class InvokeAksCommandTests(unittest.TestCase):
    def run_with_response(self, response, cli_exit_code=0, extra_args=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_az = root / "az"
            fake_az.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    if [[ {cli_exit_code} != 0 ]]; then
                      echo "token=cli-secret" >&2
                      exit {cli_exit_code}
                    fi
                    cat <<'JSON'
                    {response}
                    JSON
                    """
                )
            )
            fake_az.chmod(0o755)
            return subprocess.run(
                [
                    sys.executable,
                    SCRIPT,
                    "--resource-group",
                    "test-rg",
                    "--name",
                    "test-aks",
                    "--command",
                    "set -eu; false",
                    *extra_args,
                ],
                env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}"},
                capture_output=True,
                text=True,
            )

    def test_success_logs_can_be_written_for_machine_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "logs.json"
            result = self.run_with_response(
                '{"provisioningState":"Succeeded","exitCode":0,'
                '"logs":"{\\"kind\\":\\"Pod\\",\\"token\\":\\"unchanged\\"}"}',
                extra_args=("--logs-output", str(output)),
            )

            self.assertEqual(0, result.returncode)
            self.assertEqual(
                '{"kind":"Pod","token":"unchanged"}',
                output.read_text(),
            )
            self.assertEqual(0o600, output.stat().st_mode & 0o777)

    def test_remote_nonzero_fails_when_azure_cli_returns_zero(self):
        result = self.run_with_response(
            '{"provisioningState":"Succeeded","exitCode":2,'
            '"logs":"/bin/sh: set: Illegal option -o pipefail"}'
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exitCode=2", result.stderr)
        self.assertIn("Illegal option -o pipefail", result.stderr)

    def test_azure_cli_nonzero_fails_and_sanitizes_stderr(self):
        result = self.run_with_response("", cli_exit_code=3)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Azure CLI failed", result.stderr)
        self.assertIn("token=***", result.stderr)
        self.assertNotIn("cli-secret", result.stderr)

    def test_malformed_or_missing_exit_code_fails(self):
        for response in (
            "not-json",
            '{"provisioningState":"Succeeded"}',
        ):
            with self.subTest(response=response):
                result = self.run_with_response(response)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("invalid AKS command response", result.stderr)

    def test_failure_logs_are_sanitized(self):
        result = self.run_with_response(
            '{"provisioningState":"Failed","exitCode":1,'
            '"logs":"token=super-secret password=hunter2 '
            'secret=value authorization: Bearer abc123\\u001b[31m failure"}'
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("token=***", result.stderr)
        self.assertIn("password=***", result.stderr)
        self.assertIn("secret=***", result.stderr)
        self.assertIn("authorization: ***", result.stderr)
        self.assertNotIn("super-secret", result.stderr)
        self.assertNotIn("hunter2", result.stderr)
        self.assertNotIn("abc123", result.stderr)
        self.assertNotIn("\u001b", result.stderr)

    def test_failure_logs_are_truncated(self):
        logs = "x" * 4100
        result = self.run_with_response(
            '{"provisioningState":"Succeeded","exitCode":1,' f'"logs":"{logs}"}}'
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("[logs truncated]", result.stderr)
        self.assertLess(len(result.stderr), 4200)

    def test_success_logs_are_suppressed_by_default(self):
        result = self.run_with_response(
            '{"provisioningState":"Succeeded","exitCode":0,'
            '"logs":"sensitive success output"}'
        )

        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)

    def test_success_logs_are_printed_only_when_requested(self):
        result = self.run_with_response(
            '{"provisioningState":"Succeeded","exitCode":0,'
            '"logs":"verified remote output"}',
            extra_args=("--print-logs",),
        )

        self.assertEqual(0, result.returncode)
        self.assertEqual("verified remote output\n", result.stdout)
        self.assertEqual("", result.stderr)


if __name__ == "__main__":
    unittest.main()
