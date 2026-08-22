#!/bin/sh
set -eu

if [ "$#" -lt 2 ] || [ "$1" != "-n" ]; then
    exit 64
fi
shift

case "${1##*/}" in
    buildx|docker) ;;
    *) exit 65 ;;
esac

exec "$@"
