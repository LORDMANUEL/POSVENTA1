#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${MZ_E2E_BASE_URL:-http://127.0.0.1}"
API="${BASE_URL%/}/api"
EMAIL="${MZ_E2E_EMAIL:-owner.e2e@milyzebra.test}"
PASSWORD="${MZ_E2E_PASSWORD:-StableE2E-2026!}"

json_get() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"
}

request() {
  local method="$1" url="$2" body="${3:-}" token="${4:-}"
  local args=(-fsS -X "$method" "$url" -H 'Accept: application/json')
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' --data "$body")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  curl "${args[@]}"
}

LOGIN=$(curl -fsS -X POST "$API/auth/login" \
  --data-urlencode "username=$EMAIL" \
  --data-urlencode "password=$PASSWORD")
TOKEN=$(printf '%s' "$LOGIN" | json_get access_token)
[[ -n "$TOKEN" ]]

MODULES=$(request GET "$API/admin/modules" '' "$TOKEN")
python3 - "$MODULES" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
expected = {
    'platform','identity','branches','audit','catalog','inventory','purchasing','pos','orders',
    'payments','delivery','returns','customers','crm','loyalty','notifications','storefront',
    'cms','marketing','mily_ads','accounting','receivables','payables','banking','fiscal','hr',
    'attendance','payroll','workflows','integrations','hardware','music','visual','rag','ai','analytics',
}
actual = {row['key'] for row in rows}
assert actual == expected, {'missing': sorted(expected-actual), 'extra': sorted(actual-expected)}
assert len(rows) == 36, len(rows)
external = {'payments','fiscal','music','visual'}
for row in rows:
    if row['key'] in external:
        assert row['enabled'] is False, row
        assert row['external_mode'] == 'blocked', row
        assert row['external_gate'], row
    else:
        assert row['enabled'] is True, row
print('MODULE_REGISTRY_36=PASS')
PY

# Core/platform/identity/branches/audit/catalog/inventory.
request GET "$API/platform/access" '' "$TOKEN" | grep -q 'platform_admin'
ME=$(request GET "$API/me" '' "$TOKEN")
printf '%s' "$ME" | grep -q '"role":"owner"'
BRANCHES=$(request GET "$API/admin/branches" '' "$TOKEN")
BRANCH_ID=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])[0]["id"])' "$BRANCHES")
request GET "$API/audit/events?limit=10" '' "$TOKEN" >/tmp/mz-module-audit.json
request GET "$API/products" '' "$TOKEN" >/tmp/mz-module-products.json
request GET "$API/inventory" '' "$TOKEN" >/tmp/mz-module-inventory.json

# Purchasing, POS, orders, delivery, returns, customers and storefront.
request GET "$API/ops/suppliers" '' "$TOKEN" >/tmp/mz-module-suppliers.json
request GET "$API/cash/current" '' "$TOKEN" >/tmp/mz-module-cash.json
request GET "$API/commerce/orders" '' "$TOKEN" >/tmp/mz-module-orders.json
request GET "$API/ops/deliveries" '' "$TOKEN" >/tmp/mz-module-deliveries.json
request GET "$API/post-sales/sales?limit=5" '' "$TOKEN" >/tmp/mz-module-returns.json
CUSTOMER=$(request POST "$API/ops/customers" \
  '{"full_name":"Module Smoke Customer","email":"module-smoke@milyzebra.test","phone":"+50400000001"}' "$TOKEN")
CUSTOMER_ID=$(printf '%s' "$CUSTOMER" | json_get id)
request GET "$API/store/mily-zebra/catalog" >/tmp/mz-module-storefront.json

# CRM, loyalty and notifications perform real writes.
LEAD=$(request POST "$API/crm/leads" \
  '{"full_name":"Module Smoke Lead","email":"lead-smoke@milyzebra.test","source":"module-smoke"}' "$TOKEN")
printf '%s' "$LEAD" | grep -q '"status"'
LOYALTY=$(request POST "$API/loyalty/entries" \
  "{\"customer_id\":\"$CUSTOMER_ID\",\"points_delta\":\"5\",\"reason\":\"module smoke\"}" "$TOKEN")
printf '%s' "$LOYALTY" | grep -q '"points":"5'
NOTIFICATION=$(request POST "$API/notifications" \
  "{\"customer_id\":\"$CUSTOMER_ID\",\"channel\":\"email\",\"recipient\":\"module-smoke@milyzebra.test\",\"template_key\":\"transactional.module_smoke\",\"payload\":{\"ok\":true}}" "$TOKEN")
printf '%s' "$NOTIFICATION" | grep -q '"status"'

# CMS, marketing and Mily Ads.
CMS=$(request POST "$API/cms/pages" \
  '{"slug":"module-smoke","title":"Module Smoke","body":{"ok":true}}' "$TOKEN")
printf '%s' "$CMS" | grep -q '"status":"draft"'
CAMPAIGN=$(request POST "$API/marketing/campaigns" \
  '{"name":"Module Smoke Campaign","channel":"web","audience":{},"content":{"ok":true},"budget":"0"}' "$TOKEN")
printf '%s' "$CAMPAIGN" | grep -q '"status":"draft"'
PLACEMENT=$(request POST "$API/ads/placements" \
  '{"placement_key":"module-smoke","name":"Module Smoke Placement","content":{"ok":true}}' "$TOKEN")
PLACEMENT_ID=$(printf '%s' "$PLACEMENT" | json_get id)
request POST "$API/ads/placements/$PLACEMENT_ID/metric" '{"metric":"impression"}' "$TOKEN" | grep -q '"impressions":1'

# Accounting, CxC, CxP and banking are read here; extended E2E performs their economic writes.
request GET "$API/accounting/accounts" '' "$TOKEN" >/tmp/mz-module-accounting.json
request GET "$API/finance/receivables" '' "$TOKEN" >/tmp/mz-module-receivables.json
request GET "$API/finance/payables" '' "$TOKEN" >/tmp/mz-module-payables.json
request GET "$API/finance/banking/accounts" '' "$TOKEN" >/tmp/mz-module-banking.json

# HR, attendance and payroll perform a complete synthetic employee/payroll path.
EMPLOYEE=$(request POST "$API/hr/employees" \
  "{\"branch_id\":\"$BRANCH_ID\",\"employee_code\":\"SMOKE-001\",\"full_name\":\"Module Smoke Employee\",\"position\":\"QA Smoke\",\"department\":\"QA\",\"hire_date\":\"2026-08-01\",\"base_salary\":\"1000.00\"}" "$TOKEN")
EMPLOYEE_ID=$(printf '%s' "$EMPLOYEE" | json_get id)
ATTENDANCE=$(request POST "$API/attendance/events" \
  "{\"employee_id\":\"$EMPLOYEE_ID\",\"branch_id\":\"$BRANCH_ID\",\"event_type\":\"check_in\",\"source\":\"module-smoke\",\"note\":\"stable smoke\"}" "$TOKEN")
printf '%s' "$ATTENDANCE" | grep -q '"event_type":"check_in"'
PAYROLL=$(request POST "$API/payroll/runs" \
  '{"period_key":"module-smoke-2026-08","period_start":"2026-08-01","period_end":"2026-08-15"}' "$TOKEN")
PAYROLL_ID=$(printf '%s' "$PAYROLL" | json_get id)
request POST "$API/payroll/runs/$PAYROLL_ID/lines" \
  "{\"employee_id\":\"$EMPLOYEE_ID\",\"gross\":\"500.00\",\"deductions\":\"25.00\",\"bonuses\":\"10.00\",\"note\":\"module smoke\"}" "$TOKEN" | grep -q '"net":"485.00"'
request POST "$API/payroll/runs/$PAYROLL_ID/approve" '' "$TOKEN" | grep -q '"status":"approved"'

# Workflows and integrations/outbox.
WORKFLOW=$(request POST "$API/workflows" \
  '{"key":"module-smoke","name":"Module Smoke Workflow","event_key":"module.smoke","condition":{},"action":{"type":"noop"}}' "$TOKEN")
printf '%s' "$WORKFLOW" | grep -q '"active":true'
DISPATCH=$(request POST "$API/workflows/dispatch" \
  '{"event_key":"module.smoke","payload":{"ok":true}}' "$TOKEN")
printf '%s' "$DISPATCH" | grep -q '"event_key":"module.smoke"'
OUTBOX=$(request POST "$API/integrations/outbox" \
  '{"topic":"module.smoke","payload":{"ok":true},"event_id":"module-smoke-event-001"}' "$TOKEN")
printf '%s' "$OUTBOX" | grep -q '"event_id":"module-smoke-event-001"'

# Hardware management surface. Extended E2E certifies enrollment + device-authenticated claim.
request GET "$API/admin/devices" '' "$TOKEN" >/tmp/mz-module-hardware.json

# RAG, AI and analytics.
RAGDOC=$(request POST "$API/rag/documents" \
  '{"source_key":"module-smoke","title":"Module Smoke Knowledge","source_type":"test","content":"La política module smoke confirma conocimiento autorizado de Mily Zebra."}' "$TOKEN")
printf '%s' "$RAGDOC" | grep -q '"chunks"'
request POST "$API/rag/search" '{"question":"política module smoke","limit":3}' "$TOKEN" | grep -q 'module-smoke'
request POST "$API/ai/ask" '{"question":"política module smoke","limit":3}' "$TOKEN" | grep -q '"sources"'
request GET "$API/analytics/dashboard?days=30" '' "$TOKEN" | grep -q '"period_days":30'

# External modules must be present but fail closed in the normal stable profile.
for key in payments fiscal music visual; do
  CODE=$(curl -sS -o "/tmp/mz-module-$key.json" -w '%{http_code}' \
    -X PUT "$API/admin/modules/$key?enabled=true" \
    -H "Authorization: Bearer $TOKEN")
  [[ "$CODE" == '409' ]]
done

# Audit must include smoke writes, proving the audit module is not only readable.
AUDIT=$(request GET "$API/audit/events?action=workflow.created&limit=20" '' "$TOKEN")
python3 - "$AUDIT" <<'PY'
import json, sys
rows = json.loads(sys.argv[1])
assert rows and all(row['action'] == 'workflow.created' for row in rows), rows
assert all('tenant_id' not in row for row in rows), rows
PY

echo 'MODULE_SMOKE_COUNT=36'
echo 'MODULE_SMOKE=PASS'
