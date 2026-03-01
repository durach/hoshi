#!/bin/sh
set -e

# Generate htpasswd at runtime (not baked into image layer)
htpasswd -cb /etc/nginx/.htpasswd "${DASHBOARD_USER:-admin}" "${DASHBOARD_PASSWORD:-changeme}"

# Inject WS_TOKEN into HTML template
export WS_TOKEN="${WS_TOKEN:-}"
envsubst '${WS_TOKEN}' < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html

exec nginx -g 'daemon off;'
