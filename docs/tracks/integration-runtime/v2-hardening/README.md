# V2 Hardening Delivery

Status: implemented and promotion-tested on Windows with WSL2.

This delivery strengthens the V2 runtime without restoring the V1 execution path. The four auditable phases are:

1. `01_MODULE_BOUNDARY.md` - Coordinator ownership and state boundaries.
2. `02_SECURITY_BOUNDARY.md` - centralized redaction and trusted failures.
3. `03_STRICT_ISOLATION.md` - WSL2/Linux namespace strict execution.
4. `04_PROMOTION_REPORT.md` - promotion gates, results, and residual risks.

The authoritative execution path is Host `CoordinatorService`; Python remains an independent verifier. `net_monitor.py` is not part of this delivery.
