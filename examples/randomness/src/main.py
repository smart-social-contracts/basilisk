import random

from basilisk import float64, update


@update
def random_number() -> float64:
    return random.random()
