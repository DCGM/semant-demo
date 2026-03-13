templates = {"Basic": "You are given a document, decide whether tag \"{tag_name}\" belongs to the document. \n " \
                "The tag's definition is: \"{tag_definition}\". \n " \
                "Here are examples of texts belonging to the tag: {tag_examples}. \n " \
                "Output Ano if the tag belongs or Ne if it does not belong to the document, do not output anything else. \n " \
                "Be benevolent and output True if there is some connection between tag and the text of the document. \n " \
                "Document: \n " \
                "{content}",
                # more strict template:
            "Strict": "You are given a document, decide whether tag \"{tag_name}\" belongs to the document. \n " \
                "The tag's definition is: \"{tag_definition}\". \n " \
                "Here are examples of texts belonging to the tag: {tag_examples}. \n " \
                "Output Ano if the tag belongs or Ne if it does not belong to the document, do not output anything else. \n " \
                "Be benevolent and output True if there is some connection between tag and the text of the document. \n " \
                "Document: \n " \
                "{content}"
                "Do not output any explanation just True or False. \n " \
                "Consider meaning of the tag. \n " \
                "Ignore exact punctuation or minor wording differences. Decide based on the meaning of the tag. \n " \
                "Do not tag document when tag is not associated with it, but tag document if the tag is associated with the content. \n " \
            }