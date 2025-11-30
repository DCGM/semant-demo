import argparse
# document processing
import json
import itertools
import re
from datetime import datetime
# weaviate
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
# metadata db
from sqlalchemy import create_engine, select, MetaData

def parse_args():
    parser = argparse.ArgumentParser(description="Print all documents from Weaviate database.")
    parser.add_argument("--document-collection", type=str, default="Documents", 
                        help="Name of the document collection.")
    parser.add_argument("--format", type=str, choices=["pretty", "json"], default="pretty",
                        help="Output format: 'pretty' for readable format or 'json' for JSON output.")
    parser.add_argument("--output-file", type=str, default=None,
                        help="Optional: Save output to a file instead of printing to console.")
    return parser.parse_args()

def get_first_valid(data):
    """
    Extracts first nonempty element in first non empty list
    """
    print(data)
    print(type(data))
    print("\n")
    if data is None:
        return None

    if isinstance(data, datetime):
        return data.date().isoformat() # year month day
    
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
    print(dateIssued)
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
    res_dict["title_main"]= get_first_valid(result.title)
    res_dict["title"]= get_first_valid(metadata.get('Title', None))
    res_dict["subtitle"]= get_first_valid(metadata.get('Subtitle', None))
    res_dict["partNumber"]=  get_first_valid(metadata.get('PartNumber', None))
    res_dict["partName"]=  get_first_valid(metadata.get('PartName', None))
    # prepare date and store it in variable to extract year later
    dateMain = get_first_valid(result.date)
    res_dict["dateMain"] = dateMain
    yearMain = prepare_year(dateMain)
    res_dict["yearMain"] = yearMain
    date = get_first_valid(metadata.get('DateIssued', None))
    res_dict["dateIssued"]=  date
    year = prepare_year(date)
    res_dict["yearIssued"]= year
    res_dict["author"]=  get_all_valid(metadata.get('Author', None))
    res_dict["publisher"] =  get_first_valid(metadata.get('Publisher', None))
    res_dict["language"] =  get_first_valid(metadata.get('Language', None))
    # missing: res_dict["description"]: "",
    res_dict['url'] = result.id
    res_dict['public'] = result.public
    res_dict['documentType'] = result.record_type
    # res_dict['missing'] = 
    # missing: res_dict["genre"] = 
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

def insert_to_weaviate(data, document_id):
    """
    Inserts info about documents into the weaviate db
    """
    pass

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
                print("ERROR: Weaviate is not ready.")
                return
            
            # Get the document collection
            doc_collection = client.collections.get(args.document_collection)
            
            # Fetch all documents
            print(f"Fetching documents from collection: {args.document_collection}")
            response = doc_collection.query.fetch_objects(limit=1000)
            
            documents = response.objects
            
            if not documents:
                print(f"\nNo documents found in collection '{args.document_collection}'")
                return
            
            print(f"\nFound {len(documents)} document(s)\n")
            
            output_lines = []
            
            if args.format == "pretty":
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
                        #result = db_connection.execute(select(db_model['meta_records']).limit(10)) #(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
                        result = db_connection.execute(select(db_model['meta_records']).where(db_model['meta_records'].c.id == doc.uuid))
                                                    #.where(db_model['meta_records'].c.metadata_json.is_not(None))
                                                    #.limit(10)) #(select(db_model['meta_records']).where(db_model['meta_records'].c.id == 'ea236b90-0777-11e4-b1a4-005056827e52'))
                        
                        results = result.all()#first()
                        # go through all results for current document
                        print(f"All results: ")
                        processed_results_list = []
                        for r in results:
                            renamed_result = map_result_names(r)
                            score = score_result(renamed_result)
                            processed_results_list.append([renamed_result,score])
                            print(r)
                            print(map_result_names(r))
                            print("\n")
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

                        print("Most complete data")
                        print(best_result)
                        # insert into weaviate the new record
                        insert_to_weaviate(best_result, doc.uuid)

            else:  # JSON format
                documents_json = []
                for doc in documents:
                    documents_json.append({
                        "uuid": str(doc.uuid),
                        "properties": doc.properties
                    })
                
                json_output = json.dumps(documents_json, indent=2, ensure_ascii=False)
                
                if args.output_file:
                    output_lines.append(json_output)
                else:
                    print(json_output)
            
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

#(semant) C:\Users\marti\Music\semANT_public\semant-demo\weaviate_utils>python sql.py
#(UUID('f93beaf0-7807-11dc-a047-000d606f5dc6'), 'nkp', UUID('110df4e0-7801-11dc-908d-000d606f5dc6'), 'nkp', True, 27, 'periodicalitem', None, '11.8.1866', '29', datetime.datetime(1866, 8, 11, 0, 0), None, None, '/mnt/matylda0/ihradis/digiknihovna_public/nkp/c8ee2480-769f-11dc-bd8b-000d606f5dc6.mods/f93beaf0-7807-11dc-a047-000d606f5dc6.mods', None, {'Title': [[], ['Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.'], ['Nikolsburger Wochenschrift für la ... (90 characters truncated) ... zxx'], ['zxx']], 'Publisher': [[], [], ['Johan Bezdieka']], 'DateIssued': [['11.8.1866'], ['1866'], ['1860-1878']], 'PartNumber': [['29'], ['7'], []]}, 'Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.. 29', None, datetime.datetime(2025, 11, 26, 16, 58, 17, 580905), datetime.datetime(2025, 11, 26, 16, 58, 17, 580905))
#nkp
#{'title_main': 'Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.. 29', 'title': [[], ['Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.'], ['Nikolsburger Wochenschrift für landwirtschaftliche, gemeinnützige Interessen und Unterhaltung.']], 'subtitle': None, 'partNumber': [['29'], ['7'], []], 'partName': None, 'dateIssued': [['11.8.1866'], ['1866'], ['1860-1878']], 'yearIssued': [['11.8.1866'], ['1866'], ['1860-1878']], 'author': None, 'publisher': [[], [], ['Johan Bezdieka']], 'language': [['zxx'], ['zxx'], ['zxx']], 'url': UUID('f93beaf0-7807-11dc-a047-000d606f5dc6'), 'public': True, 'documentType': 'periodicalitem', 'placeOfPublication': None, 'SeriesName': None, 'SeriesNumber': None, 'Edition': None, 'ManufacturePublisher': None, 'ManufacturePlaceTerm': None, 'Illustrator': None, 'Translator': None, 'Editor': None, 'Redaktor': None}