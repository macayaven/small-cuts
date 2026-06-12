"""Deterministic movie-style title cards for Small Cuts."""

from PIL import Image, ImageDraw, ImageFont

from .styles import STYLES

STYLE_CARDS = {
    "deadpan": ("#F2EFE6", "#1A1A1A", "rules"),
    "noir": ("#0D0D0F", "#E8E4D8", "hard_frame"),
    "nature_doc": ("#0E2A1B", "#F0E9D2", "double_frame"),
    "trailer": ("#101014", "#D4AF37", "spaced"),
    "telenovela": ("#5C0A14", "#FFE9EC", "ornament"),
    "symmetrist": ("#F7D6C9", "#5B3A29", "thin_frame"),
}


def derive_title(text: str, max_len: int = 60) -> str:
    value = text.strip()
    if value.startswith("["):
        tag_end = value.find("]")
        if tag_end != -1:
            value = value[tag_end + 1 :].strip()
    if not value:
        return "Untitled Scene"
    title = _first_clause(value).strip()
    if not title:
        return "Untitled Scene"
    return _truncate_title(title, max_len)


def render_title_card(
    title: str,
    style_key: str,
    size: tuple[int, int] = (1280, 720),
) -> Image.Image:
    style = STYLES[style_key]
    bg, fg, treatment = STYLE_CARDS[style_key]
    width, height = size
    image = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(image)
    if treatment == "hard_frame":
        inset = max(8, min(width, height) // 22)
        box = (inset, inset, width - inset - 1, height - inset - 1)
        draw.rectangle(box, outline=fg, width=2)
    elif treatment == "double_frame":
        inset = max(8, min(width, height) // 24)
        for offset in (inset, inset + max(4, inset // 3)):
            box = (offset, offset, width - offset - 1, height - offset - 1)
            draw.rectangle(box, outline=fg)
    elif treatment == "thin_frame":
        draw.rectangle((8, 8, width - 9, height - 9), outline=fg)
    margin = max(12, width // 9)
    content_width = max(1, width - margin * 2)
    max_title_height = max(24, int(height * 0.42))
    spaced = treatment == "spaced"
    for size_px in range(max(12, int(height * 0.12)), 5, -2):
        title_font = _font(size_px)
        lines = _wrap(draw, title.strip().upper(), title_font, content_width, spaced)
        block_width, block_height = _block(draw, lines, title_font)
        if block_width <= content_width and block_height <= max_title_height:
            break
    else:
        title_font = _font(6)
        lines = _wrap(draw, title.strip().upper(), title_font, content_width, spaced)
        _, block_height = _block(draw, lines, title_font)
    kicker_font = _font(max(10, int(height * 0.04)))
    subtitle_font = _font(max(10, int(height * 0.035)))
    _center(draw, "A SMALL CUTS PICTURE", width, int(height * 0.17), kicker_font, fg)
    if lines:
        title_top = max(int(height * 0.28), (height - block_height) // 2)
        title_size = getattr(title_font, "size", 12)
        if treatment == "rules":
            top_rule = max(8, title_top - title_size // 2)
            bottom_rule = min(height - 8, title_top + block_height + title_size // 2)
            draw.line((margin, top_rule, width - margin, top_rule), fill=fg)
            draw.line((margin, bottom_rule, width - margin, bottom_rule), fill=fg)
        line_height = _measure(draw, "Ag", title_font)[1]
        y = title_top
        for line in lines:
            _center(draw, line, width, y, title_font, fg)
            y += line_height
        if treatment == "ornament":
            _center(draw, "♦ ─── ♦", width, y + max(8, title_size // 4), subtitle_font, fg)
    subtitle_y = min(height - getattr(subtitle_font, "size", 10) * 2, int(height * 0.78))
    _center(draw, style.label.upper(), width, subtitle_y, subtitle_font, fg)
    return image


def _first_clause(text: str) -> str:
    index = 0
    while index < len(text):
        if text.startswith("...", index):
            if _ellipsis_ends_clause(text, index, 3):
                return text[:index]
            index += 3
            continue
        if text[index] == "…":
            if _ellipsis_ends_clause(text, index, 1):
                return text[:index]
        elif text[index] in ".!?;—":
            return text[:index]
        index += 1
    return text


def _ellipsis_ends_clause(text: str, index: int, width: int) -> bool:
    if len(text[:index].split()) < 3:
        return False
    next_index = index + width
    if next_index >= len(text) or not text[next_index].isspace():
        return False
    while next_index < len(text) and text[next_index].isspace():
        next_index += 1
    return next_index < len(text) and text[next_index].isupper()


def _truncate_title(title: str, max_len: int) -> str:
    if max_len < 1:
        return ""
    if len(title) <= max_len:
        return title
    if max_len == 1:
        return "…"
    cut = -1
    for index, char in enumerate(title[:max_len]):
        if char.isspace():
            cut = index
    if cut <= 0:
        return "…"
    return f"{title[:cut].rstrip()}…"


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_width, spaced):
    def show(value):
        return " ".join(value) if spaced else value

    def fits(value):
        return _measure(draw, show(value), font)[0] <= max_width

    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if fits(candidate):
            current = candidate
            continue
        if current:
            lines.append(show(current))
        current = word
        while len(current) > 1 and not fits(current):
            split = 1
            while split < len(current) and fits(current[: split + 1]):
                split += 1
            lines.append(show(current[:split]))
            current = current[split:]
    if current:
        lines.append(show(current))
    return lines


def _block(draw, lines, font):
    line_height = _measure(draw, "Ag", font)[1]
    widths = [_measure(draw, line, font)[0] for line in lines]
    return max(widths, default=0), len(lines) * line_height


def _center(draw, text, width, y, font, fill):
    x = (width - _measure(draw, text, font)[0]) / 2
    draw.text((x, y), text, font=font, fill=fill)


def _measure(draw, text, font):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top
