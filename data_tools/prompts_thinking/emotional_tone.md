# Task context
You are annotating digitized library texts for filtering in a search interface of a public web portal.

# Task - emotional tone
- Characterize the dominant emotional tone of `Text to be classified`.
- Choose one primary class that best describes the dominant affective coloring of the classified passage.
- Optionally choose a second class only if a second emotional tone is clearly and substantially present in the classified passage.
- Use the provided `Context` only for better understanding, but assign classes relevant only to `Text to be classified`.
- Focus on the affective register and emotional coloring of the language, not on rhetorical stance, communicative mode, or topic.

# Classes
- `neutral_or_detached` — emotionally unmarked, matter-of-fact, or affectively flat presentation
- `solemn_or_grave` — serious, weighty, restrained, dignified, or gravely measured tone
- `celebratory_or_triumphant` — festive, exultant, joyful, or triumphant tone
- `anxious_or_alarmed` — worried, fearful, urgent, apprehensive, or alarmed tone
- `mournful_or_elegiac` — sorrowful, lamenting, grief-inflected, or elegiac tone
- `indignant_or_outraged` — morally offended, angry, indignant, or righteously aggrieved tone
- `hopeful_or_aspirational` — forward-looking, optimistic, visionary, or aspirational tone
- `reverent_or_devotional` — prayerful, worshipful, reverential, or spiritually awed tone
- `ironic_or_sardonic` — detached mockery, sardonic humor, or ironic distancing from the subject
- `affectionate_or_tender` — warm, caring, intimate, or emotionally close tone
- `other_tone` — recognizable emotional tone not covered by the available classes
- `uncertain` — emotional tone cannot be determined reliably from the passage

# Preference rules
- Prefer `neutral_or_detached` when no affective coloring is clearly dominant.
- Prefer `reverent_or_devotional` over `solemn_or_grave` when the emotional register is specifically religious or spiritually awed rather than merely weighty or serious.
- Prefer `indignant_or_outraged` over `anxious_or_alarmed` when the dominant affect is moral offense rather than fear or apprehension.
- Prefer `ironic_or_sardonic` only when irony or sardonic distancing is clearly signaled in the passage, not merely implicit or possible.
- Use `other_tone` only if the passage has a recognizable emotional tone not covered by the listed classes.
- Use `uncertain` only if the text is too fragmentary, ambiguous, or corrupted for reliable classification.

# Output
Write only a JSON with reason for classification and one or two class labels without any additional text or explanation.

Output example 1: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["neutral_or_detached"]}
Output example 2: {"reason": "Clear reasoning for the classification with evidence from the text.", "classes": ["mournful_or_elegiac", "solemn_or_grave"]}

# Previous context from the document is:
{prefix_text}

# Text to be classified is:
{text}
