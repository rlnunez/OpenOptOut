# ClusterFuzzLite build image for OpenOptOut's Python fuzz targets (fuzz/).
# See .clusterfuzzlite/build.sh and docs/SECURITY_SCANNING.md → "Fuzzing".
#
# TODO(pin): replace the tag with a digest so OpenSSF Scorecard's
# "Pinned-Dependencies" check counts it as pinned, e.g.
#   docker pull gcr.io/oss-fuzz-base/base-builder-python
#   docker inspect --format '{{index .RepoDigests 0}}' gcr.io/oss-fuzz-base/base-builder-python
# then use:  FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:<digest>
# Dependabot (.github/dependabot.yml) keeps a pinned digest up to date.
FROM gcr.io/oss-fuzz-base/base-builder-python@sha256:b02a06f9d3918428825b1ebfa2c3627b591a5924a83436b8aaec40c85fd15b16

COPY . $SRC/openoptout
WORKDIR $SRC/openoptout
COPY .clusterfuzzlite/build.sh $SRC/
