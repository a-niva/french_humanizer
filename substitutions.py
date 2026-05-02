"""
Module de substitutions rule-based.
Charge le référentiel JSON et applique les remplacements regex
conditionnés par le mode de style actif.
"""
import json
import re
from pathlib import Path

# Regex emoji compilée en Python (les plans supplémentaires Unicode
# ne peuvent pas être exprimés correctement dans un fichier JSON).
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symboles & pictographes
    "\U0001F680-\U0001F6FF"  # transport & cartes
    "\U0001F1E0-\U0001F1FF"  # drapeaux
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero-width joiner
    "\U000024C2-\U0001F251"
    "]+"
)

_DEFAULT_JSON = "substitutions_fr.json"


def charger_referentiel(chemin=None):
    """Charge le fichier JSON de substitutions. Retourne le dict complet."""
    chemin = chemin or Path(__file__).parent / _DEFAULT_JSON
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def appliquer_substitutions(texte, mode, referentiel):
    """
    Applique les substitutions regex au texte.
    - Si la substitution a un champ 'modes' vide → s'applique partout.
    - Si 'modes' contient des valeurs → s'applique seulement si `mode` est dedans.
    """
    for sub in referentiel.get("substitutions", []):
        modes_cibles = sub.get("modes", [])
        if modes_cibles and mode not in modes_cibles:
            continue
        pattern = sub["pattern"]
        repl = sub["replacement"]
        texte = re.sub(pattern, repl, texte, flags=re.IGNORECASE)

    return _nettoyer_espaces(texte)


def appliquer_nettoyage_typo(texte, referentiel):
    """
    Normalise la typographie : guillemets courbes → droits,
    tirets cadratins → virgules, suppression des emojis.
    """
    # Emojis (géré en Python, pas depuis le JSON)
    texte = _EMOJI_RE.sub("", texte)
    # Patterns typographiques depuis le JSON
    nettoyage = referentiel.get("nettoyage_typographique", {})
    for _cle, spec in nettoyage.items():
        texte = re.sub(spec["pattern"], spec["replacement"], texte)
    return _nettoyer_espaces(texte)


def pipeline_substitutions(texte, mode, referentiel):
    """Applique successivement le nettoyage typo puis les substitutions."""
    texte = appliquer_nettoyage_typo(texte, referentiel)
    texte = appliquer_substitutions(texte, mode, referentiel)
    return texte


# --- Utilitaires internes ---

def _nettoyer_espaces(texte):
    """Supprime doubles espaces, espaces avant ponctuation."""
    texte = re.sub(r" {2,}", " ", texte)
    texte = re.sub(r" \.", ".", texte)
    texte = re.sub(r" ,", ",", texte)
    # En français, on conserve l'espace avant : ; ! ? (règle typographique)
    # On normalise seulement les doubles espaces avant ces signes
    texte = re.sub(r" {2,}([;:!?])", r" \1", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()
