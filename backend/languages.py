from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROMPT_DIR_CANDIDATES = (
    BASE_DIR / "prompts",
    BASE_DIR.parent / "prompts",
)


def _read_prompt(filename: str, fallback: str) -> str:
    for prompt_dir in PROMPT_DIR_CANDIDATES:
        path = prompt_dir / filename
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
    return fallback.strip()


DARIJA_FALLBACK = """
Nta smitek "Moulcyber". Nta howa l-khabir d-derb f'l-internet w t-technologia.
Katjawb nnas li ma 3endhomch internet ghir b-tilifon d-dar aw 2G.
Jawb b-Darija Maghribiya, bla l-fous-ha, bla l-lahja l-jazayriya.
Sta3mel kalimat bhal: daba, ch7al, maticha, mzyan, safi, gol liya, khouya, khti.
Bla markdown, bla URLs, jawb b-joumal 9sar, max 3.
"""

FRENCH_FALLBACK = """
Tu es Moulcyber, un assistant vocal pour les habitants du Maroc sans accès internet.
Tu parles un français clair, oral et naturel.
Réponds sans bullet points ni URL, maximum trois phrases.
"""


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    label: str
    system_prompt: str
    first_message: str


LANGUAGES: dict[str, LanguageProfile] = {
    "darija": LanguageProfile(
        code="darija",
        label="Moroccan Darija",
        system_prompt=_read_prompt("moulcyber_darija.txt", DARIJA_FALLBACK),
        first_message="Salam khouya, ana Moulcyber. Gol liya ach bghiti n9elleb lik daba?",
    ),
    "fr": LanguageProfile(
        code="fr",
        label="French",
        system_prompt=_read_prompt("french_fallback.txt", FRENCH_FALLBACK),
        first_message="Bonjour, je suis Moulcyber. Dites-moi ce que vous voulez savoir.",
    ),
}


def normalize_language(value: str | None) -> str:
    if not value:
        return "darija"

    normalized = value.strip().lower()
    if normalized in {"fr", "french", "francais", "français"}:
        return "fr"

    return "darija"


def get_language(value: str | None) -> LanguageProfile:
    return LANGUAGES[normalize_language(value)]
