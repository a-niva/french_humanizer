# 🖊️ Humanizer v2

**Reformulateur de texte français — élimine les patterns d'écriture IA.**

Humanizer v2 prend un texte qui "sonne IA" et le reformule pour qu'il paraisse écrit par un humain. Il combine des substitutions déterministes (regex), des passes de reformulation LLM, une évaluation automatique et un audit final en deux temps — le tout en local, sans API cloud.

---

## Fonctionnement

```
Texte source
    │
    ▼
[1] Nettoyage typographique + substitutions rule-based
    │   Guillemets courbes → droits, emojis, tirets cadratins,
    │   48 expressions IA remplacées (conditionnées par mode)
    ▼
[2] Reformulation LLM (modèle principal, prompt enrichi + few-shot)
    │
    ▼
[3] Substitutions rule-based (post-nettoyage)
    │
    ▼
[4] Évaluation LLM (modèle secondaire, 4 méta-critères + score /10)
    │
    ├── Score ≥ 8 → audit final
    └── Score < 8 → critique ciblée → retour à [2] (max 3 passes)
    │
    ▼
[5] Audit phase 1 : « Qu'est-ce qui trahit encore l'IA ? »
    │
    ▼
[6] Audit phase 2 : réécriture ciblée sur les défauts identifiés
    │
    ▼
[7] Nettoyage final
    │
    ▼
Texte reformulé
```

## Prérequis

- **Python** 3.10+
- **[Ollama](https://ollama.com)** installé et lancé
- **GPU** avec ≥ 12 Go VRAM (16 Go recommandé pour deux modèles simultanés)
- Deux modèles Ollama — par défaut :
  - `qwen3:14b` (reformulation — 9 Go)
  - `qwen3:8b` (évaluation — 5 Go)

> Les modèles sont interchangeables. Tout modèle compatible Ollama fonctionne — `mistral-nemo:12b`, `llama3.1:8b`, `gemma2:9b`, etc. L'UI permet de choisir et télécharger les modèles.

## Installation

```bash
git clone https://github.com/votre-utilisateur/humanizer-v2.git
cd humanizer-v2

pip install ollama pyperclip gradio

ollama pull qwen3:14b
ollama pull qwen3:8b
```

## Utilisation

### Interface web (recommandé)

```bash
python ui.py
```

Ouvre automatiquement `http://localhost:7860` dans le navigateur.

L'interface permet de :
- Choisir les modèles Ollama (reformulation + évaluation)
- Télécharger un nouveau modèle directement depuis l'UI
- Sélectionner le mode de style (familier, pro, académique, créatif)
- Calibrer le style sur un texte de référence
- Lancer la reformulation et consulter le journal détaillé

### CLI (mode presse-papiers)

```bash
python humanizer_v2.py
```

1. Choisissez un mode et (optionnellement) calibrez le style
2. Copiez un texte dans le presse-papiers
3. Confirmez → le résultat est copié automatiquement

## Modes de style

| Mode | Description | Exemple |
|------|-------------|---------|
| **familier** | Oral, comme un message à un ami. Contractions, interjections. | *« Faut vérifier, tu vois. »* |
| **pro** | Professionnel direct, ni froid ni pompeux. | *« Vérifiez, s'il vous plaît. »* |
| **académique** | Précis mais vivant. Connecteurs logiques tolérés si justifiés. | *« On observe que les résultats suggèrent… »* |
| **créatif** | Expressif, presque littéraire. Métaphores, rythme marqué. | *« Le silence s'étirait, épais comme un brouillard. »* |

Les substitutions regex sont conditionnées par le mode : « néanmoins » est conservé en mode académique mais remplacé par « pourtant » en mode familier.

## Calibration de voix

La calibration analyse un échantillon de votre écriture (~300 mots) pour en extraire un profil stylistique : longueur des phrases, registre, usage de la première personne, ponctuation, tics de langage, gestion des transitions. Ce profil est ensuite injecté dans le prompt de reformulation pour que le résultat colle à votre style.

## Évaluation

Le modèle d'évaluation note chaque reformulation sur 10 et diagnostique 4 méta-critères :

| Critère | Ce qu'il détecte |
|---------|-----------------|
| `artificialite_lexicale` | Connecteurs pompeux, superlatifs d'inflation, synonymes abusifs, remplissages |
| `structure_mecanique` | Triades forcées, parallélismes symétriques, rythme monotone |
| `ton_impersonnel` | Voix passive systématique, tournures impersonnelles, hedging excessif |
| `contenu_creux` | Fins génériques, attributions vagues, annonces méta, fausse profondeur |

Si le score est < 8, la critique est renvoyée au reformulateur pour une passe corrective.

## Structure du projet

```
humanizer-v2/
├── ui.py                  # Interface web Gradio
├── humanizer_v2.py        # CLI (mode presse-papiers)
├── config.py              # Modèles par défaut, températures, seuils
├── core.py                # Appels LLM, gestion modèles, audit
├── prompts.py             # Prompts système par mode (few-shot inclus)
├── substitutions.py       # Chargement JSON, regex, nettoyage typo
├── substitutions_fr.json  # Référentiel français (48 subs, 68 expressions, 9 structures)
└── README.md
```

## Configuration

Éditer `config.py` pour ajuster :

```python
DEFAULT_MODEL_REFORMULATE = "qwen3:14b"   # modèle principal
DEFAULT_MODEL_EVALUATE    = "qwen3:8b"    # modèle d'évaluation
REFORM_TEMP   = 0.8    # créativité de reformulation
EVAL_TEMP     = 0.1    # précision d'évaluation
MAX_ITERATIONS = 3     # passes max reformulation/évaluation
SCORE_SEUIL    = 8     # score minimum pour valider
AUDIT_SPLIT    = True  # audit en 2 phases (diagnostic + réécriture)
```

## Référentiel de substitutions

Le fichier `substitutions_fr.json` contient :

- **48 substitutions regex** avec conditions par mode (ex : `"en vue de"` → `"pour"` dans tous les modes, `"néanmoins"` → `"pourtant"` uniquement en mode familier)
- **68 expressions à éviter** (mots et tournures typiques de l'écriture IA en français)
- **9 structures à éviter** avec exemples avant/après (triades, parallélismes, fins génériques…)
- **Nettoyage typographique** (guillemets courbes, tirets cadratins, emojis)
- **Instructions de personnalité** injectées dans les prompts

Le fichier est éditable. Ajoutez vos propres patterns selon vos besoins.

## Particularités techniques

- **Support Qwen3** : gestion des blocs `<think>...</think>` + injection de `/no_think` dans les messages utilisateur
- **Substitutions conditionnelles** : chaque regex spécifie les modes où elle s'applique (liste vide = tous les modes)
- **Double passe rule-based** : les substitutions s'appliquent avant *et* après chaque appel LLM
- **Audit en deux temps** : séparation du diagnostic (liste des défauts résiduels) et de la réécriture ciblée
- **Score clampé** : le score d'évaluation est forcé dans [0, 10] même si le LLM hallucine une valeur hors bornes

## Inspirations

L'approche s'inspire de [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) (WikiProject AI Cleanup) et de la skill [humanizer](https://github.com/anthropics/courses/tree/master/skills) pour Claude Code, adaptées au français avec un référentiel de patterns spécifique.

## Licence

MIT
