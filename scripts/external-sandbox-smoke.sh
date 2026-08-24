#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${MZ_E2E_BASE_URL:-http://127.0.0.1}"
API="${BASE_URL%/}/api"
EMAIL="${MZ_E2E_EMAIL:-sandbox.owner@milyzebra.test}"
PASSWORD="${MZ_E2E_PASSWORD:-SandboxExternal-2026!}"
BOOTSTRAP_TOKEN="${MZ_BOOTSTRAP_TOKEN:-sandbox-external-bootstrap-token}"

json_get() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

request() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}" idem="${5:-}"
  local args=(-fsS -X "$method" "$url" -H 'Accept: application/json')
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data "$body")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$idem" ]] && args+=(-H "Idempotency-Key: $idem")
  curl "${args[@]}"
}

for attempt in $(seq 1 90); do
  if curl -fsS "$API/health" >/dev/null 2>&1; then break; fi
  if [[ "$attempt" -eq 90 ]]; then echo 'API sandbox no respondió' >&2; exit 1; fi
  sleep 2
done

BOOTSTRAP=$(curl -fsS -X POST "$API/bootstrap" \
  -H 'Content-Type: application/json' \
  -H "X-Bootstrap-Token: $BOOTSTRAP_TOKEN" \
  --data "{\"store_name\":\"Mily Zebra External Sandbox\",\"store_slug\":\"mily-zebra\",\"branch_name\":\"Sandbox\",\"email\":\"$EMAIL\",\"full_name\":\"Sandbox Owner\",\"password\":\"$PASSWORD\"}")
TOKEN=$(printf '%s' "$BOOTSTRAP" | json_get access_token)
[[ -n "$TOKEN" ]]
BRANCHES=$(request GET "$API/admin/branches" '' "$TOKEN")
BRANCH_ID=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])[0]["id"])' "$BRANCHES")

for key in payments fiscal music visual; do
  ENABLED=$(request PUT "$API/admin/modules/$key?enabled=true" '' "$TOKEN")
  python3 - "$ENABLED" "$key" <<'PY'
import json,sys
row=json.loads(sys.argv[1]); key=sys.argv[2]
assert row['key']==key and row['enabled'] is True, row
assert row['external_mode']=='sandbox', row
PY
done

MODULES=$(request GET "$API/admin/modules" '' "$TOKEN")
python3 - "$MODULES" <<'PY'
import json,sys
rows={row['key']:row for row in json.loads(sys.argv[1])}
for key in ('payments','fiscal','music','visual'):
    assert rows[key]['enabled'] is True, rows[key]
    assert rows[key]['external_mode']=='sandbox', rows[key]
print('EXTERNAL_SANDBOX_MODES=PASS')
PY

# Payments software contract: order -> deterministic intent -> idempotent replay -> confirmation.
PRODUCT=$(request POST "$API/products" \
  '{"sku":"EXT-SBX-001","name":"External Sandbox Product","unit_cost":"30.00","sale_price":"90.00"}' "$TOKEN")
PRODUCT_ID=$(printf '%s' "$PRODUCT" | json_get id)
request POST "$API/inventory/movements" \
  "{\"product_id\":\"$PRODUCT_ID\",\"quantity_delta\":\"3\",\"reason\":\"external_sandbox_seed\"}" "$TOKEN" >/dev/null
ORDER_BODY="{\"full_name\":\"External Sandbox Customer\",\"email\":\"external-sandbox@example.com\",\"payment_method\":\"manual_transfer\",\"fulfillment_method\":\"pickup\",\"lines\":[{\"product_id\":\"$PRODUCT_ID\",\"quantity\":\"1\"}]}"
ORDER=$(request POST "$API/store/mily-zebra/checkout" "$ORDER_BODY" '' 'external-sandbox-order-001')
ORDER_ID=$(printf '%s' "$ORDER" | json_get id)
PAYMENT_STATUS=$(request GET "$API/payments/status" '' "$TOKEN")
printf '%s' "$PAYMENT_STATUS" | grep -q '"provider":"sandbox"'
INTENT=$(request POST "$API/payments/orders/$ORDER_ID/intent" '' "$TOKEN" 'external-intent-001')
INTENT_REF=$(printf '%s' "$INTENT" | json_get reference)
printf '%s' "$INTENT" | grep -q '"amount":"90.00"'
INTENT_REPLAY=$(request POST "$API/payments/orders/$ORDER_ID/intent" '' "$TOKEN" 'external-intent-001')
[[ "$(printf '%s' "$INTENT_REPLAY" | json_get reference)" == "$INTENT_REF" ]]
CONFIRMED=$(request POST "$API/payments/orders/$ORDER_ID/sandbox-confirm" '' "$TOKEN")
printf '%s' "$CONFIRMED" | grep -q '"payment_status":"paid"'
printf '%s' "$CONFIRMED" | grep -q '"order_status":"confirmed"'

# Fiscal software contract with synthetic, explicitly non-production identifiers.
RANGE=$(request POST "$API/fiscal/ranges" \
  "{\"branch_id\":\"$BRANCH_ID\",\"document_type\":\"invoice\",\"cai\":\"SANDBOX-NOT-A-REAL-CAI\",\"prefix\":\"SBX-\",\"range_start\":1,\"range_end\":10,\"expires_on\":\"2099-12-31\"}" "$TOKEN")
RANGE_ID=$(printf '%s' "$RANGE" | json_get id)
[[ -n "$RANGE_ID" ]]
FISCAL_BODY="{\"branch_id\":\"$BRANCH_ID\",\"document_type\":\"invoice\",\"source_type\":\"sandbox_order\",\"source_id\":\"$ORDER_ID\",\"payload\":{\"sandbox\":true}}"
DOC=$(request POST "$API/fiscal/documents" "$FISCAL_BODY" "$TOKEN")
DOC_ID=$(printf '%s' "$DOC" | json_get id)
printf '%s' "$DOC" | grep -q 'SANDBOX-NOT-A-REAL-CAI'
DOC_REPLAY=$(request POST "$API/fiscal/documents" "$FISCAL_BODY" "$TOKEN")
[[ "$(printf '%s' "$DOC_REPLAY" | json_get id)" == "$DOC_ID" ]]
request POST "$API/fiscal/documents/$DOC_ID/void" '{"reason":"Fin de smoke sandbox"}' "$TOKEN" | grep -q '"status":"voided"'

# Music/perifoneo software contract. No physical speaker is claimed or required.
ZONE=$(request POST "$API/music/zones" \
  "{\"branch_id\":\"$BRANCH_ID\",\"name\":\"Sandbox Audio Zone\",\"player_device_id\":\"sandbox-player\"}" "$TOKEN")
ZONE_ID=$(printf '%s' "$ZONE" | json_get id)
PLAYLIST=$(request POST "$API/music/playlists" \
  '{"name":"Sandbox Playlist","items":[{"title":"Synthetic track","url":"sandbox://track"}]}' "$TOKEN")
printf '%s' "$PLAYLIST" | grep -q '"active":true'
ANNOUNCEMENT=$(request POST "$API/music/announcements" \
  "{\"zone_id\":\"$ZONE_ID\",\"text\":\"Prueba de software Mily Zebra\",\"duck_music\":true}" "$TOKEN")
printf '%s' "$ANNOUNCEMENT" | grep -q '"duck_music":true'

# Visual/kiosk software contract with explicit consent and synthetic locators.
NO_CONSENT=$(curl -sS -o /tmp/mz-visual-no-consent.json -w '%{http_code}' \
  -X POST "$API/visual/sessions" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data "{\"branch_id\":\"$BRANCH_ID\",\"session_type\":\"virtual_fitting\",\"consent_granted\":false,\"ttl_minutes\":30}")
[[ "$NO_CONSENT" == '422' ]]
VISUAL=$(request POST "$API/visual/sessions" \
  "{\"branch_id\":\"$BRANCH_ID\",\"session_type\":\"virtual_fitting\",\"consent_granted\":true,\"input_locator\":\"sandbox://input\",\"ttl_minutes\":30}" "$TOKEN")
VISUAL_ID=$(printf '%s' "$VISUAL" | json_get id)
request POST "$API/visual/sessions/$VISUAL_ID/complete" '{"result_locator":"sandbox://result"}' "$TOKEN" | grep -q '"status":"completed"'
request POST "$API/visual/kiosk/heartbeat" \
  "{\"branch_id\":\"$BRANCH_ID\",\"device_id\":\"sandbox-kiosk\",\"status\":\"online\"}" "$TOKEN" | grep -q '"status":"online"'

echo 'PAYMENTS_SOFTWARE_SANDBOX=PASS'
echo 'FISCAL_SOFTWARE_SANDBOX=PASS'
echo 'MUSIC_SOFTWARE_SANDBOX=PASS'
echo 'VISUAL_SOFTWARE_SANDBOX=PASS'
echo 'EXTERNAL_SOFTWARE_SANDBOX=PASS'
echo 'EXTERNAL_REAL_WORLD_CERTIFICATION=NOT_CLAIMED'
