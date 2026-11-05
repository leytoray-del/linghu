#!/usr/bin/env bash
# Read-only server inspection for deployment planning.
# It changes nothing and does not print passwords, private keys or environment variables.
# Usage: sudo bash inspect-server.sh > report.txt 2>&1

section() { printf '\n===== %s =====\n' "$1"; }
have() { command -v "$1" >/dev/null 2>&1; }

section "OS and hardware"
cat /etc/os-release 2>/dev/null | grep -E '^(PRETTY_NAME|VERSION_ID)='
uname -r
nproc
section "Memory and swap"
free -m
swapon --show 2>/dev/null
section "Disk"
df -h -x tmpfs -x devtmpfs 2>/dev/null

section "Google Cloud instance metadata"
md() { curl -s -m 3 -H 'Metadata-Flavor: Google' "http://metadata.google.internal/computeMetadata/v1/instance/$1"; echo; }
echo "machine-type: $(md machine-type)"
echo "zone:         $(md zone)"
echo "external-ip:  $(md network-interfaces/0/access-configs/0/external-ip)"

section "Listening TCP ports and owning processes"
ss -tlnp 2>/dev/null | sed 's/users:/\n    users:/'

section "Top 15 processes by memory (RSS MB)"
ps -eo rss,comm,args --sort=-rss | head -16 | awk 'NR==1{print "RSS_MB  COMMAND  ARGS"; next}{printf "%6.0f  %s  ", $1/1024, $2; $1=$2=""; print substr($0,1,120)}'

section "Web servers and runtimes"
for b in nginx caddy apache2 httpd docker podman python3 node pm2 gunicorn uvicorn certbot sqlite3 git; do
  if have "$b"; then printf '%-10s %s\n' "$b" "$($b --version 2>&1 | head -1)"; else printf '%-10s (not installed)\n' "$b"; fi
done

section "Running systemd services (non-default)"
systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print $1}' \
  | grep -vE '^(systemd-|dbus|cron|ssh|rsyslog|getty|serial-getty|google-|chrony|unattended|polkit|networkd|udisks|multipathd|snapd|packagekit|user@)' 

section "Nginx sites (server_name, listen, proxy_pass, root only)"
if have nginx; then
  nginx -T 2>/dev/null | grep -E '^\s*(# configuration file|server_name|listen|proxy_pass|root|location)\b' | sed 's/^\s*/  /'
fi

section "Caddy sites"
for f in /etc/caddy/Caddyfile /etc/caddy/*.caddy; do
  [ -f "$f" ] && { echo "# $f"; grep -vE '^\s*#|^\s*$' "$f" | grep -viE 'password|secret|token|key'; }
done

section "Docker containers"
if have docker; then docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}' 2>/dev/null; docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' 2>/dev/null; fi

section "PM2 processes"
if have pm2; then pm2 ls 2>/dev/null; fi

section "TLS certificates (domains and expiry only)"
if have certbot; then certbot certificates 2>/dev/null | grep -E 'Certificate Name|Domains|Expiry'; fi
ls /var/lib/caddy/.local/share/caddy/certificates/*/ 2>/dev/null

section "Host firewall"
if have ufw; then ufw status 2>/dev/null; fi

section "Done"
