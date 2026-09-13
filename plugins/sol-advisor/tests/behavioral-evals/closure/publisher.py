def _early_valid(owner, now):
    return owner["scope"] == "PUBLISHER" and owner["expires_at"] > now()

def publish(value, owner, prepare, now, output):
    if not _early_valid(owner, now):
        return False
    prepared = prepare(value)
    output.append(prepared)
    return True

def merge(value, owner, prepare, now, output):
    if not _early_valid(owner, now):
        return False
    prepared = prepare(value)
    output.append({"merged": prepared})
    return True
