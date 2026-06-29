#!/usr/bin/env bash
# =============================================================================
#  Exact Hour - smoke test against a LIVE clock (the Pi running main.py, or the
#  demo: py demo_server.py). Hits every endpoint with curl and prints the JSON.
#
#  Usage:  ./smoke_test.sh 192.168.1.50          # port defaults to 8080
#          ./smoke_test.sh 192.168.1.50:8080
#          ./smoke_test.sh localhost:8731         # against demo_server.py
# =============================================================================
set -u

HOST="${1:-}"
if [ -z "$HOST" ]; then
  echo "usage: $0 <ip[:port]>   e.g. $0 192.168.1.50"
  exit 2
fi
case "$HOST" in
  http://*|https://*) BASE="$HOST" ;;
  *:*)                BASE="http://$HOST" ;;
  *)                  BASE="http://$HOST:8080" ;;
esac
BASE="${BASE%/}"

FAIL=0
# curl: -f fail on HTTP >=400, -s silent, -S show errors, -m 4s timeout
req() {
  local label="$1"; shift
  printf '%-26s ' "$label"
  if curl -fsS -m 4 "$@"; then echo
  else echo "  <request FAILED>"; FAIL=1; fi
}
post() { req "$1" -X POST -H 'Content-Type: application/json' "${@:2}"; }

echo "Target: $BASE"
echo "------------------------------------------------------------"
req  "1 GET status"        "$BASE/api/status"
post "2 set 25:00"         -d '{"minutes":25,"seconds":0}' "$BASE/api/set"
post "3 adjust +5"         -d '{"delta":5}'                "$BASE/api/adjust"
post "4 start (toggle)"    "$BASE/api/toggle"
sleep 1
req  "5 status (running)"  "$BASE/api/status"
post "6 pause (toggle)"    "$BASE/api/toggle"
post "7 reset"             "$BASE/api/reset"
req  "8 status (final)"    "$BASE/api/status"
echo "------------------------------------------------------------"

if [ "$FAIL" -eq 0 ]; then
  echo "OK - every endpoint responded."
else
  echo "FAILED - one or more requests did not respond (is the clock on this IP?)."
fi
exit "$FAIL"