#!/usr/bin/env python3
"""Render a validated immutable runner image into ARC Helm values."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import urlparse


IMAGE_PLACEHOLDER = "__ARC_RUNNER_IMAGE__"
GITHUB_CONFIG_URL_PLACEHOLDER = "__ARC_GITHUB_CONFIG_URL__"


def _repository_slug(github_config_url: str) -> str:
    parsed = urlparse(github_config_url)
    path_parts = parsed.path.strip("/").split("/")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or len(path_parts) != 2
        or not all(path_parts)
    ):
        raise ValueError(
            "GitHub config URL must be an https://github.com/<owner>/<repository> URL"
        )
    return "/".join(path_parts)


def render(template: str, image: str, github_config_url: str) -> str:
    repository = _repository_slug(github_config_url)
    image_pattern = re.compile(
        rf"^ghcr\.io/{re.escape(repository)}-arc-runner@sha256:[0-9a-f]{{64}}$",
        re.IGNORECASE,
    )
    if not image_pattern.fullmatch(image):
        raise ValueError(
            "runner image must be the approved GHCR repository with an "
            "immutable sha256 digest"
        )
    if template.count(IMAGE_PLACEHOLDER) != 1:
        raise ValueError("runner values must contain exactly one image placeholder")
    if template.count(GITHUB_CONFIG_URL_PLACEHOLDER) != 1:
        raise ValueError(
            "runner values must contain exactly one GitHub config URL placeholder"
        )
    return template.replace(IMAGE_PLACEHOLDER, image).replace(
        GITHUB_CONFIG_URL_PLACEHOLDER,
        github_config_url,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--github-config-url", required=True)
    args = parser.parse_args()
    args.output.write_text(
        render(
            args.template.read_text(encoding="utf-8"),
            args.image,
            args.github_config_url,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
