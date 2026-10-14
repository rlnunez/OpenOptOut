# ClusterFuzzLite build image for OpenOptOut's Python fuzz targets (fuzz/).
# See .clusterfuzzlite/build.sh and docs/SECURITY_SCANNING.md → "Fuzzing".
#
# Pinned by digest for OpenSSF Scorecard. Dependabot keeps it up to date.
# Note: Root is required by OSS-Fuzz's compile_python_fuzzer build toolchain.
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:21f6fab17ace4dc76e1c56de91ee95d3d03da021df94b41056ba036f6c6f55e9

COPY . $SRC/openoptout
WORKDIR $SRC/openoptout
COPY .clusterfuzzlite/build.sh $SRC/
