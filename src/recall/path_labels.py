from __future__ import annotations


def _match(parts: list[str], template: str) -> dict[str, str] | None:
    pattern = template.strip("/").split("/")
    if len(pattern) != len(parts):
        return None
    labels: dict[str, str] = {}
    for part, token in zip(parts, pattern):
        if token == "*":
            continue
        if token.startswith("{") and token.endswith("}"):
            labels[token[1:-1]] = part
        elif token != part:
            return None
    return labels


def path_labels(file_path: str, templates: list[str] | None) -> dict[str, str]:
    parts = file_path.strip("/").split("/")
    for template in templates or []:
        labels = _match(parts, template)
        if labels is not None:
            return labels
    return {}
