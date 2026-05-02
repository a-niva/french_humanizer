"""
Configuration du projet humanizer_v2.
Adapter les paramètres selon votre installation.
"""

# --- Modèles par défaut (modifiables via l'UI ou set_models()) ---
DEFAULT_MODEL_REFORMULATE = "qwen3:14b"
DEFAULT_MODEL_EVALUATE    = "qwen3:8b"

# --- Paramètres d'inférence ---
REFORM_TEMP   = 0.8      # créativité pour la reformulation
EVAL_TEMP     = 0.1      # précision pour l'évaluation
AUDIT_TEMP    = 0.6      # compromis pour l'audit final
CALIB_TEMP    = 0.3      # analyse de style
KEEP_ALIVE    = "5m"    # durée de rétention en VRAM

# --- Pipeline ---
MAX_ITERATIONS = 3       # passes de reformulation/évaluation
SCORE_SEUIL    = 8       # score minimum pour valider sans itérer
AUDIT_SPLIT    = True    # audit en deux temps (analyse puis réécriture)
