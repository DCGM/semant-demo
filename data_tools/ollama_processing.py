import json
import os
import argparse
import glob
from tqdm import tqdm
from ollama import Client
from concurrent.futures import ThreadPoolExecutor, as_completed


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read JSONL files, process each record via Ollama Python client, and store responses."
    )
    parser.add_argument(
        "--source-dir", type=str, required=True,
        help="Directory to read source JSONL files from."
    )
    parser.add_argument(
        "--target-dir", type=str, required=True,
        help="Directory to write processed JSONL files to."
    )
    parser.add_argument(
        "--server", type=str, required=True,
        help="Ollama server URL, e.g. http://localhost:11434"
    )
    parser.add_argument(
        "--model", type=str, required=True,
        help="Model name on the Ollama server"
    )
    parser.add_argument(
        "--prompt", type=str, required=True,
        help="Prompt template for the model. Can be text or a file path. Use {text} as placeholder for the record's text and {prefix_text} for the prefix if --prefix-characters is used."
    )
    parser.add_argument(
        "--response-key", type=str, default="ollama_response",
        help="Key under which to store the model's response in each JSON record"
    )
    parser.add_argument(
         "--threads", type=int, default=1,
    )
    parser.add_argument(
        "--prefix-characters", type=int, default=0,
        help="Number of characters from previous chunks to include as prefix for context (default: 0)"
    )
    parser.add_argument(
        "--skip-attribute-values", type=str, default="{}",  
        help="Skip processing of records containing any of these attribute values. Format is JSON dictionary. E.g.: '{\"language\": [\"ces\", \"eng\"]}'",
    )
    parser.add_argument(
        "--json-response", action="store_true",
        help="Whether to expect JSON responses from the model and parse them accordingly. If not set, the raw text response will be stored under response-key." 
    )
    return parser.parse_args()


def call_ollama(client: Client, model: str, prompt_template: str, json_response: bool, rec: dict) -> str | None:
    """
    Use the Ollama Python client to generate a response from the model.
    """
    text = rec.get("text", "")
    prefix_text = rec.get("prefix_text", "")
    prompt = prompt_template.format(text=text, prefix_text=prefix_text)
    try:
        response = client.generate(model=model, prompt=prompt, think=False, options={"num_predict": 512})
    except KeyboardInterrupt:
        raise KeyboardInterrupt("Ollama call interrupted by user.")
    except Exception as e:
        print(f"Error calling model {model}: {e}")
        return None

    text_response = None

    # Extract text or message content
    if isinstance(response, dict) and "choices" in response and response["choices"]:
        choice = response["choices"][0]
        # Chat-style
        if isinstance(choice, dict) and "message" in choice:
            text_response = choice["message"].get("content", None)
        # Completion-style
        elif isinstance(choice, dict) and "text" in choice:
            text_response = choice.get("text", None)
    # Fallback keys
    if text_response is None:
        for key in ("response", "result"):
            if key in response:
                text_response = response.get(key, None)
    
    if text_response is None:
        print(f"Could not extract text response from model output: {response}")
        return None
    
    if json_response:
        # We need to strip ```json ... ``` if present, because some models include that in the response when asked for JSON output
        text_response = text_response.strip("```json").strip("```").strip()

        try:
            return json.loads(text_response)
        except KeyboardInterrupt:
            raise KeyboardInterrupt("Ollama call interrupted by user.")
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response: {e}\nResponse text was: {text_response}")

    return text_response


def should_skip(rec: dict, skip_attribute_values: dict) -> bool:
    for attr, values in skip_attribute_values.items():
        if rec.get(attr) in values:
            return True
    return False


def main():
    args = parse_args()
    skip_attribute_values = json.loads(args.skip_attribute_values)
    client = Client(args.server)
    os.makedirs(args.target_dir, exist_ok=True)


    # read prompt template from file if it exists
    if os.path.isfile(args.prompt):
        with open(args.prompt, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    else:
        prompt_template = args.prompt  


    jsonl_files = glob.glob(os.path.join(args.source_dir, "*.jsonl"))
    if not jsonl_files:
        print(f"No JSONL files found in {args.source_dir}.")
        return

    for src_path in tqdm(jsonl_files, desc="Files", smoothing=0.05):
        dst_path = os.path.join(args.target_dir, os.path.basename(src_path))
        if os.path.exists(dst_path):
            tqdm.write(f"Skipping existing file: {dst_path}")
            continue
        else:
            # Create an empty target file to take possesion of it
            # when multiple processes are running on the same directory
            open(dst_path, 'a').close()

        # 1) Load all records into memory
        with open(src_path, 'r', encoding='utf-8') as infile:
            records = [json.loads(line) for line in infile]

        # Add prefix characters from previous chunks if specified
        if args.prefix_characters > 0:
            prefix = ""
            for i in range(1, len(records)):
                records[i]["prefix_text"] = str(prefix)
                prefix = prefix + ' ' + records[i-1].get("text", "")
                prefix = prefix[-args.prefix_characters:]  # Keep only the last N characters

        # 2) Dispatch Ollama calls in parallel, skipping records that match skip-attribute-values
        to_process = [rec for rec in records if not should_skip(rec, skip_attribute_values)]
        n_skipped = len(records) - len(to_process)
        if n_skipped:
            tqdm.write(f"Skipping processing of {n_skipped} records matching skip-attribute-values")

        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            future_to_rec = {
                executor.submit(
                    call_ollama,
                    client,
                    args.model,
                    prompt_template,
                    args.json_response,
                    rec
                ): rec
                for rec in to_process
            }

            # 3) Collect results as they complete, with a progress bar
            for future in tqdm(as_completed(future_to_rec),
                               desc="Records", total=len(future_to_rec), leave=False, smoothing=0.05):
                rec = future_to_rec[future]
                try:
                    result_value = future.result()
                    if result_value is None:
                        tqdm.write("No response from model for record.")
                    else:
                        rec[args.response_key] = result_value
                except KeyboardInterrupt:
                    tqdm.write("Processing interrupted by user.")
                    return
                except Exception as e:
                    print(f"Error processing record with text: {e}")

        # 4) Write out all records in original order (skipped records pass through unchanged)
        with open(dst_path, 'w', encoding='utf-8') as outfile:
            for rec in records:
                if "prefix_text" in rec:
                    del rec["prefix_text"] 
                outfile.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("Processing complete.")


if __name__ == "__main__":
    main()


