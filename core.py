"""
Module cœur : appels LLM (Ollama) pour reformulation, évaluation, audit, calibration.
Gère le stripping des blocs <think> de Qwen3 et le nettoyage des sorties.
"""
import json
import re
import sys

import ollama

from config import (
    DEFAULT_MODEL_REFORMULATE, DEFAULT_MODEL_EVALUATE,
    REFORM_TEMP, EVAL_TEMP, AUDIT_TEMP, CALIB_TEMP,
    KEEP_ALIVE,
)
from prompts import (
    construire_prompt_reformulation,
    construire_user_reformulation,
    SYSTEM_EVALUATE,
    SYSTEM_AUDIT_DIAGNOSTIC,
    construire_prompt_audit_reecriture,
    SYSTEM_CALIBRATION,
)
from substitutions import pipeline_substitutions

# --- État global des modèles (modifiable par l'UI ou le CLI) ---
_models = {
    "reformulate": DEFAULT_MODEL_REFORMULATE,
    "evaluate": DEFAULT_MODEL_EVALUATE,
}


def set_models(reformulate, evaluate):
    """Permet à l'UI ou au CLI de choisir les modèles."""
    _models["reformulate"] = reformulate
    _models["evaluate"] = evaluate


# ======================================================================
# Utilitaires
# ======================================================================

def strip_think_blocks(text):
    """Supprime les blocs <think>...</think> que Qwen3 peut produire."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# Préfixes connus que les LLM ajoutent avant le texte reformulé
_PREFIX_RE = re.compile(
    r"^(?:"
    r"Voici\s+(?:le\s+|la\s+|une?\s+)?(?:texte|version|reformulation)[^:]*:\s*"
    r"|Texte\s+reformulé\s*:\s*"
    r"|Résultat\s*:\s*"
    r"|Version\s+(?:finale|réécrite|corrigée)\s*:\s*"
    r")",
    re.IGNORECASE,
)


def strip_prefix(text):
    """Supprime les préfixes méta ajoutés par le modèle, sans toucher au contenu."""
    text = text.strip()
    # Supprimer les guillemets englobants si le modèle a entouré toute sa réponse
    if len(text) > 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].strip()
    # Supprimer les préfixes connus
    match = _PREFIX_RE.match(text)
    if match:
        text = text[match.end():].strip()
    return text


def clean_output(raw):
    """Pipeline de nettoyage complet d'une sortie LLM."""
    return strip_prefix(strip_think_blocks(raw))


def _append_no_think(user_msg):
    """Ajoute /no_think pour Qwen3 (désactive le raisonnement interne)."""
    return user_msg + "\n/no_think"


def _chat(model, system, user, temperature, fmt=None, no_think=True):
    """Wrapper autour d'ollama.chat avec gestion d'erreurs."""
    if no_think:
        user = _append_no_think(user)
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": temperature},
        "keep_alive": KEEP_ALIVE,
    }
    if fmt:
        kwargs["format"] = fmt
    resp = ollama.chat(**kwargs)
    return resp["message"]["content"]


# ======================================================================
# Gestion des modèles
# ======================================================================

def lister_modeles_ollama():
    """Retourne la liste des modèles installés dans Ollama."""
    try:
        result = ollama.list()
        return [m.model for m in result.models]
    except Exception:
        return []


def verifier_modele(nom):
    """Vérifie si un modèle est installé. Retourne True/False."""
    installes = lister_modeles_ollama()
    # Correspondance exacte ou correspondance sans tag
    for m in installes:
        if m == nom or m.split(":")[0] == nom.split(":")[0]:
            return True
    return False


def telecharger_modele(nom, callback=None):
    """
    Télécharge un modèle via ollama.pull avec progression.
    callback(status, completed, total) est appelé pendant le téléchargement.
    """
    try:
        for progress in ollama.pull(nom, stream=True):
            status = progress.get("status", "")
            completed = progress.get("completed", 0)
            total = progress.get("total", 0)
            if callback:
                callback(status, completed, total)
            elif total > 0:
                pct = int(completed / total * 100)
                print(f"\r  {status}: {pct}%", end="", flush=True)
        print()
        return True
    except Exception as e:
        print(f"\n  [Erreur] Impossible de télécharger {nom}: {e}", file=sys.stderr)
        return False


def charger_modeles(callback_print=None):
    """Précharge les deux modèles en VRAM via un ping."""
    _print = callback_print or print
    _print("Chargement des modèles en VRAM...")
    for role, model in _models.items():
        try:
            ollama.chat(
                model=model,
                messages=[{"role": "user", "content": "Ping."}],
                options={"temperature": 0},
                keep_alive=KEEP_ALIVE,
            )
            _print(f"  ✓ {model} ({role})")
        except Exception as e:
            _print(f"  ✗ {model} ({role}) — {e}")
            raise
    _print("")


# ======================================================================
# Reformulation
# ======================================================================

def reformuler(texte_source, critique, mode, referentiel, style_profile=None):
    """
    Reformule le texte avec le modèle principal.
    Applique les substitutions en pré- et post-traitement.
    """
    # Pré-nettoyage rule-based
    texte_pre = pipeline_substitutions(texte_source, mode, referentiel)

    system = construire_prompt_reformulation(mode, style_profile)
    user = construire_user_reformulation(texte_pre, critique)

    raw = _chat(_models["reformulate"], system, user, REFORM_TEMP)
    cleaned = clean_output(raw)

    # Post-nettoyage rule-based
    return pipeline_substitutions(cleaned, mode, referentiel)


# ======================================================================
# Évaluation
# ======================================================================

def evaluer(texte_source, texte_reformule):
    """
    Évalue la qualité de la reformulation.
    Retourne un dict avec score_humain, passe, resultats, commentaire.
    Retourne None en cas d'erreur.
    """
    user = (
        f"Texte original :\n{texte_source}\n\n"
        f"Texte reformulé :\n{texte_reformule}"
    )
    try:
        raw = _chat(_models["evaluate"], SYSTEM_EVALUATE, user, EVAL_TEMP, fmt="json")
        raw = strip_think_blocks(raw)
        # Extraire le JSON même si du texte traîne autour
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("Pas de JSON trouvé dans la réponse")
        data = json.loads(raw[start:end])
        # Valeurs par défaut
        data.setdefault("passe", False)
        data.setdefault("score_humain", 5)
        data.setdefault("resultats", {})
        data.setdefault("commentaire", "")
        # Clamp le score entre 0 et 10
        data["score_humain"] = max(0, min(10, int(data["score_humain"])))
        return data
    except Exception as e:
        print(f"  [Erreur d'évaluation] {e}", file=sys.stderr)
        return None


# ======================================================================
# Audit en deux temps
# ======================================================================

def audit_diagnostic(texte_source, texte_reformule):
    """
    Phase 1 : identifie les défauts résiduels sans réécrire.
    Retourne la liste des défauts (texte brut).
    """
    user = (
        f"Texte original :\n{texte_source}\n\n"
        f"Texte reformulé :\n{texte_reformule}"
    )
    raw = _chat(_models["reformulate"], SYSTEM_AUDIT_DIAGNOSTIC, user, AUDIT_TEMP)
    return strip_think_blocks(raw)


def audit_reecriture(texte_reformule, defauts, mode, referentiel, style_profile=None):
    """Phase 2 : réécrit en ciblant les défauts identifiés."""
    system = construire_prompt_audit_reecriture(mode, style_profile)
    user = (
        f"Texte à corriger :\n{texte_reformule}\n\n"
        f"Défauts résiduels identifiés :\n{defauts}"
    )
    raw = _chat(_models["reformulate"], system, user, AUDIT_TEMP)
    cleaned = clean_output(raw)
    return pipeline_substitutions(cleaned, mode, referentiel)


def audit_unique(texte_source, texte_reformule, mode, referentiel, style_profile=None):
    """Audit en un seul appel (fallback si AUDIT_SPLIT est False)."""
    system = construire_prompt_audit_reecriture(mode, style_profile)
    system += (
        "\nAnalyse d'abord rapidement ce qui pourrait encore trahir une IA "
        "(mots, structures, ton), puis réécris pour corriger ces défauts."
    )
    user = (
        f"Texte original :\n{texte_source}\n\n"
        f"Dernière reformulation :\n{texte_reformule}"
    )
    raw = _chat(_models["reformulate"], system, user, AUDIT_TEMP)
    cleaned = clean_output(raw)
    return pipeline_substitutions(cleaned, mode, referentiel)


# ======================================================================
# Calibration de voix
# ======================================================================

def analyser_style(echantillon):
    """Analyse un échantillon pour en extraire un profil stylistique."""
    raw = _chat(
        _models["reformulate"],
        SYSTEM_CALIBRATION,
        f"Texte à analyser :\n{echantillon}",
        CALIB_TEMP,
    )
    return strip_think_blocks(raw)
