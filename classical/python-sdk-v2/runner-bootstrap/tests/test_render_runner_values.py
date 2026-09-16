import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "render_runner_values.py"
VALUES_PATH = Path(__file__).parents[1] / "helm" / "runner-set-values.yaml"
SPEC = importlib.util.spec_from_file_location("render_runner_values", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class RenderRunnerValuesTests(unittest.TestCase):
    def test_renders_approved_digest(self):
        image = "ghcr.io/example/project-arc-runner@sha256:" + "a" * 64
        template = VALUES_PATH.read_text(encoding="utf-8")

        rendered = MODULE.render(
            template,
            image,
            "https://github.com/example/project",
        )

        for expected in (
            "githubConfigUrl: https://github.com/example/project",
            "- name: runner",
            f"image: {image}",
            "command:\n          - /home/runner/run.sh",
            "resources:\n          requests:\n            cpu: 500m",
            'limits:\n            cpu: "2"',
            "securityContext:\n          allowPrivilegeEscalation: false",
            "runAsUser: 1001",
        ):
            self.assertIn(expected, rendered)

    def test_rejects_mutable_tag(self):
        with self.assertRaisesRegex(ValueError, "immutable sha256"):
            MODULE.render(
                (
                    "githubConfigUrl: __ARC_GITHUB_CONFIG_URL__\n"
                    "image: __ARC_RUNNER_IMAGE__\n"
                ),
                "ghcr.io/example/project-arc-runner:latest",
                "https://github.com/example/project",
            )

    def test_rejects_unapproved_repository(self):
        with self.assertRaisesRegex(ValueError, "approved GHCR repository"):
            MODULE.render(
                (
                    "githubConfigUrl: __ARC_GITHUB_CONFIG_URL__\n"
                    "image: __ARC_RUNNER_IMAGE__\n"
                ),
                "ghcr.io/example/runner@sha256:" + "a" * 64,
                "https://github.com/example/project",
            )

    def test_requires_exactly_one_placeholder(self):
        image = "ghcr.io/example/project-arc-runner@sha256:" + "a" * 64
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.render(
                "githubConfigUrl: __ARC_GITHUB_CONFIG_URL__\nimage: runner\n",
                image,
                "https://github.com/example/project",
            )


if __name__ == "__main__":
    unittest.main()
