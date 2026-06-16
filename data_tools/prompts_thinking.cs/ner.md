# Task context
You are processing digitized library texts with the goal to identify named entities which could be saved in a database, disambiguated, and later used to search and navigate the vast collection of library documents, and to read records of the named entities

# Task
- Recognize all named entities in the text - that is an entity which would have, for example, have an entry in an encyclopedia.
- Classify the entity.
- Copy short context.
- Summarize information about the entity. Focus on information which could be used to identify or disambiguate the entity. The summary has to be self-contained. It must not reference the text or summaries of other entities.
- Make sure that you identify all named entitites in the text.

# Possible entity types
- `event` — named time periods or events: e.g. Big bang, WW II, 4th Anual Conference on AI, World Cup 2026, Olympics
- `being` — includes all named beigs, people, animals, fictional charaters, mithological beings, and similar
- `place` — anywhere a person can "be", e.g. adresses, buildings, streets, squares, cities, rivers, hills, mountain ranges, lakes, oceans, territories, continents, planets
- `institution` - e.g. conferences, contests, fairs, companies, cults, schools, government institutions, 
- `media` - e.g. websites, radio and TV stations, periodicals
- `artificial_artifact` - man made artifacts, e.g. games, applications, operating systems, laws, norms, directives, books, movies, products, statues, car models, 
- `group` - group of people - e.g. nationalities, religious groups, entnicities
- `sciantific_names` - e.g. specific substances, animal and plant taxonomy, theories, lemmas, diseases, drugs, therapies, algorithms, ...
- `other_entity` - any other named entities
- `date` - specific date or longer time-period: july 2026, 24.5.2025, Jurassic Period, 19th century


# What are not entities
- Do not extract rather genera  entities that are not uniquely identifiable: e.g. President of ČR, river in Asia, moon of some planet, beseda se čtením poezie
- Do not extart common names: water, H2O, carbon, iron, nafta, petrol, influensa, plague, 
- Do not extract entities which are relevant only within the document: e.g. Table 5, Chapter 4, reference 5, page 27,
- Do not extract entities where the name is rather descriptive and is not intedent as unique name. E.g. pozdní brambory, české pivo, pražská politická scéna, mladé víno

# Output
JSON list of objects representing individual named entities. Attributes are:
- `entity` - name of the entity
- `type` - one of the entity types from the list
- `all_name_variants` - list of all name variants as the entity appears in the text
- `information` - Concise, specific, and self-contained summary of the important information about the entity extracted from the text. It must be understandable by itself (self-contained). It must not add outside knowledge or context. It must not reference the original text or information outside this summary. Write it in Czech. Do not use formulations like: "je zmíněn", "je uveden" 

# Example input
Ostnákovití je čeleď ptáků z řádu Charadriiformes, mezi jejíž hlavní znaky patří dlouhé nohy s extrémně prodlouženými prsty zakončené dlouhými drápy a rohovitý osten nebo hrbolek v ohbí křídla. Ostnáci se vyskytují v mělkých stojatých močálovitých vodách tropů a subtropů Jižní Ameriky. Byli objeveni Karlem Pokorným v 19. století. Jsou nositeli proteinu Elantofanie, který jim propůjčuje výrazné červené zabarvení.


# Example output
```
[
  {
    "entity": "Ostnákovití",
    "type": "sciantific_names",
    "all_name_variants": [
      "Ostnákovití",
      "Ostnáci"
    ],
    "information": "Čeleď ptáků z řádu Charadriiformes. Mají dlouhé nohy s extrémně prodlouženými prsty, dlouhé drápy a rohovitý osten nebo hrbolek v ohbí křídla. Vyskytují se v mělkých stojatých močálovitých vodách tropů a subtropů Jižní Ameriky. Jsou červeně zbravení kvůli proteinu Elantofanie. Objeveni Karlem Pokorným v 19.století."
  },
  {
    "entity": "Charadriiformes",
    "type": "sciantific_names",    
    "all_name_variants": [
      "Charadriiformes"
    ],
    "information": "Řád ptáků z čeleďí Ostnákovití."
  },
  {
    "entity": "Jižní Amerika",
    "type": "place",
    "all_name_variants": [
      "Jižní Ameriky"
    ],
    "information": "V tropech a subtropech Jižní Ameriky se vyskytují Ostnáci."
  },
  {
    "entity": "Karel Pokorný",
    "type": "being",
    "all_name_variants": [
      "Karlem Pokorným"
    ],
    "information": "Objevitel ostnáků, žil v 19. století."
  },
  {
    "entity": "19. století",
    "type": "date",
    "all_name_variants": [
      "19. století"
    ],
    "information": "Tehdy objevil Karel Pokorný ostnáky v Jižní Americe."
  },
  {
    "entity": "Elantofanie",
    "type": "sciantific_names",
    "all_name_variants": [
      "Elantofanie"
    ],
    "information": "Protein ostnáků, propůjčující jim červené zabarvení."
  }
]
```

# This text precedes the the section of interest. Use it for context, but do not extract entities from here.
{prefix_text}

# Text to be be processed follows. Make sure you identify all named entities in this text, extract all variants and the relevant information, especialy information usefull to disambiguate the entities:
{text}
