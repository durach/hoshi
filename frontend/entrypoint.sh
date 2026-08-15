#!/bin/sh
set -e

# Inject WS_TOKEN into HTML template
export WS_TOKEN="${WS_TOKEN:-}"
envsubst '${WS_TOKEN}' < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html

exec nginx -g 'daemon off;'
