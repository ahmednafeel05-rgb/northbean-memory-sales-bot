"""C3 PII masking before any LLM call sees the message (I7, FR-2, design brief §5/§7.2).

Every C3 type we need (cards, emails, phones, SSN/driver-license/passport IDs, IBAN, crypto,
password phrases) is a Presidio regex/pattern recognizer -- none need a trained NER model.

ponytail: a trained spaCy model (en_core_web_sm) would add LOCATION (address) detection, but
loading it crashes in this sandbox (OverflowError deep in spaCy's tokenizer deserialization --
a known spaCy/platform incompatibility, unrelated to our code) and no C3 type we actually need
depends on it. Using a blank tokenizer-only pipeline sidesteps the crash entirely. Upgrade path
if address detection is ever needed: fix/pin the spaCy model version in an environment where it
loads, then switch back to NlpEngineProvider with a real model.
"""
import spacy
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import SpacyNlpEngine


class _BlankSpacyNlpEngine(SpacyNlpEngine):
    def load(self) -> None:
        self.nlp = {m["lang_code"]: spacy.blank(m["lang_code"]) for m in self.models}


_analyzer = AnalyzerEngine(nlp_engine=_BlankSpacyNlpEngine())
_analyzer.registry.add_recognizer(
    PatternRecognizer(
        supported_entity="PASSWORD",
        patterns=[Pattern(name="password_phrase", regex=r"(?i)\b(?:password|pwd)\b\s*[:=]?\s*\S+", score=0.9)],
    )
)

# C3 per design brief §5: cards, passwords, phones, emails, IDs. (Addresses deferred, see above.)
C3_ENTITIES = [
    "CREDIT_CARD",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "US_DRIVER_LICENSE",
    "US_PASSPORT",
    "IBAN_CODE",
    "CRYPTO",
    "PASSWORD",
]


def mask(text: str) -> tuple[str, list[str]]:
    """Returns (masked_text, entity_types_found). Never returns the original PII value."""
    results = sorted(_analyzer.analyze(text=text, entities=C3_ENTITIES, language="en"), key=lambda r: r.start, reverse=True)
    masked = text
    found = []
    for r in results:
        masked = f"{masked[: r.start]}[REDACTED_{r.entity_type}]{masked[r.end :]}"
        found.append(r.entity_type)
    return masked, found


if __name__ == "__main__":
    demo_masked, demo_found = mask("My card is 4111 1111 1111 1111, email me at a@b.com")
    assert "4111" not in demo_masked
    assert "CREDIT_CARD" in demo_found
    print("pii_filter self-check OK:", demo_masked, demo_found)
