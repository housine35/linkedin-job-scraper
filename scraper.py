import requests
import time
import os
from parser import parse_job_postings
from urllib.parse import quote_plus


def fetch_linkedin_jobs(
    keyword, location, start=0, days=1, hours=None, work_type="all"
):
    """
    Sends a GET request to LinkedIn's hidden job search API endpoint using requests.
    Tries with proxy first, falls back to local IP if proxy fails.

    Args:
        keyword (str): The job title or keywords to search for.
        location (str): The location where to search for jobs.
        start (int): The pagination offset (0 for the first page, 10 for the second, etc.).
        days (int): Number of days to filter jobs (e.g., 1 for last 24h, 30 for last 30 days). Ignored if hours is provided.
        hours (int, optional): Number of hours to filter jobs (e.g., 24 for last 24 hours). Takes precedence over days.
        work_type (str): Type of work ('remote', 'hybrid', or 'all' for all types).

    Returns:
        str: The raw HTML content of the job listings or None if the request fails.
    """
    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keyword,
        "location": location,
        "start": start,
    }

    # Set time filter: hours takes precedence over days
    if hours is not None:
        if hours < 1:
            raise ValueError("Hours must be between 1 and 720.")
        params["f_TPR"] = (
            f"r{int(hours) * 3600}"  # Convert hours to seconds (1 hour = 3600 seconds)
        )
    else:
        if days < 1:
            raise ValueError("Days must be between 1 and 30.")
        params["f_TPR"] = (
            f"r{int(days) * 86400}"  # Convert days to seconds (1 day = 86400 seconds)
        )

    # Set work type parameter
    work_type_map = {
        "remote": "2",
        "hybrid": "3",
        "all": "1,2,3",  # Include on-site, remote, and hybrid
    }
    if work_type.lower() in work_type_map:
        params["f_WT"] = work_type_map[work_type.lower()]
    else:
        params["f_WT"] = work_type_map["all"]  # Default to all types

    # Headers from the provided JavaScript object
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.linkedin.com/jobs",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    }

    # Configure proxy if provided
    proxies = None
    proxy_url = os.getenv("PROXY_URL")
    proxy_username = os.getenv("PROXY_USERNAME")
    proxy_password = os.getenv("PROXY_PASSWORD")

    if proxy_url and proxy_username and proxy_password:
        encoded_username = quote_plus(proxy_username)
        encoded_password = quote_plus(proxy_password)
        proxy_string = f"http://{encoded_username}:{encoded_password}@{proxy_url}"
        proxies = {
            "http": proxy_string,
            "https": proxy_string,
        }
        print(f"Tentative avec le proxy : {proxy_url}")
    else:
        proxies = None

    # Try with proxy first, then without if it fails
    for use_proxy in [True, False] if proxies else [False]:
        attempt_proxies = proxies if use_proxy else None
        attempt_desc = "proxy" if use_proxy else "IP locale"

        for attempt in range(3):  # Retry up to 3 times
            try:
                response = requests.get(
                    base_url,
                    params=params,
                    headers=headers,
                    proxies=attempt_proxies,
                    timeout=10,
                )
                response.raise_for_status()  # Raise an error for bad status codes
                response_text = response.text

                # Check for empty response or CAPTCHA
                if not response_text.strip() or "captcha" in response_text.lower():
                    print(f"Empty response or CAPTCHA detected avec {attempt_desc}.")
                    return None

                return response_text
            except requests.RequestException as e:
                print(f"Erreur avec {attempt_desc} (tentative {attempt + 1}/3) : {e}")
                if attempt < 2:  # Wait before retrying
                    time.sleep(2**attempt)
                continue
        else:
            print(f"Échec après 3 tentatives avec {attempt_desc}.")
            if use_proxy:
                print("Basculement vers l'IP locale...")
            continue

    print("Échec de toutes les tentatives (proxy et IP locale).")
    return None


def scrape_all_jobs(
    keyword, location, days=1, hours=None, work_type="all", max_jobs=50
):
    """
    Scrapes all job postings for a given keyword, location, time filter, and work type, handling pagination.

    Args:
        keyword (str): The job title or keywords to search for.
        location (str): The location where to search for jobs.
        days (int): Number of days to filter jobs (e.g., 1 for last 24h, 30 for last 30 days). Ignored if hours is provided.
        hours (int, optional): Number of hours to filter jobs (e.g., 24 for last 24 hours). Takes precedence over days.
        work_type (str): Type of work ('remote', 'hybrid', or 'all' for all types).
        max_jobs (int): Maximum number of jobs to scrape (to avoid infinite loops).

    Returns:
        list: A list of all job postings.
    """
    all_jobs = []
    start = 0
    page_size = 10  # LinkedIn returns up to 10 jobs per page

    while True:
        print(f"Fetching jobs starting at index {start}...")
        job_postings_html = fetch_linkedin_jobs(
            keyword, location, start, days, hours, work_type
        )

        if not job_postings_html:
            print("No more data or error occurred.")
            break

        jobs = parse_job_postings(job_postings_html)

        if not jobs:  # If no jobs are found, stop
            print("No more jobs found.")
            break

        all_jobs.extend(jobs)
        print(f"Found {len(jobs)} jobs in this page. Total jobs: {len(all_jobs)}")

        if len(all_jobs) >= max_jobs:  # Stop if max_jobs limit is reached
            print(f"Reached max_jobs limit of {max_jobs}.")
            break

        start += page_size  # Move to the next page
        time.sleep(1)  # Add a delay to avoid overwhelming the server

    return all_jobs
