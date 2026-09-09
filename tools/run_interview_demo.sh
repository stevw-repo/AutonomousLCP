#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "${project_root}"
exec "${project_root}/.venv/bin/python" -B -m tools.interview_demo "$@"
