# Inventory Slices 2c & 2d — source draft & roadmap notes

**STATUS: RAW SOURCE MATERIAL — NOT an approved design.**
Captured 2026-07-03 so it survives context clears. These are the original
field-level models the user drafted (before the organizations app existed), plus
roadmap notes. When we actually build 2c and 2d, each still goes through the full
**brainstorming → spec → plan → subagent-driven implementation** cycle, exactly
like 2a and 2b did — and the draft below must be adapted to current conventions
(see "Adaptation required").

## Where these sit

- 2a — Catalog & locations — **DONE, merged** (`a12ea96`).
- 2b — Par templates — spec + plan committed on `feat/inventory-par-templates`;
  implementation pending.
- **2c — Stock & submissions** — the models below (`StockLot`,
  `InventorySubmission`, `InventorySubmissionItem`, `SubmissionLot`) + the
  count lifecycle and reconciliation into `StockLot`.
- **2d — Alert engine** — no model draft exists; low-quantity + expiring-soon
  detection reading `StockLot`. Introduces an `Alert` model + Celery-beat sweep
  (the repo already runs `worker`/`beat` containers).

## Adaptation required (when 2c/2d are actually designed)

The draft below predates the org app. Before implementing, it must be brought in
line with everything 2a/2b established:

- Inherit `apps.common.models.BaseModel` (UUID pk + `created_at`/`updated_at`);
  drop the hand-rolled `created_at`/`updated_at` and integer pks.
- Reuse `OrgScopedMixin`, `IsOrgMember`/`IsOrgAdmin`, the `{"error":{"detail":…}}`
  envelope, `StandardResultsSetPagination`, and cross-org FK validation.
- Everything is org-scoped. `StockLot`/submissions reach the org *through*
  `unit.organization` (like par lines reach it through `template.organization`),
  so decide whether to denormalize an `organization` FK or scope via the unit.
- `InventoryUnit.par_template` and `ParTemplate`/`ParTemplateItem` now EXIST
  (2b) — submissions can snapshot the unit's par as `expected_quantity`.
- The `PROTECT` FKs on `Item`/`UnitOfMeasure` here compound 2b's: the
  `ProtectedError → 409` handling (2b, on Item/UoM delete) already covers this,
  but confirm StockLot/submission references are included.

## 2c model draft (as originally drafted — pre-org-app, unadapted)

```python
class StockLot(models.Model):
    """Current believed stock of an item in a unit, grouped by expiration lot.
    This is the live state the alert engine reads; completed submissions
    reconcile into it. No hard uniqueness constraint: reconciliation replaces a
    unit's lots for an item wholesale, and nullable expiration dates make a
    composite unique constraint awkward across databases."""
    unit = models.ForeignKey(
        InventoryUnit, on_delete=models.CASCADE, related_name="stock_lots"
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="stock_lots")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="stock_lots"
    )
    expiration_date = models.DateField(null=True, blank=True)  # null = non-perishable
    lot_number = models.CharField(max_length=100, blank=True)
    last_counted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["expiration_date"]),  # nightly expiration sweep
            models.Index(fields=["unit", "item"]),  # per-unit low-quantity rollup
        ]


class InventorySubmission(models.Model):
    """A single count event for a unit (the "what we actually found").
    Serves as the audit trail of who counted what, and when."""
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    unit = models.ForeignKey(
        InventoryUnit, on_delete=models.CASCADE, related_name="submissions"
    )
    par_template = models.ForeignKey(
        ParTemplate, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submissions",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="submissions",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class InventorySubmissionItem(models.Model):
    submission = models.ForeignKey(
        InventorySubmission, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="submission_lines"
    )
    # Snapshot of the par at submission time, so history stays accurate when the
    # template later changes.
    expected_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Total found across all lots (sum of SubmissionLot rows for tracked items).
    counted_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_of_measure = models.ForeignKey(
        UnitOfMeasure, on_delete=models.PROTECT, related_name="submission_lines"
    )

    class Meta:
        unique_together = ("submission", "item")

    @property
    def variance(self):
        """Negative = short of par, positive = over."""
        return self.counted_quantity - self.expected_quantity


class SubmissionLot(models.Model):
    """One observed expiration lot recorded during a count. Used for items with
    tracks_expiration=True; rolls up into counted_quantity and reconciles into
    StockLot when the submission completes."""
    submission_item = models.ForeignKey(
        InventorySubmissionItem, on_delete=models.CASCADE, related_name="lots"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    expiration_date = models.DateField(null=True, blank=True)
    lot_number = models.CharField(max_length=100, blank=True)
```

## 2c behavior notes (from the draft's intent)

- **Submission lifecycle:** `in_progress → completed`. While in progress, a user
  records `SubmissionLot` rows per item (for `tracks_expiration` items) and/or a
  `counted_quantity`; `expected_quantity` is snapshotted from the unit's par at
  submission time so history stays accurate if the template later changes.
- **Reconciliation on completion:** completing a submission **replaces a unit's
  `StockLot` rows for each counted item wholesale** with the counted lots, and
  stamps `last_counted_at`. This is the live state 2d reads. (Deliberately no
  hard uniqueness on StockLot — nullable expiration dates make a composite
  unique constraint awkward.)
- **Variance** = `counted_quantity - expected_quantity` (negative = short of
  par).

## 2d scope notes (no model draft — design fresh)

- Reads `StockLot` (the two indexes above are for this): a **nightly expiration
  sweep** over `expiration_date`, and a **per-unit low-quantity rollup** over
  `(unit, item)`.
- **Low-quantity** = a unit's on-hand for an item (sum of its StockLots) below
  the par line's `min_quantity` (or `par_quantity`) from the unit's assigned
  `ParTemplate` (only `is_active` templates — 2b decision).
- **Expiring-soon** = `StockLot.expiration_date` within `Item.
  expiration_warning_days` (falls back to an org default when null — the 2a
  `expiration_warning_days` field feeds this).
- Likely a new `Alert` model + Celery-beat scheduled tasks (repo has
  `worker`/`beat`), plus an API to list/acknowledge alerts. All TBD at design
  time.

## Open questions to resolve when designing 2c/2d

- StockLot org-scoping: denormalized `organization` FK vs. scope-through-unit.
- Whether counting is per-leaf-unit only or any unit (2a chose "any unit holds
  stock").
- Submission editing/permissions: who can open/complete a count; can a submission
  be reopened; are partial counts allowed.
- Idempotency/transactionality of reconciliation (wrap in a transaction; guard
  double-complete).
- Alert model shape (per-unit-item? severity? acknowledge/resolve lifecycle) and
  notification channel (email via existing infra? in-app only?).
