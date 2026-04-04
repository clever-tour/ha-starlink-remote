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
tests/unit/test_aggregate_empty_returns_empty_dict PASSED
tests/unit/test_aggregate_single_sample        PASSED
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

---

## 12. Current Starlink Settings (Automated Update)

**Last Updated:** Sat Apr 4 2026

### Active Session Cookies
```
1.1.1075706988.1775039010; sx_selected_locale=en-US; __stripe_mid=d9c9227b-ce7c-4402-861b-13bdb5bc0151a605c4; Starlink.Com.Sso.CheckSession=CB586348F75F9D763DAD484E0D808C67; Starlink.Com.Sso=CfDJ8LtfW3omojlBhUQi_zkD2NTWXUPyI0ywIH9etIF4p_VZwLZDgD_14QUtq-yjXBi3O4F49MwRjveuHgwG0SQm-v8KTgSe58i-FRVL4eS1U9W1VIKpsEj2y6kG6vh8-HzUifvZxZ6IHCIOUUryLACFdmOucLjpf0PRbvwE8h4mOcOj2CAblZBYmXrnPJGw83Mm3tf3GrfcA1pnjw7eKHnDCppQvbUQxV_p9omfeSTo9kCUrw_FxZ9JhZkh9Qw7LLx_tzjaZ0LJLZdZRKkYnXRzdMbS7e_rruRl0rFllq8b3tWM781F3cf1QolYTqNJJ0Z3mBDJgjrqFB7Hg51pR1E0beE; starlink.com.account_number=ACC-5147187-41313-10; Starlink.Com.Access.V1=CfDJ8LtfW3omojlBhUQi_zkD2NSbWkpEweYGRZ6XiUossjXQJEYi34fq94efoQtHaiV45W0UWwmc8E5BpREM7TbvOcaFq53zt2czUzRXK-ce6Y7JPqzEt3AXV9CbzARUbdyCCE6HC6BBjdLGAlb4kGn6DwkAvDsPB_hrWmmSvtm17zTJkNIuh47LFrAhKM3qCPMaujCtvE3scfmnFf9k7RBPALePOc6whqtj_JYgTa2xIen-DOwzcZ2V38fPOW9_GlpJeRShFPdfg43zAfRCP-TseorHW8KjOXqULsSb3-6Q_3Yvfh58okurLHfAgnyVtpLUjIiSN8MKr2JqHaq-Tdb7vxcAWV7cgWykA7-nDENMD0fcNV3JpoqcYCHYfV77uoEjE6wqigah37r3tnWBTSDiQiwtyyDqeE17FE9kwEf9a0O2xAWQ6rsT7cTnJE3lYv8E8Rwfv-vJRlXdGYCe4FdrBFYRNGWcqBNnJYus-sJaytbuTGIT4HI7l-gSJyhTQX3H965td86O8uuWllZkUDqiPlkZZXSHZ3d44NWwhb-DhpPTJNrx36xUM30UxkTZZt_1n5yLqd_KStQcV6QdX-3uibESo2nG7wQRuMNygA9zStrHpTxBpIwCBUDZZwEyLZ2fFt0WSgu_zbyOZjrrZ3msg2pvPJwSG8cvWRvldEYYRjtRGYWfesZVXsuqdwm8HqSA6grr2vtTwLB2n8eg6Bix0FFScwF4MKPSGBToJqc_L_aU4QjgQYJjUBC1FdHyOpRI32IrVGsK7-rEYRrBkxS07LFMA68-b2UGkPjpMPrIff7JiXsEeyu-tcCKxqy44eorLIts_Z3YiPitMS6B8RBMeIEV-gYvKy-umU4sfzZ-e80sNNQUHFBWEojZynW2BO_V4z03INg1Rm7pB-Pruq6GgL6Cxa7NFlfdM3JizHAgMFvQxx3ijqOwIMiDUW0pbGgasmX-rPvs22uMYGkRglGUNpMCdRWYpn2Bm-fF8ymVG2g028YfgyuM4McUnl6CUhhqlg0aa1R0SIKnE3iT4rlen4JeCKb4K1-KTGvPDbghVCJ0L4m-VWwvzWZ30DihOXNlTAa2dg0DgaOq9EE_esaRrNbxGjLGHlTxpRgCr8OcKju4IIkYmCDcVNniGrbruQAytPe9zf6nVfHUHbB5qKBpNz5Ot-TkHrLtVWS1zEQaX0IRysh-beR9lAsDFJiFx6LpZcdWm0FDOwV4DVK93nNDXEcm6FFtBP0h-SI1UbTA16cU27ywouquKEFs_tocow4hTzJrnNcsYJv3hDlsxXbwJvnudaeUIlPVPRSJbHdb3iaFOhDY-lR4ehPkyYRynY_GZ0drT24eX3uIEYUhE8bOdUwvEvLtfpLq9iDY6xN0IQs5yVrFf8S-z-0dg_GsedhITGGYtbzTDt0Lb8Y6vuQNNwfXQ92Yp-t_wyNWRgOn-2kddT67W10Ppl5PQEtHcQ-9DoT38lSH6VRVnizZvolyzrnV5T5PF0VO02uENhlvoy00uNPzshGslST4mtyiVcaU_JWUi8s9rX7bOPrYZmuXqikQXHFyxY0pf2TZ0zEtBt8oTGOQUX2whddZC8basFFa3PYnOaFFCyQ6JmS3zj2l2HEiqBnddGiNWgRKzwIsHjBr1KAiygWc0AbeI4pZnKTBadkb-eyvyXOfxlH6wni9WFfTkrG08j3gpCjn1IggyUG_QHvzmfV5bQ3oAPV7vIzyuUg-fC1aSw2DJFMEvBuIX3kWoAyC16WefkInVaxoVBddwGP-3fEAtIZkLVQvtm0mJPEDuzxl5hImXZQ1lwN65rgz-_GjSa2qf3pTGz3VUrFRRvXpSDbWOoskUyX6GQNMgdV00b9rFcD_SvTI5D1FtZb7TgJFOElo5dS6veFT8U0KHcRcwgBJsXURyGH1QJLNWNoQpWXrRgb8dWxe0aSVY2PAvemJXWli49KGQIcYalGg6YL3vD0baMMCB20d6gBnHvDWhaEeCpzy22r1PnpeUGDLVbTZvtQOKBtm2XawAcKksSeCYgDkg7NFElVnU85qv4XQwerVXPRwXnRBO5OB_7GmxFEOs-EsoJrzAYer2-PptyZuVOj3Z4T65U9n5BuTyw5_TPYcHREciXbQrp5I6gQsBnPe5JKPU6k-2wyfW8f2S-wX5t_oHwhMX2o40fJzsrQTvahCLVpnei3NxoEctIudLctt9DAwtrhqxoejN6YTbYwhH7tTkFQ5YC9LsaMxS2fO56VIr_Xm7ivDoqt7jBFvJnBSLDKZKGes6RsrGCKKo9JibytaJ_A8ghOAL6jSVG9J0RdWQ4aI6DCINwJd7dJX4ER4xZmtgH77j6LmLvC5om1qFK1Vdv6QQkhyqBsty_Zkh4zsaF-atcyQwaGcLykcvoV0ayFpGHI7A8RS64dpHY3LhzDRMhtY7iPEf0Mwl7ITazwvuzDeLV-S5IsBU1KedIcxaDjRtoWFZigKTITh_krYPV4YBQmFeXHWrHYsPudFN2Oyzto_7it910qh2-VDEYEIV7TUU02bpQ0u1f7KCgjC7g83-cr_VKsWM4uXByQypMxoezesLsvTmrD2xhyOGtPNFA9FJTPgUmpHw2nGfUF-2A6iOk5gGMWeTOK_vixnTfZvJVY207BHIR_CLafzhuL059XqzbslMnDhZ-AInLav4VmSI66n-rMl-l0zV00koy5SIFcAtDYjOLIgTft62x566m0W7mzg_a5PtnQnjTU7ld8FD6olT-FDOvBwn1y08Nrt8KTraENN3r5jClVAoK8a0IeOUUIPIJJBqdACjUbsiXqpxdJtWOIUEPv5_YnZaaKdeH9OiQrD1Bjq6dXtZTXuO_FgyE3eIQFA-3EBunSr-RXhY6-e9tk-SoVlcozc4GOr-rT8rBLL8wfWF6zaGEiw-DBPfOrzS-Q97n7q7Tr4KqIkRD4Lh4Pl8nRxVIisozVMalzs_f-mwPJLVfYjOVum8bxU_AyEg92Op8f28iEoO--jDa_wm4oob1iF3cKV26jZyNJKWMhBv5m9LnCCpdaARcOzyTO7skWF8uXyxdVScpPIHnSp-E_bfYKy8iTVQZqWb7Q5mZxsyN4_IJR-_FEDtf6noKAFD1VNSiiyYTz4a9i1qyW5PJEoE7zPxaq6yYE-c-eS2JIPoqbMlNcUrTxKiU7F-8aRSmM7Fg1B_wc1Q0Fw5z9Kakl8QPqg; _ga_S07SYD5D4F=GS2.1.s1775315405$o23$g1$t1775320755$j56$l0$h0
```

### Account Information
- **Account Number:** ACC-5147187-41313-10
- **Support Group:** https://signal.group/#CjQKIGdi3Eu4cjebMN6Lmno_8BikvfyduehDNeBGTXjvHt7SEhD9VRQGqufkCsp8Khz7xKzT
