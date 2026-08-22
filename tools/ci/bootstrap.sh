#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
  printf 'usage: %s EXACT_TOOL_ROOT\n' "$0" >&2
  exit 2
fi

tool_root="$1"
uv_version="0.12.5"
uv_archive="uv-x86_64-unknown-linux-gnu.tar.gz"
uv_sha256="68a509da24b06b4223a1c0175fb5eb5bc79342b76cbeff0cfe51ac3f5b17b6b2"
node_version="24.19.0"
node_archive="node-v${node_version}-linux-x64.tar.xz"
node_sha256="14b342e71204f811bde6153be8e04b62aef63c236fef92b55f9c83154b409647"

mkdir -p "$tool_root"
uv_path="$tool_root/$uv_archive"
node_path="$tool_root/$node_archive"

curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
  --output "$uv_path" \
  "https://github.com/astral-sh/uv/releases/download/${uv_version}/${uv_archive}"
printf '%s  %s\n' "$uv_sha256" "$uv_path" | sha256sum --check --status
tar --extract --gzip --file "$uv_path" --directory "$tool_root"

curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
  --output "$node_path" \
  "https://nodejs.org/dist/v${node_version}/${node_archive}"
printf '%s  %s\n' "$node_sha256" "$node_path" | sha256sum --check --status
tar --extract --xz --file "$node_path" --directory "$tool_root"

uv_binary="$tool_root/uv-x86_64-unknown-linux-gnu/uv"
node_binary="$tool_root/node-v${node_version}-linux-x64/bin/node"
if [ "$("$uv_binary" --version)" != "uv ${uv_version} (x86_64-unknown-linux-gnu)" ]; then
  printf 'unexpected uv executable version\n' >&2
  exit 1
fi
if [ "$("$node_binary" --version)" != "v${node_version}" ]; then
  printf 'unexpected Node.js executable version\n' >&2
  exit 1
fi

export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$tool_root/python}"
"$uv_binary" python install --no-bin 3.14.7
python_binary="$("$uv_binary" python find --managed-python 3.14.7)"
if [ "$("$python_binary" --version)" != "Python 3.14.7" ]; then
  printf 'unexpected Python executable version\n' >&2
  exit 1
fi
