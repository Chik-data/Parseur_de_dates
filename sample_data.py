"""
sample_data.py
==============

Jeu de dates "sales" synthétique, inclus directement dans le dépôt pour que la
démonstration et les tests tournent sans aucun fichier externe.

On y trouve volontairement une grande variété de formats rencontrés dans des
données réelles, recensés à partir d'un vrai jeu de données de niveau Master 2
(`dirty_dates_master2_level.csv`, 362 lignes, également fourni dans le dépôt) :
formats ISO, européens/américains, mois en lettres, suffixes ordinaux,
séparateurs multiples, étiquettes textuelles, composantes horaires, fuseaux,
ponctuation parasite, ainsi que de vraies valeurs invalides ou manquantes.
"""

import os
import pandas as pd

# Au moins un exemple de CHAQUE modalité présente dans le vrai jeu de données.
dates_sales = [
    # --- Formats standards déjà reconnaissables ---
    "2022/11/27",                       # ISO avec slash
    "2004-01-18",                       # ISO avec tiret
    "21-7-13",                          # année sur 2 chiffres (-> 2013)
    "03/04/2020",                       # ambigu jour/mois (européen -> 3 avril)

    # --- Étiquettes / préfixes textuels ---
    "Date:2023-01-01",
    "logged:2020-2-23",
    "created on 1996/01/21",
    "approx 2018-10-28",
    "update[2005/12/4]",                # date entre crochets

    # --- Mots parasites autour de la date ---
    "random_text 2007-12-9",
    "2003-7-13 random_text",
    "2007/9/2 extra words",
    "2018-07-22 TEXT",

    # --- Ponctuation / marqueurs parasites ---
    "30-April-1995 ???",
    "### 2022-8-14 ###",
    "error 2009-10-4 TEXT",

    # --- Composante horaire et fuseaux ---
    "2018-07-22T12:45:00 TEXT",         # heure ISO avec T
    "2010-1-10 00:00:00 random",        # heure séparée par espace
    "2013/12/08Z",                      # suffixe Z (UTC)
    "2010-03-14+02:00",                 # décalage de fuseau

    # --- Mois en lettres + suffixes ordinaux ---
    "25th October 1998",
    "January 22 2017",
    "13-Aug-2023 random",
    "28th February 2016",

    # --- Séparateurs exotiques ---
    "2004..10..24",                     # doubles points
    "1997.7.20 TEXT",                   # point simple

    # --- Valeurs réellement invalides ou manquantes (DOIVENT rester NaT) ---
    "unknown",
    "yesterday",
    "9999-99-99",
    "Feb 30 2020",                      # 30 février n'existe pas
    "31/02/2018",                       # 31 février n'existe pas
    "",                                 # vide
    None,                               # manquant
]


def charger_csv_reel():
    """
    Charge le vrai jeu de données fourni dans le dépôt et renvoie sa colonne
    `raw_date`. Pratique pour évaluer le parseur sur des données réalistes.
    """
    chemin = os.path.join(os.path.dirname(__file__), "dirty_dates_master2_level.csv")
    return pd.read_csv(chemin)["raw_date"]

