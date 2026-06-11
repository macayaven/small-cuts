#!/usr/bin/env bash
# Connect this (ephemeral, cloud) Claude Code session to Carlos's tailnet.
#
# Requires TS_AUTHKEY in the environment — set it as a secret in the Claude
# Code environment settings (never commit it). Exits quietly when unset so
# the SessionStart hook is a no-op on machines that don't need it.
#
# Containers here have no TUN device, so tailscaled runs in userspace mode;
# outbound connections to tailnet hosts go through `tailscale nc` (see the
# ssh ProxyCommand this script installs).
set -euo pipefail

STATE_DIR=/tmp/tailscale
SOCKET="$STATE_DIR/tailscaled.sock"
TS="tailscale --socket=$SOCKET"
HOSTNAME_TS="${TS_HOSTNAME:-claude-small-cuts}"

if [ -z "${TS_AUTHKEY:-}" ]; then
  echo "tailnet-connect: TS_AUTHKEY not set; skipping." >&2
  exit 0
fi

if ! command -v tailscale >/dev/null; then
  echo "tailnet-connect: installing tailscale..."
  curl -sL --max-time 120 -o /tmp/ts.tgz "https://pkgs.tailscale.com/stable/tailscale_latest_amd64.tgz"
  tar xzf /tmp/ts.tgz -C /tmp
  cp /tmp/tailscale_*_amd64/tailscale /tmp/tailscale_*_amd64/tailscaled /usr/local/bin/
fi

mkdir -p "$STATE_DIR"
if ! $TS status >/dev/null 2>&1; then
  nohup tailscaled --tun=userspace-networking \
    --socks5-server=localhost:1055 \
    --outbound-http-proxy-listen=localhost:1056 \
    --state="$STATE_DIR/tailscaled.state" \
    --socket="$SOCKET" >"$STATE_DIR/tailscaled.log" 2>&1 &
  sleep 3
fi

$TS up --auth-key="$TS_AUTHKEY" --hostname="$HOSTNAME_TS" --accept-dns

# SSH through the tailnet without a TUN device: dial via `tailscale nc`.
# DGX_SPARK_USER / MAC_STUDIO_USER env vars (from environment secrets) set the login users.
mkdir -p ~/.ssh && chmod 700 ~/.ssh
if ! grep -q "tail48bab7" ~/.ssh/config 2>/dev/null; then
  cat >>~/.ssh/config <<EOF
Host *.tail48bab7.ts.net mac-studio spark
  ProxyCommand tailscale --socket=$SOCKET nc %h %p
  StrictHostKeyChecking accept-new
Host mac-studio
  HostName mac-studio.tail48bab7.ts.net
${MAC_STUDIO_USER:+  User $MAC_STUDIO_USER}
Host spark
  HostName spark-caeb.tail48bab7.ts.net
${DGX_SPARK_USER:+  User $DGX_SPARK_USER}
EOF
  chmod 600 ~/.ssh/config
fi

echo "tailnet-connect: connected as $HOSTNAME_TS"
$TS status | head -10
