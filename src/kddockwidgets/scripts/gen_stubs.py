"""Run shiboken6-genpyi in-process"""

from __future__ import annotations

import argparse
import builtins
import glob
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("genpyi_exe")
    parser.add_argument("outpath")
    parser.add_argument("pyd_file")
    parser.add_argument("namespace")
    parser.add_argument("dll_dirs", nargs="*")
    return parser.parse_args()


def register_runtime_paths(dll_dirs: list[str]) -> None:
    for d in dll_dirs:
        if not os.path.isdir(d):
            continue
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(d)
        if d not in sys.path:
            sys.path.insert(0, d)


def prepare_generator_imports() -> None:
    try:
        import PySide6
        import shiboken6

        if (shiboken6_dir := shiboken6.__path__[0]) not in sys.path:
            sys.path.insert(0, shiboken6_dir)
        if (pyside6_dir := PySide6.__path__[0]) not in sys.path:
            sys.path.insert(0, pyside6_dir)

        builtins.PySide6 = PySide6  # type: ignore[attr-defined]
        builtins.Shiboken = shiboken6  # type: ignore[attr-defined]
    except ImportError:
        pass


def run_generator(genpyi_exe: str, outpath: str, pyd_file: str) -> None:
    sys.argv = [genpyi_exe, "--outpath", outpath, pyd_file]
    from shibokensupport.signature.lib.pyi_generator import main as genpyi_main # pyright: ignore[reportMissingImports]

    genpyi_main()


def generated_pyi_paths(outpath: str, pyd_file: str) -> list[str]:
    pyd_stem = os.path.splitext(os.path.basename(pyd_file))[0]
    if "." in pyd_stem:
        pyd_stem = pyd_stem.split(".")[0]
    return glob.glob(os.path.join(outpath, f"{pyd_stem}.pyi"))


def main() -> None:
    args = parse_args()
    register_runtime_paths(args.dll_dirs)
    prepare_generator_imports()
    run_generator(args.genpyi_exe, args.outpath, args.pyd_file)


if __name__ == "__main__":
    main()
