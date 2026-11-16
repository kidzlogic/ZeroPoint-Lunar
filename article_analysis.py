"""Explainable keyword screening for lunar hazard signals in mission articles."""
import re


_SIGNAL_TERMS = {
    "Dust / plume": (
        "dust plume",
        "lunar dust",
        "regolith",
        "ejecta",
        "thruster",
        "electrostatic dust",
    ),
    "Rough terrain": (
        "boulder",
        "crater",
        "steep slope",
        "uneven terrain",
        "rough terrain",
        "rock field",
    ),
    "Mission risk": (
        "hazard",
        "danger",
        "unsafe",
        "unstable",
        "tip-over",
        "traction loss",
    ),
}
_NEGATION = re.compile(r"\b(?:no|not|without|absence of|free of|unlikely to)\s+(?:\w+\s+){0,3}$")


def analyze_article(text: str):
    """Return matching hazard phrases without presenting keyword counts as probabilities."""
    normalized = text.casefold()
    findings = []
    for category, terms in _SIGNAL_TERMS.items():
        matches = []
        for term in terms:
            for match in re.finditer(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized):
                context_start = max(0, match.start() - 48)
                context = normalized[context_start:match.start()]
                if not _NEGATION.search(context):
                    matches.append(term)
                    break
        if matches:
            findings.append({"category": category, "evidence": matches})
    return {
        "findings": findings,
        "summary": (
            "Textual hazard terms found; review the cited context."
            if findings
            else "No configured hazard terms found in the supplied text."
        ),
    }
