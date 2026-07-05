"""
date_cleaner.py
===============

Nettoyage et normalisation de dates "sales" (formats hétérogènes) vers un
type datetime exploitable, à partir d'une colonne pandas (Serie).

Idée directrice
---------------
Plutôt que d'identifier à l'oeil tous les formats possibles et écrire une
regex géante, je procède par passes successives :

    1. Tenter un parsing générique sur tout ce qui reste à traiter.
       Ce qui est reconnu est rangé dans le résultat, à la bonne place 
       (index aligné).
    2. Isoler UNIQUEMENT les valeurs qui ont échoué.
    3. Appliquer un nettoyage ciblé (regex) sur ces échecs pour les rapprocher
       d'un format reconnaissable.
    4. Recommencer ce processus en 3 étapes sur les échecs nettoyés jusqu'à 
       ce que toutes les dates soient reconnues en 'datetime' par le pareur.

S'arrêter lorsqu'il ne reste plus que des valeurs réellement invalides
(vraies valeurs manquantes ou dates impossibles) qui doivent rester à NaT.

Cette approche "débroussailler d'abord, raffiner ensuite" évite de sur-spécifier
des regex fragiles et concentre l'effort de nettoyage là où c'est nécessaire.
"""

from __future__ import annotations

import re
import pandas as pd


# Correspondance mois abrégé -> mois complet (en anglais, format des données source).
# Utilisée pour homogénéiser "Jan", "Feb"... avant le parsing textuel.
_MOIS_ABREGES = {
    "Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
    "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
    "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December",
}

# Liste des mois (complets et abrégés) pour les regex de capture.
_MOIS_PATTERN = (
    "January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|"
    "July|Jul|August|Aug|September|Sept|Sep|October|Oct|"
    "November|Nov|December|Dec"
)


def _parser(series: pd.Series, dayfirst: bool) -> pd.Series:
    """
    Tente de convertir chaque valeur en date (type datetime)
    élément par élément.

    Une colonne sale mélange des formats différents d'une ligne à
    l'autre (ISO, mois en lettres, jour/mois inversés...). Or les versions
    récentes de pandas refusent d'inférer un format global sur un mélange
    hétérogène. Donc en parsant chaque valeur indépendamment, chacune peut suivre
    son propre format. Ce qui échoue devient NaT, sans bloquer les autres.

    Subtilité importante sur `dayfirst` : ce paramètre ne tranche QUE
    l'ambiguïté entre le jour et le mois. Il ne doit pas s'appliquer quand
    l'année est déjà identifiable en tête (4 chiffres au début, ex. "2005/12/4"
    = année/mois/jour). Sinon "2005/12/4" serait lu comme le 12 du mois 4.
    On détecte donc l'année en tête dans ce cas on force l'ordre année-mois-jour
    .
    """
    annee_en_tete = re.compile(r"^\s*\d{4}\D")

    def _un(v):
        if isinstance(v, str) and annee_en_tete.match(v):
            # Année en première position -> ordre AAAA/MM/JJ, dayfirst sans objet.
            return pd.to_datetime(v, errors="coerce", dayfirst=False)
        return pd.to_datetime(v, errors="coerce", dayfirst=dayfirst)

    return series.apply(_un)


def _ranger_succes(resultat: pd.Series, parses: pd.Series) -> pd.Series:
    """
    Range dans `resultat` les dates nouvellement parsées, uniquement aux endroits
    encore vides (NaT). On ne remplace jamais une date déjà trouvée.

    `resultat` et `parses` partagent le même index : chaque ligne d'entrée
    correspond à une ligne de sortie (les opérations préservent l'index).
    """
    a_remplir = resultat.index.intersection(parses.index)
    resultat.loc[a_remplir] = resultat.loc[a_remplir].fillna(parses.loc[a_remplir])
    return resultat


def _nettoyer_suffixes_ordinaux(series: pd.Series) -> pd.Series:
    """Supprime les suffixes ordinaux anglais : 1st -> 1, 22nd -> 22, etc."""
    return series.str.replace(r"(\d+)(st|nd|rd|th)\b", r"\1", regex=True)


def _homogeneiser_separateurs_numeriques(series: pd.Series) -> pd.Series:
    """
    Normalise les dates purement numériques séparées par -, ., espace... vers
    un séparateur unique "/", et retire d'éventuels mots parasites autour.
    Exemple : "2023 year 10 month 22 day random" -> "2023/10/22"
    """
    s = series.str.replace(r"\b(year|month|day|random|TEXT)\b", " ", regex=True)
    s = s.str.strip()
    # 3 groupes de chiffres séparés par n'importe quel non-chiffre -> j/m/a en "/"
    s = s.str.replace(r"(\d{1,4})\D+(\d{1,4})\D+(\d{1,4})", r"\1/\2/\3", regex=True)
    # Chiffres collés "20231022" -> "2023/10/22"
    s = s.str.replace(r"\b(\d{4})(\d{2})(\d{2})\b", r"\1/\2/\3", regex=True)
    return s


def _developper_mois_abreges(series: pd.Series) -> pd.Series:
    """
    Remplace les mois abrégés par leur forme complète, en utilisant des
    frontières de mot \\b pour ne pas casser un mot plus long.

    Note sur la regex : on écrit r")\b" et non r"\b)". En effet "\b(Jan|...|Dec\b)"
    appliquerait la frontière seulement à "Dec". On veut "\b(Jan|...|Dec)\b",
    donc la frontière englobe tout le groupe.
    """
    pattern = r"\b(" + "|".join(_MOIS_ABREGES.keys()) + r")\b"
    return series.str.replace(pattern, lambda m: _MOIS_ABREGES[m.group()], regex=True)


def _debruiter(series: pd.Series) -> pd.Series:
    """
    Retire le bruit qui entoure les dates réelles, sans toucher aux chiffres de
    la date elle-même. Couvre toutes les modalités rencontrées dans les données
    sources :

      - préfixes d'étiquette : "Date:", "logged:", "created on", "approx",
        "update[...]", "random_text", "TEXT"...
      - mots parasites : random, random_text, TEXT, extra words...
      - ponctuation parasite de fin : "???"
      - crochets autour de la date : "update[2005/12/4]"
      - composante horaire : "T12:45:00", " 00:00:00", "12:45:00"
      - fuseaux horaires : suffixe "Z", décalage "+02:00"

    On débruite AVANT de parser, pour que ne reste idéalement que le coeur datant.
    """
    s = series

    # 1) Crochets : on garde leur contenu -> "update[2005/12/4]" devient "update 2005/12/4"
    s = s.str.replace(r"[\[\]]", " ", regex=True)

    # 2) Fuseaux horaires : "Z" en fin de bloc, ou décalage "+02:00" / "-05:00"
    s = s.str.replace(r"Z\b", " ", regex=True)
    s = s.str.replace(r"[+-]\d{2}:\d{2}\b", " ", regex=True)

    # 3) Composante horaire. Le "T" ISO sépare date et heure : on coupe à partir
    #    du T (ex. "2018-07-22T12:45:00" -> "2018-07-22"). Puis on retire toute
    #    heure restante de la forme HH:MM(:SS).
    s = s.str.replace(r"T\d{1,2}:\d{2}(:\d{2})?", " ", regex=True)
    s = s.str.replace(r"\b\d{1,2}:\d{2}(:\d{2})?\b", " ", regex=True)

    # 4) Étiquettes et mots parasites (insensible à la casse).
    #    \w*: capture aussi "logged", "created", etc. avant un éventuel ":".
    s = s.str.replace(r"(?i)\b(date|logged|created|recorded|updated?|approx\w*)\b\s*:?", " ", regex=True)
    s = s.str.replace(r"(?i)\b(on|at|extra|words?|random_text|random|text)\b", " ", regex=True)

    # 5) Marqueurs et ponctuation parasites restants : "###", "???"...
    s = s.str.replace(r"#+", " ", regex=True)
    s = s.str.replace(r"(?i)\berror\b", " ", regex=True)
    s = s.str.replace(r"[?]+", " ", regex=True)

    # 6) Espaces/tabulations multiples -> un seul espace, et trim.
    s = s.str.replace(r"\s+", " ", regex=True).str.strip()

    return s


def _isoler_date_textuelle(series: pd.Series) -> pd.Series:
    """
    Pour les dates où le mois est écrit en lettres, isole le coeur de la date et
    enlève le bruit autour. Gère deux motifs :
        - "Month 12 2003"  (mois jour année)
        - "12-Mar-2003 random" (jour-mois-année avec mots parasites)
    """
    s = series.str.replace(
        rf".*?({_MOIS_PATTERN})\s+(\d{{1,2}})\s+(\d{{2,4}}).*",
        r"\1 \2 \3", regex=True,
    )
    s = s.str.replace(
        rf"(\d{{1,2}})[-\s]({_MOIS_PATTERN})[-\s](\d{{2,4}}).*",
        r"\1 \2 \3", regex=True,
    )
    return s


def clean_dates(series: pd.Series, dayfirst: bool = True) -> pd.Series:
    """
    Convertit une Series de dates "sales" en Series datetime64[ns].

    Paramètres
    ----------
    series : pd.Series
        Colonne de dates au format texte, potentiellement très hétérogène.
    dayfirst : bool, défaut True
        Convention par défaut pour les formats ambigus jour/mois (ex. 03/04/2020).
        True = on suppose jour en premier (convention européenne).

    Retour
    ------
    pd.Series (datetime64[ns])
        Même index que l'entrée. Les valeurs non interprétables restent à NaT.

    Démarche : passes successives de (parsing générique -> isolement des échecs
    -> nettoyage ciblé) jusqu'à ne plus pouvoir progresser.
    """
    # Type chaîne stable de pandas : permet les opérations .str vectorisées et
    # une gestion homogène des valeurs manquantes (une seule sentinelle <NA>).
    travail = series.astype("string")

    # Conteneur résultat, pré-rempli de NaT, aligné sur l'index d'entrée.
    resultat = pd.Series(pd.NaT, index=travail.index, dtype="datetime64[ns]")

    # --- Passe 0 : parsing générique direct ("débroussaillage") ---
    parses = _parser(travail, dayfirst)
    resultat = _ranger_succes(resultat, parses)
    echecs = travail[parses.isna()]

    if echecs.empty:
        return resultat

    # --- Passe 1 : débruitage général (étiquettes, mots parasites, heures,
    #     fuseaux, ponctuation, séparateurs doublés) puis ré-essai ---
    echecs = _debruiter(echecs)
    # Séparateurs doublés ou exotiques entre nombres -> un seul "/"
    echecs = echecs.str.replace(r"(\d)\.\.+(\d)", r"\1/\2", regex=True)
    parses = _parser(echecs, dayfirst)
    resultat = _ranger_succes(resultat, parses)
    echecs = echecs[parses.isna()]

    if echecs.empty:
        return resultat

    # --- Passe 2 : suffixes ordinaux (+ "of") + ré-essai ---
    echecs = _nettoyer_suffixes_ordinaux(echecs)
    echecs = echecs.str.replace(r"\bof\b", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    parses = _parser(echecs, dayfirst)
    resultat = _ranger_succes(resultat, parses)
    echecs = echecs[parses.isna()]

    if echecs.empty:
        return resultat

    # --- Passe 3 : dates textuelles (mois en lettres) ---
    echecs = _developper_mois_abreges(echecs)
    echecs = _isoler_date_textuelle(echecs)
    parses = _parser(echecs, dayfirst)
    resultat = _ranger_succes(resultat, parses)
    echecs = echecs[parses.isna()]

    if echecs.empty:
        return resultat

    # --- Passe 4 : dates numériques bruitées / collées ---
    echecs = _homogeneiser_separateurs_numeriques(echecs)
    parses = _parser(echecs, dayfirst)
    resultat = _ranger_succes(resultat, parses)
    # Ce qui échoue encore = vraiment invalide -> reste NaT (volontairement).

    return resultat


def cleaning_report(original: pd.Series, parsed: pd.Series) -> dict:
    """
    Petit rapport chiffré du nettoyage : utile pour le README et pour montrer
    objectivement le taux de réussite.
    """
    total = len(original)
    reconnues = int(parsed.notna().sum())
    # Valeurs d'entrée réellement vides (NA ou chaîne vide) : on ne les compte
    # pas comme des "échecs" de parsing, ce sont des manquants légitimes.
    vides = int(original.isna().sum() + (original.astype("string").str.strip() == "").sum())
    non_reconnues = total - reconnues
    return {
        "total": total,
        "reconnues": reconnues,
        "non_reconnues": non_reconnues,
        "vides_a_l_origine": vides,
        "taux_reconnaissance": round(reconnues / total, 4) if total else 0.0,
    }


if __name__ == "__main__":
    # Démonstration en ligne de commande : python date_cleaner.py
    # On tourne en priorité sur le vrai jeu de données fourni ; à défaut, sur
    # le petit échantillon synthétique.
    try:
        from sample_data import charger_csv_reel
        s = charger_csv_reel()
        source = "dirty_dates_master2_level.csv (jeu réel, 362 lignes)"
    except Exception:
        from sample_data import dates_sales
        s = pd.Series(dates_sales)
        source = "sample_data.dates_sales (échantillon synthétique)"

    out = clean_dates(s)
    rapport = cleaning_report(s, out)

    print(f"Source : {source}\n")
    # Aperçu : 25 premières lignes, entrée vs sortie.
    apercu = pd.DataFrame({
        "entree": s.head(25),
        "sortie": out.head(25).dt.strftime("%Y-%m-%d").fillna("(NaT)"),
    })
    print(apercu.to_string())
    print()
    print("Rapport :", rapport)
