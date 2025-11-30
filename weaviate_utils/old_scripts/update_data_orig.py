import sys
from pathlib import Path

# add pero-ocr to path
pero_ocr_path = Path(r"C:\Users\marti\Music\semant_other\pero-ocr-master\pero-ocr-master")
if pero_ocr_path not in sys.path:
    sys.path.insert(0, str(pero_ocr_path))

import argparse
import os
import json
from pero_ocr.core.layout import PageLayout
import zipfile
from glob import glob
from uuid import uuid4
from tqdm import tqdm
from collections import defaultdict
from sqlalchemy import create_engine, select, MetaData
import logging
from multiprocessing import Pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract text from a list of PAGE XML files. Input is a list of .zip files with PAGE XML files. The script reads metadata from a database.")
    parser.add_argument("-i", "--input-file", required=True, type=str, help="Input json file.")
    parser.add_argument("--output-chunk-dir", required=True, type=str, help="Output jsonl directory.")
    parser.add_argument("--page-xml-dir", required=True, type=str, help="Directory with PAGE XML files.")
    parser.add_argument("--line-confidence", default=0.6, type=float,
                        help="Minimum line confidence to include in the chunk (default is 0.6).")
    parser.add_argument("--min-chunk-chars", default=768, type=int,
                        help="Minimum number of characters in a chunk (default is 768).")
    parser.add_argument("--max-chunk-chars", default=1152, type=int,
                        help="Maximum number of characters in a chunk (default is 1152).")
    parser.add_argument("--max-count", type=int, default=100000000,
                        help="Maximum number of documents to process (default is 100000000).")
    return parser.parse_args()


def save_jsonl(data, filename):
    to_save = {}
    to_save["id"] = data["id"]
    to_save["dateIssued"] = data["startDate"]
    for key in ["title", "subTitle", "placeTerm", "publisher", "author"]:
        if key in data:
            if data[key] == None:
                to_save[key] = None
                continue
            to_save[key] = data[key][0]
            if type(to_save[key]) == list:
                to_save[key] = to_save[key][0]

    json.dump(to_save, open(filename, "w", encoding="utf-8"), ensure_ascii=False, indent=4)


def extract_chunks(doc_id, db_pages, line_confidence,
                   min_chunk_chars=768, max_chunk_chars = 1024 + 128):
    chunks = []
    page_xml_dir = f'{doc_id}.temp'
    os.makedirs(page_xml_dir, exist_ok=True)

    try:
        empty_pages = len([p for p in db_pages if not p.page_xml_path])
        not_found = len([p for p in db_pages if p.page_xml_path == "not_found"])
        good = len([p.page_xml_path for p in db_pages if p.page_xml_path and p.page_xml_path != "not_found"])
        #print(doc_id, good, empty_pages, not_found)
        zip_file_path = [p.page_xml_path for p in db_pages if p.page_xml_path and p.page_xml_path != "not_found"][0]

        if not zip_file_path or not os.path.exists(zip_file_path):
            logging.debug(f"Page XML file {zip_file_path} does not exist.")
            return None

        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(page_xml_dir)

        for db_page in db_pages:
            layout = PageLayout()
            page_xml_file = os.path.join(page_xml_dir, f'{db_page.id}.xml')
            try:
                layout.from_pagexml(page_xml_file)
            except OSError:
                logging.debug(f"{page_xml_file} is not a valid PAGE XML file or does not exist.")
                continue

            for paragraph in layout.regions:
                # confidences = ' '.join([str(line.transcription_confidence) for line in paragraph.lines])
                # print(confidences)
                if not chunks:
                    chunks.append(
                        {"text": "", "start_page_id": str(db_page.id), "from_page": db_page.order, "order": len(chunks)})

                paragraph_lines = [line for line in paragraph.lines if
                                   line.transcription and line.transcription_confidence > line_confidence]

                while paragraph_lines:
                    paragraph_text = '\n'.join([line.transcription for line in paragraph_lines])
                    if len(paragraph_text) <= 10:
                        break

                    if len(chunks[-1]["text"]) + len(paragraph_text) > max_chunk_chars:
                        chunks[-1]["to_page"] = db_page.order
                        chunks[-1]["end_paragraph"] = False
                        chunks[-1]["text"] = chunks[-1]["text"] + '\n'
                        while len(chunks[-1]["text"]) < min_chunk_chars:
                            chunks[-1]["text"] = chunks[-1]["text"] + f'\n{paragraph_lines[0].transcription}'
                            paragraph_lines = paragraph_lines[1:]
                        chunks.append(
                            {"text": "", "start_page_id": str(db_page.id), "from_page": db_page.order, "order": len(chunks)})

                    elif len(chunks[-1]["text"]) + len(paragraph_text) > min_chunk_chars:
                        chunks[-1]["to_page"] = db_page.order
                        chunks[-1]["end_paragraph"] = True
                        chunks[-1]["text"] = f'{chunks[-1]["text"]}\n\n{paragraph_text}'
                        chunks.append(
                            {"text": "", "start_page_id": str(db_page.id), "from_page": db_page.order, "order": len(chunks)})
                        paragraph_lines = []
                    else:
                        chunks[-1]["text"] = f'{chunks[-1]["text"]}\n\n{paragraph_text}'
                        paragraph_lines = []

        if len(chunks) > 0:
            chunks[-1]["to_page"] = db_page.order
            chunks[-1]["end_paragraph"] = True

        if not chunks[-1]["text"]:
            chunks.pop()

        for chunk in chunks:
            chunk["id"] = str(uuid4())
            chunk["text"] = chunk["text"].strip()
    except Exception as e:
        #logging.error(f"Error processing document {doc_id}: {e}")
        return None
    finally:
        # delete the temporary extracted files and the directory
        for file_name in glob(os.path.join(page_xml_dir, "*.xml")):
            os.remove(file_name)
        os.rmdir(page_xml_dir)

    return chunks


class ProcessingWorker:
    def __init__(self, db_url, line_confidence, min_chunk_chars, max_chunk_chars, output_chunk_dir):
        self.db_url = db_url
        self.line_confidence = line_confidence
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self.output_chunk_dir = output_chunk_dir

        self.db_model = None
        self.db_engine = None

    def _init_db(self):
        self.db_engine = create_engine(self.db_url)
        self.db_model = MetaData()
        self.db_model.reflect(bind=self.db_engine)
        self.db_model = self.db_model.tables

    def __call__(self, request) -> dict | None:

        if self.db_model is None:
            self._init_db()

        doc_id, library_id = request
        output_chunk_file = os.path.join(self.output_chunk_dir, f"{doc_id}.jsonl")

        function_result = {
                "doc_id": doc_id,
                "library": library_id,
                "doc_missing": True,
                "chunks_extracted": False
            }

        with self.db_engine.connect() as db_connection:
            try:
                result = db_connection.execute(select(self.db_model['meta_records']).where(self.db_model['meta_records'].c.id == doc_id,
                                                                                          self.db_model['meta_records'].c.library == library_id))
            except Exception as e:
                return function_result
            result = result.fetchall()
            if not result:
                return function_result

            db_doc = result[0]
            function_result["doc_missing"] = False

            try:
                doc_id = db_doc.id
                pages_result = db_connection.execute(
                    select(self.db_model['meta_records']).where(self.db_model['meta_records'].c.parent_id == doc_id))
                db_pages = pages_result.fetchall()
                db_pages = sorted(db_pages, key=lambda p: p.order)
                page_count = len(db_pages)
                image_count = 0
                mods_count = 0
                page_xml_count = 0
                for db_page in db_pages:
                    if db_page.image_path:
                        image_count += 1
                    if db_page.mods_path:
                        mods_count += 1
                    if db_page.page_xml_path:
                        page_xml_count += 1

                chunks = extract_chunks(doc_id, db_pages, self.line_confidence,
                                        min_chunk_chars=self.min_chunk_chars, max_chunk_chars=self.max_chunk_chars)
                if chunks is None:
                    return function_result

            except Exception as e:
                logging.error(f"Error processing document {doc_id}: {e}")
                return function_result

            function_result["chunks_extracted"] = True
            with open(output_chunk_file, "w", encoding="utf-8") as f:
                for i, chunk in enumerate(chunks):
                    chunk["document"] = str(result[0].id)
                    f.write(json.dumps(chunk, ensure_ascii=False, default=str) + "\n")

            function_result["image_count"] = image_count
            function_result["mods_count"] = mods_count
            function_result["page_xml_count"] = page_xml_count
            function_result["page_count"] = page_count

            if len(chunks) > 0:
                chunk_lengths = [len(chunk["text"]) for chunk in chunks]
                chunk_sum = sum(chunk_lengths)
                chunk_count = len(chunks)
                chunk_avg = chunk_sum / chunk_count
                chunk_min = min(chunk_lengths)
                chunk_max = max(chunk_lengths)
                chunk_median = sorted(chunk_lengths)[chunk_count // 2]
                function_result["chunk_sum"] = chunk_sum
                function_result["chunk_count"] = chunk_count
                function_result["chunk_avg"] = chunk_avg
                function_result["chunk_min"] = chunk_min
                function_result["chunk_median"] = chunk_median
                function_result["chunk_max"] = chunk_max
                #print(
                #    f'{result[0].id}, {chunk_count}, {chunk_sum}, {chunk_avg:.2f}, {chunk_min}, {chunk_median}, {chunk_max}')
            else:
                function_result["chunk_sum"] = 0
                function_result["chunk_count"] = 0
                function_result["chunk_avg"] = 0.0
                function_result["chunk_min"] = 0
                function_result["chunk_median"] = 0
                function_result["chunk_max"] = 0
                #print(f'{result[0].id}, 0, 0, 0.00, 0, 0, 0')

            return function_result


_worker = None

def _init_worker(db_url, line_confidence, min_chunk_chars, max_chunk_chars, output_chunk_dir):
    # called exactly once in each worker process
    global _worker
    _worker = ProcessingWorker(db_url, line_confidence, min_chunk_chars, max_chunk_chars, output_chunk_dir)

def worker_process(doc_id):
    # called for every task in each worker, but uses the same _worker
    return _worker(doc_id)


def main():
    args = parse_args()

    DATABASE_URL = os.getenv("DATABASE_URL", None)  # Replace with your actual database URL
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")

    doc_to_process = []
    with open(args.input_file, "r", encoding="utf-8") as f:
        for line in tqdm(f, desc="Reading input file", unit="line"):
            file_path = line.strip()
            library_id = os.path.basename(file_path).split(".")[0]
            doc_id = os.path.basename(file_path).split(".")[1]
            doc_to_process.append((doc_id, library_id))


    logging.info(f"Read {len(doc_to_process)} documents from input file.")
    doc_to_process = doc_to_process[:args.max_count]

    logging.info(f"Documents to process: {len(doc_to_process)}")
    # filter already processed documents
    tmp_doc_to_process = doc_to_process
    doc_to_process = []
    for counter, (doc_id, library_id) in tqdm(list(enumerate(tmp_doc_to_process)), desc="Filtering already processed documents"):
        output_chunk_file = os.path.join(args.output_chunk_dir, f"{doc_id}.jsonl")
        if not os.path.exists(output_chunk_file):
            doc_to_process.append((doc_id, library_id))

    logging.info(f"Documents to process after filtering: {len(doc_to_process)}")

    if not doc_to_process:
        logging.info("No documents to process. Exiting.")
        return

    if not os.path.exists(args.output_chunk_dir):
        os.makedirs(args.output_chunk_dir, exist_ok=True)

    image_count = 0
    mods_count = 0
    page_xml_count = 0
    page_count = 0
    chunk_count = 0
    failed_doc_count = 0

    missing_docs = defaultdict(int)

    counter = 0
    with Pool(processes=12,
                initializer=_init_worker,
                initargs=(DATABASE_URL, args.line_confidence, args.min_chunk_chars, args.max_chunk_chars, args.output_chunk_dir)
              ) as pool:
        for result in tqdm(pool.imap(worker_process, doc_to_process), total=len(doc_to_process), desc="Processing documents"):
            if counter % 1000 == 0:
                print(f"Failed documents: {failed_doc_count} / {counter}")
                print(
                    f"page_count: {page_count}, image_count: {image_count}, mods_count: {mods_count}, page_xml_count: {page_xml_count}")

                for library, count in missing_docs.items():
                    print(f"Library {library} has {count} missing documents.")

            counter += 1

            if result["doc_missing"]:
                failed_doc_count += 1
                missing_docs[result["library"]] += 1
                continue

            if not result["chunks_extracted"]:
                failed_doc_count += 1
                continue

            doc_id = result["doc_id"]

            image_count += result["image_count"]
            mods_count += result["mods_count"]
            page_xml_count += result["page_xml_count"]
            page_count += result["page_count"]
            chunk_count += result["chunk_count"]


if __name__ == "__main__":
    main()