#!/usr/bin/env bash
# One root session for the whole V1 POC host setup.
#
# Everything in this repository that needs root is here, in dependency order, so
# you run one command instead of four. It is safe to re-run: each step is
# idempotent, and the script stops at the first failure rather than continuing
# into a half-configured state.
#
#   sudo ./infrastructure/poc/ROOT_SETUP.sh
#
# What it does, in order:
#   1. checks the things that must already be true, and stops if they are not
#   2. installs the units, launchers, and service configuration  (80-install.sh)
#   3. seals all 25 credentials to this host's TPM               (70-credentials.sh)
#   4. enables asklegal.target so the stack starts at boot
#   5. waits for every application to report READY, and prints what it found
#
# What it deliberately does NOT do:
#   - it does not apply egress firewall rules. The egress proxy is a convention,
#     not a boundary: a worker on a routable egress network can reach the internet
#     directly. Closing that needs DOCKER-USER rules and was explicitly deferred.
#   - it does not rotate the SQL passwords. See the warning it prints.
#   - it does not delete your plaintext staging directory. You should, afterwards.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
repository="$(cd "$here/../.." && pwd)"
units="$here/units"
staging="${1:-$repository/var/run/staging-all}"

say() { printf "\n\033[1m== %s\033[0m\n" "$1"; }
fail() { printf "\033[31mSTOP: %s\033[0m\n" "$1" >&2; exit 1; }

# ---------------------------------------------------------------- preflight --
say "1/5  Preflight"

[ "$(id -u)" -eq 0 ] || fail "run this with sudo"
command -v docker >/dev/null || fail "docker is not installed"
systemctl --version >/dev/null 2>&1 || fail "systemd is not available"

[ -d "$units" ] || fail "no rendered units at $units"
[ -x "$units/80-install.sh" ] || fail "missing $units/80-install.sh"
[ -x "$units/70-credentials.sh" ] || fail "missing $units/70-credentials.sh"

[ -d "$staging" ] || fail "no credential staging directory at $staging
  Build it first, as your normal user, with:
    ./var/run/assemble_staging.sh"

# Sealing fails one credential at a time and leaves the rest sealed, which is a
# confusing half-state. Check the whole set up front instead.
missing=""
while read -r name; do
  [ -f "$staging/$name" ] || missing="$missing $name"
done < <(grep -oP "^seal '\K[^']+" "$units/70-credentials.sh")
[ -z "$missing" ] || fail "staging directory is missing:$missing"

required=$(grep -c "^seal '" "$units/70-credentials.sh")
printf "  rendered units:      %s\n" "$(find "$units" -maxdepth 1 -name '*.service' | wc -l)"
printf "  credentials staged:  %s of %s required\n" \
  "$(find "$staging" -maxdepth 1 -type f | wc -l)" "$required"

# systemd-creds needs a TPM for the sealing mode the credential step uses.
if [ ! -e /dev/tpmrm0 ] && [ ! -e /dev/tpm0 ]; then
  printf "\033[33m  WARNING: no TPM device found. 70-credentials.sh seals with\n"
  printf "  --with-key=host+tpm2 and will fail without one.\033[0m\n"
fi

# Every image the units name has to exist locally; these are tags, not digests.
say "  Checking that every image the units name exists"
absent=""
while read -r image; do
  docker image inspect "$image" >/dev/null 2>&1 || absent="$absent $image"
done < <(grep -ohP "^\s*'\K(asklegal/[^']+)" "$units"/launch/*.sh | sort -u)
[ -z "$absent" ] || fail "these images are not built on this host:$absent
  Build them as your normal user with:
    python3 tools/v1_poc_build_images.py --tag-suffix v1"
printf "  all images present\n"

# ------------------------------------------------------------------ install --
say "2/5  Installing units, launchers, and configuration"
"$units/80-install.sh"

# -------------------------------------------------------------- credentials --
say "3/5  Sealing credentials to this host"
"$units/70-credentials.sh" "$staging"

# ------------------------------------------------------------------- enable --
say "4/5  Enabling asklegal.target"
systemctl enable asklegal.target
# On a re-run the target is already active, and `enable --now` would leave the
# old unit files running. Restart so a corrected unit actually takes effect.
if systemctl is-active --quiet asklegal.target; then
  printf "  target already active; restarting so new unit files take effect\n"
  systemctl restart asklegal.target
else
  systemctl start asklegal.target
fi

# ------------------------------------------------------------------- verify --
say "5/5  Waiting for the applications to report READY"

applications="control-plane review-api acquisition-worker legal-processing-worker promotion-worker"
deadline=$(( $(date +%s) + 180 ))
pending="$applications"
while [ -n "$pending" ] && [ "$(date +%s)" -lt "$deadline" ]; do
  still=""
  for application in $pending; do
    if journalctl -u "asklegal-$application.service" --since "-10 min" --no-pager 2>/dev/null \
        | grep -q " READY "; then
      printf "  \033[32mREADY\033[0m   %s\n" "$application"
    else
      still="$still $application"
    fi
  done
  pending="$(echo "$still" | tr -s ' ' | sed 's/^ //')"
  [ -z "$pending" ] || sleep 5
done

printf "\n"
systemctl --no-pager --plain list-units 'asklegal-*.service' 2>/dev/null || true

if [ -n "$pending" ]; then
  printf "\n\033[31mNot every application reported READY:%s\033[0m\n" "$pending"
  printf "Look at one with:\n"
  printf "  journalctl -u asklegal-<name>.service -n 60 --no-pager\n"
  exit 1
fi

printf "\n\033[32mAll five applications reported READY.\033[0m\n"

cat <<'NOTES'

Three things to do now, in your own time:

1. ROTATE THE SQL PASSWORDS. sa-password and app-password have sat in plain
   files under var/run/ since the register work and have been read by more than
   one session. They are sealed on this host now, but the plaintext originals
   are still on disk and were never secret.

2. DELETE THE PLAINTEXT STAGING DIRECTORY. The credentials are sealed to this
   host's TPM now; the plaintext copies are the weakest thing on this machine.
       shred -u <staging>/* && rmdir <staging>

3. TEST THE REBOOT. Nothing here has ever survived one. That is the last thing
   the units are supposed to prove, and it is not proved until you do it:
       sudo reboot
   then, once it is back:
       systemctl --no-pager --plain list-units 'asklegal-*.service'
NOTES
