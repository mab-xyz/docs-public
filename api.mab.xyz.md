# api.mab.xyz — API Reference

**Base URL:** `https://api.mab.xyz`

## Authentication

All endpoints require an API key sent in the `X-API-Key` HTTP header.

```
X-API-Key: <your-api-key>
```

A missing key returns `401 Unauthorized`. An invalid or revoked key returns `403 Forbidden`.

Before running any of the curl examples in this document, export your API key:

```bash
export MAB_API_KEY=<your-api-key>
```

---

## POST /v1/analysis/tx-risk-raw

Decode a raw unsigned or signed Ethereum transaction, simulate its execution, analyze every contract touched in the call chain, and return a risk assessment before the transaction is broadcast.

This endpoint is designed for wallets, frontends, and compliance workflows that need a pre-sign safety check. It accepts the raw transaction payload exactly as it would be submitted to the network.

### What the endpoint does

- **Validates and decodes** the hex-encoded transaction. Supports legacy (Type 0), EIP-2930 (Type 1), and EIP-1559 (Type 2) transactions, both signed and unsigned.
- **Simulates the transaction** using `trace_call` against the configured chain state at the requested block.
- **Extracts every touched contracts** including contracts reached through internal calls and `DELEGATECALL`s.
- **Checks source-code availability** for each touched contract. Any unverified contract in the execution path is flagged as dangerous.
- **Checks interaction novelty** using on-chain scan history. A *first-time interaction* means the sender or the root contract has never called this address before and thus is suspicious.

### Request

**Content-Type:** `application/json`

#### Body fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `raw_tx` | `string` | **yes** | — | 0x-prefixed hex of the raw transaction bytes. Accepts signed and unsigned legacy, EIP-2930, and EIP-1559 transactions. |
| `sender_address` | `string` | conditional | `null` | 0x-prefixed sender address. Required when `raw_tx` is an unsigned transaction. Ignored when the transaction is signed (the sender is recovered from the signature instead). |
| `block_tag` | `string` | no | `"latest"` | Block tag (`"latest"`, `"pending"`, `"safe"`, `"finalized"`) or a decimal block number at which to simulate the transaction. |
| `latest_offset` | `integer` | no | `100` | Limits first-time interaction checks to the most recent N blocks. Reduces database scan cost for high-traffic deployments. |
| `from_block` | `string` | no | `null` | Lower bound block (decimal number or tag) for the interaction history scan window. |
| `to_block` | `string` | no | `null` | Upper bound block (decimal number or tag) for the interaction history scan window. |

#### Response

#### Top-level fields

| Field | Type | Description |
|---|---|---|
| `status` | `string` | Overall risk verdict. One of `OK`, `DANGEROUS`, `POTENTIAL_DANGEROUS`. |
| `danger_reason` | `string \| null` | Root cause of a non-OK verdict. See [Danger reasons](#danger-reasons). |
| `ok_reason` | `string \| null` | Why the verdict is OK when no risk was found. See [OK reasons](#ok-reasons). |
| `interaction_status` | `object \| null` | Per-interaction-type verdict. Keys are the four interaction types; values are `ok`, `dangerous`, `potential_dangerous`, or `not_checked`. |
| `dangerous_interaction_types` | `string[] \| null` | The contract-based interaction types that confirmed a first-time interaction. Null when `status` is `OK`. |
| `details` | `object[]` | Per-contract breakdown for every address touched during simulation. See [details items](#details-items). |

#### Status values

| Value | Meaning |
|---|---|
| `OK` | All checked interactions have prior history and all contracts are verified. No risk signals detected. |
| `DANGEROUS` | The transactions is dangerous and should not be signed (eg at least one touched contract is unverified or never-seen before interaction was detected. |
| `POTENTIAL_DANGEROUS` | No confirmed danger, but interaction history is missing for at least one contract-based check. A definitive assessment cannot be made. |

#### Danger reasons

| Value | Meaning |
|---|---|
| `UNVERIFIED` | At least one touched contract (excluding EIP-7702 delegated EOAs) does not have verified source code. Takes priority over all other reasons. |
| `EIP_7702_UNVERIFIED_DELEGATE` | The transaction targets an EIP-7702 delegated EOA whose delegate contract is not verified. |
| `FIRST_TIME_INTERACTION` | Existing scan data confirms this is a first-time contract-based interaction for the sender or root contract. |
| `MISSING_HISTORY` | No historical scan data is available for at least one contract-based check. Risk cannot be ruled out. |

#### OK reasons

| Value | Meaning |
|---|---|
| `to EOA` | The destination address has no bytecode (plain ETH transfer). No contract risk applies. |
| `allowlist` | At least one contract bypassed source-code verification through the configured allowlist and no other risk signals were found. |
| `EIP-7702 delegated EOA (verified delegate)` | The destination is an EIP-7702 delegated EOA whose delegate contract is verified. |

#### Details items

Each element in `details` describes one address touched during the simulation.

| Field | Type | Description |
|---|---|---|
| `address` | `string` | Checksummed Ethereum address. |
| `first_time` | `boolean` | `true` if any of the checked interaction types is a first-time interaction for this address. |
| `verification` | `object \| null` | Source-code verification status fetched from Etherscan/Sourcify. Contains at minimum a `"verification"` key with values such as `"verified"`, `"fully-verified"`, `"not-verified"`, or `"allowlisted"`. `null` when no data is available. |
| `depth` | `integer \| null` | Call depth at which this address was reached: `0` is the direct `to` target, `1+` are internal or delegate calls. |
| `types` | `object \| null` | Map of EVM call opcodes to their observed frequency for this address, e.g. `{"CALL": 2, "DELEGATECALL": 1}`. |
| `interaction_first_time` | `object \| null` | Per-interaction-type first-time flag. Keys are interaction types; values are `true` if this is the first recorded interaction of that type for this address. |
| `interaction_state` | `object \| null` | Per-interaction-type data availability. `"FOUND"` means historical scan data exists and the result is authoritative; `"MISSING"` means no scan data is available and the result is best-effort. |
| `is_eip7702` | `boolean` | Whether this address is an EIP-7702 delegated EOA. |
| `delegate_address` | `string \| null` | For EIP-7702 delegated EOAs, the delegate contract address. The `verification` field refers to this delegate, not the EOA itself. |

---

## Examples

All examples use a real mainnet transaction. The raw transaction hex is taken directly from the signed payload as broadcast on Ethereum mainnet.

Before running any example, make sure your API key is exported in your shell:

```bash
export MAB_API_KEY=<your-api-key>
```

---

### OK — known contract with existing interaction history

**Mainnet tx:** `0xdde7709b60fc7f2be018eaef80009dda517639afd57d5bd8518ac20a2dc682e4`

The target contract (`0xD1669Ac6044...`) is on the allowlist. Both `contract_direct` and `contract_transitive` have `interaction_state: FOUND`, meaning the scan database has prior history and neither is a first-time interaction.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0x02f901b301832a90248307144384039158c18302f47a94d1669ac6044269b59fa12c5822439f609ca54f4180b901440dcd7a6c0000000000000000000000005a9a742d7af169bc38344d54a02c38e8b183431b0000000000000000000000000000000000000000000000145767bbedaba1ef00000000000000000000000000bdbdbdd0c22888e63cb9098ad6d68439197cb0910000000000000000000000000000000000000000000000000000000069bef062000000000000000000000000000000000000000000000000000000000033867d00000000000000000000000000000000000000000000000000000000000000c00000000000000000000000000000000000000000000000000000000000000041a114a6a3a0dd34cdd6a62ab101b4ea544f10e8065e8b947bcd38b79387e1b1c72049b66ceca3278c1442bb13e696e6f67839e898faadb96e7a5199f06defaf0c1c00000000000000000000000000000000000000000000000000000000000000c080a0578a92cd90ee12319d1389899e9d62ad262ed5f0b29ca2ceb5124e8579036caea02eb3ebd5d70f5d1704121a920adf0ee6417c93a796d4a6d4b50438c01b307bee"
  }'
```

```json
{
  "status": "OK",
  "danger_reason": null,
  "ok_reason": null,
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "ok",
    "contract_transitive": "ok"
  },
  "dangerous_interaction_types": [],
  "details": [
    {
      "address": "0xD1669Ac6044269b59Fa12c5822439F609Ca54F41",
      "first_time": false,
      "verification": {
        "address": "0xd1669ac6044269b59fa12c5822439f609ca54f41",
        "verification": "allowlisted",
        "verifiedAt": "N/A",
        "source": "allowlist"
      },
      "depth": 0,
      "types": null,
      "interaction_first_time": {
        "contract_direct": false,
        "contract_transitive": false
      },
      "interaction_state": {
        "contract_direct": "FOUND",
        "contract_transitive": "FOUND"
      },
      "is_eip7702": false,
      "delegate_address": null
    }
  ]
}
```

`first_time: false` and `interaction_state: "FOUND"` for both types confirm this is a repeat interaction backed by historical scan data.

---

### OK — plain ETH transfer to an EOA

**Mainnet tx:** `0xd07fb0e7783899dd01f5106e67ae92c98f5f70212de8b4b50a8ee38fd91a18f8`

The destination (`0x28FBDAE892...`) has no contract bytecode. No simulation occurs, `details` is empty, and the API returns immediately with `ok_reason: "to EOA"`.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0x02f86d011283154c23840e77afb18252d09428fbdae892ffe613a89c3ae8fa8b336b68cf6e08843b9aca0080c080a0688e45615884726452b61365ea76ed15993e7b83363064f6b0eb2377bf9650e9a022e06a13ceb12a061c7a80524948930791a0b98c0d51f78ac987f8a862a4aa2e"
  }'
```

```json
{
  "status": "OK",
  "danger_reason": null,
  "ok_reason": "to EOA",
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "ok",
    "contract_transitive": "ok"
  },
  "dangerous_interaction_types": [],
  "details": []
}
```

---

### DANGEROUS — unverified contract

**Mainnet tx:** `0xff3620eb165e2dabc0e630da58da0abd0403bb8d1d588881ed740861fe8692cf`

The target contract (`0x62E4d5D74b...`) has no verified source code on Etherscan. Any unverified contract in the execution path triggers an immediate `DANGEROUS` verdict regardless of interaction history.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0x02f86d014f830f424084072e132a8252089462e4d5d74bf8e3074baeff17a197ca105499d87d843b9aca0080c001a07d86c3231ff90ed7c8271f044d291520982248713ad620f64a2f6dfe9c172b69a01f0fa98a239114d55272a328a34a8dc4f717899dbd7d89176d81c5c8993e6e5c"
  }'
```

```json
{
  "status": "DANGEROUS",
  "danger_reason": "UNVERIFIED",
  "ok_reason": null,
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "ok",
    "contract_transitive": "ok"
  },
  "dangerous_interaction_types": [],
  "details": [
    {
      "address": "0x62E4d5D74bF8E3074BAeFf17A197Ca105499D87d",
      "first_time": false,
      "verification": {
        "address": "0x62e4d5d74bf8e3074baeff17a197ca105499d87d",
        "verification": "not-verified",
        "verifiedAt": "N/A",
        "source": "etherscan"
      },
      "depth": 0,
      "types": null,
      "interaction_first_time": {
        "contract_direct": false,
        "contract_transitive": false
      },
      "interaction_state": {
        "contract_direct": "FOUND",
        "contract_transitive": "FOUND"
      },
      "is_eip7702": false,
      "delegate_address": null
    }
  ]
}
```

`verification: "not-verified"` is the sole reason for the `DANGEROUS` verdict. Note that `interaction_status` shows `"ok"` for both contract types — the interaction history is known — but the missing source code still makes the transaction dangerous.

---

### DANGEROUS — first-time interaction with confirmed history

**Mainnet tx:** `0x4adf6d6330a08724e532dcd069ba75fd2c2b306b52054315769c212275405f39`

The root contract (`0x3073f7aAA4...`) is fully verified. During simulation it issues a `DELEGATECALL` to `0x2e2Bc0e292...` (depth 1). The scan database has historical data for this pair (`interaction_state: "FOUND"`) and confirms this is the first time the root contract has called that delegate — triggering `FIRST_TIME_INTERACTION`.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0x02f8b00103841b003b40850162d3924082f230943073f7aaa4db83f95e9fff17424f71d4751a307380b844a9059cbb0000000000000000000000009c308b1665097af7ab2e38a41577bfecdc2d1c5c00000000000000000000000000000000000000000000000000002b9477e53eaac001a0cfce777b36576d4a859cd2e9bd534afb89b61fcddddf476f0ad48006601ba7dda0747e74465d6f855e34bbdf87080f6665b9c8ea18098fe014ee0f0db8f3e5be3b"
  }'
```

```json
{
  "status": "DANGEROUS",
  "danger_reason": "FIRST_TIME_INTERACTION",
  "ok_reason": null,
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "dangerous",
    "contract_transitive": "dangerous"
  },
  "dangerous_interaction_types": ["contract_direct", "contract_transitive"],
  "details": [
    {
      "address": "0x3073f7aAA4DB83f95e9FFf17424F71D4751a3073",
      "first_time": false,
      "verification": {
        "address": "0x3073f7aAA4DB83f95e9FFf17424F71D4751a3073",
        "verification": "fully-verified",
        "verifiedAt": "2024-09-28T00:33:11Z",
        "source": "sourcify"
      },
      "depth": 0,
      "types": null,
      "interaction_first_time": {
        "contract_direct": false,
        "contract_transitive": false
      },
      "interaction_state": {
        "contract_direct": "FOUND",
        "contract_transitive": "FOUND"
      },
      "is_eip7702": false,
      "delegate_address": null
    },
    {
      "address": "0x2e2Bc0e2920578E0d46d1f83787b01f1d8094695",
      "first_time": true,
      "verification": {
        "address": "0x2e2Bc0e2920578E0d46d1f83787b01f1d8094695",
        "verification": "fully-verified",
        "verifiedAt": "2026-02-21T20:04:27Z",
        "source": "sourcify"
      },
      "depth": 1,
      "types": { "DELEGATECALL": 1 },
      "interaction_first_time": {
        "contract_direct": true,
        "contract_transitive": true
      },
      "interaction_state": {
        "contract_direct": "FOUND",
        "contract_transitive": "FOUND"
      },
      "is_eip7702": false,
      "delegate_address": null
    }
  ]
}
```

The root contract at `depth: 0` is known and fine. The delegate at `depth: 1` has `first_time: true` with `interaction_state: "FOUND"` — the history is authoritative and proves this delegate was never called before. Both `contract_direct` and `contract_transitive` are `"dangerous"` because the delegate is reached through both relationship types.

---

### DANGEROUS — first-time interaction with no prior scan data

**Mainnet tx:** `0x0af5a6d2d8b49f68dcfd4599a0e767450e76e08a5aeba9b3d534a604d308e60b`

The target is the SushiSwap router (`0xd9e1cE17f2...`, verified). The scan database has no history for this sender/contract pair — `interaction_state: "MISSING"` — so the system cannot confirm prior interaction. It conservatively treats this as a first-time interaction. All touched contracts are verified, so `UNVERIFIED` does not apply.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0xf901948201b0851bf08eb000830c920294d9e1ce17f2641f24ae83637ab66a2cca9c378b9f87038d7ea4c68000b901247ff36ab50000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000051841d9afe10fe55571bdb8f4af1060415003528ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff0000000000000000000000000000000000000000000000000000000000000004000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2000000000000000000000000798d1be841a82a273720ce31c822c61a67a601c30000000000000000000000002260fac5e5542a773aa44fbcfedf7c193bc2c599000000000000000000000000c02aaa39b223fe8d0a0e5c4f27ead9083c756cc225a06a5139f2697ee961c68d22527b6d098e93ce31a1b3edea73cc0713b5e6ce7ba1a0197c99469297315da8bce6d095d211745df5afa1f8bee110e706e6e273c86e3f"
  }'
```

```json
{
  "status": "DANGEROUS",
  "danger_reason": "FIRST_TIME_INTERACTION",
  "ok_reason": null,
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "dangerous",
    "contract_transitive": "dangerous"
  },
  "dangerous_interaction_types": ["contract_direct", "contract_transitive"],
  "details": [
    {
      "address": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
      "first_time": true,
      "verification": {
        "address": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        "verification": "verified",
        "verifiedAt": "2025-07-04T20:43:16Z",
        "source": "sourcify"
      },
      "depth": 0,
      "types": null,
      "interaction_first_time": {
        "contract_direct": true,
        "contract_transitive": true
      },
      "interaction_state": {
        "contract_direct": "MISSING",
        "contract_transitive": "MISSING"
      },
      "is_eip7702": false,
      "delegate_address": null
    },
    {
      "address": "0xf41E354EB138B328d56957B36B7F814826708724",
      "first_time": true,
      "verification": {
        "address": "0xf41e354eb138b328d56957b36b7f814826708724",
        "verification": "verified",
        "verifiedAt": "N/A",
        "source": "etherscan"
      },
      "depth": 1,
      "types": { "STATICCALL": 1 },
      "interaction_first_time": {
        "contract_direct": false,
        "contract_transitive": true
      },
      "interaction_state": {
        "contract_direct": "FOUND",
        "contract_transitive": "FOUND"
      },
      "is_eip7702": false,
      "delegate_address": null
    }
  ]
}
```

`interaction_state: "MISSING"` on the root contract means the scan database has no history for this sender/contract pair. The system conservatively treats it as first-time. The second touched contract at `depth: 1` has `FOUND` history and is not first-time for `contract_direct`, but is first-time for `contract_transitive` — triggering the dangerous verdict through the transitive check as well.

---

### POTENTIAL_DANGEROUS — missing history for a verified contract

This scenario occurs when a contract is verified (source code is available) but the scan database has not yet indexed the interaction history for this address pair. No danger is confirmed, but it cannot be ruled out.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0x02f8...",
    "sender_address": "0xYourSenderAddress"
  }'
```

```json
{
  "status": "POTENTIAL_DANGEROUS",
  "danger_reason": "MISSING_HISTORY",
  "ok_reason": null,
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "potential_dangerous",
    "contract_transitive": "potential_dangerous"
  },
  "dangerous_interaction_types": [],
  "details": [
    {
      "address": "0xSomeVerifiedContract",
      "first_time": false,
      "verification": {
        "verification": "fully-verified",
        "verifiedAt": "2025-01-01T00:00:00Z",
        "source": "sourcify"
      },
      "depth": 0,
      "types": { "CALL": 1 },
      "interaction_first_time": {
        "contract_direct": false,
        "contract_transitive": false
      },
      "interaction_state": {
        "contract_direct": "MISSING",
        "contract_transitive": "MISSING"
      },
      "is_eip7702": false,
      "delegate_address": null
    }
  ]
}
```

The contract is verified so `UNVERIFIED` does not apply. `interaction_state: "MISSING"` with a verified contract produces `POTENTIAL_DANGEROUS` rather than `DANGEROUS`.

---

### OK — contract deployment (no `to` address)

**Mainnet tx:** `0xaf63f86aeb19f6bd88ee7acadb508f7628337e43e50b80a5cc4d04085b90ef8f`

This is a legacy Type 0 transaction that deploys a new contract (the `to` field is absent in the RLP encoding). Contract-based interaction checks are skipped entirely. `interaction_status` shows all four types as `"not_checked"`.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0xf8ae2b850826299e00830120428080b85c61004456600436101561000d5761003a565b600035601c52600051341561002157600080fd5b63d2dce03d81141561003857600060005260206000f35b505b60006000fd5b61000461004403610004600039610004610044036000f325a082dbaaf0e0136eb02866de434c006744711062148fcde08aff0dd85f4d9bbb12a02fa1fdb368a4e6f48f93d3915feecd0b3935e006fa88536cdd8cc44fd82839d8"
  }'
```

```json
{
  "status": "OK",
  "danger_reason": null,
  "ok_reason": null,
  "interaction_status": {
    "sender_direct": "not_checked",
    "sender_transitive": "not_checked",
    "contract_direct": "not_checked",
    "contract_transitive": "not_checked"
  },
  "dangerous_interaction_types": [],
  "details": []
}
```

All interaction types are `"not_checked"` because there is no destination contract to evaluate. The newly deployed contract's address is not known until the transaction is mined.

---

### Unsigned transaction — providing `sender_address` explicitly

When a wallet generates a transaction before signing it, the sender cannot be recovered from the signature. Pass `sender_address` alongside the raw unsigned bytes.

The example below is the unsigned form of mainnet tx `0xd07fb0e7783899dd01f5106e67ae92c98f5f70212de8b4b50a8ee38fd91a18f8` (a plain ETH transfer), produced by stripping the `v`, `r`, `s` fields from the signed RLP.

```bash
curl -X POST https://api.mab.xyz/v1/analysis/tx-risk-raw \
  -H "X-API-Key: $MAB_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "raw_tx": "0x02ea011283154c23840e77afb18252d09428fbdae892ffe613a89c3ae8fa8b336b68cf6e08843b9aca0080c0",
    "sender_address": "0x97c542f03aE3A0be3079a54d8e1532D5Ebe56982"
  }'
```

If `sender_address` is omitted for an unsigned transaction the endpoint returns HTTP 422:

```json
{
  "detail": "Transaction Error: This transaction appears to be unsigned ... 'sender_address' must be provided in the request body for simulation."
}

