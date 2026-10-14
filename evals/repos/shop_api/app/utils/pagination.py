def parse_page_params(page: int | None, size: int | None) -> tuple[int, int]:
    """Clamp user-supplied page / size query params to sane bounds."""
    return max(page or 1, 1), min(max(size or 20, 1), 100)


def paginate(items: list, page: int, size: int) -> dict:
    """Slice a list into one page and report total and page count."""
    start = (page - 1) * size
    return {
        "items": items[start : start + size],
        "total": len(items),
        "pages": -(-len(items) // size),
    }
