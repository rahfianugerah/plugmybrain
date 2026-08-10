#!/usr/bin/env bash
# Runs once on a fresh Debian/Ubuntu GCE VM, as root. Idempotent: safe to re-run.
# Prepares the host only. It creates no GCP resource and installs no application.
set -euo pipefail

SWAP_GB="${SWAP_GB:-4}"
MIN_DISK_GB="${MIN_DISK_GB:-25}"
TZ_NAME="${TZ_NAME:-Asia/Jakarta}"

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo bash $0" >&2
  exit 1
fi

# A full disk is how a Postgres data directory gets corrupted, and it is the one failure here
# with no clean recovery. Refuse rather than proceed onto a disk that will fill.
disk_gb=$(df -BG --output=size / | tail -1 | tr -dc '0-9')
if [ "$disk_gb" -lt "$MIN_DISK_GB" ]; then
  echo "root disk is ${disk_gb}GB, need at least ${MIN_DISK_GB}GB for images, data and WAL" >&2
  exit 1
fi

# Swap turns a 2 GiB memory spike into slow instead of OOM-killed. It is the whole reason
# e2-small is viable for this workload.
if ! swapon --show | grep -q /swapfile; then
  fallocate -l "${SWAP_GB}G" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  # Swap late rather than eagerly: this is a safety net, not a tier of storage.
  sysctl -w vm.swappiness=10
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
fi

# Cron reads local time. Without this the nightly backup at 03:00 fires at 10:00 in Jakarta.
timedatectl set-timezone "$TZ_NAME"

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker

install -d -m 700 /opt/brain
install -d -m 700 /var/backups/brain

echo "provisioned: ${SWAP_GB}G swap, ${disk_gb}G disk, timezone ${TZ_NAME}, docker enabled at boot"
echo "next: put the repo in /opt/brain, write /opt/brain/.env (chmod 600), then docker compose up -d"
