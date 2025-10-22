# How to setup weaviate
Use weaviate with new schema. [db benchmarks](https://github.com/Martin-Toma/db_benchmarks/tree/collection-and-tag-update) in there follow `run notes.md`.

# Tagging

Tagging incorporates tag creation, creating references from text chunks to tag objects. Tagging functionality and weaviate schema is showed in [link to draw.io sequence diagrams ans schema](https://drive.google.com/file/d/1xlcM5zWyfa7aW9OCGwvnpS19TXJGAuvy/view?usp=drive_link)

## Search
In the search (`SearchPage.vue`), user can filter by tag and also add chunks to tags.

#### Filter by tag
Option to filter by tag filters the chunks by automatic, positive and automatic OR positive (searches filters out chunks with negative references to a tag). User can select which filter to use in checkboxes. In the backend the selected options are applied in form of weaviate filters. These filters are add to existing weaviate filters by AND operator.

#### Add user tag
After searching, user can add a chunk to selected tag, this will be stored as positive connection from chunk to the tag - user tag. The same `approve_tag` method as for approving existing tag is used to add tag to the chunk.

## Manage
Tag management page (`semant_demo_frontend\src\pages\TagManagementPage.vue`) serves to create new tag, to run automatic tagging task, to see the chunks with their tags and also to approve/disapprove tag associated with a chunk.

#### Create tag
For tag creation, there is a dialog window which pops up after clicking button "+ CREATE TAG".

#### Run tagging task
To run tagging task, user selects tag or multiple tags and presses "RUN TAGGING TASK". This starts a separate task for each selected tag over all chunks.

Chunks which has positive reference to the target tag are not fed to LLM anymore.

User can cancle the tagging task while it is running. The cancelation is done by canceling asyncio task. When asyncio task is created, it's name is stored in the SQL database. When user wants to cancle the task, the name is found in database, then the task is found in the running tasks and finally cancled. 

#### Show tagging results
Button GET TAGGED TEXTS reveals all chunks with associated automatic, positive or negative tags. It doesn't show chunks which were not tagged by the LLM - the negatively tagged chunks were tagged by LLM but user decided to reject the tag association to the chunk.

Each chunk is shown as the chunk text and all it's tags. The tags are visualized using badges. When user wants to approve/disapprove the tag correctness for each chunk, he uses the tag badge. When user hover over the badge it shows option X which changes reference from automatic to negative. On the other side when user clicks on the tag name, it approves the tag and changes reference from automatic to positive.

The change of tag type is done using `approve_tag` method. To describe how reference is changed I will describe a change from automatic to positive. In the background the change of reference is done by loading current references lists, remove the reference for selected tag from the local list of current (automatic) references, finally updating the current (automatic) reference list in weaviate. Then changing the local list of target (positive) referneces by adding the selected tag, finally updating the weaviate reference list with the updated local list.  

# User collections

## Collection management
For collections management there is a separated page called `TagManagementPage.vue`. Here, user can create new collections and see the chunks in the collection. However to add chunks to the collection, user needs to go to search page (`SearchPage.vue`), search database and select which chunks he wants to add to the collection.

## Search
User searches the chunks. The user can add the chunks (which are found in searching process) to the a selected collection.