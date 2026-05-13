from __future__ import annotations


def personalise(template: str, customer_name: str | None) -> str:
    """Replace [Name] placeholder with the actual customer name if known."""
    name = customer_name or "there"
    return template.replace("[Name]", name)
