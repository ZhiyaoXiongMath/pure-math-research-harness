# Local body locator staging

Final scientific locators always contain real SHA-256 identities and exact UTF-8 byte or Unicode codepoint ranges. A new Knowledge Change body has no identity until the host seals its bytes. The submission grammar therefore accepts `blob_hash: "body:<local_key>"` and `quoted_sha256: null` only for a body in the same NEW/REVISE transaction. The host validates the range, computes both hashes and resolves the staging locator before validating or identifying the scientific record. Unknown local keys, invalid UTF-8 boundaries and out-of-range intervals fail. Persisted records never contain staging references or null hashes.

A submission with explicit correct hashes and one with these host-resolved staging locators identify the same content. This complements the existing `local:<key>` record references and does not change scientific identity, support authority.
