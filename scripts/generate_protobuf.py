#!/usr/bin/env python3
"""Generate Python files from Arrow Flight SQL proto definitions."""

import subprocess
import sys
from pathlib import Path


def generate_protobuf_files():
    # Get the project root
    project_root = Path(__file__).parent.parent
    proto_dir = project_root / "proto"  # Adjust this path as needed
    output_dir = project_root / "src" / "mpzsql" / "flightsql" / "generated"

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create __init__.py
    (output_dir / "__init__.py").write_text("")

    # Find all .proto files
    proto_files = list(proto_dir.rglob("*.proto"))

    if not proto_files:
        print(f"No .proto files found in {proto_dir}")
        return False

    # Generate Python files
    for proto_file in proto_files:
        print(f"Generating Python code for {proto_file.name}")

        cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={proto_dir}",
            f"--python_out={output_dir}",
            f"--grpc_python_out={output_dir}",
            str(proto_file),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            print(f"Error generating {proto_file.name}:")
            print(result.stderr)
            return False

    print(f"Successfully generated Python files in {output_dir}")
    return True


if __name__ == "__main__":
    success = generate_protobuf_files()
    sys.exit(0 if success else 1)
