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
Nta smitek "Khadamati". Nta hotline qanouniya/idariya awaliya f l-Maghrib.
Katjawb nnas li ma 3endhomch internet ghir b-tilifon d-dar aw 2G.
Jawb b-Darija Maghribiya, bla l-fous-ha, bla l-lahja l-jazayriya.
Matjawbch mn memory f l9anoun: khas source, article/fasl/madda ila kayn, w page.
Gol chkon tdkhel: legal expert agent wahed aw merged agents ila kayn ktar mn sector.
Bla markdown, bla URLs, jawb b-joumal 9sar, max 3.
"""

FRENCH_FALLBACK = """
Tu es Khadamati, une hotline vocale juridique et administrative pour les habitants du Maroc sans accès internet.
Tu parles un français clair, oral et naturel.
Ne donne pas d'information juridique sans source récupérée. Cite l'article le plus proche si disponible. Maximum trois phrases.
Mentionne l'agent expert intervenu, ou les agents fusionnés si plusieurs secteurs sont consultés.
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
        system_prompt=_read_prompt("khadamati_darija.txt", DARIJA_FALLBACK),
        first_message="Salam, ana Khadamati. Gol liya chno l-mochkil qanouni aw idari?",
    ),
    "fr": LanguageProfile(
        code="fr",
        label="French",
        system_prompt=_read_prompt("french_fallback.txt", FRENCH_FALLBACK),
        first_message="Bonjour, je suis Khadamati. Dites-moi votre question juridique ou administrative.",
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
