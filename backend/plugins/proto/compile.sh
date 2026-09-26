#!/usr/bin/env bash
#
# Compiles the plugin protocol (plugin.proto) into Python gRPC stubs.
# Run once after install, or whenever plugin.proto changes:
#
#   bash backend/plugins/proto/compile.sh
#
# Requires grpcio-tools (in requirements.txt). Generates:
#   backend/plugins/proto/plugin_pb2.py
#   backend/plugins/proto/plugin_pb2_grpc.py
#
set -euo pipefail

PROTO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Compiling plugin.proto -> Python stubs..."
python -m grpc_tools.protoc \
  -I"$PROTO_DIR" \
  --python_out="$PROTO_DIR" \
  --grpc_python_out="$PROTO_DIR" \
  "$PROTO_DIR/plugin.proto"

# Fix the import in the generated grpc file so it works as a package module
# (protoc emits `import plugin_pb2` which needs to be relative).
GRPC_FILE="$PROTO_DIR/plugin_pb2_grpc.py"
if [ -f "$GRPC_FILE" ]; then
  sed -i.bak 's/^import plugin_pb2 as/from . import plugin_pb2 as/' "$GRPC_FILE" && rm -f "$GRPC_FILE.bak"
fi

# Ensure the proto dir is a package
touch "$PROTO_DIR/__init__.py"

echo "Done. Generated plugin_pb2.py and plugin_pb2_grpc.py"
