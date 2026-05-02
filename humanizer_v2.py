"""
Humanizer v2 — Reformulateur de texte en style humain (français).
Pipeline : substitutions → reformulation LLM → évaluation → audit en 2 temps.

Usage CLI : python humanizer_v2.py
Usage UI  : python ui.py

Ctrl+C pour quitter.
"""
import sys

import pyperclip

from config import (
    MAX_ITERATIONS, SCORE_SEUIL, AUDIT_SPLIT,
    DEFAULT_MODEL_REFORMULATE, DEFAULT_MODEL_EVALUATE,
)
from substitutions import charger_referentiel
from core import (
    set_models,
    charger_modeles,
    verifier_modele,
    telecharger_modele,
    reformuler,
    evaluer,
    audit_diagnostic,
    audit_reecriture,
    audit_unique,
    analyser_style,
)
from prompts import STYLES


# ======================================================================
# Pipeline principal
# ======================================================================

def process(texte_source, mode, referentiel, style_profile=None):
    """Reformulation itérative + évaluation + audit final."""
    critique = ""
    meilleur_texte = texte_source
    dernier_score = 0

    # --- Boucle reformulation / évaluation ---
    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- Passe {i}/{MAX_ITERATIONS} ---")
        nouvelle = reformuler(texte_source, critique, mode, referentiel, style_profile)
        print(f"  Reformulation : {nouvelle[:150]}{'...' if len(nouvelle) > 150 else ''}")

        eval_json = evaluer(texte_source, nouvelle)
        if eval_json is None:
            critique = "La reformulation n'est pas assez naturelle."
            meilleur_texte = nouvelle
            continue

        score = eval_json.get("score_humain", 5)
        passe = eval_json.get("passe", False)
        commentaire = eval_json.get("commentaire", "")
        resultats = eval_json.get("resultats", {})
        defauts = [k for k, v in resultats.items() if v]

        print(f"  Score humanité : {score}/10")
        if defauts:
            print(f"  Défauts : {', '.join(defauts)}")
        if commentaire:
            print(f"  Commentaire : {commentaire}")

        dernier_score = score
        meilleur_texte = nouvelle

        if passe and score >= SCORE_SEUIL:
            print(f"  ✅ Score ≥ {SCORE_SEUIL}, critères satisfaits.")
            break

        # Construire la critique pour la prochaine passe
        if defauts:
            critique = f"Défauts détectés : {', '.join(defauts)}. {commentaire}"
        else:
            critique = f"Améliore encore la naturalité. {commentaire}"
        print(f"  ❌ On itère.")

    # --- Audit final ---
    if dernier_score >= 10:
        print("\n✨ Score parfait, pas d'audit supplémentaire.")
        return meilleur_texte

    if AUDIT_SPLIT:
        print("\n--- Audit final (phase 1 : diagnostic) ---")
        defauts_residuels = audit_diagnostic(texte_source, meilleur_texte)
        print(f"  Défauts résiduels :\n{_indent(defauts_residuels)}")

        print("\n--- Audit final (phase 2 : réécriture ciblée) ---")
        meilleur_texte = audit_reecriture(
            meilleur_texte, defauts_residuels, mode, referentiel, style_profile
        )
    else:
        print("\n--- Audit final (passe unique) ---")
        meilleur_texte = audit_unique(
            texte_source, meilleur_texte, mode, referentiel, style_profile
        )

    print(f"  Version après audit : {meilleur_texte[:150]}{'...' if len(meilleur_texte) > 150 else ''}")
    return meilleur_texte


# ======================================================================
# Interface utilisateur
# ======================================================================

def choisir_mode():
    """Demande le mode de style à l'utilisateur."""
    modes = list(STYLES.keys())
    print(f"Modes disponibles : {', '.join(modes)}")
    choix = input("Choisissez un mode (ou Entrée pour 'familier') : ").strip().lower()
    if choix not in STYLES:
        choix = "familier"
    print(f"→ Mode : {choix}\n")
    return choix


def calibrer_style():
    """Propose la calibration optionnelle sur un texte de référence."""
    reponse = input("Calibrer le style sur un texte de référence ? (o/n) : ").strip().lower()
    if reponse != "o":
        return None

    print("Collez votre texte de référence, puis appuyez sur Entrée deux fois :")
    lignes = []
    while True:
        try:
            ligne = input()
            if ligne == "" and lignes and lignes[-1] == "":
                break
            lignes.append(ligne)
        except EOFError:
            break

    echantillon = "\n".join(lignes).strip()
    if not echantillon:
        print("Échantillon vide, calibration ignorée.\n")
        return None

    print("Analyse du style en cours...")
    profil = analyser_style(echantillon)
    print(f"Profil détecté : {profil}\n")
    return profil


def main():
    print("=" * 60)
    print("  Humanizer v2 — Reformulateur français")
    print("  (Ctrl+C pour quitter)")
    print("=" * 60)
    print()

    # Charger le référentiel
    referentiel = charger_referentiel()
    nb_subs = len(referentiel.get("substitutions", []))
    nb_mots = len(referentiel.get("mots_et_expressions_a_eviter", []))
    print(f"Référentiel chargé : {nb_subs} substitutions, {nb_mots} expressions à éviter.\n")

    # Configuration des modèles
    model_reform = DEFAULT_MODEL_REFORMULATE
    model_eval = DEFAULT_MODEL_EVALUATE
    print(f"Modèles par défaut : {model_reform} (reformulation), {model_eval} (évaluation)")
    changer = input("Changer les modèles ? (o/n) : ").strip().lower()
    if changer == "o":
        r = input(f"  Modèle reformulation [{model_reform}] : ").strip()
        if r:
            model_reform = r
        e = input(f"  Modèle évaluation [{model_eval}] : ").strip()
        if e:
            model_eval = e
    set_models(model_reform, model_eval)
    print()

    # Vérification et téléchargement des modèles
    for nom in (model_reform, model_eval):
        if not verifier_modele(nom):
            print(f"⚠ Le modèle '{nom}' n'est pas installé.")
            dl = input(f"  Télécharger '{nom}' maintenant ? (o/n) : ").strip().lower()
            if dl == "o":
                if not telecharger_modele(nom):
                    print(f"Impossible de continuer sans '{nom}'.")
                    sys.exit(1)
            else:
                print("Annulé.")
                sys.exit(1)

    # Choix du mode
    mode = choisir_mode()

    # Calibration optionnelle
    style_profile = calibrer_style()

    # Chargement des modèles en VRAM
    charger_modeles()

    # Boucle principale
    dernier_texte_traite = ""
    while True:
        try:
            print("-" * 60)
            texte = pyperclip.paste().strip()
            if not texte:
                print("Le presse-papiers est vide. Copiez un texte puis appuyez sur Entrée.")
                input("→ Entrée pour relire le presse-papiers...")
                continue
            if texte == dernier_texte_traite:
                print("Ce texte a déjà été traité. Copiez un NOUVEAU texte.")
                input("→ Entrée pour continuer...")
                continue

            print(f"\nTexte source ({len(texte)} caractères) :")
            apercu = texte[:300] + ("..." if len(texte) > 300 else "")
            print(apercu)
            print()

            confirmation = input("Lancer la reformulation ? (o/n) : ").strip().lower()
            if confirmation != "o":
                continue

            resultat = process(texte, mode, referentiel, style_profile)

            print("\n" + "=" * 60)
            print("  RÉSULTAT FINAL")
            print("=" * 60)
            print(resultat)
            print()

            pyperclip.copy(resultat)
            dernier_texte_traite = resultat
            print("(Copié dans le presse-papiers)")

        except KeyboardInterrupt:
            print("\n\nFin du programme.")
            sys.exit(0)


# ======================================================================
# Utilitaires d'affichage
# ======================================================================

def _indent(texte, prefix="    "):
    """Indente chaque ligne d'un texte."""
    return "\n".join(prefix + line for line in texte.splitlines())


if __name__ == "__main__":
    main()
