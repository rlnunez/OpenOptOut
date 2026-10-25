# NIST SP 800-57 Key Management & Epoch Versioning

This document specifies OpenOptOut's cryptographic key lifecycle management conforming to **NIST Special Publication 800-57 Part 1 Revision 5 (Recommendation for Key Management)** Section 8 (Cryptoperiods and Key Transitions).

---

## 1. Overview & Regulatory Rationale

NIST SP 800-57 mandates that symmetric data encryption keys (such as AES-256-GCM field keys) have defined cryptoperiods (typically 1 to 2 years) after which they must be retired and replaced with freshly derived keys.

Simply rotating an environment variable causes all existing ciphertexts to become unreadable unless the system supports:
1. **Epoch Key Versioning:** Ciphertexts carry an explicit prefix identifying the key version/epoch used during encryption (`gcm:v{epoch}:{base64(nonce + ct + tag)}`).
2. **Multi-Epoch Decryption:** The decryption engine maintains knowledge of active and retired epoch keys.
3. **Automated Background Re-encryption:** A maintenance pipeline that reads records encrypted under retired epochs and re-wraps them under the active epoch without service downtime.

---

## 2. Key Derivation & Epoch Isolation

OpenOptOut derives epoch-specific keys using **HKDF-SHA256 (RFC 5869 / NIST SP 800-132)**:

$$\text{Key}_{\text{epoch}} = \text{HKDF-Expand}(\text{HKDF-Extract}(\text{Salt}, \text{MasterSecret}), \text{"openoptout:field-encryption-gcm:epoch-"} \parallel \text{epoch}, 32)$$

* **Epoch 1:** Compatible with baseline derivation `info=b"openoptout:field-encryption-gcm:v1"`.
* **Epoch 2+:** Derived with unique contextual info strings, ensuring mathematical independence between epochs even if one epoch key is theoretically compromised.

---

## 3. Storage Format Evolution

| Format Prefix | Cryptographic Primitive | Epoch | Notes |
| :--- | :--- | :--- | :--- |
| `gcm:v{N}:` | AES-256-GCM (NIST SP 800-38D) | Epoch $N$ | Modern versioned format |
| `gcm1:` | AES-256-GCM (NIST SP 800-38D) | Epoch 1 | Baseline GCM format |
| `Fernet` (urlsafe) | AES-128-CBC + HMAC-SHA256 | Legacy | Historical fallback |

---

## 4. Automated Re-encryption Pipeline

Administrators can trigger or schedule background cryptoperiod re-encryption via `encryption.reencrypt_all_records(db)`:
- Scans `Identity.value`, `FamilyMember.formal_name`, and `User.email`.
- Decrypts values encrypted under older epochs.
- Re-encrypts with the current `FIELD_ENCRYPTION_EPOCH`.
- Emits structured audit events recording the count of upgraded records.
