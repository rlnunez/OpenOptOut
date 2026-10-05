# ClusterFuzzLite build image for OpenOptOut's Python fuzz targets (fuzz/).
# See .clusterfuzzlite/build.sh and docs/SECURITY_SCANNING.md → "Fuzzing".
#
# Pinned by digest for OpenSSF Scorecard. Dependabot keeps it up to date.
# Note: Root is required by OSS-Fuzz's compile_python_fuzzer build toolchain;
# ignored in .trivyignore (DS-0002).
# trivy:ignore:AVD-DS-0001
# trivy:ignore:DS-0001
# trivy:ignore:AVD-DS-0026
# trivy:ignore:DS-0026
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:b02a06f9d3918428825b1ebfa2c3627b591a5924a83436b8aaec40c85fd15b16

COPY . $SRC/openoptout
WORKDIR $SRC/openoptout
COPY .clusterfuzzlite/build.sh $SRC/
