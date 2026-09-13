def _early_valid(owner, now):
    return owner["scope"] == "PUBLISHER" and owner["expires_at"] > now()

def publish(value, owner, prepare, now, output):
    identity = (owner["owner_id"], owner["token"], owner["acquired_at"])
    if not _early_valid(owner, now):
        return False
    prepared = prepare(value)
    if not _early_valid(owner, now) or identity != (owner["owner_id"], owner["token"], owner["acquired_at"]):
        return False
    output.append(prepared)
    return True

def merge(value, owner, prepare, now, output):
    identity = (owner["owner_id"], owner["token"], owner["acquired_at"])
    if not _early_valid(owner, now):
        return False
    prepared = prepare(value)
    if not _early_valid(owner, now) or identity != (owner["owner_id"], owner["token"], owner["acquired_at"]):
        return False
    output.append({"merged": prepared})
    return True
