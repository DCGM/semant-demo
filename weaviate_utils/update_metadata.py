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

def parse_args():
    parser = argparse.ArgumentParser(description="Print all documents from Weaviate database.")
    parser.add_argument("--document-collection", type=str, default="Documents", 
                        help="Name of the document collection.")
    parser.add_argument("--output-file", type=str, default=None,
                        help="Optional: Save output to a file instead of printing to console.")
    parser.add_argument("--logging-on", action="store_true",
                        help="Turn on (yes) or off (no or anything accept yes) logging info printing to terminal")
    
    return parser.parse_args()

def get_first_valid(data):
    """
    Extracts first nonempty element in first non empty list
    """
    #logging.info(data)
    #logging.info(type(data))
    #logging.info("\n")
    if data is None:
        return None

    if isinstance(data, datetime):
        return data.date() #.isoformat() # year month day
    
    # Base case scalar value (not list)
    if not isinstance(data, list):
        return data if data not in ("", [], None) else None

    # If list is empty
    if len(data) == 0:
        return None

    # Recursive search each element
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

def map_result_names(result):
    """
    Renames and moves the data from db query result into a dictionary
    """
    res_dict = {}
    metadata = result.metadata_json
    if metadata is None:
        metadata = {}

    #res_dict['library'] = result.library
    #res_dict['metadata_json'] = result.metadata_json

    # already in weaviate
    res_dict["title"]= get_first_valid(result.title)
    res_dict["titleMetadata"]= get_first_valid(metadata.get('Title', None))
    res_dict["subtitle"]= get_first_valid(metadata.get('Subtitle', None))
    res_dict["partNumber"]=  get_first_valid(metadata.get('PartNumber', None))
    res_dict["partName"]=  get_first_valid(metadata.get('PartName', None))
    # prepare date and store it in variable to extract year later
    dateMain = get_first_valid(result.date)
    res_dict["dateIssued"] = dateMain
    yearMain = prepare_year(dateMain)
    res_dict["yearIssued"] = yearMain
    date = get_first_valid(metadata.get('DateIssued', None))
    res_dict["dateIssuedMetadata"]=  date
    year = prepare_year(date)
    res_dict["yearIssuedMetadata"]= year
    res_dict["author"]=  get_all_valid(metadata.get('Author', None))
    res_dict["publisher"] =  get_first_valid(metadata.get('Publisher', None))
    res_dict["language"] =  get_first_valid(metadata.get('Language', None))
    # missing: res_dict["description"]: "",
    res_dict['url'] = str(result.id)
    res_dict['public'] = "True" if result.public else "False"
    res_dict['documentType'] = result.record_type
    # res_dict['missing']
    # missing: res_dict["genre"]
    res_dict["placeOfPublication"] =  get_first_valid(metadata.get('PlaceTerm', None))
    
    # not yet in weaviate
    res_dict["seriesName"] =  get_first_valid(metadata.get('SeriesName', None))
    res_dict["seriesNumber"] =  get_first_valid(metadata.get('SeriesNumber', None))
    res_dict["edition"] =  get_first_valid(metadata.get('Edition', None))
    res_dict["manufacturePublisher"] =  get_first_valid(metadata.get('ManufacturePublisher', None))
    res_dict["manufacturePlaceTerm"] =  get_first_valid(metadata.get('ManufacturePlaceTerm', None))
    res_dict["illustrators"] =  get_all_valid(metadata.get('Illustrator', None))
    res_dict["translators"] =  get_all_valid(metadata.get('Translator', None))
    res_dict["editors"] =  get_all_valid(metadata.get('Editor', None))
    res_dict["redaktors"] =  get_all_valid(metadata.get('Redaktor', None))

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

def normalize_date(date_str):
    """
    convert format like 22.5.1929 to datetime or date format
    """
    if isinstance(date_str, date):
        return date_str  # already a date

    if isinstance(date_str, datetime):
        return date_str

    if isinstance(date_str, str):
        match = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", date_str)
        if match:
            d, m, y = match.groups()
            try:
                return date(int(y), int(m), int(d))
            except ValueError:
                return None  # invalid calendar date

    return None  # unparseable

def decide(main_key, second_key, best_result):
    if best_result[main_key] is None or best_result[main_key] == []:
        best_result[main_key] = best_result[second_key]
    return best_result

def clean_data(best_result):
    """
    removes duplicate dates, titles, unify names,
    remove items with missing - None or [] values
    """
    # decide title
    best_result = decide("title", "titleMetadata", best_result)
    # decide date
    best_result = decide("dateIssued", "dateIssuedMetadata", best_result)
    # decide year
    best_result = decide("yearIssued", "yearIssuedMetadata", best_result)
    # remove items with None values or empty list as a value
    best_result = {
        key: value for key, value in best_result.items()
        if value not in [None, []]
    }
    return best_result

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
    print(f"\n{'='*80}")
    print(f"DOCUMENT #{index + 1}")
    print(f"{'='*80}")
    print(f"UUID: {doc.uuid}")
    print(f"\nProperties:")
    print("-" * 80)
    
    for key, value in sorted(doc.properties.items()):
        if isinstance(value, list):
            print(f"  {key:20s}: {', '.join(str(v) for v in value)}")
        elif value is not None:
            print(f"  {key:20s}: {value}")
    print(f"\n{'='*80}")

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
            
            output_lines = []

            for idx, doc in enumerate(documents):
                    if args.output_file:
                        output_lines.append("=" * 80)
                        output_lines.append(f"DOCUMENT #{idx + 1}")
                        output_lines.append("=" * 80)
                        output_lines.append(f"UUID: {doc.uuid}")
                        output_lines.append("\nProperties:")
                        output_lines.append("-" * 80)
                        for key, value in sorted(doc.properties.items()):
                            if isinstance(value, list):
                                output_lines.append(f"  {key:20s}: {', '.join(str(v) for v in value)}")
                            elif value is not None:
                                output_lines.append(f"  {key:20s}: {value}")
                        output_lines.append("")
                    else:
                        print_document_pretty(doc, idx)
                    #################
                    # actual update #
                    #result = db_connection.execute(select(db_model['meta_records']).limit(10)) #(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
                    result = db_connection.execute(select(db_model['meta_records']).where(db_model['meta_records'].c.id == doc.uuid))
                                                #.where(db_model['meta_records'].c.metadata_json.is_not(None))
                                                #.limit(10)) #(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
                        
                    results = result.all()#first()
                    # go through all results for current document
                    logging.info(f"All results: ")
                    processed_results_list = []
                    for r in results:
                        renamed_result = map_result_names(r)
                        score = score_result(renamed_result)
                        processed_results_list.append([renamed_result,score])
                        logging.info(r)
                        logging.info(map_result_names(r))
                        logging.info("\n")
                    # choose the most informative item
                    best_result, _ = min(processed_results_list, key=lambda x: x[1])
                    # add missing value from different records
                    for key in best_result.keys(): # iterate over keys in best_result
                        if best_result[key] is None or best_result[key] == []:
                            # look for first nonmissing value in other results
                            for other_result, _ in processed_results_list:
                                if other_result[key] not in [None, []]:
                                    best_result[key] = other_result[key]
                                    break  # stop at the first value found

                    logging.info("Most complete data")
                    logging.info(best_result)
                    # insert into weaviate the new record
                    best_result = clean_data(best_result)
                    logging.info("Cleaned data")
                    logging.info(best_result)
                    insert_to_weaviate(client=client, data=best_result, documents_collection=args.document_collection, document_id=doc.uuid)
            
            # Write to file if specified
            if args.output_file:
                with open(args.output_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(output_lines))
                print(f"\nOutput saved to: {args.output_file}")
            
            print(f"\n{'='*80}")
            print(f"Total documents: {len(documents)}")
            print(f"{'='*80}")
        
        finally:
            client.close()

if __name__ == "__main__":
    main()
