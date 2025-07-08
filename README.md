## You can see Life scraping here in my website : https://portfolio-hocine-abed.onrender.com/jobs/linkedin ## 
## LinkedIn Job Scraper
This project scrapes job postings from LinkedIn using its unofficial job search API. It allows filtering by keyword, location, time period (hours or days), and work type (remote, hybrid, or all). Results can be saved to a CSV file or a MongoDB database, with duplicates prevented by using the normalized job url.
Prerequisites

## Python 3.8+
MongoDB server running locally (for MongoDB storage, default: mongodb://localhost:27017)
Dependencies listed in requirements.txt

## Installation

Clone or download this project.
Create a virtual environment (optional but recommended):python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows


## Install the dependencies:pip install -r requirements.txt


Configure the environment variables in .env (see below).
For MongoDB storage, ensure a MongoDB server is running:mongod  # Start MongoDB server (default port: 27017)



## Configuration
Edit the .env file to set the search parameters, storage options, and proxy details (if needed). Ensure each variable is on a separate line:
KEYWORD=Scraping
LOCATION=worldwide
HOURS=1
DAYS=30
WORK_TYPE=remote
MAX_JOBS=50
PROXY_URL=
PROXY_USERNAME=
PROXY_PASSWORD=
STORAGE_TYPE=mongo  # Options: csv, mongo
MONGO_URI=mongodb://localhost:27017
MONGO_DB=linkedin
MONGO_COLLECTION=scraping
OUTPUT_FILE=jobs_output.csv


HOURS: Number of hours to filter jobs (e.g., 1 for the last hour). If set, takes precedence over DAYS.
DAYS: Number of days (ignored if HOURS is set).
PROXY_URL, PROXY_USERNAME, PROXY_PASSWORD: Proxy authentication details (optional). If the proxy fails, the script falls back to the local IP.
STORAGE_TYPE: Storage method (csv for CSV file, mongo for MongoDB).
MONGO_URI, MONGO_DB, MONGO_COLLECTION: MongoDB connection details (used if STORAGE_TYPE=mongo). The normalized url is used as the unique _id to prevent duplicates.
OUTPUT_FILE: CSV file path (used if STORAGE_TYPE=csv).

## Usage
Run the main script:
python main.py


If STORAGE_TYPE=csv, results are saved to the file specified in OUTPUT_FILE (default: jobs_output.csv). The CSV includes an etat column (new for newly added jobs, old for existing jobs). Duplicate jobs (based on normalized URL) are skipped, and the script reports the number of new, duplicate, and invalid jobs.
If STORAGE_TYPE=mongo, results are saved to the MongoDB database (linkedin, collection scraping by default). The normalized url is used as the _id field to prevent duplicates, and the script reports the number of new jobs added, duplicates skipped, and invalid URLs.

To verify MongoDB data:
mongo
use linkedin
db.scraping.find().pretty()
db.scraping.countDocuments()  # Check total documents

To check for duplicates in MongoDB:
mongo
use linkedin
db.scraping.aggregate([{ $group: { _id: "$url", count: { $sum: 1 } } }, { $match: { count: { $gt: 1 } } }])

To clean duplicates in MongoDB:
mongo
use linkedin
db.scraping.drop()  # Drops the entire collection
# OR
db.scraping.aggregate([
  { $group: { _id: "$url", uniqueIds: { $addToSet: "$_id" }, count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } }
]).forEach(function(doc) {
  doc.uniqueIds.slice(1).forEach(function(dupId) {
    db.scraping.deleteOne({ _id: dupId });
  });
});

To check CSV contents:
cat jobs_output.csv  # Linux/Mac
type jobs_output.csv  # Windows

To check for duplicates in CSV (using Python):
python -c "import csv; from collections import Counter; with open('jobs_output.csv', 'r', encoding='utf-8') as f: reader = csv.DictReader(f); urls = [row['url'] for row in reader]; duplicates = {url: count for url, count in Counter(urls).items() if count > 1}; print(duplicates)"

To clear CSV (if needed):
rm jobs_output.csv  # Linux/Mac
del jobs_output.csv  # Windows

## Troubleshooting

.env parsing error: Ensure each variable is on a separate line with no extra spaces or invisible characters. Check the parameter output in the console.
MongoDB connection error: Ensure the MongoDB server is running (mongod) and that MONGO_URI, MONGO_DB, and MONGO_COLLECTION are correct in .env.
MongoDB duplicate handling: The normalized url is used as the unique _id to prevent duplicates. The script skips existing jobs and reports: "Saved X new jobs, Skipped Y duplicate jobs, Skipped Z jobs with invalid URLs". If duplicates persist:
Check for duplicates (see Usage section above).
Drop and recreate the collection:db.scraping.drop()

Then rerun the script.


CSV duplicate handling: The normalized url is used to prevent duplicates. Existing jobs are marked with etat=old, and new jobs are marked with etat=new. If duplicates appear in the CSV:
Check for duplicates (see Usage section above).
Clear the CSV file:rm jobs_output.csv  # Linux/Mac
del jobs_output.csv  # Windows


## Rerun the script.


Invalid URLs: Jobs with missing or invalid URLs are skipped and reported.
CSV file errors: If you see Error reading existing CSV file or Error writing to CSV file, check file permissions or encoding issues. Clear the CSV file and rerun.
CAPTCHA or empty response: If LinkedIn detects scraping, verify the proxy configuration in .env. Increase the delay in scraper.py (time.sleep(2)) if needed.
No jobs found: Check the Response preview in the console. If the HTML structure has changed, update the selectors in parser.py.
HTTP 429 error: LinkedIn rate-limits requests. The script retries up to 3 times automatically. Check the proxy configuration if the issue persists.
Proxy error: Ensure PROXY_URL, PROXY_USERNAME, and PROXY_PASSWORD are correct. If the proxy fails, the script falls back to the local IP.



##Future Improvements

Add support for other databases (e.g., SQL).
Implement proxy rotation for increased reliability.
Add options to configure retry attempts or delays.
Allow updating existing jobs in MongoDB (e.g., update posting_time or status) instead of skipping duplicates.
