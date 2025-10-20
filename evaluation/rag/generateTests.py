import os
from dotenv import load_dotenv
import random
import json
import pandas
import argparse
import glob
from typing import List

from llama_index.core import Document
from llama_index.core.evaluation import DatasetGenerator
from tqdm import tqdm
#openai
from llama_index.llms.openai import OpenAI
#ollama
from llama_index.llms.ollama import Ollama
from llama_index.core.prompts import PromptTemplate

#colors for better logs in terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'

#load .env
load_dotenv()

#function that load data from .jsonl given path
#in this case load all chunks from document
def loadDataFromJsonl (path: str) -> List[str]:
    texts = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'text' in data and data['text']:
                    texts.append(data['text'])
            except json.JSONDecodeError:
                continue 
    return texts

#"arguments"
#path to data
in_dir_path = "/mnt/ssd2/weaviate_data/all.768/chunks.vec.lang"
out_dir_path = "dataset_synthetick_gt.json"
ending = "*.jsonl"   #glob
#number of generated questions
GPTmodel = "gpt-4o"
OLLAMAmodel = "gemma3:12b"

def main():
    #parse parameters
    parser = argparse.ArgumentParser(description="Genereting questions for RAG.")
    parser.add_argument("--model",
                        type=str,
                        default="OLLAMA",
                        choices=["OLLAMA", "OPENAI"],
                        help="Evaluation models: 'OLLAMA' (server/local) or 'OPENAI' (API) ")
    parser.add_argument("--num_questions",
                    type=int,
                    default=1)
    parser.add_argument("--num_chunks_to_proc",
                    type=int,
                    default=1)
    parser.add_argument("--num_files_to_proc",
                    type=int,
                    default=1)
    
    args = parser.parse_args()
    print(f"{Colors.GREEN} Generating with model: {args.model}, number of tests to generate: {args.num_questions} from: {args.num_files_to_proc} documents, using {args.num_chunks_to_proc} chunks. {Colors.RESET} ")
    
    #TODO fix ollama generating bigger dataset
    num_questions = args.num_questions
    num_chunks_to_proc = args.num_chunks_to_proc
    num_files_to_proc = args.num_files_to_proc

    if (num_questions < num_chunks_to_proc):
        print(f"{Colors.YELLOW} Because given number of questions (num_questions) to generate is smaller then number of chunks to process (num_chunks_to_proc), program will generate: {num_chunks_to_proc} questions (num_chunks_to_proc).\n{Colors.RESET} ")
    #--- load data ---
    try:
        #get all files and select desired amount (base on input arguments)
        files = glob.glob(os.path.join(in_dir_path, ending))
        num_files_final = min(num_files_to_proc, len(files))
        selected_files = random.sample(files, num_files_final)

        #load data from selected files
        data = []
        print(f"Number of files found: {len(files)}, Number of files to process: {len(selected_files)}")
        #load data from files
        for filepath in selected_files:
            data.extend(loadDataFromJsonl(filepath))
        #gen desired amount of chunks to process
        data_reduced = random.sample(data, min(num_chunks_to_proc, len(data)))
        #get desired amout of questions to generate (per chunk)
        num_questions_per_chunk = max(round(num_questions / num_chunks_to_proc), 1)
        #convert to desired format
        documents = [Document(text=t) for t in data_reduced]

        print("----- Data loaded -----")
    except Exception as e:
        print("\nError occured while loading data, error detail:", e)

    #--- generate data ---
    if (args.model == "OPENAI"):    #OPENAI
        generator_llm = OpenAI(model=GPTmodel)
        generator = DatasetGenerator.from_documents(
            documents=documents,
            llm=generator_llm,
            num_questions_per_chunk=num_questions_per_chunk,
            show_progress=True
        )

    else:   #OLLAMA
        generator_llm = Ollama(model=OLLAMAmodel, base_url=os.getenv("OLLAMA_URL"), request_timeout = 300.0)
        #custom promts are required, otherwise ollama wil act like chatbot 
        text_question_template_str = (
            """
            Here is the context:\n {context_str}\n
            Given the context, generate ONE question that can be answered by the context. Do not generate any other text. Respond ONLY with the question. \n
            """
        )
        
        text_qa_template_str = (
            """
            Here is the context:\n
            {context_str}\n
            Here is the question: {query_str}\n
            Answer the question using ONLY the given context. Do not generate any other text. Respond ONLY with the answer.\n
            """
        )
        text_question_template_tem = PromptTemplate(text_question_template_str)
        text_qa_template_tem = PromptTemplate(text_qa_template_str)

        generator = DatasetGenerator.from_documents(
            documents=documents,
            llm=generator_llm,
            num_questions_per_chunk=num_questions_per_chunk,
            show_progress=True,
            # rewrite weird ollama prompt
            text_question_template=text_question_template_tem,
            text_qa_template=text_qa_template_tem
        )


    #generate questions and gt
    gen_out = generator.generate_dataset_from_nodes()

    #--- save data ---
    final_data = []
    for i, pair in enumerate(gen_out.qr_pairs):
        final_data.append({
            "question_id": f"gen_li_{i + 1}",
            "question": pair[0],
            "ground_truth": pair[1]
        })

    with open(out_dir_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)

    print(f"{Colors.GREEN} ----- Generating completed, saved to file: {out_dir_path} ----- {Colors.RESET}")

if __name__ == "__main__":
    main()