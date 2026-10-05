#!/bin/bash -eu
# Build OpenOptOut's fuzz targets for ClusterFuzzLite.
#
# The fuzz targets (fuzz/fuzz_*.py) only exercise pure-Python modules of the
# backend, so no third-party packages are needed beyond Atheris, which the base
# image already provides. The backend is made importable as the package `app`
# (the same way backend/Dockerfile does it), then each target is packaged with
# PyInstaller by OSS-Fuzz's compile_python_fuzzer helper.

PKGROOT="$SRC/openoptout-pkgroot"
bash "$SRC/openoptout/fuzz/build_pkgroot.sh" "$PKGROOT"

for fuzzer in "$SRC"/openoptout/fuzz/fuzz_*.py; do
  compile_python_fuzzer "$fuzzer" --paths "$PKGROOT" --paths "$SRC/openoptout/fuzz"
done
