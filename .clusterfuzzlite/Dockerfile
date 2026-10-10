# ClusterFuzzLite build image for OpenOptOut's Python fuzz targets (fuzz/).
# See .clusterfuzzlite/build.sh and docs/SECURITY_SCANNING.md → "Fuzzing".
#
# Pinned by digest for OpenSSF Scorecard. Dependabot keeps it up to date.
# Note: Root is required by OSS-Fuzz's compile_python_fuzzer build toolchain.
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:690445a4d5f14cb2019f221fecf7bec45f62179dcc56314f2e1731c4082823a4

COPY . $SRC/openoptout
WORKDIR $SRC/openoptout
COPY .clusterfuzzlite/build.sh $SRC/
