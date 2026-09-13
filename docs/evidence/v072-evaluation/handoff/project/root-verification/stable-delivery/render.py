from policy import LIMIT
from worker import mutate_if_editing

def render():
    # Deterministic external-writer boundary after Python imported the dependency.
    mutate_if_editing()
    return f"limit={LIMIT}"

if __name__ == "__main__":
    print(render())
