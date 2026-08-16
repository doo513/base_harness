# 06 — Evidence Standard

Evidence levels:
- **A** direct implementation/runtime evidence: source, executed test, shell output, hash, environment probe, CI log.
- **B** primary external evidence: official repo/docs, original paper, release note.
- **C** synthesis/design inference.

Never report C as A.

Record important claims as:
```yaml
claim_id:
claim:
evidence_level: A|B|C
source:
test_or_file:
result:
limitations:
status: supported|refuted|uncertain
```

Save negative evidence: what failed, why, whether assumption was wrong, what changed. Use VERIFIED only when required verifier strength is met; SUPPORTED when insufficient; PROPOSED for actor claims; REFUTED when contradicted.
