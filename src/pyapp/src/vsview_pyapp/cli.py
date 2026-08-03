import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Self

import dotenv
import niquests
from compression import zstd
from cyclopts import App, Parameter
from jetpytools import SPath
from rich.console import Console
from rich.panel import Panel
from rich.pretty import pretty_repr

console = Console(stderr=True)

DISTRO_URLS = {
    (
        "x86_64",
        "windows",
    ): "https://github.com/astral-sh/python-build-standalone/releases/download/20260728/cpython-3.14.6%2B20260728-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
    (
        "x86_64",
        "linux",
    ): "https://github.com/astral-sh/python-build-standalone/releases/download/20260728/cpython-3.14.6%2B20260728-x86_64_v3-unknown-linux-gnu-install_only_stripped.tar.gz",
    (
        "aarch64",
        "linux",
    ): "https://github.com/astral-sh/python-build-standalone/releases/download/20260728/cpython-3.14.6%2B20260728-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz",
    (
        "x86_64",
        "darwin",
    ): "https://github.com/astral-sh/python-build-standalone/releases/download/20260728/cpython-3.14.6%2B20260728-x86_64-apple-darwin-install_only_stripped.tar.gz",
    (
        "aarch64",
        "darwin",
    ): "https://github.com/astral-sh/python-build-standalone/releases/download/20260728/cpython-3.14.6%2B20260728-aarch64-apple-darwin-install_only_stripped.tar.gz",
}


vsapp = App(name="vsapp", help="VSView PyApp CLI - A tool for creating a PyApp for VSView.", console=console)


@vsapp.command
def build(
    *,
    output: SPath = SPath("dist"),
    manifest_path: SPath = SPath("submodules/pyapp/Cargo.toml"),
    env: SPath = SPath("src/pyapp/.env.example"),
    offline: bool = False,
    clear: bool = False,
    verbose: Annotated[int, Parameter(alias="-v", count=True)] = 0,
) -> None:
    """
    Build the application.

    Args:
        output: Directory where the final compiled binary will be placed.
        manifest_path: Path to the PyApp Cargo.toml manifest.
        env: Path to the .env file containing PyApp configuration.
        clear: Remove existing build artifacts and run 'cargo clean' before building.
        verbose: Increase output verbosity (can be used multiple times).
    """
    if not env.exists():
        console.print(f"[bold red]Error:[/bold red] Could not find environment file at {env!r}")
        raise SystemExit(1)

    env_vars = dotenv.dotenv_values(env, verbose=bool(verbose))
    env_vars = {k: v for k, v in env_vars.items() if v}

    out_dist = SPath("dist/python-offline.tar.zst")
    main_wheel = create_dist(out_dist=out_dist, offline=offline, quiet=not verbose)
    main_wheel = main_wheel.resolve().to_str()

    if offline:
        env_vars["PYAPP_PROJECT_PATH"] = main_wheel
        env_vars["PYAPP_DISTRIBUTION_PYTHON_PATH"] = "python/python.exe" if os.name == "nt" else "python/bin/python3"
        env_vars["PYAPP_DISTRIBUTION_PATH"] = out_dist.resolve().to_str()
        env_vars["PYAPP_DISTRIBUTION_EMBED"] = "true"
        env_vars["PYAPP_SKIP_INSTALL"] = "true"
    else:
        env_vars["PYAPP_PROJECT_PATH"] = main_wheel
        env_vars["PYAPP_PIP_EXTRA_ARGS"] = (
            "--extra-index-url https://jaded-encoding-thaumaturgy.github.io/vs-wheels/simple"
        )

    # Resolve paths to absolute to prevent issues with Cargo build-script CWD
    for var in ["PYAPP_WINDOWS_ICON_PATH", "PYAPP_PROJECT_PATH", "PYAPP_DISTRIBUTION_PATH"]:
        if path_str := (env_vars | dict(os.environ)).get(var):
            if (path := SPath(path_str)).exists():
                env_vars[var] = path.resolve().to_str()
            else:
                console.print(f"[yellow]{var} path {path_str} does not exist, skipping...[/yellow]")
                del env_vars[var]

    console.print(
        Panel(
            pretty_repr(env_vars),
            title="[bold green]Environment variables[/bold green]",
            expand=False,
            border_style="green",
        )
    )

    env_vars = env_vars | dict(os.environ)

    def cargo_cmd(action: str) -> list[str]:
        cmd = ["cargo", action, "-r", "--manifest-path", str(manifest_path)]
        if verbose:
            cmd.append("-" + "v" * verbose)
        return cmd

    if clear:
        console.print("Running Cargo clean...")
        subprocess.run(cargo_cmd("clean"), env=env_vars, check=True)

    console.print("Running Cargo build...")
    subprocess.run(cargo_cmd("build"), env=env_vars, check=True)

    console.print("\n[bold green]Build completed successfully![/bold green]")

    target_dir = Path(env_vars.get("CARGO_TARGET_DIR", manifest_path.parent / "target")).resolve()
    binary_name = env_vars.get("PYAPP_BINARY_NAME", "pyapp")

    ext = ".exe" if os.name == "nt" else ""
    source_binary = target_dir / "release" / f"pyapp{ext}"

    if source_binary.exists():
        output.mkdir(parents=True, exist_ok=True)
        dest_binary = output / f"{binary_name}{ext}"

        shutil.copy2(source_binary, dest_binary)
        console.print(f"Artifact deployed to: [bold blue]{dest_binary}[/bold blue]")
    else:
        console.print(f"[bold red]Error:[/bold red] Could not find compiled binary at {source_binary!r}")
        raise SystemExit(1)


@vsapp.command
def create_dist(
    *,
    main_dir: SPath = SPath("dist"),
    plugins_dir: SPath = SPath("dist/plugins"),
    offline: bool = False,
    out_dist: SPath = SPath("dist/python-offline.tar.zst"),
    quiet: bool = True,
) -> SPath:
    """
    Create distribution wheels and optional offline Python distribution archive.

    Args:
        main_dir: Output directory for main wheel.
        plugins_dir: Output directory for plugin wheels and dependencies.
        offline: Prepare full offline Python distribution archive.
        out_dist: Output path for the offline distribution archive.

    Returns:
        main_wheel

    """
    q = ["--quiet" if quiet else ""]
    console.print("Building main wheel...")
    if main_dir.exists():
        main_dir.rmdirs()
    main_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "build", "--wheel", "--out-dir", main_dir, *q], check=True)

    main_wheel = next(SPath(main_dir).glob("*.whl")).resolve()

    if not offline:
        return main_wheel

    console.print("Building plugins wheels...")
    if plugins_dir.exists():
        plugins_dir.rmdirs()
    plugins_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["uv", "build", "--out-dir", plugins_dir, "--all-packages", *q], check=True)
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print(e.stderr)
        raise
    for dist in plugins_dir.glob("*.tar.gz"):
        dist.unlink()

    url = DISTRO_URLS[get_target()]
    build_dir = SPath("build/offline_prep")
    if build_dir.exists():
        build_dir.rmdirs()
    build_dir.mkdir(parents=True)

    console.print(f"Downloading Python standalone distribution from {url}...")
    response = niquests.get(url, stream=True).raise_for_status()

    archive_name = build_dir / "cpython_standalone.tar.gz"
    with archive_name.open("wb") as f:
        f.writelines(response.iter_content(chunk_size=65536))

    console.print("Extracting Python standalone distribution...")
    with tarfile.open(archive_name, "r:gz") as tar:
        tar.extractall(path=build_dir)

    if not (python_dir := build_dir / "python").exists():
        raise RuntimeError("Extracted archive did not contain top-level 'python' directory")

    python_exe = python_dir / "python.exe" if os.name == "nt" else python_dir / "bin" / "python3"

    if not [*Path(main_dir).resolve().glob("*.whl"), *Path(plugins_dir).resolve().glob("*.whl")]:
        raise RuntimeError("No wheels found to install into offline distribution")

    console.print("Installing wheels into Python distribution...")
    install_cmd: list[Any] = [
        "uv",
        "pip",
        "install",
        "--python",
        python_exe,
        "--find-links",
        main_dir.resolve(),
        "--find-links",
        plugins_dir.resolve(),
        "--extra-index-url",
        "https://jaded-encoding-thaumaturgy.github.io/vs-wheels/simple",
        main_wheel,
        "vsview-nativeres",
        *q,
    ]
    subprocess.run(install_cmd, check=True)

    out_dist_path = out_dist.resolve()
    out_dist_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"Packaging offline distribution to {out_dist_path} with zstd...")

    options: dict[int, int] = {
        zstd.CompressionParameter.compression_level: 20,
        zstd.CompressionParameter.nb_workers: os.cpu_count() or 4,
    }
    with zstd.open(out_dist_path, "wb", options=options) as zf, tarfile.open(fileobj=zf, mode="w") as tar:
        tar.add(python_dir, arcname="")

    console.print(f"[bold green]Successfully generated offline distribution at {out_dist_path}[/bold green]")
    if gh_output := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_output, "a") as f:
            f.write(f"offline-distribution-path={out_dist_path}\n")

    return main_wheel


@vsapp.command
def icon(
    source: SPath = SPath("src/vsview/assets/icon@4x.png"),
    *,
    output: Annotated[SPath, Parameter(alias="-o")] = SPath("build/icons"),
    clear: bool = False,
) -> None:
    """
    Generate icon sets.

    Args:
        source: Source image for icon generation.
        output: Target directory for the generated Icon assets.
        clear: Remove existing contents from the output directory before generation.
    """
    if not source.exists():
        console.print(f"[bold red]Error:[/bold red] Source image {source!r} does not exist.")
        raise SystemExit(1)

    im = ImageMagick.detect()

    output = output.resolve()

    if clear:
        console.print("clearing output directory...")
        output.rmdirs(missing_ok=True, ignore_errors=True)

    (windows_dir := output / "windows").mkdir(parents=True, exist_ok=True)
    (macos_dir := output / "macos").mkdir(parents=True, exist_ok=True)
    (linux_dir := output / "linux").mkdir(parents=True, exist_ok=True)

    windows_icon_sizes = [256, 128, 96, 64, 48, 32, 16]
    iconset_entries = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]

    with tempfile.TemporaryDirectory(prefix="vsview-icon-") as temp_dir:
        master_icon = Path(temp_dir) / "master.png"

        im.resize(
            source,
            None,
            1024,
            f"PNG32:{master_icon}",
            extent=True,
            extra_args=("-background", "none", "-gravity", "center"),
        )
        console.print(f"[bold green]Master icon generated successfully in {master_icon!r}[/bold green]")

        windows_icon_inputs = list[Path]()
        for size in windows_icon_sizes:
            icon = Path(temp_dir) / f"windows-{size}.png"
            im.resize(master_icon, (1024, 1024), size, f"PNG32:{icon}")
            windows_icon_inputs.append(icon)

        im.convert(*windows_icon_inputs, (p := (windows_dir / "vsview.ico")))
        console.print(f"[bold green]Windows icon generated successfully in {p!r}[/bold green]")

        (iconset_dir := macos_dir / "vsview.iconset").mkdir(parents=True, exist_ok=True)

        for file_name, size in iconset_entries:
            im.resize(master_icon, (1024, 1024), size, f"PNG32:{iconset_dir / file_name}")
            console.print(f"[bold]Generated {file_name} ({size}x{size})[/bold]")
        console.print(f"[bold green]macOS icon generated successfully in {iconset_dir!r}[/bold green]")

        linux_icon_sizes = [16, 32, 48, 64, 128, 256]

        for size in linux_icon_sizes:
            size_dir = linux_dir / f"{size}x{size}"
            size_dir.mkdir(parents=True, exist_ok=True)
            im.resize(master_icon, (1024, 1024), size, f"PNG32:{size_dir / 'vsview.png'}")
            console.print(f"[bold]Generated Linux icon {size}x{size}[/bold]")
        console.print(f"[bold green]Linux icons generated successfully in {linux_dir!r}[/bold green]")

    console.print(f"[bold cyan]Icons generated successfully in {output!r}[/bold cyan]")


@dataclass(frozen=True, slots=True)
class ImageMagick:
    identify_cmd: tuple[str, ...]
    convert_cmd: tuple[str, ...]

    @classmethod
    def detect(cls) -> Self:
        if magick := shutil.which("magick"):
            console.print(f"[bold green]ImageMagick found: {Path(magick).resolve()}[/bold green]")
            return cls(identify_cmd=(magick, "identify"), convert_cmd=(magick,))

        raise SystemExit("ImageMagick was not found in PATH.")

    def get_size(self, image: Path) -> tuple[int, int]:
        p = subprocess.run(
            [*self.identify_cmd, "-format", "%w %h", image],
            capture_output=True,
            text=True,
            check=True,
        )
        w, h = p.stdout.strip().split()
        return int(w), int(h)

    def resize(
        self,
        source: Path,
        source_size: tuple[int, int] | None,
        target_size: int,
        output: str | Path,
        *,
        extent: bool = False,
        extra_args: tuple[str, ...] = (),
    ) -> None:
        sw, sh = source_size or self.get_size(source)

        filter_name = "Lanczos" if target_size > max(sw, sh) else "Hermite"
        size_str = f"{target_size}x{target_size}"

        cmd: list[str | Path] = [*self.convert_cmd, *extra_args, source]

        if filter_name == "Hermite":
            cmd.extend(["-colorspace", "RGB"])
        cmd.extend(["-filter", filter_name, "-resize", size_str])
        if extent:
            cmd.extend(["-extent", size_str])
        if filter_name == "Hermite":
            cmd.extend(["-colorspace", "sRGB"])
        cmd.append(output)

        subprocess.run(cmd, check=True)

    def convert(self, *args: str | Path) -> None:
        subprocess.run([*self.convert_cmd, *args], check=True)


@vsapp.command
def bundle(
    source: SPath,
    version: str,
    *,
    output: Annotated[SPath, Parameter(alias="-o")] = SPath("dist/AppBundle"),
    iconset_dir: SPath = SPath("src/pyapp/icons/macos/vsview.iconset"),
    env: Annotated[SPath, Parameter(alias="-e")] = SPath("src/pyapp/.env.example"),
    bundle_id: str = "io.github.jaded-encoding-thaumaturgy.vsview",
    clear: bool = False,
) -> None:
    """
    Create app bundle for macOS.

    Args:
        source: Path to the compiled application binary.
        version: Application version string (e.g., 1.0.0).
        output: Destination path for the generated macOS App Bundle.
        iconset_dir: Source directory containing Iconset assets for Macintosh icons.
        env: Environment file.
        bundle_id: Reverse-DNS style bundle identifier.
        clear: Remove existing contents from the output directory before bundling.
    """
    if not source.exists():
        console.print(f"[bold red]Error:[/bold red] Source binary {source!r} does not exist.")
        raise SystemExit(1)

    env_vars = dotenv.dotenv_values(env)
    env_vars = {k: v for k, v in env_vars.items() if v}
    binary_name = env_vars.get("PYAPP_BINARY_NAME", "pyapp")

    contents_dir = output / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    icns_dir = iconset_dir.parent / "vsview.icns"

    if clear:
        contents_dir.rmdirs(missing_ok=True, ignore_errors=True)
        icns_dir.unlink(missing_ok=True)

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    bundle_binary = macos_dir / binary_name
    shutil.copy2(source, bundle_binary)
    bundle_binary.chmod(bundle_binary.stat().st_mode | 0o111)

    subprocess.run(["iconutil", "--convert", "icns", iconset_dir, "--output", icns_dir], check=True)

    shutil.copy2(icns_dir, resources_dir / icns_dir.name)
    write_info_plist(contents_dir / "Info.plist", binary_name, version, bundle_id)


def write_info_plist(path: Path, app_name: str, version: str, bundle_id: str) -> None:
    import plistlib

    payload = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": app_name,
        "CFBundleExecutable": app_name,
        "CFBundleIconFile": "vsview",
        "CFBundleIdentifier": bundle_id,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": app_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "CFBundleSupportedPlatforms": ["MacOSX"],
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    }
    path.write_bytes(plistlib.dumps(payload))


def get_target() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        raise ValueError(f"Unsupported architecture: {machine}")

    return arch, system


if __name__ == "__main__":
    vsapp()
