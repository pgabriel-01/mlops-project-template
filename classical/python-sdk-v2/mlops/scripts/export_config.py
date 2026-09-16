import argparse
import json
import os
from pathlib import Path

from project_config import derive_config, load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("config_file", type=Path)
    args = parser.parse_args()
    config = derive_config(load_config(args.config_file))

    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            for key, value in config.items():
                rendered = str(value).lower() if isinstance(value, bool) else str(value)
                output.write(f"{key}={rendered}\n")
    else:
        print(json.dumps(config, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
