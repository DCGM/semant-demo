from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM

from datasets import load_dataset

template = """Only return the matching tags as a comma-separated list (no other explanation).
Do not take into account the case sensitivity. Consider meaning of the tags. 
Carefully consider is it is suitable to tag the document with the given tag, do not tag document when tag is not associated with it.
Use exactly the following tags do not add no other tags: {tag_keys}.
Tags to check with explanation: {tags}

Document:
{content}
"""

tags_with_examples = [{"Dog": ["Dogs are friendly.", "Puppies are cute."]}, 
        {"car": ["Fast vehicle.", "I was driving home"]},
        {"ai": ["Thinking machine.", "A tool for processing data"]},
        {"Parrot": ["A bird", "Talking animal"]}]
tag_keys = [k.keys() for k in tags_with_examples]

dataset = load_dataset("sgoel9/paul_graham_essays")
#print(dataset["train"][0])

from langchain_core.documents import Document

documents = [
    Document(
        page_content=entry["text"],
        metadata={"title": entry["title"], "date": entry["date"]}
    )
    for entry in dataset["train"]
]

prompt = ChatPromptTemplate.from_template(template)
model = OllamaLLM(model="llama3.2")
chain = prompt | model

documents = documents[:2]

dummy_docs = ["Car is a vehicle.", "This is an ai which do nothing. Buggati si really fast."]

tags = chain.batch([{"tag_keys": tag_keys, "tags": tags_with_examples, "content": doc} for doc in dummy_docs])
print("Tags from 0 document:")
print(tags[0])
print("Tags from 1 document:")
print(tags[1])