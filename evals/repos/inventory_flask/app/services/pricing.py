DEFAULT_MARKUP = 0.25


def apply_markup(cost: float, markup: float = DEFAULT_MARKUP) -> float:
    """Selling price: cost plus a percentage markup, rounded to cents."""
    return round(cost * (1 + markup), 2)
