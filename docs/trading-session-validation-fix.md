# Trading Session Validation Fix

Factor history, style windows, and forward-return endpoints are computed before
decision-date universe filtering. ST, suspended, and limit-price observations do
not disappear from the temporal sequence.

The session index is the sorted union of dates in the unfiltered input panel,
not an independently verified exchange calendar. Dates missing for every symbol
cannot be detected from this input alone.

Missing symbol observations remain missing within rolling windows. Prices are
never forward-filled. A missing, non-finite, or non-positive endpoint produces
an unmeasured return, not a shifted endpoint or a zero return. Existing rolling
minimum-observation thresholds and reversal suspension checks still apply.

Only original observations are returned, and eligibility still applies to the
decision date. Native parameter perturbations use the same unfiltered history.
Precomputed factor values remain keyed by date/code and still undergo existing
validation gates. Duplicate normalized date/code keys are rejected.

These labels are research price returns, not executable fills. This change does
not implement trading at suspended or limit-price sessions. Historical validation
results affected by compressed windows must be regenerated.

Synthetic regression tests cover endpoint selection, missing observations,
factor/style windows, perturbations, input order, invalid prices, duplicate keys,
and training boundaries. Synthetic tests are not evidence of factor validity.
