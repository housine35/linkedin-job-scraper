import os
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
import pycountry
import pycountry_convert

# Configure logging
logging.basicConfig(filename='location_update_errors.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Dictionary of US state abbreviations
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

# Function to extract country from location string
def extract_country(location):
    if not location or location.lower() in ["remote", "unknown", ""]:
        return None

    parts = [part.strip() for part in location.split(',')]
    if not parts:
        return None

    potential_country = parts[-1]
    country = None

    if potential_country in US_STATES:
        return US_STATES[potential_country]

    try:
        country_data = pycountry.countries.search_fuzzy(potential_country)
        if country_data:
            country = country_data[0].name
    except LookupError:
        for part in reversed(parts[:-1]):
            try:
                country_data = pycountry.countries.search_fuzzy(part)
                if country_data:
                    country = country_data[0].name
                    break
            except LookupError:
                continue

    special_cases = {
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
    if location in special_cases:
        country = special_cases[location]

    return country

# Function to get country and continent
def get_country_continent(location):
    if location.lower() in ["remote", "unknown", ""]:
        logging.info(f"Ambiguous location '{location}', returning null values")
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
        return None, None

    logging.info(f"Success for location '{location}': {country}, {continent}")
    return country, continent

# Function to connect to MongoDB and update documents
def update_locations():
    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB", "scraping")
    collection_name = os.getenv("MONGO_COLLECTION", "linkedin")

    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        documents = collection.find()
        updated_count = 0
        skipped_count = 0
        failed_locations = []

        for doc in documents:
            location = doc.get("location")
            if not location:
                logging.info(f"Skipping document with missing location: {doc.get('_id')}")
                skipped_count += 1
                continue

            country, continent = get_country_continent(location)

            if country is None and continent is None:
                failed_locations.append((doc['_id'], location))
                skipped_count += 1
                continue

            try:
                result = collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"country": country, "continent": continent}}
                )
                if result.modified_count > 0:
                    updated_count += 1
                    print(f"Updated document with ID: {doc['_id']} (country: {country}, continent: {continent})")
                else:
                    skipped_count += 1
                    print(f"No update needed for document with ID: {doc['_id']}")
            except Exception as e:
                logging.error(f"Error updating document with ID: {doc['_id']}: {str(e)}")
                skipped_count += 1

        print(f"Updated {updated_count} documents with country and continent in MongoDB.")
        print(f"Skipped {skipped_count} documents (missing location, no update needed, or failed processing)")
        if failed_locations:
            logging.info(f"Failed to process {len(failed_locations)} locations: {failed_locations}")
            print(f"Failed to process {len(failed_locations)} locations. Check 'location_update_errors.log' for details.")

        client.close()

    except ConnectionFailure as e:
        logging.error(f"Error connecting to MongoDB: {e}")
    except Exception as e:
        logging.error(f"Error processing MongoDB updates: {e}")

# Function to clean MongoDB by removing documents with title containing 'meat market'
def clean_db():
    mongo_uri = os.getenv("mongodb+srv://redsdz:Foot199407%40%23@cluster0.ypgrqjo.mongodb.net/linkedin?retryWrites=true&w=majority")
    db_name = os.getenv("MONGO_DB", "scraping")
    collection_name = os.getenv("MONGO_COLLECTION", "linkedin")

    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]
        collection = db[collection_name]

        logging.info(f"Accessing database: {db_name}, collection: {collection_name}")

        query = {"title": {"$regex": "meat market", "$options": "i"}}
        matching_documents = collection.count_documents(query)
        if matching_documents == 0:
            logging.warning("No documents found with title containing 'meat market'.")
            print("No documents found with title containing 'meat market'.")
        else:
            logging.info(f"Found {matching_documents} documents with title containing 'meat market'.")

        sample_docs = collection.find().limit(5)
        for doc in sample_docs:
            title = doc.get("title", "No title field")
            logging.info(f"Sample document ID: {doc.get('_id')}, title: {title}")

        result = collection.delete_many(query)

        print(f"Deleted {result.deleted_count} documents where title contains 'meat market'.")
        logging.info(f"Deleted {result.deleted_count} documents where title contains 'meat market'.")

        client.close()

    except ConnectionFailure as e:
        logging.error(f"Error connecting to MongoDB for cleaning: {e}")
        print(f"Error connecting to MongoDB: {str(e)}")
    except Exception as e:
        logging.error(f"Error cleaning MongoDB: {e}")
        print(f"Error cleaning MongoDB: {str(e)}")

if __name__ == "__main__":
    update_locations()
    clean_db()
