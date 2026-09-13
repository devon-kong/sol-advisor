def check_quantity(quantity):
    if type(quantity) is not int or not 1 <= quantity <= 20:
        raise ValueError("quantity")
    return quantity

def create_order(quantity):
    check_quantity(quantity)
    return {"quantity": quantity, "action": "create"}

def amend_order(quantity):
    check_quantity(quantity)
    return {"quantity": quantity, "action": "amend"}

def retry_order(quantity):
    check_quantity(quantity)
    return {"quantity": quantity, "action": "retry"}

def quote_order(quantity):
    return check_quantity(quantity) * 3
