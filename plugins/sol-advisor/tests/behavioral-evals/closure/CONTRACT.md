# Publish contract
publish and merge use the same qualification: scope=PUBLISHER, owner_id/token/acquired_at
match the identity at entry, and authority has not expired at actual publication.
prepare can finish after time or owner identity changed. Such a result must not publish.
Normal valid publish appends the value; valid merge appends {"merged": value}.
Owner state is caller-owned: reject without deleting/changing it or prior output.
