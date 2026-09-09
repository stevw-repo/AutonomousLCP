#!/usr/bin/env bash
# Execute one parser-validated host-plan action. Never call this directly: the
# Python executor binds every action to a detached authority and retained state.
set -euo pipefail

if [ "$#" -ne 2 ]; then
  printf 'HOST_APPLY_HELPER_INPUT_INVALID\n' >&2
  exit 2
fi

action="$1"
state_dir="$2"
here="$(cd "$(dirname "$0")" && pwd)"
repository="$(cd "$here/../../.." && pwd)"
snapshot="$state_dir/predecessor"

case "$action" in
  *'|PROVISION_RUNTIME_PATHS|'*)
    if [ ! -e "$snapshot/complete" ]; then
      snapshot_stage="$state_dir/.predecessor.new"
      rm -rf -- "$snapshot_stage"
      install -d -o root -g root -m 0700 \
        "$snapshot_stage/etc-systemd-system" "$snapshot_stage/bootstrap-helpers"
      if [ -d /etc/asklegal ]; then
        cp -a -- /etc/asklegal "$snapshot_stage/etc-asklegal"
        printf 'present\n' > "$snapshot_stage/etc-asklegal.state"
      else
        printf 'absent\n' > "$snapshot_stage/etc-asklegal.state"
      fi
      find /etc/systemd/system -maxdepth 1 -type f \
        \( -name 'asklegal-*.service' -o -name 'asklegal-*.timer' -o -name 'asklegal*.target' \) \
        -exec cp -a -- '{}' "$snapshot_stage/etc-systemd-system/" ';'
      for helper in \
        asklegal-register-migrate asklegal-vault-bootstrap \
        asklegal-vault-application-rotation-network \
        asklegal-vault-primary-root-rotation-network; do
        if [ -f "/usr/local/libexec/$helper" ] && [ ! -L "/usr/local/libexec/$helper" ]; then
          cp -a -- "/usr/local/libexec/$helper" "$snapshot_stage/bootstrap-helpers/$helper"
          printf 'present\n' > "$snapshot_stage/bootstrap-helpers/$helper.state"
        elif [ ! -e "/usr/local/libexec/$helper" ]; then
          printf 'absent\n' > "$snapshot_stage/bootstrap-helpers/$helper.state"
        else
          printf 'HOST_APPLY_PREDECESSOR_INVALID\n' >&2
          exit 2
        fi
      done
      if [ -d /opt/asklegal/management-register/migrations ] && \
         [ ! -L /opt/asklegal/management-register/migrations ]; then
        cp -a -- /opt/asklegal/management-register/migrations \
          "$snapshot_stage/management-register-migrations"
        printf 'present\n' > "$snapshot_stage/management-register-migrations.state"
      elif [ ! -e /opt/asklegal/management-register/migrations ]; then
        printf 'absent\n' > "$snapshot_stage/management-register-migrations.state"
      else
        printf 'HOST_APPLY_PREDECESSOR_INVALID\n' >&2
        exit 2
      fi
      docker network ls --format '{{.Name}}' | LC_ALL=C sort > "$snapshot_stage/docker-networks.before"
      if nft list table inet asklegal > "$snapshot_stage/asklegal-firewall.before" 2>/dev/null; then
        printf 'present\n' > "$snapshot_stage/asklegal-firewall.state"
      else
        : > "$snapshot_stage/asklegal-firewall.before"
        printf 'absent\n' > "$snapshot_stage/asklegal-firewall.state"
      fi
      systemctl is-enabled asklegal.target > "$snapshot_stage/target-enabled.before" 2>/dev/null || true
      systemctl is-active asklegal.target > "$snapshot_stage/target-active.before" 2>/dev/null || true
      : > "$snapshot_stage/complete"
      rm -rf -- "$snapshot"
      mv -- "$snapshot_stage" "$snapshot"
    fi
    /usr/bin/bash "$repository/infrastructure/poc/provisioning/30-identities.sh"
    ;;
  *'|STAGE_RUNTIME_CONFIGURATION|'*)
    install -d -o root -g root -m 0755 \
      /etc/asklegal/launch /etc/asklegal/config /usr/local/libexec \
      /opt/asklegal/management-register
    find "$repository/infrastructure/poc/config" -maxdepth 1 -type f \
      -exec install -o root -g root -m 0644 '{}' /etc/asklegal/config/ ';'
    install -d -o root -g root -m 0755 /etc/asklegal/config/hk-v1-promotion
    profile_source="$repository/infrastructure/poc/config/hk-v1-promotion/serving-profile.json"
    profile_stage=/etc/asklegal/config/hk-v1-promotion/.serving-profile.json.new
    test "$(wc -l < "$profile_source")" -eq 1
    head -c -1 -- "$profile_source" > "$profile_stage"
    chown root:root "$profile_stage"
    chmod 0644 "$profile_stage"
    mv -f -- "$profile_stage" /etc/asklegal/config/hk-v1-promotion/serving-profile.json
    install -o root -g root -m 0644 \
      "$repository"/packages/processing/src/asklegal_processing/_resources/o200k_base.tiktoken \
      /etc/asklegal/config/hk-v1-promotion/o200k_base.tiktoken
    install -o root -g root -m 0755 "$repository"/infrastructure/poc/units/launch/*.sh /etc/asklegal/launch/
    install -o root -g root -m 0755 \
      "$repository"/infrastructure/poc/libexec/asklegal-register-migrate \
      /usr/local/libexec/asklegal-register-migrate
    install -o root -g root -m 0755 \
      "$repository"/infrastructure/poc/libexec/asklegal-vault-bootstrap \
      /usr/local/libexec/asklegal-vault-bootstrap
    install -o root -g root -m 0755 \
      "$repository"/infrastructure/poc/libexec/asklegal-vault-application-rotation-network \
      /usr/local/libexec/asklegal-vault-application-rotation-network
    install -o root -g root -m 0755 \
      "$repository"/infrastructure/poc/libexec/asklegal-vault-primary-root-rotation-network \
      /usr/local/libexec/asklegal-vault-primary-root-rotation-network
    migration_stage="$state_dir/.management-register-migrations.new"
    rm -rf -- "$migration_stage"
    install -d -o root -g root -m 0755 "$migration_stage"
    cp -a -- "$repository"/packages/management-register-adapter/migrations/. "$migration_stage/"
    find "$migration_stage" -type d -exec chmod 0755 {} +
    find "$migration_stage" -type f -exec chmod 0644 {} +
    chown -R root:root "$migration_stage"
    rm -rf -- /opt/asklegal/management-register/migrations
    mv -- "$migration_stage" /opt/asklegal/management-register/migrations
    ;;
  *'|RECONCILE_NETWORKS|'*)
    systemctl start asklegal-networks.service
    ;;
  *'|APPLY_HOST_FIREWALL|'*)
    CONFIRM_SECONDS=900 \
      /usr/bin/bash "$repository/infrastructure/poc/provisioning/60-firewall.sh"
    ;;
  *'|INSTALL_SYSTEMD_UNITS|'*)
    install -o root -g root -m 0644 "$repository"/infrastructure/poc/units/*.service \
      "$repository"/infrastructure/poc/units/*.target \
      "$repository"/infrastructure/poc/units/*.timer /etc/systemd/system/
    systemctl daemon-reload
    ;;
  *'|VERIFY_DIGEST_PINNED_CANDIDATE|'*)
    service="${action#*|service=}"
    service="${service%%|*}"
    candidate_tag="${action#*|candidate_tag=}"
    candidate_tag="${candidate_tag%%|*}"
    image_id="${action##*|image_id=}"
    docker image inspect --format '{{.Id}}' "$image_id" | grep -Fx -- "$image_id" >/dev/null
    docker image inspect --format '{{.Id}}' "$candidate_tag" | grep -Fx -- "$image_id" >/dev/null
    printf '%s %s\n' "$service" "$image_id"
    ;;
  *'|ENABLE_START_TARGET_AND_TIMERS|'*)
    bindings="${action##*|bindings=}"
    manifest_stage=/etc/asklegal/.deployment-images.new
    rm -f -- "$manifest_stage"
    umask 077
    : > "$manifest_stage"
    for expected_service in \
      acquisition-worker control-plane legal-processing-worker promotion-worker review-api; do
      binding="${bindings%%,*}"
      if [ "$bindings" = "$binding" ]; then
        bindings=""
      else
        bindings="${bindings#*,}"
      fi
      service="${binding%%@*}"
      image_id="${binding#*@}"
      [ "$service" = "$expected_service" ]
      printf '%s\n' "$image_id" | grep -Ex 'sha256:[0-9a-f]{64}' >/dev/null
      docker image inspect --format '{{.Id}}' "$image_id" | grep -Fx -- "$image_id" >/dev/null
      printf '%s %s\n' "$service" "$image_id" >> "$manifest_stage"
    done
    [ -z "$bindings" ]
    chown root:root "$manifest_stage"
    chmod 0400 "$manifest_stage"
    sync -d "$manifest_stage"
    mv -f -- "$manifest_stage" /etc/asklegal/deployment-images
    sync -d /etc/asklegal/deployment-images
    sync -f /etc/asklegal
    test ! -L /etc/asklegal/deployment-images
    test -f /etc/asklegal/deployment-images
    test "$(stat -c '%u:%g:%a' /etc/asklegal/deployment-images)" = '0:0:400'
    systemctl restart asklegal-register-migrate.service
    systemctl is-active --quiet asklegal-register-migrate.service
    test ! -L /var/lib/asklegal/control/register-migration-readback.json
    test "$(stat -c '%u:%g:%a' /var/lib/asklegal/control/register-migration-readback.json)" = '0:0:600'
    systemctl restart asklegal-vault-bootstrap.service
    systemctl is-active --quiet asklegal-vault-bootstrap.service
    test ! -L /var/lib/asklegal/control/vault-bootstrap-readback.json
    test "$(stat -c '%u:%g:%a' /var/lib/asklegal/control/vault-bootstrap-readback.json)" = '0:0:600'
    systemctl enable asklegal.target
    systemctl restart asklegal.target
    systemctl is-active --quiet asklegal.target
    ;;
  *'|CONFIRM_HOST_FIREWALL|'*)
    test -f "$repository/var/hk-v1/host/post-reconcile.json"
    nft list chain inet asklegal input | grep -F 'policy drop' >/dev/null
    nft list chain inet asklegal asklegal-container-egress | grep -F 'policy drop' >/dev/null
    touch /run/asklegal-firewall-confirmed
    ;;
  *'|RESTORE_RUNTIME_CONFIGURATION|'*)
    test -e "$snapshot/complete"
    test -f "$snapshot/etc-asklegal.state"
    rm -rf -- /etc/asklegal
    if [ -d "$snapshot/etc-asklegal" ]; then
      cp -a -- "$snapshot/etc-asklegal" /etc/asklegal
    else
      grep -Fx 'absent' "$snapshot/etc-asklegal.state" >/dev/null
    fi
    for helper in \
      asklegal-register-migrate asklegal-vault-bootstrap \
      asklegal-vault-application-rotation-network \
      asklegal-vault-primary-root-rotation-network; do
      rm -f -- "/usr/local/libexec/$helper"
      case "$(cat "$snapshot/bootstrap-helpers/$helper.state")" in
        present)
          install -o root -g root -m 0755 "$snapshot/bootstrap-helpers/$helper" \
            "/usr/local/libexec/$helper"
          ;;
        absent) ;;
        *) exit 2 ;;
      esac
    done
    rm -rf -- /opt/asklegal/management-register/migrations
    case "$(cat "$snapshot/management-register-migrations.state")" in
      present)
        cp -a -- "$snapshot/management-register-migrations" \
          /opt/asklegal/management-register/migrations
        ;;
      absent) ;;
      *) exit 2 ;;
    esac
    ;;
  *'|RESTORE_SYSTEMD_UNIT_BYTES|'*)
    test -e "$snapshot/complete"
    find /etc/systemd/system -maxdepth 1 -type f \
      \( -name 'asklegal-*.service' -o -name 'asklegal-*.timer' -o -name 'asklegal*.target' \) \
      -delete
    cp -a -- "$snapshot/etc-systemd-system"/. /etc/systemd/system/
    systemctl daemon-reload
    case "$(cat "$snapshot/target-enabled.before")" in
      enabled) systemctl enable asklegal.target ;;
      *) systemctl disable asklegal.target ;;
    esac
    case "$(cat "$snapshot/target-active.before")" in
      active) systemctl start asklegal.target ;;
      *) systemctl stop asklegal.target || true ;;
    esac
    ;;
  *'|RESTORE_NETWORK_SET|'*)
    test -e "$snapshot/complete"
    docker network ls --format '{{.Name}}' | LC_ALL=C sort > "$snapshot/docker-networks.after"
    comm -13 "$snapshot/docker-networks.before" "$snapshot/docker-networks.after" | \
      while IFS= read -r network; do
        case "$network" in asklegal-*) docker network rm "$network" ;; esac
      done
    ;;
  *'|RESTORE_HOST_FIREWALL|'*)
    test -e "$snapshot/complete"
    touch /run/asklegal-firewall-confirmed
    nft delete table inet asklegal 2>/dev/null || true
    case "$(cat "$snapshot/asklegal-firewall.state")" in
      present) nft -f "$snapshot/asklegal-firewall.before" ;;
      absent) ;;
      *) exit 2 ;;
    esac
    ;;
  *'|RESTORE_PREDECESSOR_SERVICE_IMAGE|'*)
    service="${action#*|service=}"
    service="${service%%|*}"
    image_id="${action##*|image_id=}"
    docker image inspect --format '{{.Id}}' "$image_id" | grep -Fx -- "$image_id" >/dev/null
    docker image tag "$image_id" "asklegal/${service}:v1"
    systemctl stop "asklegal-${service}.service" || true
    ;;
  *'|RESTORE_PREDECESSOR_SERVICE_ABSENCE|'*)
    service="${action##*|service=}"
    systemctl stop "asklegal-${service}.service" || true
    docker rm -f "asklegal-${service}" >/dev/null 2>&1 || true
    ;;
  *)
    printf 'HOST_APPLY_HELPER_ACTION_UNSUPPORTED\n' >&2
    exit 2
    ;;
esac

printf 'HOST_APPLY_HELPER_ACTION_COMPLETE\n'
