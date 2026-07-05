"""
test_date_cleaner.py
====================

Tests du parseur. Exécutables de deux façons :
    pytest (si pytest est installé)
    python test_date_cleaner.py (lanceur intégré, sans dépendance)

Chaque test documente un comportement attendu comme une forme de
spécification lisible de ce que le parseur garantit.
"""

import pandas as pd
from date_cleaner import clean_dates, cleaning_report


def _d(s):
    """Raccourci : convertit une chaîne ISO en Timestamp pour comparaison."""
    return pd.Timestamp(s)


def test_formats_iso():
    """Les formats ISO standards sont reconnus directement."""
    out = clean_dates(pd.Series(["2023-10-22", "2021/03/14"]))
    assert out.iloc[0] == _d("2023-10-22")
    assert out.iloc[1] == _d("2021-03-14")


def test_mois_en_lettres():
    """Mois écrit en toutes lettres, avec ou sans virgule."""
    out = clean_dates(pd.Series(["March 12 2003", "January 5, 2018"]))
    assert out.iloc[0] == _d("2003-03-12")
    assert out.iloc[1] == _d("2018-01-05")


def test_mois_abrege_avec_bruit():
    """Mois abrégé entouré de mots parasites."""
    out = clean_dates(pd.Series(["3-Aug-2025 random", "22nd Oct 2021"]))
    assert out.iloc[0] == _d("2025-08-03")
    assert out.iloc[1] == _d("2021-10-22")


def test_suffixes_ordinaux():
    """Suffixes 1st / 2nd / 3rd / th et 'of' sont gérés."""
    out = clean_dates(pd.Series(["1st January 2020", "3rd of March 2019"]))
    assert out.iloc[0] == _d("2020-01-01")
    assert out.iloc[1] == _d("2019-03-03")


def test_numerique_bruite():
    """Dates numériques avec mots parasites ou chiffres collés."""
    out = clean_dates(pd.Series(["2017 year 3 month 26 day", "20231022"]))
    assert out.iloc[0] == _d("2017-03-26")
    assert out.iloc[1] == _d("2023-10-22")


def test_convention_dayfirst():
    """
    Format ambigu : 03/04/2020.
    dayfirst=True (défaut) -> 3 avril ; dayfirst=False -> 4 mars.
    """
    assert clean_dates(pd.Series(["03/04/2020"]), dayfirst=True).iloc[0] == _d("2020-04-03")
    assert clean_dates(pd.Series(["03/04/2020"]), dayfirst=False).iloc[0] == _d("2020-03-04")


def test_valeurs_invalides_restent_nat():
    """Une valeur impossible ou non datée reste NaT, sans faire planter le reste."""
    out = clean_dates(pd.Series(["not a date", "2021-13-45", "2020-01-15"]))
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == _d("2020-01-15")  # la date valide passe quand même


def test_valeurs_manquantes():
    """Chaîne vide et None restent NaT et ne sont pas comptées comme des échecs."""
    s = pd.Series(["", None, "2022-06-30"])
    out = clean_dates(s)
    assert pd.isna(out.iloc[0])
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == _d("2022-06-30")
    rapport = cleaning_report(s, out)
    assert rapport["vides_a_l_origine"] == 2


def test_index_preserve():
    """Le résultat conserve exactement l'index d'entrée (alignement garanti)."""
    s = pd.Series(["2020-01-01", "bad", "2021-05-05"], index=[10, 20, 30])
    out = clean_dates(s)
    assert list(out.index) == [10, 20, 30]
    assert out.loc[10] == _d("2020-01-01")
    assert out.loc[30] == _d("2021-05-05")


def test_type_de_sortie():
    """La sortie est bien de type datetime64[ns]."""
    out = clean_dates(pd.Series(["2020-01-01"]))
    assert str(out.dtype) == "datetime64[ns]"


def test_etiquettes_textuelles():
    """Préfixes variés : Date:, logged:, created on, approx, [crochets]."""
    out = clean_dates(pd.Series([
        "Date:2023-01-01", "logged:2020-2-23", "created on 1996/01/21",
        "approx 2018-10-28", "update[2005/12/4]",
    ]))
    assert out.iloc[0] == _d("2023-01-01")
    assert out.iloc[1] == _d("2020-02-23")
    assert out.iloc[2] == _d("1996-01-21")
    assert out.iloc[3] == _d("2018-10-28")
    assert out.iloc[4] == _d("2005-12-04")


def test_composante_horaire_et_fuseaux():
    """L'heure et le fuseau sont retirés donc seule la date est conservée."""
    out = clean_dates(pd.Series([
        "2018-07-22T12:45:00 TEXT", "2010-1-10 00:00:00 random",
        "2013/12/08Z", "2010-03-14+02:00",
    ]))
    assert out.iloc[0] == _d("2018-07-22")
    assert out.iloc[1] == _d("2010-01-10")
    assert out.iloc[2] == _d("2013-12-08")
    assert out.iloc[3] == _d("2010-03-14")


def test_marqueurs_parasites():
    """Marqueurs ###, mots 'error', '???' n'empêchent pas de retrouver la date."""
    out = clean_dates(pd.Series([
        "### 2022-8-14 ###", "error 2009-10-4 TEXT", "30-April-1995 ???",
    ]))
    assert out.iloc[0] == _d("2022-08-14")
    assert out.iloc[1] == _d("2009-10-04")
    assert out.iloc[2] == _d("1995-04-30")


def test_separateurs_exotiques():
    """Doubles points et point simple comme séparateurs."""
    out = clean_dates(pd.Series(["2004..10..24", "1997.7.20 TEXT"]))
    assert out.iloc[0] == _d("2004-10-24")
    assert out.iloc[1] == _d("1997-07-20")


def test_dates_impossibles_restent_nat():
    """Dates calendairement impossibles : ne JAMAIS les "réparer" en une vraie date."""
    out = clean_dates(pd.Series([
        "Feb 30 2020", "31/02/2018", "9999-99-99", "unknown", "yesterday",
    ]))
    assert out.isna().all()


def test_sur_vrai_jeu_de_donnees():
    """
    Sur le vrai fichier fourni : j'exige un taux de reconnaissance élevé et
    surtout aucune fausse date où les valeurs non datables doivent rester NaT.
    """
    from sample_data import charger_csv_reel
    s = charger_csv_reel()
    out = clean_dates(s)
    rapport = cleaning_report(s, out)
    # Au moins 95 % des valeurs reconnues (le reste = vrais invalides/manquants).
    assert rapport["taux_reconnaissance"] >= 0.95
    # Aucune valeur réellement non datable ne doit avoir été convertie.
    for piege in ["unknown", "yesterday", "tomorrow", "9999-99-99", "Feb 30 2020"]:
        masque = s == piege
        if masque.any():
            assert out[masque].isna().all(), f"Faux positif sur {piege!r}"


if __name__ == "__main__":
    # Lanceur sans dépendance : exécute tous les tests test_* de ce module.
    import traceback

    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    echecs = 0
    for t in tests:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception:
            echecs += 1
            print(f"  FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - echecs}/{len(tests)} tests réussis.")
    raise SystemExit(1 if echecs else 0)
