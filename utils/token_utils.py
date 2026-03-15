import re
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Single-pass regex pattern for custom format placeholders -> strftime codes
_FORMAT_MAP = {
    "yyyy": "%Y",
    "MM": "%m",
    "dd": "%d",
    "HH": "%H",
    "mm": "%M",
    "ss": "%S",
}

# Alternation pattern ordered longest-first for correct matching
_FORMAT_PATTERN = re.compile("|".join(sorted(_FORMAT_MAP.keys(), key=len, reverse=True)))

# Token pattern: %token% or %token:format%
_TOKEN_PATTERN = re.compile(r"%(\w+)(?::([^%]*))?%")


def _custom_to_strftime(fmt: str) -> str:
    """Convert custom format placeholders to Python strftime codes using single-pass regex."""
    return _FORMAT_PATTERN.sub(lambda m: _FORMAT_MAP[m.group()], fmt)


def resolve_tokens(template: str, context: dict | None = None) -> str:
    """Resolve path template tokens to their values.

    Args:
        template: String containing tokens like %date%, %date:dd-MM-yyyy%, %filename%, %layer%
        context: Optional dict with 'filename' (str or None) and 'layer' (str or None)

    Returns:
        The template string with recognized tokens replaced. Unrecognized tokens are left as-is.
    """
    if "%" not in template:
        return template

    if context is None:
        context = {}

    now = datetime.now()

    def _replace_token(match):
        token = match.group(1)
        fmt = match.group(2)

        if token == "date":
            if not fmt:
                return now.strftime("%Y-%m-%d")
            return now.strftime(_custom_to_strftime(fmt))

        if token == "time":
            if not fmt:
                return now.strftime("%H-%M-%S")
            return now.strftime(_custom_to_strftime(fmt))

        if token == "filename":
            value = context.get("filename")
            if value:
                return value
            return "FILENAME_MISSING"

        if token == "layer":
            value = context.get("layer")
            if value:
                return value
            return "LAYER_MISSING"

        # Unknown token: leave as-is
        return match.group(0)

    return _TOKEN_PATTERN.sub(_replace_token, template)
