# PyKDDockWidgetsQt6

`PyKDDockWidgetsQt6` packages unofficial PySide6 bindings for [KDDockWidgets](https://github.com/KDAB/KDDockWidgets)

## Requirements

- Python 3.12+
- PySide6 6.10.2
- shiboken6 6.10.2
- Qt 6.10.2
- CMake 3.20+
- A C++ toolchain compatible with Qt 6.10.2

## Build Locally

Point CMake at a Qt 6.10.2 installation, then build with `uv build`.

You can use [`aqt`](https://github.com/miurahr/aqtinstall) to install the required Qt version:

```powershell
uv pip install aqtinstall
uv run --no-sync aqt install-qt windows desktop 6.10.2 win64_msvc2022_64 --outputdir C:\opt\qt
```

Then build the wheel:

```powershell
pushd .\src\kddockwidgets
uv build --wheel `
  -C cmake.define.CMAKE_PREFIX_PATH="C:\opt\qt\6.10.2\msvc2022_64" `
  -C cmake.define.CMAKE_GENERATOR="Ninja"
popd
```

<!-- Restoring submodule state -->
<!-- git -C src/kddockwidgets/submodules/KDDockWidgets restore . -->

`CMAKE_PREFIX_PATH` must use an absolute path.

## License

This package is an unofficial binding package for KDDockWidgets.

Upstream KDDockWidgets code remains under KDAB's licensing terms, including GPL-2.0-only or GPL-3.0-only
and optional commercial licensing from KDAB.

The local package glue in this directory does not relicense upstream KDDockWidgets code;
see [`LICENSE`](./LICENSE) and the upstream source tree for details.
