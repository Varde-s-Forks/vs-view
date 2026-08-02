import os
import subprocess
from pathlib import Path


def main() -> None:
    gh_output = os.environ["GITHUB_OUTPUT"]
    ref = os.environ.get("GITHUB_REF", "")
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    tag_prefix = "refs/tags/vsview/v"

    version = ref.removeprefix(tag_prefix) if ref.startswith(tag_prefix) else "0.0.0-dev"
    print(f"Version: {version}")

    if event == "workflow_dispatch":
        subprocess.run(["uv", "build", "--wheel", "--out-dir", "dist/wheel", "--clear"], check=True)
        wheel_path = next(Path("dist/wheel").glob("*.whl")).resolve()
        print(f"Wheel: {wheel_path}")
    else:
        wheel_path = ""

    with open(gh_output, "a") as f:
        f.write(f"version={version}\n")
        f.write(f"wheel-path={wheel_path}\n")


if __name__ == "__main__":
    main()
