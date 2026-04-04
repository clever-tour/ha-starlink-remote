# ha-starlink — Gemini CLI Build & Test Instructions

> **Runtime:** Gemini CLI agent  
> **Goal:** Test the `starlink_ha` Home Assistant integration without a real Starlink dish, then deploy and configure it inside the `ha-test1` Docker container.

---

## 0. Prerequisites check

Run these before anything else. Stop and report failures clearly.

```bash
python3 --version          # must be >= 3.11
docker --version           # must be installed
docker ps -a --filter name=ha-test1 --format "{{.Names}} {{.Status}}"
                           # ha-test1 must appear (can be stopped)
pip install pytest requests websockets voluptuous
```

---

## 1. Repository layout

```
ha-starlink/
├── GEMINI.md                          ← this file
├── README.md
├── hacs.json
├── custom_components/
│   └── starlink_ha/
│       ├── __init__.py                ← integration setup
│       ├── config_flow.py             ← GUI config flow (multi-instance)
│       ├── coordinator.py             ← data fetch + history dedup
│       ├── sensor.py                  ← numeric / text sensors
│       ├── binary_sensor.py           ← alert + connectivity sensors
│       ├── entity_base.py
│       ├── const.py
│       ├── manifest.json              ← requires: starlink-client
│       ├── strings.json
│       └── translations/en.json
├── tests/
│   ├── fixtures/
│   │   └── mock_starlink_data.py      ← shared mock data factory
│   ├── unit/
│   │   ├── test_coordinator_dedup.py  ← history deduplication logic
│   │   ├── test_sensor_values.py      ← sensor value_fn extractors
│   │   └── test_config.py             ← config schema validation
│   └── integration/
│       └── test_mock_starlink.py      ← coordinator pipeline w/ mocks
└── scripts/
    ├── mock_starlink_server.py        ← HTTP mock of starlink-client
    ├── run_local_test.py              ← end-to-end local pipeline test
    ├── deploy_to_ha_test.py           ← deploys + configures ha-test1
    └── verify_ha_entities.py          ← entity state reporter
```

---

## 2. Phase 1 — Unit tests (no Docker, no HA, no dish)

These tests are pure Python. They must pass before touching Docker.

```bash
cd ha-starlink
pytest tests/unit/ -v --tb=short
```

**Expected output:**
```
tests/unit/test_coordinator_dedup.py::test_first_batch_entirely_novel     PASSED
tests/unit/test_coordinator_dedup.py::test_identical_second_batch_is_zero PASSED
tests/unit/test_coordinator_dedup.py::test_partial_overlap_returns_only_new PASSED
tests/unit/test_coordinator_dedup.py::test_seen_set_pruned_after_retention PASSED
tests/unit/test_coordinator_dedup.py::test_aggregate_computes_p95         PASSED
tests/unit/test_coordinator_dedup.py::test_aggregate_empty_returns_empty_dict PASSED
tests/unit/test_coordinator_dedup.py::test_aggregate_single_sample        PASSED
tests/unit/test_sensor_values.py::...                                      PASSED (9 tests)
tests/unit/test_config.py::...                                             PASSED (7 tests)
```

If any unit test fails, **stop and fix the failing test before continuing**.

---

## 3. Phase 2 — Integration tests (mock coordinator, no HA)

```bash
pytest tests/integration/ -v --tb=short
```

All tests in `test_mock_starlink.py` should pass.

---

## 4. Phase 3 — Local pipeline smoke test

This runs the full coordinator data pipeline (dedup, aggregation, WiFi) using
fixture data. No HA or Docker needed.

```bash
# Normal scenario
python scripts/run_local_test.py

# Degraded signal scenario
python scripts/run_local_test.py --scenario degraded

# Obstructed scenario
python scripts/run_local_test.py --scenario obstructed
```

**Expected output for each run:**  
- A JSON block for DISH STATUS  
- A JSON block for HISTORY SUMMARY  
- A JSON block for WIFI CLIENTS  
- Final line: `RESULT: PASSED ✓`

If the result is `FAILED`, read the error lines and fix the issue.

---

## 5. Phase 4 — Deploy to ha-test1

### 5.1 Get a Home Assistant long-lived token

**Option A — if HA is already onboarded:**
1. Open `http://localhost:8123` in a browser
2. Go to Profile (bottom left) → Long-Lived Access Tokens → Create Token
3. Name it `gemini-test`, copy the token
4. Set: `export HA_TOKEN=<paste_token_here>`

**Option B — if HA is freshly installed (needs onboarding first):**
The deploy script will detect a 401 on `/api/` and print this instruction.
Complete onboarding in the browser, then re-run.

### 5.2 Run the deploy script

```bash
export HA_TOKEN=your_token_here
export HA_URL=http://localhost:8123

python scripts/deploy_to_ha_test.py \
  --ha-url "$HA_URL" \
  --ha-token "$HA_TOKEN" \
  --cookie '{"mock": true}' \
  --router-id Router-MOCK00000000 \
  --instance-name "Test Instance" \
  --scan-interval 60
```

The script performs these steps automatically:
1. ✓ Verifies `ha-test1` container is running (starts it if stopped)
2. ✓ Copies `custom_components/starlink_ha/` into `/config/custom_components/`
3. ✓ Waits for HA to be reachable
4. ✓ Restarts HA core to load the new component
5. ✓ Creates a `starlink_ha` config entry via the WebSocket API
6. ✓ Polls until entities appear in the entity registry
7. ✓ Runs a 3-entity smoke test

### 5.3 Deploy with a real Starlink connection

If you have real Starlink credentials:

```bash
python scripts/deploy_to_ha_test.py \
  --ha-url "$HA_URL" \
  --ha-token "$HA_TOKEN" \
  --cookie "$(cat /path/to/cookie.json)" \
  --router-id Router-010000000000abcd \
  --instance-name Home \
  --scan-interval 60
```

### 5.4 Re-deploy without restart (files already in place)

If iterating on the integration code without changing the component structure:

```bash
python scripts/deploy_to_ha_test.py \
  --ha-url "$HA_URL" \
  --ha-token "$HA_TOKEN" \
  --skip-restart
```

---

## 6. Phase 5 — Verify entities in ha-test1

After deploy, verify all entities are reporting data:

```bash
python scripts/verify_ha_entities.py \
  --ha-url http://localhost:8123 \
  --ha-token "$HA_TOKEN"
```

**Good output looks like:**
```
  [BINARY_SENSOR]
    ✓  binary_sensor.test_instance_starlink_connected        on                   (45s ago)
    ✓  binary_sensor.test_instance_starlink_obstructed       off                  (45s ago)

  [SENSOR]
    ✓  sensor.test_instance_starlink_state                   CONNECTED            (45s ago)
    ✓  sensor.test_instance_starlink_downlink_throughput     250000000.0 bit/s    (45s ago)
    ✓  sensor.test_instance_starlink_ping_latency            22.5 ms              (45s ago)
    ✓  sensor.test_instance_starlink_wifi_clients            3 devices            (45s ago)
    ...
  ✓ All 25 entities are reporting data
```

If entities show `unavailable`:
1. Check HA logs: `docker logs ha-test1 --tail 100 | grep starlink`
2. The mock cookie `{"mock": true}` will cause `cannot_connect` on real validation.  
   This is expected — the coordinator will log `UpdateFailed` but entities will still be created.  
   To suppress this, the `_validate_input` in `config_flow.py` skips the connection test when  
   the cookie contains `"mock": true`. See §9 below.

---

## 7. Complete test sequence (copy-paste for Gemini CLI)

Run this exact sequence in order. Stop at the first failure.

```bash
# 0. Install test deps
pip install pytest requests websockets voluptuous

# 1. Unit tests
cd ha-starlink
pytest tests/unit/ -v --tb=short
[ $? -eq 0 ] || { echo "UNIT TESTS FAILED"; exit 1; }

# 2. Integration tests
pytest tests/integration/ -v --tb=short
[ $? -eq 0 ] || { echo "INTEGRATION TESTS FAILED"; exit 1; }

# 3. Local pipeline test (all 3 scenarios)
python scripts/run_local_test.py --scenario normal
python scripts/run_local_test.py --scenario degraded
python scripts/run_local_test.py --scenario obstructed

# 4. Deploy to ha-test1 (set HA_TOKEN first)
python scripts/deploy_to_ha_test.py \
  --ha-url http://localhost:8123 \
  --ha-token "$HA_TOKEN" \
  --cookie '{"mock": true}' \
  --router-id Router-MOCK00000000 \
  --instance-name "Test Instance"

# 5. Verify entities
python scripts/verify_ha_entities.py \
  --ha-url http://localhost:8123 \
  --ha-token "$HA_TOKEN"
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: homeassistant` in unit tests | Expected — HA is stubbed | Tests stub HA automatically; ensure you're running from the repo root |
| `Container 'ha-test1' not found` | Container doesn't exist | `docker run -d --name ha-test1 -p 8123:8123 -v ha-test1-config:/config homeassistant/home-assistant:stable` |
| `Auth failed` in deploy script | Token is wrong or expired | Re-create token in HA profile page |
| Entities stuck as `unavailable` | Mock cookie rejected by real starlink-client | Expected with mock credentials. Entities are created but coordinator returns `UpdateFailed`. Use `--skip-restart` after first deploy to avoid creating a second entry. |
| `config_entries/flow/create` WebSocket error | Component not loaded yet | Wait 10s after restart and retry. HA takes time to scan custom_components. |
| HA shows `Integration not found` | Files not copied correctly | `docker exec ha-test1 ls /config/custom_components/starlink_ha/` to verify |

---

## 9. Mock mode for ha-test1 (no real dish)

When `cookie` contains `"mock": true`, the `config_flow._validate_input()` function
skips the real gRPC connection test and always returns success. The coordinator will
still attempt real connections on each poll and log `UpdateFailed`, but the integration
will be fully configured and all entities will be registered.

To test entity state updates with mock data, start the mock server alongside HA:

```bash
# Terminal 1 — mock Starlink server
python scripts/mock_starlink_server.py --port 9200 --scenario normal

# Terminal 2 — deploy (mock server is on localhost:9200 = default dish IP)
python scripts/deploy_to_ha_test.py \
  --ha-url http://localhost:8123 \
  --ha-token "$HA_TOKEN" \
  --cookie '{"mock": true}' \
  --router-id Router-MOCK00000000
```

Note: The mock server speaks HTTP/JSON, not real gRPC. For it to work with the
coordinator you would need to patch `GrpcWebClient.call()` to hit the mock URL.
This is tracked as a future enhancement. For now, the mock server is used by
`run_local_test.py` via the fixture layer, not through the real coordinator.

---

## 10. Adding a second Starlink instance

To test multi-instance support, run the deploy script a second time with a different
`--instance-name`. Each invocation creates an independent config entry:

```bash
python scripts/deploy_to_ha_test.py \
  --ha-url http://localhost:8123 \
  --ha-token "$HA_TOKEN" \
  --instance-name "Office" \
  --router-id Router-OFFICE000000 \
  --skip-restart   # already deployed, no restart needed
```

Then verify both device sets appear:
```bash
python scripts/verify_ha_entities.py --ha-token "$HA_TOKEN" --filter starlink
```

---

## 11. CI pipeline

The GitHub Actions workflow (`.github/workflows/validate.yml`) runs:
1. HACS validation (manifest.json, hacs.json, directory structure)
2. hassfest validation (HA integration quality gates)
3. pytest unit + integration tests

All three must pass before merging or submitting to HACS.
