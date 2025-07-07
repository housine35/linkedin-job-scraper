from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import re


def convert_relative_time(relative_time_str, current_time=None):
    """
    Converts a relative time string (e.g., '16 hours ago') to an exact datetime.

    Args:
        relative_time_str (str): Relative time string (e.g., '16 hours ago', '10 minutes ago').
        current_time (datetime, optional): Reference time for calculation. Defaults to now in CEST.

    Returns:
        str: Exact datetime in 'YYYY-MM-DD HH:MM:SS' format, or None if parsing fails.
    """
    if not relative_time_str:
        return None

    # Set current time to CEST if not provided
    if current_time is None:
        current_time = datetime.now(pytz.timezone("Europe/Paris"))  # CEST

    # Regex to extract number and unit (e.g., "16 hours ago" -> 16, "hours")
    pattern = r"(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks)\s*ago"
    match = re.match(pattern, relative_time_str.lower().strip())

    if not match:
        print(f"Warning: Could not parse relative time '{relative_time_str}'")
        return None

    value, unit = int(match.group(1)), match.group(2)

    # Define time delta based on unit
    if unit in ["minute", "minutes"]:
        delta = timedelta(minutes=value)
    elif unit in ["hour", "hours"]:
        delta = timedelta(hours=value)
    elif unit in ["day", "days"]:
        delta = timedelta(days=value)
    elif unit in ["week", "weeks"]:
        delta = timedelta(weeks=value)
    else:
        print(f"Warning: Unknown time unit '{unit}' in '{relative_time_str}'")
        return None

    # Calculate exact time
    exact_time = current_time - delta

    # Format as string
    return exact_time.strftime("%Y-%m-%d %H:%M:%S")


def parse_job_postings(job_postings_html):
    """
    Parses the HTML content to extract job postings.

    Args:
        job_postings_html (str): The raw HTML content of the job listings.

    Returns:
        list: A list of dictionaries containing job details.
    """
    if not job_postings_html:
        return []

    job_postings = []
    soup = BeautifulSoup(job_postings_html, "html.parser")
    job_card_elements = soup.select("div.base-card")

    if not job_card_elements:
        print("No job cards found in the HTML. Possible HTML structure change.")
        return []

    # Get current time in CEST for consistent calculations
    current_time = datetime.now(pytz.timezone("Europe/Paris"))

    for job_card in job_card_elements:
        link_element = job_card.select_one("a.base-card__full-link")
        link = link_element["href"] if link_element else None

        title_element = job_card.select_one("span.sr-only")
        title = title_element.text.strip() if title_element else None

        company_element = job_card.select_one("a.hidden-nested-link")
        company = company_element.text.strip() if company_element else None

        location_element = job_card.select_one("span.job-search-card__location")
        location = location_element.text.strip() if location_element else None

        time_element = job_card.select_one("time")
        posting_time = time_element.text.strip() if time_element else None

        # Calculate exact posting time
        exact_posting_time = (
            convert_relative_time(posting_time, current_time) if posting_time else None
        )

        status_element = job_card.select_one("span.job-search-card__status")
        status = status_element.text.strip() if status_element else None

        job_posting = {
            "url": link,
            "title": title,
            "company": company,
            "location": location,
            "posting_time": exact_posting_time,  # New field for exact datetime
            "status": status,
        }
        job_postings.append(job_posting)

    return job_postings
