# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - text mode / slohový postup
- Characterize the communicative mode of `Text to be classified`.
- Choose only from the classes below.
- Choose one primary class that best describes the dominant communicative function of the classified passage.
- If multiple classes apply, prefer the most specific and dominant class.
- Optionally choose a second class only if a second communicative mode is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but select classes relevant only to `Text to be classified`.
- Focus on what the passage is doing communicatively, not on its page layout, genre, or topic.

# Classes
- `narration` / `vyprávěcí` — recounts events, actions, or happenings over time
- `description` / `popisný` — depicts persons, objects, places, situations, or qualities
- `exposition` / `výkladový` — explains facts, concepts, causes, mechanisms, or background information
- `argumentation` / `argumentační` — advances, supports, disputes, or interprets a claim or position
- `instruction` / `návodový` — tells how something should be done or what steps/rules should be followed
- `record` / `záznamový` — documents facts, entries, transactions, proceedings, or observations in a documentary or evidentiary manner
- `interaction` / `dialogický` — addresses another party in communicative exchange, such as requesting, replying, notifying, or directing
- `expression` / `expresivní` — foregrounds feeling, reflection, devotion, praise, lament, or aesthetic verbal expression
- `other_mode` — recognizable communicative mode not covered by the available classes
- `uncertain` — communicative mode cannot be determined reliably from the passage

# Preference rules
- Prefer `record` over `description` when the passage mainly documents facts in an official, archival, administrative, legal, medical, or observational way.
- Prefer `exposition` over `description` when the passage mainly explains rather than merely depicts.
- Prefer `argumentation` over `exposition` when the passage mainly defends, disputes, or interprets a position.
- Prefer `expression` over `narration` when the passage mainly conveys emotion, devotion, lament, praise, or poetic reflection rather than recounting events.
- Prefer `instruction` over `argumentation` when the passage mainly prescribes actions or rules rather than justifying them.
- Use `other_mode` only if the passage has a clear dominant communicative mode not covered by the listed classes.
- Use `uncertain` only if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON list of one or two class labels without any additional text or explanation.

Output example 1: ["exposition"]
Output example 2: ["record", "description"]

# Previous context from the document is:
{{prefix_text}}

# Text to be classified is:
{{text}}
