"""
Humanizer v2 — Interface web (Gradio).
Lance avec : python ui.py
Ouvre automatiquement http://localhost:7860 dans le navigateur.
"""
import threading

import gradio as gr

from config import (
    DEFAULT_MODEL_REFORMULATE, DEFAULT_MODEL_EVALUATE,
    MAX_ITERATIONS, SCORE_SEUIL, AUDIT_SPLIT,
)
from substitutions import charger_referentiel
from core import (
    set_models,
    lister_modeles_ollama,
    verifier_modele,
    telecharger_modele,
    charger_modeles,
    reformuler,
    evaluer,
    audit_diagnostic,
    audit_reecriture,
    audit_unique,
    analyser_style,
)
from prompts import STYLES

# --- État global ---
_referentiel = charger_referentiel()
_style_profile = None


# ======================================================================
# Fonctions de gestion des modèles
# ======================================================================

def rafraichir_modeles():
    """Retourne la liste des modèles Ollama installés."""
    modeles = lister_modeles_ollama()
    if not modeles:
        return gr.update(choices=["(aucun modèle)"]), gr.update(choices=["(aucun modèle)"])
    return (
        gr.update(choices=modeles, value=DEFAULT_MODEL_REFORMULATE if DEFAULT_MODEL_REFORMULATE in modeles else modeles[0]),
        gr.update(choices=modeles, value=DEFAULT_MODEL_EVALUATE if DEFAULT_MODEL_EVALUATE in modeles else modeles[0]),
    )


def telecharger_et_rafraichir(nom_modele, progress=gr.Progress()):
    """Télécharge un modèle puis rafraîchit les listes."""
    nom_modele = nom_modele.strip()
    if not nom_modele:
        return "⚠ Entrez un nom de modèle.", *rafraichir_modeles()

    progress(0, desc=f"Téléchargement de {nom_modele}...")

    def cb(status, completed, total):
        if total > 0:
            progress(completed / total, desc=f"{status}")

    ok = telecharger_modele(nom_modele, callback=cb)
    if ok:
        msg = f"✓ Modèle '{nom_modele}' installé."
    else:
        msg = f"✗ Échec du téléchargement de '{nom_modele}'."
    return msg, *rafraichir_modeles()


# ======================================================================
# Calibration
# ======================================================================

def lancer_calibration(echantillon, model_reform):
    """Analyse un texte de référence pour calibrer le style."""
    global _style_profile
    if not echantillon or not echantillon.strip():
        _style_profile = None
        return "Calibration désactivée."
    set_models(model_reform, model_reform)  # on utilise le modèle reform pour l'analyse
    profil = analyser_style(echantillon.strip())
    _style_profile = profil
    return f"Profil détecté :\n{profil}"


def effacer_calibration():
    """Efface le profil de calibration."""
    global _style_profile
    _style_profile = None
    return "Calibration désactivée.", ""


# ======================================================================
# Pipeline principal (adapté pour Gradio avec progression)
# ======================================================================

def lancer_reformulation(texte_source, mode, model_reform, model_eval, progress=gr.Progress()):
    """Lance le pipeline complet et retourne le résultat + le journal."""
    if not texte_source or not texte_source.strip():
        return "", "⚠ Collez un texte à reformuler."

    texte_source = texte_source.strip()
    set_models(model_reform, model_eval)

    journal = []

    def log(msg):
        journal.append(msg)

    # Pré-chargement
    progress(0, desc="Chargement des modèles...")
    try:
        charger_modeles(callback_print=log)
    except Exception as e:
        return "", f"✗ Erreur de chargement : {e}"

    # Boucle reformulation / évaluation
    critique = ""
    meilleur_texte = texte_source
    dernier_score = 0

    for i in range(1, MAX_ITERATIONS + 1):
        progress(i / (MAX_ITERATIONS + 2), desc=f"Passe {i}/{MAX_ITERATIONS}...")
        log(f"--- Passe {i}/{MAX_ITERATIONS} ---")

        nouvelle = reformuler(texte_source, critique, mode, _referentiel, _style_profile)
        apercu = nouvelle[:120] + ("..." if len(nouvelle) > 120 else "")
        log(f"  Reformulation : {apercu}")

        eval_json = evaluer(texte_source, nouvelle)
        if eval_json is None:
            critique = "La reformulation n'est pas assez naturelle."
            meilleur_texte = nouvelle
            log("  ⚠ Évaluation échouée, on continue.")
            continue

        score = eval_json.get("score_humain", 5)
        passe = eval_json.get("passe", False)
        commentaire = eval_json.get("commentaire", "")
        resultats = eval_json.get("resultats", {})
        defauts = [k for k, v in resultats.items() if v]

        log(f"  Score : {score}/10")
        if defauts:
            log(f"  Défauts : {', '.join(defauts)}")
        if commentaire:
            log(f"  → {commentaire}")

        dernier_score = score
        meilleur_texte = nouvelle

        if passe and score >= SCORE_SEUIL:
            log(f"  ✓ Score ≥ {SCORE_SEUIL}")
            break

        if defauts:
            critique = f"Défauts : {', '.join(defauts)}. {commentaire}"
        else:
            critique = f"Améliore la naturalité. {commentaire}"
        log("  → On itère.")

    # Audit final
    if dernier_score < 10:
        progress((MAX_ITERATIONS + 1) / (MAX_ITERATIONS + 2), desc="Audit final...")
        if AUDIT_SPLIT:
            log("--- Audit (diagnostic) ---")
            defauts_residuels = audit_diagnostic(texte_source, meilleur_texte)
            log(f"  {defauts_residuels[:200]}")

            log("--- Audit (réécriture) ---")
            meilleur_texte = audit_reecriture(
                meilleur_texte, defauts_residuels, mode, _referentiel, _style_profile
            )
        else:
            log("--- Audit (passe unique) ---")
            meilleur_texte = audit_unique(
                texte_source, meilleur_texte, mode, _referentiel, _style_profile
            )
    else:
        log("Score parfait, audit ignoré.")

    progress(1, desc="Terminé.")
    log(f"--- Score final : {dernier_score}/10 ---")

    return meilleur_texte, "\n".join(journal)


# ======================================================================
# Construction de l'interface
# ======================================================================

def construire_ui():
    modeles_installes = lister_modeles_ollama()
    if not modeles_installes:
        modeles_installes = ["(aucun modèle)"]

    def val_defaut(defaut, liste):
        return defaut if defaut in liste else liste[0]

    with gr.Blocks(
        title="Humanizer v2",
        theme=gr.themes.Soft(),
        css="footer {display: none !important;}",
    ) as app:

        gr.Markdown("## ✍️ Humanizer v2 — Reformulateur français")
        gr.Markdown(
            "Reformule un texte pour éliminer les patterns d'écriture IA. "
            "Pipeline : substitutions → reformulation LLM → évaluation → audit."
        )

        # --- Modèles ---
        with gr.Accordion("⚙️ Modèles Ollama", open=False):
            with gr.Row():
                dd_reform = gr.Dropdown(
                    choices=modeles_installes,
                    value=val_defaut(DEFAULT_MODEL_REFORMULATE, modeles_installes),
                    label="Reformulation (≥ 12B recommandé)",
                    interactive=True,
                )
                dd_eval = gr.Dropdown(
                    choices=modeles_installes,
                    value=val_defaut(DEFAULT_MODEL_EVALUATE, modeles_installes),
                    label="Évaluation (≥ 7B recommandé)",
                    interactive=True,
                )
            with gr.Row():
                txt_pull = gr.Textbox(
                    label="Télécharger un modèle",
                    placeholder="ex: qwen3:14b",
                    scale=3,
                )
                btn_pull = gr.Button("⬇ Télécharger", scale=1)
                btn_refresh = gr.Button("🔄 Rafraîchir", scale=1)
            lbl_pull_status = gr.Textbox(label="Statut", interactive=False, max_lines=1)

            btn_refresh.click(
                fn=rafraichir_modeles,
                outputs=[dd_reform, dd_eval],
            )
            btn_pull.click(
                fn=telecharger_et_rafraichir,
                inputs=[txt_pull],
                outputs=[lbl_pull_status, dd_reform, dd_eval],
            )

        # --- Mode + Calibration ---
        with gr.Row():
            radio_mode = gr.Radio(
                choices=list(STYLES.keys()),
                value="familier",
                label="Mode de style",
            )

        with gr.Accordion("🎯 Calibration de voix (optionnel)", open=False):
            txt_calib = gr.Textbox(
                label="Texte de référence",
                placeholder="Collez ici un échantillon de votre style d'écriture (~300 mots)...",
                lines=5,
            )
            with gr.Row():
                btn_calib = gr.Button("Analyser le style")
                btn_calib_clear = gr.Button("Effacer")
            lbl_calib = gr.Textbox(label="Profil stylistique", interactive=False, lines=3)

            btn_calib.click(
                fn=lancer_calibration,
                inputs=[txt_calib, dd_reform],
                outputs=[lbl_calib],
            )
            btn_calib_clear.click(
                fn=effacer_calibration,
                outputs=[lbl_calib, txt_calib],
            )

        # --- Zone principale ---
        with gr.Row(equal_height=True):
            txt_input = gr.Textbox(
                label="Texte source",
                placeholder="Collez le texte à reformuler...",
                lines=12,
                scale=1,
            )
            txt_output = gr.Textbox(
                label="Texte reformulé",
                lines=12,
                scale=1,
                show_copy_button=True,
            )

        btn_go = gr.Button("▶ Reformuler", variant="primary", size="lg")

        with gr.Accordion("📋 Journal du pipeline", open=False):
            txt_log = gr.Textbox(
                label="Détails des passes",
                lines=15,
                interactive=False,
                show_copy_button=True,
            )

        btn_go.click(
            fn=lancer_reformulation,
            inputs=[txt_input, radio_mode, dd_reform, dd_eval],
            outputs=[txt_output, txt_log],
        )

    return app


# ======================================================================
# Point d'entrée
# ======================================================================

if __name__ == "__main__":
    app = construire_ui()
    app.launch(inbrowser=True)
