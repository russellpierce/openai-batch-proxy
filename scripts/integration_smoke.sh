#!/usr/bin/env bash
#
# integration_smoke.sh — End-to-end smoke test against the real Docker stack.
#
# Discovers scripts/fixtures/config-*.yaml and iterates over each:
#   1. Populates api_keys.yaml from template
#   2. Copies fixture → config.yaml, rebuilds Docker stack
#   3. Tests every configured route (concurrent)
#   4. Runs standard health/models/auth checks
#   5. Tears down
#
# Usage:  ./scripts/integration_smoke.sh
# Requires: docker compose, curl, jq, OPENAI_API_KEY env var
#
set -euo pipefail
export LOG_LEVEL=DEBUG
PROJ_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ_DIR"

FIXTURES_DIR="$PROJ_DIR/scripts/fixtures"

# ── Colours ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${CYAN}▸ $*${NC}"; }
ok()    { echo -e "  ${GREEN}✔ $*${NC}"; }
fail()  { echo -e "  ${RED}✘ $*${NC}"; FAILURES=$((FAILURES + 1)); }
header(){ echo; echo -e "${BOLD}━━━ $* ━━━${NC}"; }

FAILURES=0
TESTS=0

# ── Caller key used in every test config ─────────────────────────────
CALLER_KEY="sk-your-caller-key-here"
OPENAI_KEY="${OPENAI_API_KEY:?OPENAI_API_KEY must be set}"

API="http://localhost:8000"

# ── Helpers ──────────────────────────────────────────────────────────
backup_configs() {
  info "Backing up live configs"
  cp config.yaml config.yaml.bak
  cp api_keys.yaml api_keys.yaml.bak 2>/dev/null || true
}

restore_configs() {
  info "Restoring original configs"
  mv config.yaml.bak config.yaml
  mv api_keys.yaml.bak api_keys.yaml 2>/dev/null || true
}

write_api_keys() {
  sed 's|__OPENAI_API_KEY__|'"$OPENAI_KEY"'|' \
    "$FIXTURES_DIR/api_keys.yaml.template" > api_keys.yaml
}

bring_up() {
  info "Rebuilding and starting stack"
  docker compose up -d --build --wait 2>&1 | tail -3
  # Extra pause for uvicorn startup inside the container
  sleep 2
}

tear_down() {
  info "Stopping stack"
  docker compose down 2>&1 | tail -2
}

assert_reachable() {
  local label="$1" status="$2"
  TESTS=$((TESTS + 1))
  if [[ "$status" =~ ^(200|400|401|403|500|502)$ ]]; then
    ok "$label  (HTTP $status)"
  else
    fail "$label  (HTTP $status)"
  fi
}

curl_post() {
  local path="$1"; shift
  curl -s -w "\n%{http_code}" \
    -X POST "$API$path" \
    -H "Authorization: Bearer $CALLER_KEY" \
    -H "Content-Type: application/json" \
    -d "$@"
}

curl_get() {
  local path="$1"
  curl -s -w "\n%{http_code}" \
    -X GET "$API$path" \
    -H "Authorization: Bearer $CALLER_KEY"
}

# Split body and status from curl output (status is last line)
split_response() {
  local raw="$1"
  BODY=$(echo "$raw" | sed '$d')
  STATUS=$(echo "$raw" | tail -1)
}

# ── Test body per endpoint type ──────────────────────────────────────
test_body_for() {
  case "$1" in
    /v1/chat/completions) echo '{"model":"gpt-5-nano","messages":[{"role":"user","content":"ping"}]}';;
    /v1/responses)        echo '{"model":"gpt-5-nano","input":"ping"}';;
    /v1/embeddings)       echo '{"model":"text-embedding-3-small","input":"ping"}';;
    /v1/moderations)      echo '{"model":"omni-moderation-latest","input":"ping"}';;
    *)                    return 1;;
  esac
}

# ── Extract configured routes from a fixture YAML ────────────────────
extract_routes() {
  grep -E '^\s{2}/v1/' "$1" | sed 's/:.*//' | tr -d ' '
}

# ── Look up the mode for a route in a fixture YAML ──────────────────
route_mode() {
  local config="$1" route="$2"
  grep -A5 "^  ${route}:" "$config" | grep 'mode:' | head -1 | sed 's/.*mode: *//' | tr -d ' "'
}

# ═════════════════════════════════════════════════════════════════════
# SETUP
# ═════════════════════════════════════════════════════════════════════
trap 'tear_down; restore_configs' EXIT
backup_configs
write_api_keys

# ═════════════════════════════════════════════════════════════════════
# DISCOVERY LOOP — iterate over every fixture config
# ═════════════════════════════════════════════════════════════════════
for config_file in "$FIXTURES_DIR"/config-*.yaml; do
  config_name=$(basename "$config_file" .yaml)
  header "$config_name"

  cp "$config_file" config.yaml
  bring_up

  routes=$(extract_routes "$config_file")

  # ── Phase A: Standard checks ───────────────────────────────────
  info "Phase A — Standard checks"

  # Health
  raw=$(curl -s -w "\n%{http_code}" "$API/health")
  split_response "$raw"
  TESTS=$((TESTS + 1))
  if [[ "$STATUS" == "200" ]]; then
    ok "GET /health  (HTTP $STATUS)"
  else
    fail "GET /health  (expected 200, got $STATUS)"
  fi

  # /v1/models passthrough
  raw=$(curl_get "/v1/models")
  split_response "$raw"
  TESTS=$((TESTS + 1))
  if [[ "$STATUS" =~ ^(200|401|403)$ ]]; then
    ok "GET /v1/models passthrough  (HTTP $STATUS)"
  else
    fail "GET /v1/models passthrough  (HTTP $STATUS)"
  fi

  # Missing auth → 401
  first_route=$(echo "$routes" | head -1)
  first_body=$(test_body_for "$first_route")
  raw=$(curl -s -w "\n%{http_code}" -X POST "$API$first_route" \
    -H "Content-Type: application/json" \
    -d "$first_body")
  split_response "$raw"
  TESTS=$((TESTS + 1))
  if [[ "$STATUS" == "401" ]]; then
    ok "POST $first_route missing auth  (HTTP $STATUS)"
  else
    fail "POST $first_route missing auth  (expected 401, got $STATUS)"
  fi

  # ── Phase B: Concurrent route tests ────────────────────────────
  route_count=$(echo "$routes" | wc -w | tr -d ' ')
  info "Phase B — Concurrent route tests ($route_count routes)"
  TMPDIR_CONC=$(mktemp -d)
  PIDS=()
  i=0
  for route in $routes; do
    mode=$(route_mode "$config_file" "$route")
    body=$(test_body_for "$route")
    i=$((i + 1))
    info "  [$i/$route_count] Launching POST $route ($mode) ..."
    (
      raw=$(curl_post "$route" "$body")
      echo "$raw" | tail -1 > "$TMPDIR_CONC/status_$((i - 1))"
    ) &
    PIDS+=($!)
  done
  info "  All $route_count requests launched — waiting for responses..."

  # Tail docker logs live while waiting
  (docker compose logs -f --since=1s 2>&1 | grep -v health) &
  LOG_PID=$!

  wait "${PIDS[@]}"
  kill "$LOG_PID" 2>/dev/null || true

  j=0
  for route in $routes; do
    status=$(cat "$TMPDIR_CONC/status_$j" 2>/dev/null || echo "TIMEOUT")
    j=$((j + 1))
    info "  [$j/$route_count] $route → HTTP $status"
    assert_reachable "$route concurrent" "$status"
  done
  rm -rf "$TMPDIR_CONC"

  tear_down
done

# ═════════════════════════════════════════════════════════════════════
# PYTEST (unit + integration)
# ═════════════════════════════════════════════════════════════════════
header "Running pytest (all tests)"
echo
.venv/bin/pytest tests/ -v --tb=short 2>&1 || FAILURES=$((FAILURES + 1))

# ═════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════
header "Summary"
echo
if [[ $FAILURES -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}All $TESTS smoke tests passed.${NC}"
else
  echo -e "${RED}${BOLD}$FAILURES failure(s) out of $TESTS smoke tests.${NC}"
fi
echo
exit "$FAILURES"
