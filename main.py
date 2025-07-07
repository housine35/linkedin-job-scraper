import os
from dotenv import load_dotenv
from scraper import scrape_all_jobs
from database import save_jobs


def main():
    # Load the .env file
    if not load_dotenv():
        print("Error: Could not load .env file or it is malformed.")
        return

    # Read and convert environment variables
    params = {
        "keyword": os.getenv("KEYWORD", "Scraping"),
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

    # Read storage configuration
    storage_type = os.getenv("STORAGE_TYPE", "csv").lower()
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", "linkedin")
    collection_name = os.getenv("MONGO_COLLECTION", "scraping")
    output_file = os.getenv("OUTPUT_FILE", "jobs_output.csv")

    # Display parameters used
    print(
        f"Scraping with: keyword='{params['keyword']}', location='{params['location']}', "
        f"hours={params['hours']}, days={params['days']}, work_type='{params['work_type']}', "
        f"max_jobs={params['max_jobs']}, storage_type='{storage_type}'"
    )

    # Start scraping
    jobs = scrape_all_jobs(**params)

    # Save results
    if jobs:
        save_jobs(jobs, storage_type, output_file, mongo_uri, db_name, collection_name)
        print(f"Results saved ({len(jobs)} jobs)")
    else:
        print("No jobs found.")


if __name__ == "__main__":
    main()
