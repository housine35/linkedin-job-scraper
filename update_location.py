import os
import re
import logging
from functools import lru_cache
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ConnectionFailure
import pycountry
import pycountry_convert
import urllib

# Chargement du fichier .env uniquement si on n'est pas sur GitHub Actions
if os.getenv("GITHUB_ACTIONS") is None:
    from dotenv import load_dotenv
    load_dotenv()

# Logging: WARNING par défaut pour éviter de gonfler le fichier de log
# (l'ancienne version logguait chaque succès en INFO -> ~1 Mo de bruit).
logging.basicConfig(
    filename="location_update_errors.log",
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Taille des lots pour les écritures groupées MongoDB
BULK_BATCH_SIZE = 500

# Dictionnaire des états américains
US_STATES = {
    'AL': 'United States', 'AK': 'United States', 'AZ': 'United States', 'AR': 'United States',
    'CA': 'United States', 'CO': 'United States', 'CT': 'United States', 'DE': 'United States',
    'FL': 'United States', 'GA': 'United States', 'HI': 'United States', 'ID': 'United States',
    'IL': 'United States', 'IN': 'United States', 'IA': 'United States', 'KS': 'United States',
    'KY': 'United States', 'LA': 'United States', 'ME': 'United States', 'MD': 'United States',
    'MA': 'United States', 'MI': 'United States', 'MN': 'United States', 'MS': 'United States',
    'MO': 'United States', 'MT': 'United States', 'NE': 'United States', 'NV': 'United States',
    'NH': 'United States', 'NJ': 'United States', 'NM': 'United States', 'NY': 'United States',
    'NC': 'United States', 'ND': 'United States', 'OH': 'United States', 'OK': 'United States',
    'OR': 'United States', 'PA': 'United States', 'RI': 'United States', 'SC': 'United States',
    'SD': 'United States', 'TN': 'United States', 'TX': 'United States', 'UT': 'United States',
    'VT': 'United States', 'VA': 'United States', 'WA': 'United States', 'WV': 'United States',
    'WI': 'United States', 'WY': 'United States'
}

# Cas particuliers connus (métropoles / formulations LinkedIn ambiguës)
SPECIAL_CASES = {
    "Greater Buenos Aires": "Argentina",
    "Mumbai Metropolitan Region": "India",
    "London Area, United Kingdom": "United Kingdom",
    "New York City Metropolitan Area": "United States",
    "Mountain View, CA": "United States",
    "San Francisco, CA": "United States",
    "San Diego, CA": "United States",
    "Manhattan Beach, CA": "United States",
    "Columbus, OH": "United States",
    "New York, NY": "United States",
    "Salt Lake City, UT": "United States",
    "Draper, UT": "United States",
    "Houston, TX": "United States",
    "Grand Prairie, TX": "United States",
    "Greater Montpellier Metropolitan Area": "France",
    "Greater Lyon Area": "France",
    "Greater Tokyo Area": "Japan",
    "Greater São Paulo Area": "Brazil",
    "Greater Paris Metropolitan Region": "France",
}

# ---------------------------------------------------------------------------
# Allowlist IT : un titre est considéré "pertinent" s'il contient au moins un
# de ces termes (recherche insensible à la casse, à frontières de mots).
# Bien plus maintenable et sûr que l'ancienne blocklist de ~80 regex non-IT.
# ---------------------------------------------------------------------------
IT_KEYWORDS = [
    r"developer", r"développeur", r"engineer", r"engineering", r"software",
    r"backend", r"back[- ]?end", r"frontend", r"front[- ]?end", r"full[- ]?stack",
    r"devops", r"sre", r"site reliability", r"platform",
    r"data engineer", r"data scientist", r"data analyst", r"machine learning",
    r"ml", r"ai", r"artificial intelligence", r"deep learning", r"nlp",
    r"python", r"java", r"javascript", r"typescript", r"golang", r"go",
    r"rust", r"c\+\+", r"c#", r"\.net", r"php", r"ruby", r"scala", r"kotlin",
    r"react", r"angular", r"vue", r"node", r"django", r"flask", r"fastapi",
    r"scraping", r"crawling", r"web scraping", r"reverse engineer",
    r"cloud", r"aws", r"azure", r"gcp", r"kubernetes", r"docker", r"terraform",
    r"database", r"sql", r"nosql", r"mongodb", r"postgres", r"elasticsearch",
    r"qa engineer", r"test automation", r"sdet", r"cyber", r"security engineer",
    r"architect", r"tech lead", r"cto", r"programmer", r"automation",
]
IT_REGEX = re.compile(r"\b(?:" + "|".join(IT_KEYWORDS) + r")\b", re.IGNORECASE)


def extract_country(location):
    if not location or location.lower() in ["remote", "unknown", ""]:
        return None

    # Les cas particuliers priment (formulations ambiguës de LinkedIn)
    if location in SPECIAL_CASES:
        return SPECIAL_CASES[location]

    parts = [part.strip() for part in location.split(',')]
    if not parts:
        return None

    potential_country = parts[-1]

    if potential_country in US_STATES:
        return US_STATES[potential_country]

    try:
        country_data = pycountry.countries.search_fuzzy(potential_country)
        if country_data:
            return country_data[0].name
    except LookupError:
        for part in reversed(parts[:-1]):
            try:
                country_data = pycountry.countries.search_fuzzy(part)
                if country_data:
                    return country_data[0].name
            except LookupError:
                continue

    return None


@lru_cache(maxsize=None)
def get_country_continent(location):
    # Mémoïsé : de nombreuses offres partagent la même localisation, ce qui
    # évite des milliers d'appels redondants au fuzzy search (lent) de pycountry.
    if not location or location.lower() in ["remote", "unknown", ""]:
        return None, None

    country = extract_country(location)
    if not country:
        logging.warning(f"Could not identify country for location '{location}'")
        return None, None

    try:
        country_data = pycountry.countries.search_fuzzy(country)[0]
        continent_code = pycountry_convert.country_alpha2_to_continent_code(country_data.alpha_2)
        continent = pycountry_convert.convert_continent_code_to_continent_name(continent_code)
    except (LookupError, KeyError):
        logging.warning(f"Could not identify continent for country '{country}'")
        return country, None

    return country, continent


def get_mongo_client():
    mongo_user = urllib.parse.quote_plus(os.getenv("MONGO_USER"))
    mongo_password = urllib.parse.quote_plus(os.getenv("MONGO_PASSWORD"))
    mongo_host = os.getenv("MONGO_HOST")
    mongo_db = os.getenv("MONGO_DB", "scraping")

    mongo_uri = f"mongodb+srv://{mongo_user}:{mongo_password}@{mongo_host}/{mongo_db}?retryWrites=true&w=majority"
    return MongoClient(mongo_uri)


def _flush(collection, ops):
    """Exécute un lot d'opérations bulk et renvoie le nombre de documents modifiés."""
    if not ops:
        return 0
    result = collection.bulk_write(ops, ordered=False)
    return result.modified_count


def update_locations():
    """
    Enrichit chaque offre avec son pays et son continent.

    Incrémental : ne traite que les documents jamais géocodés (champ
    `geo_checked` absent). Chaque document traité est marqué `geo_checked: True`
    — même en cas d'échec — pour ne plus jamais le re-scanner. Écritures
    groupées via bulk_write pour limiter les aller-retours réseau.
    """
    db_name = os.getenv("MONGO_DB", "scraping")
    collection_name = os.getenv("MONGO_COLLECTION", "linkedin")

    try:
        client = get_mongo_client()
        collection = client[db_name][collection_name]

        query = {"geo_checked": {"$ne": True}}
        cursor = collection.find(query, {"_id": 1, "location": 1})

        ops = []
        updated = 0
        scanned = 0
        unresolved = 0

        for doc in cursor:
            scanned += 1
            location = doc.get("location")
            country, continent = get_country_continent(location) if location else (None, None)
            if country is None and continent is None:
                unresolved += 1

            ops.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"country": country, "continent": continent, "geo_checked": True}},
                )
            )

            if len(ops) >= BULK_BATCH_SIZE:
                updated += _flush(collection, ops)
                ops = []

        updated += _flush(collection, ops)

        print(
            f"Geo enrichment done: scanned={scanned}, updated={updated}, unresolved={unresolved}"
        )
        client.close()

    except ConnectionFailure as e:
        logging.error(f"Error connecting to MongoDB: {e}")
        print(f"Error connecting to MongoDB: {e}")
    except Exception as e:
        logging.error(f"Error processing MongoDB updates: {e}")
        print(f"Error processing MongoDB updates: {e}")


def tag_relevance():
    """
    Tague chaque offre avec `relevant: True/False` selon l'allowlist IT.

    Non destructif (remplace l'ancien clean_db qui faisait delete_many).
    Incrémental : ne traite que les documents non encore tagués (`relevant`
    absent). Le portfolio peut ensuite filtrer sur `relevant: True`.
    """
    db_name = os.getenv("MONGO_DB", "scraping")
    collection_name = os.getenv("MONGO_COLLECTION", "linkedin")

    try:
        client = get_mongo_client()
        collection = client[db_name][collection_name]

        query = {"relevant": {"$exists": False}}
        cursor = collection.find(query, {"_id": 1, "title": 1})

        ops = []
        scanned = 0
        relevant_count = 0

        for doc in cursor:
            scanned += 1
            title = doc.get("title") or ""
            is_relevant = bool(IT_REGEX.search(title))
            if is_relevant:
                relevant_count += 1
            ops.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": {"relevant": is_relevant}})
            )

            if len(ops) >= BULK_BATCH_SIZE:
                _flush(collection, ops)
                ops = []

        _flush(collection, ops)

        print(
            f"Relevance tagging done: scanned={scanned}, "
            f"relevant={relevant_count}, non_relevant={scanned - relevant_count}"
        )
        client.close()

    except ConnectionFailure as e:
        logging.error(f"Error connecting to MongoDB for tagging: {e}")
        print(f"Error connecting to MongoDB: {e}")
    except Exception as e:
        logging.error(f"Error tagging MongoDB documents: {e}")
        print(f"Error tagging MongoDB documents: {e}")


if __name__ == "__main__":
    update_locations()
    tag_relevance()
