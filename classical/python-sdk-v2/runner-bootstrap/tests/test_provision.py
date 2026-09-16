import json
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PROVISION = ROOT / "scripts" / "provision.sh"
BICEP_TEMPLATE = ROOT / "infrastructure" / "main.bicep"
BICEP_PARAMETERS = ROOT / "infrastructure" / "main.bicepparam"


class ProvisionTests(unittest.TestCase):
    def _run(self, action, overrides=None):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            calls_path = directory_path / "calls.jsonl"
            az_path = directory_path / "az"
            az_path.write_text(
                """#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
if args[:2] == ["account", "show"]:
    print(os.environ["AZURE_SUBSCRIPTION_ID"])
elif args[:3] == ["network", "vnet", "show"]:
    print(json.dumps({"addressPrefixes": ["10.240.0.0/16"], "subnets": []}))
elif args[:3] == ["vm", "list-skus", "--location"]:
    print(json.dumps([{
        "name": os.environ["ARC_NODE_SKU"],
        "family": "testVmFamily",
        "capabilities": [{"name": "vCPUs", "value": "2"}],
        "restrictions": [],
    }]))
elif args[:3] == ["vm", "list-usage", "--location"]:
    print(json.dumps([
        {"name": {"value": "cores"}, "currentValue": 0, "limit": 100},
        {"name": {"value": "testVmFamily"}, "currentValue": 0, "limit": 100},
    ]))
elif args[:2] == ["deployment", "sub"]:
    with open(os.environ["AZ_CALLS_PATH"], "a", encoding="utf-8") as calls:
        calls.write(json.dumps(args) + "\\n")
else:
    raise SystemExit(f"Unexpected az arguments: {args}")
""",
                encoding="utf-8",
            )
            az_path.chmod(az_path.stat().st_mode | stat.S_IXUSR)

            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{directory}{os.pathsep}{environment['PATH']}",
                    "AZ_CALLS_PATH": str(calls_path),
                }
            )
            if overrides:
                environment.update(overrides)

            subprocess.run(
                ["bash", str(PROVISION), action],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            return json.loads(calls_path.read_text(encoding="utf-8").strip())

    def _parameter_values(self, arguments):
        parameters_index = arguments.index("--parameters")
        return arguments[parameters_index + 2 :]

    def test_passes_overrides_to_what_if(self):
        overrides = {
            "AZURE_SUBSCRIPTION_ID": "test-subscription",
            "LOCATION": "westus3",
            "ARC_HUB_RESOURCE_GROUP": "rg-custom",
            "ARC_HUB_VNET": "vnet-custom",
            "ARC_RUNNER_SUBNET_NAME": "snet-custom",
            "ARC_RUNNER_SUBNET_PREFIX": "10.240.3.0/24",
            "ARC_NODE_SKU": "Standard_D4ads_v6",
            "ARC_SYSTEM_NODE_COUNT": "3",
        }

        arguments = self._run("what-if", overrides)

        self.assertEqual(arguments[:3], ["deployment", "sub", "what-if"])
        self.assertEqual(
            self._parameter_values(arguments),
            [
                "location=westus3",
                "hubVnetResourceGroupName=rg-custom",
                "hubVnetName=vnet-custom",
                "runnerSubnetPrefix=10.240.3.0/24",
                "runnerSubnetName=snet-custom",
                "nodeVmSize=Standard_D4ads_v6",
                "systemNodeCount=3",
            ],
        )

    def test_passes_overrides_to_apply(self):
        arguments = self._run(
            "apply",
            {
                "AZURE_SUBSCRIPTION_ID": "test-subscription",
                "ARC_SYSTEM_NODE_COUNT": "2",
            },
        )

        self.assertEqual(arguments[:3], ["deployment", "sub", "create"])
        self.assertIn("systemNodeCount=2", self._parameter_values(arguments))

    def test_shared_defaults_match_bicep_parameters(self):
        matches = re.findall(
            r"^param (\w+) = (?:'([^']*)'|(\d+))$",
            BICEP_PARAMETERS.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        parameters = {
            name: string_value or number_value
            for name, string_value, number_value in matches
        }

        arguments = self._run(
            "what-if", {"AZURE_SUBSCRIPTION_ID": "test-subscription"}
        )
        resolved = dict(
            parameter.split("=", 1)
            for parameter in self._parameter_values(arguments)
        )

        for name, value in resolved.items():
            self.assertEqual(value, parameters[name])
        self.assertEqual(resolved["systemNodeCount"], "2")
        self.assertRegex(
            BICEP_TEMPLATE.read_text(encoding="utf-8"),
            r"param systemNodeCount int = 2\b",
        )


if __name__ == "__main__":
    unittest.main()
