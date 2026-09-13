# Prior closure
OBSERVED: expired owner could publish.
CAUSE: missing entry-time expiry check.
SURFACE: publish is affected; merge is excluded because it calls the same validity helper.
CHANGE: added an early validity check to both functions.
EVIDENCE: valid-at-entry and expired-at-entry tests passed.
UNVERIFIED: none.
New report: prepare may cross expiry; publish still returns True.
