import heavy_sdk  # loads on boot (cost) — but only used inside functions below (deferrable)


def charge(amount):
    return heavy_sdk.charge(amount)
