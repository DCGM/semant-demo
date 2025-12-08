import argparse
# document processing
import json
import itertools
import re
from datetime import datetime, date
# weaviate
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
# metadata db
from sqlalchemy import create_engine, select, MetaData
# logging
import logging
# date format
from datetime import datetime, date

def parse_args():
    parser = argparse.ArgumentParser(description="Update metadata of all documents from Weaviate database.")
    parser.add_argument("--document-collection", type=str, default="Documents", 
                        help="Name of the document collection.")
    parser.add_argument("--logging-on", action="store_true",
                        help="Turn on (yes) or off (no or anything accept yes) logging info printing to terminal")
    
    return parser.parse_args()

def get_first_valid(data):
    """
    Extracts first nonempty element in first non empty list
    """
    if data is None:
        return None

    if isinstance(data, datetime):
        return data.date() # year month day
    
    # base case scalar value (not list)
    if not isinstance(data, list):
        return data if data not in ("", [], None) else None

    # if list is empty
    if len(data) == 0:
        return None

    # recursive search each element
    for element in data:
        value = get_first_valid(element)
        if value not in (None, "", []):
            return value

    return None

def get_all_valid(data):
    """
    Take all values from all lists and keep unique values
    """
    if data is None:
        return None
    flat_list = list(itertools.chain.from_iterable(data))
    unique_list = list(set(flat_list))
    return unique_list

def parse_date(date_str: str) -> str:
    if re.match(r'\d{1,2}\.\d{1,2}\.\d{4}', date_str):
        date_match = re.search(r'\d{1,2}\.\d{1,2}\.\d{4}', date_str)
        date_str = date_match.group(0)

def extractYear(dateIssued):
    #logging.info(dateIssued)
    if dateIssued is not None:
        match = re.search(r'\d{4}', dateIssued)
        if match is not None:
            year = match.group(0)
            return year
    return None

def prepare_year(date):
    # prepare year
    year = None
    if date is not None:
        if isinstance(date, datetime):
            year = date.year
        else:
            year = extractYear(date)
    return year

def normalize_date(date_str):
    """
    Convert format like 22.5.1929 to a datetime object (naive, no timezone)
    suitable for Weaviate DATE property.
    """
    if isinstance(date_str, datetime):
        return date_str  # already datetime

    if isinstance(date_str, date):
        # convert date to datetime at midnight
        return datetime(date_str.year, date_str.month, date_str.day)

    if isinstance(date_str, str):
        match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if match:
            d, m, y = match.groups()
            try:
                return datetime(int(y), int(m), int(d))  # naive datetime
            except ValueError:
                return None  # invalid calendar date

    return None  # unparseable

def map_result_names(result):
    """
    Renames and moves the data from db query result into a dictionary
    """
    res_dict = {}
    metadata = result.metadata_json
    if metadata is None:
        metadata = {}
    # already in weaviate
    res_dict["title"] = get_first_valid(result.title)
    res_dict["titleMetadata"] = get_first_valid(metadata.get('Title', None))
    res_dict["subtitle"] = get_first_valid(metadata.get('Subtitle', None))
    res_dict["partNumber"] = get_first_valid(metadata.get('PartNumber', None))
    res_dict["partName"] = get_first_valid(metadata.get('PartName', None))
    # prepare date and store it in variable to extract year later
    dateMain = get_first_valid(result.date)
    res_dict["dateIssued"] = normalize_date(dateMain)
    yearMain = prepare_year(dateMain)
    if yearMain is not None:
        yearMain = int(yearMain)
    res_dict["yearIssued"] = yearMain
    date = get_first_valid(metadata.get('DateIssued', None))
    res_dict["dateIssuedMetadata"] = normalize_date(date)
    year = prepare_year(date)
    if year is not None:
        year = int(year)
    res_dict["yearIssuedMetadata"] = year
    res_dict["author"] = get_all_valid(metadata.get('Author', None))
    res_dict["publisher"] = get_first_valid(metadata.get('Publisher', None))
    res_dict["language"] = get_first_valid(metadata.get('Language', None))
    res_dict['public'] = result.public
    res_dict['documentType'] = result.record_type
    res_dict["placeOfPublication"] = get_first_valid(metadata.get('PlaceTerm', None))
    
    # new in weaviate
    res_dict["seriesName"] = get_first_valid(metadata.get('SeriesName', None))
    res_dict["seriesNumber"] = get_first_valid(metadata.get('SeriesNumber', None))
    res_dict["edition"] = get_first_valid(metadata.get('Edition', None))
    res_dict["manufacturePublisher"] = get_first_valid(metadata.get('ManufacturePublisher', None))
    res_dict["manufacturePlaceTerm"] = get_first_valid(metadata.get('ManufacturePlaceTerm', None))
    res_dict["illustrators"] = get_all_valid(metadata.get('Illustrator', None))
    res_dict["translators"] = get_all_valid(metadata.get('Translator', None))
    res_dict["editors"] = get_all_valid(metadata.get('Editor', None))
    res_dict["redaktors"] = get_all_valid(metadata.get('Redaktor', None))

    return res_dict

def score_result(result):
    """
    Scores the result adding one point for missing data
    Lower score is better
    """
    score = 0
    for _, value in result.items():
        if value is None or value == []:
            score += 1
    return score

def decide(main_key, second_key, best_db_doc):
    if best_db_doc[main_key] is None or best_db_doc[main_key] == []:
        best_db_doc[main_key] = best_db_doc[second_key]
    return best_db_doc

def clean_data(best_db_doc):
    """
    removes duplicate dates, titles, unify names,
    remove items with missing - None or [] values
    """
    # decide title
    best_db_doc = decide("title", "titleMetadata", best_db_doc)
    # decide date
    best_db_doc = decide("dateIssued", "dateIssuedMetadata", best_db_doc)
    # decide year
    best_db_doc = decide("yearIssued", "yearIssuedMetadata", best_db_doc)
    # remove items with None values or empty list as a value
    best_db_doc = {
        key: value for key, value in best_db_doc.items()
        if value not in [None, []]
    }
    return best_db_doc

def insert_to_weaviate(client, data, documents_collection, document_id):
    """
    Updates additional info about documents into the weaviate db
    """
    try:
        doc_collection = client.collections.get(documents_collection)
        doc_collection.data.update(
            uuid=document_id,
            properties=data,
        )
        return True
    except Exception as e:
        logging.exception(f"Not updated the data due to error: {e}")
        return False


def print_document_pretty(doc, index):
    """Print a document in a human-readable format."""
    logging.info(f"\n{'='*80}")
    logging.info(f"DOCUMENT #{index + 1}")
    logging.info(f"{'='*80}")
    logging.info(f"UUID: {doc.uuid}")
    logging.info(f"\nProperties:")
    logging.info("-" * 80)
    
    for key, value in sorted(doc.properties.items()):
        if isinstance(value, list):
            logging.info(f"  {key:20s}: {', '.join(str(v) for v in value)}")
        elif value is not None:
            logging.info(f"  {key:20s}: {value}")
    logging.info(f"\n{'='*80}")

def main():
    args = parse_args()
    if args.logging_on:
        logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
                handlers=[logging.StreamHandler()] # print to console
            )
    else:
        logging.basicConfig(level=logging.CRITICAL)  # suppress logs
    db_engine = create_engine("postgresql://librarymetadata_all:@localhost:5888/librarymetadata_all")

    db_model = MetaData()
    db_model.reflect(bind=db_engine)
    db_model = db_model.tables

    # connect to sql db
    with db_engine.connect() as db_connection:
    
        # Connect to Weaviate
        client = WeaviateClient(
            connection_params=ConnectionParams.from_params(
                http_host="localhost", http_port=8080, http_secure=False,
                grpc_host="localhost", grpc_port=50051, grpc_secure=False,
            ))
        
        try:
            client.connect()
            
            if not client.is_ready():
                logging.error("ERROR: Weaviate is not ready.")
                return
            
            # Get the document collection
            doc_collection = client.collections.get(args.document_collection)
            
            # Fetch all documents
            logging.info(f"Fetching documents from collection: {args.document_collection}")
            response = doc_collection.query.fetch_objects()
            
            documents = response.objects
            
            if not documents:
                logging.info(f"\nNo documents found in collection '{args.document_collection}'")
                return
            
            logging.info(f"\nFound {len(documents)} document(s)\n")
            for idx, doc in enumerate(documents):
                    print_document_pretty(doc, idx)
                    #################
                    # actual update #
                    db_documents = db_connection.execute(select(db_model['meta_records']).where(db_model['meta_records'].c.id == doc.uuid))
                        
                    db_documents_data = db_documents.all() # load all document records (mostly from different libraries)
                    # go through all results for current document
                    logging.info(f"All results: ")
                    processed_db_doc_list = []
                    for document in db_documents_data:
                        renamed_db_doc = map_result_names(document)
                        score = score_result(renamed_db_doc)
                        processed_db_doc_list.append([renamed_db_doc,score])
                        logging.info(document)
                        logging.info(renamed_db_doc)
                        logging.info("\n")
                    # choose the most informative item
                    best_db_doc, _ = min(processed_db_doc_list, key=lambda x: x[1])
                    # add missing value from different records
                    for key in best_db_doc.keys(): # iterate over keys in best_db_doc
                        if best_db_doc[key] is None or best_db_doc[key] == []:
                            # look for first nonmissing value in other results
                            for other_result, _ in processed_db_doc_list:
                                if other_result[key] not in [None, []]:
                                    best_db_doc[key] = other_result[key]
                                    break  # stop at the first value found

                    logging.info("Most complete data")
                    logging.info(best_db_doc)
                    # insert into weaviate the new record
                    best_db_doc = clean_data(best_db_doc)
                    logging.info("Cleaned data - these will be inserted")
                    logging.info(best_db_doc)
                    insert_to_weaviate(client=client, data=best_db_doc, documents_collection=args.document_collection, document_id=doc.uuid)
            
            logging.info(f"\n{'='*80}")
            logging.info(f"Total documents: {len(documents)}")
            logging.info(f"{'='*80}")
        
        finally:
            client.close()

if __name__ == "__main__":
    main()
