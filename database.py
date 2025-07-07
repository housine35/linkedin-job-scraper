import csv
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError, BulkWriteError
from urllib.parse import urlparse, urlunparse
from datetime import datetime


def normalize_url(url):
    """
    Normalizes a URL by removing query parameters and trailing slashes.

    Args:
        url (str): The URL to normalize.

    Returns:
        str: The normalized URL, or None if invalid.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
        # Keep only scheme, netloc, and path; remove query, fragment, etc.
        normalized = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", "")
        )
        return normalized
    except Exception as e:
        return None


def save_jobs_to_csv(jobs, output_file):
    """
    Saves the list of job postings to a CSV file, preventing duplicates based on normalized URL
    and adding an 'etat' column ('new' for new jobs, 'old' for existing jobs).

    Args:
        jobs (list): List of dictionaries containing job details.
        output_file (str): Path to the output CSV file.
    """
    if not jobs:
        print("No jobs to save to CSV.")
        return

    # Define CSV fieldnames with 'etat' column
    fieldnames = [
        "url",
        "title",
        "company",
        "location",
        "posting_time",
        "status",
        "etat",
    ]

    # Normalize URLs for incoming jobs and prepare new jobs list
    new_jobs = []
    invalid_jobs = 0
    for job in jobs:
        normalized_url = normalize_url(job.get("url"))
        if normalized_url:
            job["url"] = normalized_url
            job["etat"] = "new"  # Mark as new initially
            new_jobs.append(job)
        else:
            invalid_jobs += 1

    if invalid_jobs > 0:
        print(f"Skipped {invalid_jobs} jobs with missing or invalid URLs")

    if not new_jobs:
        print("No valid jobs to save to CSV.")
        return

    # Read existing jobs from CSV (if file exists)
    existing_jobs = []
    existing_urls = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                # Ensure all required fields are present
                for row in reader:
                    normalized_url = normalize_url(row.get("url"))
                    if normalized_url:
                        row["url"] = normalized_url
                        row["etat"] = "old"  # Mark existing jobs as old
                        existing_jobs.append(row)
                        existing_urls.add(normalized_url)
                    else:
                        print(f"Skipped invalid URL in existing CSV: {row.get('url')}")
        except Exception as e:
            print(f"Error reading existing CSV file: {e}")
            return

    # Filter out duplicates and update new jobs
    jobs_to_write = existing_jobs.copy()  # Start with existing jobs (marked as old)
    added_count = 0
    skipped_count = 0
    for job in new_jobs:
        if job["url"] in existing_urls:
            skipped_count += 1
        else:
            jobs_to_write.append(job)  # Add new job (already marked as new)
            existing_urls.add(job["url"])
            added_count += 1

    # Write all jobs to CSV
    try:
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(jobs_to_write)
    except Exception as e:
        print(f"Error writing to CSV file: {e}")
        return

    print(f"Saved {added_count} new jobs to CSV (file: {output_file})")
    if skipped_count > 0:
        print(f"Skipped {skipped_count} duplicate jobs (already exist in CSV)")
    if invalid_jobs > 0:
        print(f"Skipped {invalid_jobs} jobs with missing or invalid URLs")


def save_jobs_to_mongo(
    jobs,
    mongo_uri="mongodb://localhost:27017",
    db_name="linkedin",
    collection_name="scraping",
):
    """
    Saves the list of job postings to a MongoDB collection, enforcing uniqueness on the '_id' field (normalized URL).
    Adds a 'date' field with the current timestamp for new jobs. Reports the number of added and skipped (duplicate) jobs.

    Args:
        jobs (list): List of dictionaries containing job details.
        mongo_uri (str): MongoDB connection string (default: localhost).
        db_name (str): MongoDB database name (default: linkedin).
        collection_name (str): MongoDB collection name (default: scraping).
    """
    if not jobs:
        print("No jobs to save to MongoDB.")
        return

    try:
        # Connect to MongoDB
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        # Normalize URLs, add date, and filter out invalid jobs
        valid_jobs = []
        invalid_jobs = 0
        current_date = datetime.now()
        for job in jobs:
            normalized_url = normalize_url(job.get("url"))
            if normalized_url:
                job["url"] = normalized_url
                job["_id"] = normalized_url  # Use normalized URL as unique _id
                job["date"] = current_date  # Add current timestamp
                valid_jobs.append(job)
            else:
                invalid_jobs += 1

        if invalid_jobs > 0:
            print(f"Skipped {invalid_jobs} jobs with missing or invalid URLs")

        if not valid_jobs:
            client.close()
            return

        # Insert jobs, counting added and skipped
        added_count = 0
        skipped_count = 0
        try:
            result = collection.insert_many(valid_jobs, ordered=False)
            added_count = len(result.inserted_ids)
        except BulkWriteError as bwe:
            write_errors = bwe.details.get("writeErrors", [])
            for error in write_errors:
                if error.get("code") == 11000:  # Duplicate key error
                    skipped_count += 1
            # Fallback to individual inserts for remaining jobs
            for job in valid_jobs:
                try:
                    collection.insert_one(job)
                    added_count += 1
                except DuplicateKeyError:
                    skipped_count += 1

        print(
            f"Saved {added_count} new jobs to MongoDB (database: {db_name}, collection: {collection_name})"
        )
        if skipped_count > 0:
            print(
                f"Skipped {skipped_count} duplicate jobs (already exist with same URL)"
            )
        if added_count + skipped_count + invalid_jobs < len(jobs):
            print(
                f"Warning: {len(jobs) - (added_count + skipped_count + invalid_jobs)} jobs were not processed"
            )

        # Close the connection
        client.close()
    except ConnectionFailure as e:
        print(f"Error connecting to MongoDB: {e}")
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")


def save_jobs(
    jobs,
    storage_type="csv",
    output_file="jobs_output.csv",
    mongo_uri="mongodb://localhost:27017",
    db_name="linkedin",
    collection_name="scraping",
):
    """
    Saves job postings to either CSV or MongoDB based on storage_type.

    Args:
        jobs (list): List of dictionaries containing job details.
        storage_type (str): Storage method ('csv' or 'mongo').
        output_file (str): Path to the output CSV file (used if storage_type is 'csv').
        mongo_uri (str): MongoDB connection string (used if storage_type is 'mongo').
        db_name (str): MongoDB database name (used if storage_type is 'mongo').
        collection_name (str): MongoDB collection name (used if storage_type is 'mongo').
    """
    if storage_type.lower() == "mongo":
        save_jobs_to_mongo(jobs, mongo_uri, db_name, collection_name)
    elif storage_type.lower() == "csv":
        save_jobs_to_csv(jobs, output_file)
    else:
        print(f"Invalid storage_type: {storage_type}. Use 'csv' or 'mongo'.")
