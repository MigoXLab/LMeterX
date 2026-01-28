#!/bin/sh
set -eu

normalize_bool() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|t|yes|y|on) printf 'true' ;;
    0|false|f|no|n|off|'') printf 'false' ;;
    *) printf 'false' ;;
  esac
}

cat <<EOF > /usr/share/nginx/html/env.js
window.RUNTIME_CONFIG = {
  VITE_API_BASE_URL: "${VITE_API_BASE_URL:-/api}",
  VITE_LDAP_ENABLED: $(normalize_bool "${VITE_LDAP_ENABLED:-false}"),
  VITE_PERSIST_ACCESS_TOKEN: $(normalize_bool "${VITE_PERSIST_ACCESS_TOKEN:-true}")
};
EOF

exec nginx -g 'daemon off;'
