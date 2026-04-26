# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - text mode / slohový postup
- Characterize the communicative mode of `Text to be classified`.
- Choose only from the classes below.
- Choose one primary class that best describes the dominant communicative function of the classified passage.
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
- `rhetorics` / `řečnický` — seeks to influence, persuade, impress, or emotionally move an audience through direct address and rhetorical devices
- `other_mode` — recognizable communicative mode not covered by the available classes. Use if the passage has a clear dominant communicative mode not covered by the listed  classes.
- `uncertain` — communicative mode cannot be determined reliably from the passage. Use if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON list of one or two class labels without any additional text or explanation.

Output example 1: ["exposition"]
Output example 2: ["record", "description"]

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
