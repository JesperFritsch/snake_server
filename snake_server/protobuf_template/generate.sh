#!/bin/bash

PROTO_FILE="./remote_snake.proto"
OUTPUT_DIR="./python"

# Ensure the output directory exists
mkdir -p "$OUTPUT_DIR"

# Generate gRPC Python code
python -m grpc_tools.protoc -I$(dirname "$PROTO_FILE") --python_out="$OUTPUT_DIR" --grpc_python_out="$OUTPUT_DIR" "$PROTO_FILE"

echo "gRPC Python code generated successfully in $OUTPUT_DIR"