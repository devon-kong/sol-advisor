def publish(value, owner, prepare, now, output):
    if owner["expires_at"] <= now():
        return False
    prepared = prepare(value)
    output.append(prepared)
    return True
