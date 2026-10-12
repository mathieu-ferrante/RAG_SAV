"""Le jeu de questions de recette, au même endroit pour les deux consoles.

Il était dupliqué dans `console.py` (10 questions) et `repondre.py` (8), et les
deux listes avaient déjà divergé : le moteur de réponse avait perdu en route
les deux écritures libres, c'est-à-dire précisément celles qui éprouvent la
détection souple. Une seule liste, importée des deux côtés.

Ce ne sont PAS des questions d'utilisateur : les consoles attendent désormais
de vraies questions tapées à la main. Cette liste sert à la recette — vérifier
d'un coup que les cinq règles d'escalade, le filtre dur et le verrou réagissent
comme prévu — et se déclenche explicitement :

    python console.py --questions-types
    python repondre.py --questions-types
"""

QUESTIONS_TYPES = [
    # Le cas nominal : code + appareil, deux gammes différentes pour le même code.
    "Mon lave-vaisselle LV-200 affiche le code erreur E23",
    "Mon lave-linge WX-450 affiche E23",
    # Un bulletin technique prévaut sur le référentiel.
    "mon wx500 affiche e52",
    # Question de procédure, sans code erreur.
    "Comment détartrer mon lave-linge WX-400 ?",
    # Question transverse, sans appareil : doit répondre depuis les CGV.
    "Quelle est la durée de la garantie ?",
    # Écritures libres : éprouvent la détection souple.
    "Modele LV verre marqués",
    "bonjour mon lave-linge 450 affiche e 23",
    # Les quatre escalades attendues.
    "Que signifie le code E23 ?",            # code ambigu sans appareil
    "j'ai un WX-460, code E23",              # référence hors catalogue
    "voir page 450 du manuel, code F12",     # code inconnu de la documentation
    "j'ai le code E77 qui s'affiche",        # code sans appareil
]
