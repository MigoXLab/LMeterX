#!/bin/sh
set -eu

cat <<EOF > /usr/share/nginx/html/env.js
window.RUNTIME_CONFIG = {
  VITE_API_BASE_URL: "${VITE_API_BASE_URL:-/api}",
  VITE_LDAP_ENABLED: "${VITE_LDAP_ENABLED:-false}",
  VITE_PERSIST_ACCESS_TOKEN: "${VITE_PERSIST_ACCESS_TOKEN:-true}"
};
EOF

exec nginx -g 'daemon off;'
