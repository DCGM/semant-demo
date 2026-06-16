# Task context
You are processing digitized library texts which will be published in a search platform. The users of the search will be displayed titles summarizing the texts, but the text are now missing these titles.

# Task
- Read and understand the presented text.
- Generate several versions of a possible informative tilte for the presented text.
- The titles should be honets, concise and informative.
- The titles should summarize and well represent the content of the text.
- The titles should be usefull for the users to decide if the text is relevant for them and that it is worth to read them.
- Generate 5 title versions, starting from a very short and concise title (2-3 words) gradually to a longer and more informative title. The longer titles should strictly add additional information, information should not dissappear.
- Consider which title is most appropriate to be used in a search engine and select it.
- Write the titles in Czech language.

# Output
JSON object with these keys:
- `titles` - list of 5 title strings from the shortest to the longes.
- `best_title` - string of the best title

# This text precedes the the section of interest. Use this for context. The title does not need to represent this text.
{prefix_text}

# Text for which the titles should be generated. Make sure you represent the content of this text well.
{text}
