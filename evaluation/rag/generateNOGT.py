import os
import json

#program to generate no gt dataset in txt from .json gt dataset
input_name = "test"
base = os.path.dirname(os.path.abspath(__file__))
in_path = os.path.join(base, ("datasets/" + input_name + ".json"))
out_path = os.path.join(base, ("datasets/" + input_name + ".txt"))

def main():
    questions = []
    #read data with GT
    with open(in_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for entry in data:
            if 'question' in entry:
                questions.append(entry['question'])

    #return TXT question withou GT
    with open(out_path, 'w', encoding='utf-8') as o:
        for q in questions:
            o.write(q + '\n')

if __name__ == "__main__":
    main()