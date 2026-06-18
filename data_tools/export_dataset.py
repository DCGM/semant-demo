import json
import os
import argparse
import tqdm
from glob import glob


def parse_arguments():
    parser = argparse.ArgumentParser(description= \
    "Take a prompt (file `{attribuge_name}.ext`) and read jsonl files from a directory with LLM processing results "
    "and create jsonl file with messages for SFT training." \
    "The objects in the input jsonl files should have the following attributes `.text`, `.{attribuge_name}.classes`" ) 
    parser.add_argument("--input-dir", type=str, required=True, help="Directory containing the input dataset.")
    parser.add_argument("--prompt-file", type=str, required=True, help="Path to the prompt file.")
    parser.add_argument("--output-file", type=str, required=True, help="Path to the output JSONL file")
    return parser.parse_args()


def main():
    args = parse_arguments()

    with open(args.prompt_file, "r") as f:
        prompt_template = f.read()

    attribuge_name = os.path.splitext(os.path.basename(args.prompt_file))[0]

    output_data = []
    for filename in glob(os.path.join(args.input_dir, "*.jsonl")):
        with open(filename, "r", encoding="utf-8") as f:
            for line in tqdm.tqdm(f, desc=f"Processing {filename}"):
                try:
                    data = json.loads(line)
                    text = data["text"]
                    if "classes" in data[attribuge_name]:
                        classes = data[attribuge_name]["classes"]
                    elif "class" in data[attribuge_name]:
                        classes = data[attribuge_name]["class"]
                    else:
                        print(f"Skipping line in {filename} due to missing 'classes' and 'class' keys: {line}")
                        continue
                    
                    messages = [
                        {"role": "system", "content": prompt_template},
                        {"role": "user", "content": text},
                        {"role": "assistant", "content": json.dumps(classes)}
                    ]
                    output_data.append({"messages": messages})
                except json.JSONDecodeError:
                    print(f"Skipping invalid JSON line in {filename}: {line}")
                except KeyError as e:
                    print(f"Missing expected key {e} in {filename}: {line}")

    with open(args.output_file, "w", encoding="utf-8") as f:
        for item in tqdm.tqdm(output_data, desc="Writing output file"):
            json.dump(item, f, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()