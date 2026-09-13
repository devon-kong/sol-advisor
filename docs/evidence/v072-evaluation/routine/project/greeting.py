def greet(name, uppercase=False):
    message = f"Hello, {name}"
    return message.upper() if uppercase else message
