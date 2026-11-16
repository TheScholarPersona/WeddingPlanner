#!/bin/sh
# Makes the local stack reachable from phones and tablets in the same Wi-Fi.
#   scripts/lan.sh        use this Mac's network name (e.g. my-mac.local) and IP address
#   scripts/lan.sh off    back to https://localhost only
set -eu
cd "$(dirname "$0")/.."
test -f .env || cp .env.example .env

# Remove earlier LAN settings from .env (portable, no sed -i).
grep -v -E '^(SITE_ADDRESS|APP_BASE_URL|LAN_HOST)=' .env > .env.tmp || true
mv .env.tmp .env

if [ "${1:-}" = "off" ]; then
  docker compose up -d proxy frontend api worker
  echo "LAN access is off. The app is at https://localhost again."
  exit 0
fi

name=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
host=$(printf '%s.local' "$name" | tr '[:upper:]' '[:lower:]')
ip=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)

addresses="localhost, $host"
[ -n "$ip" ] && addresses="$addresses, $ip"
{
  echo "SITE_ADDRESS=$addresses"
  echo "APP_BASE_URL=https://$host"
  echo "LAN_HOST=$host${ip:+,$ip}"
} >> .env

docker compose up -d proxy frontend api worker
# Give Caddy a moment to issue the certificates for the new names.
sleep 3
docker compose cp proxy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt

cat <<INFO

The app is now reachable in your Wi-Fi at:
  https://$host${ip:+
  https://$ip   (if a device cannot find the name)}

On the phone, trust the local certificate once (otherwise Safari shows a warning):
  iPhone/iPad: AirDrop caddy-root.crt (in this folder) to the phone, then
    Settings > Profile Downloaded > Install, and
    Settings > General > About > Certificate Trust Settings > turn on "Caddy Local Authority".
  Android: Settings > Security > Encryption & credentials > Install a certificate > CA certificate.

If the phone cannot connect: allow incoming connections for Docker in
  System Settings > Network > Firewall > Options.
Emails and calendar links now use https://$host. Back to localhost only: make lan-off
INFO
