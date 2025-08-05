import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
from scraper import scrape_all_jobs
from database import save_jobs


def main():
    # Charge .env uniquement en local (facultatif)
    if os.getenv("GITHUB_ACTIONS") != "true":
        load_dotenv()

    # Lire et convertir les variables d'environnement
    # Convertir KEYWORD en liste
    keyword_input = os.getenv("KEYWORD", "Scraping")
    keywords = [k.strip() for k in keyword_input.split(",")]  # Divise la chaîne en liste et supprime les espaces

    params = {
        "keywords": keywords,  # Utiliser une liste de mots-clés
        "location": os.getenv("LOCATION", "worldwide"),
        "work_type": os.getenv("WORK_TYPE", "remote"),
        "hours": None,
        "days": 30,
        "max_jobs": 100,
    }

    try:
        if os.getenv("HOURS"):
            params["hours"] = int(os.getenv("HOURS"))
        params["days"] = int(os.getenv("DAYS", "30"))
        params["max_jobs"] = int(os.getenv("MAX_JOBS", "50"))
    except ValueError as e:
        print(f"Error: Invalid HOURS, DAYS, or MAX_JOBS values. Using defaults. ({e})")
        params["hours"] = None
        params["days"] = 30
        params["max_jobs"] = 50

    # Configuration MongoDB sécurisée via secrets séparés
    storage_type = os.getenv("STORAGE_TYPE", "csv").lower()
    db_name = os.getenv("MONGO_DB", "scraping")
    collection_name = os.getenv("MONGO_COLLECTION", "linkedin")
    output_file = os.getenv("OUTPUT_FILE", "jobs_output.csv")

    mongo_uri = ""
    if storage_type == "mongo":
        mongo_user = os.getenv("MONGO_USER")
        mongo_password = quote_plus(os.getenv("MONGO_PASSWORD", ""))
        mongo_host = os.getenv("MONGO_HOST")
        mongo_uri = f"mongodb+srv://{mongo_user}:{mongo_password}@{mongo_host}/{db_name}?retryWrites=true&w=majority"
        print(f"Using MongoDB URI: {mongo_uri}")

    # Afficher les paramètres utilisés
    print(
        f"Scraping with: keywords={params['keywords']}, location='{params['location']}', "
        f"hours={params['hours']}, days={params['days']}, work_type='{params['work_type']}', "
        f"max_jobs={params['max_jobs']}, storage_type='{storage_type}'"
    )
    print(f"Mongo URI used: {mongo_uri if mongo_uri else 'Not used'}")

    # Lancer le scraping
    jobs = []
    for keyword in params["keywords"]:
        # Mettre à jour le paramètre keyword pour chaque itération
        single_keyword_params = params.copy()
        single_keyword_params["keyword"] = keyword
        print(f"Scraping jobs for keyword: {keyword}")
        # Supprimer la clé 'keywords' pour éviter des erreurs dans scrape_all_jobs
        single_keyword_params.pop("keywords", None)
        jobs.extend(scrape_all_jobs(**single_keyword_params))

    # Sauvegarder les résultats
    if jobs:
        save_jobs(jobs, storage_type, output_file, mongo_uri, db_name, collection_name)
        print(f"Results saved ({len(jobs)} jobs)")
    else:
        print("No jobs found.")


if __name__ == "__main__":
    main()