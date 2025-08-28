import logging
import weaviate
from time import time
from weaviate import use_async_with_custom, WeaviateAsyncClient
from weaviate.classes.query import Filter
from semant_demo import schemas
from semant_demo.config import Config
from semant_demo.gemma_embedding import get_query_embedding
from weaviate.classes.query import QueryReference
import weaviate.collections.classes.internal
from weaviate.collections.classes.filters import Filter
from uuid import UUID
from .ollama_proxy import OllamaProxy
from .config import config
import asyncio

from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama.llms import OllamaLLM
from langchain_core.documents import Document
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import Runnable

from langchain_core.prompt_values import PromptValue
from langchain_core.messages import BaseMessage

import logging
import re
import json

class OllamaProxyRunnable(Runnable):
    def __init__(self, proxy, model_name):
        self.proxy = proxy
        self.model_name = model_name

    async def ainvoke(self, input, config=None):
        # Handle PromptValue (e.g. from ChatPromptTemplate)
        if isinstance(input, PromptValue):
            input = input.to_string()

        # Handle list of messages
        elif isinstance(input, list) and all(isinstance(m, BaseMessage) for m in input):
            input = "\n".join([m.content for m in input])

        # Now input is guaranteed to be a string
        response = await self.proxy.call_ollama(self.model_name, input)
        return response

    def invoke(self, input, config=None):
        return asyncio.run(self.ainvoke(input, config))

class WeaviateSearch:
    def __init__(self, client: WeaviateAsyncClient):
        self.client = client
        self.ollama_proxy = OllamaProxy(config.OLLAMA_URLS)
        self.ollama_model = config.OLLAMA_MODEL
        # collections.get() is synchronous, no await needed
        self.chunk_col = self.client.collections.get("Chunks")
        self.title_prompt = "Generate a title in Czech from the following text: \"{text}\" \n " \
                "The title should be relevant for this search query: \"{query}\" \n" \
                "If the the text is not relavant, write \"N/A\" \n"
        self.summary_prompt = "Generate a sort summary in Czech from the following text: \"{text}\" \n " \
                "The summary should be in a list of concise facts extracted from the text which are relevant for this search query: \"{query}\""           
        self.tag_template = "You are given a document, decide whether tag \"{tag_name}\" belongs to the document. \n " \
                "The tag's definition is: \"{tag_definition}\". \n " \
                "Here are examples of texts belonging to the tag: {tag_examples}. \n " \
                "Output Ano if the tag belongs or Ne if it does not belong to the document, do not output anything else. \n " \
                "Be benevolent and output True if there is some connection between tag and the text of the document. \n " \
                "Document: \n " \
                "{content}"
                #"Do not output any explanation just True or False. \n " \
                #"Consider meaning of the tag. \n " \
                #"Ignore exact punctuation or minor wording differences. Decide based on the meaning of the tag. \n " \
        
#"Do not tag document when tag is not associated with it, but tag document if the tag is associated with the content. \n " \

    @classmethod
    async def create(cls, config:Config) -> "WeaviateSearch":
        # Instantiate async client with custom params
        async_client = weaviate.use_async_with_custom(
            http_host=config.WEAVIATE_HOST, http_port=config.WEAVIATE_REST_PORT, http_secure=False,
            grpc_host=config.WEAVIATE_HOST, grpc_port=config.WEAVIATE_GRPC_PORT, grpc_secure=False,
        )
        # Connect and verify readiness
        await async_client.connect()  # :contentReference[oaicite:0]{index=0}
        if not await async_client.is_ready():  # :contentReference[oaicite:1]{index=1}
            logging.error("Weaviate is not ready.")
            await async_client.close()
            exit(-1)
        return cls(async_client)

    async def close(self):
        await self.client.close()  # :contentReference[oaicite:2]{index=2}

    async def _process_with_llm(self, search_results: list[schemas.TextChunkWithDocument], search_request: schemas.SearchRequest) -> list[schemas.TextChunkWithDocument]:

        title_prompt_template = search_request.search_title_prompt if search_request.search_title_prompt else self.title_prompt
        summary_prompt_template = search_request.search_summary_prompt if search_request.search_summary_prompt else self.summary_prompt

        if search_request.search_title_generate:
            title_responses = [self.ollama_proxy.call_ollama(
                self.ollama_model,
                title_prompt_template.format(text=chunk.text, query=search_request.query)
            ) for chunk in search_results]
            title_responses = await asyncio.gather(*title_responses)
            for search_result, generated_title in zip(search_results, title_responses):
                search_result.query_title = generated_title

        if search_request.search_summary_generate:
            summary_responses = [self.ollama_proxy.call_ollama(
                self.ollama_model,
                summary_prompt_template.format(text=chunk.text, query=search_request.query)
            ) for chunk in search_results]
            summary_responses = await asyncio.gather(*summary_responses)
            for search_result, generated_summary in zip(search_results, summary_responses):
                search_result.query_summary = generated_summary

        return search_results
  

    async def search(self, search_request: schemas.SearchRequest) -> schemas.SearchResponse:
        # Build filters
        filters = []
        if search_request.min_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").greater_than(search_request.min_year)
            )
        if search_request.max_year:
            filters.append(
                Filter.by_ref(link_on="document").by_property("yearIssued").less_than(search_request.max_year)
            )
        if search_request.language:
            filters.append(Filter.by_property("language").equal(search_request.language))

        # Combine with AND logic
        combined_filter = None
        if filters:
            combined_filter = filters[0]
            for f in filters[1:]:
                combined_filter &= f

        t1 = time()
        if search_request.type == schemas.SearchType.hybrid:
            q_vector = await get_query_embedding(search_request.query)

            # Execute hybrid search
            result = await self.chunk_col.query.hybrid(
                query=search_request.query,
                alpha=1,
                vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=None)
            )
        elif search_request.type == schemas.SearchType.text:
            # Execute text search
            print("HERE in text search")
            result = await self.chunk_col.query.bm25(
                query=search_request.query,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=None)
            )
        elif search_request.type == schemas.SearchType.vector:
            q_vector = await get_query_embedding(search_request.query)
            result = await self.chunk_col.query.near_vector(
                near_vector=q_vector,
                limit=search_request.limit,
                filters=combined_filter,
                return_references=QueryReference(link_on="document", return_properties=None)
            )
        else:
            raise ValueError(f"Unknown search type: {search_request.type}")

        print("RESULT is:")
        print(result)

        search_time = time() - t1

        # Parse results
        results: list[schemas.TextChunkWithDocument] = []
        log_entry = (
            f"Top {len(result.objects)} results for “{search_request.query}”. "
            f"Retrieved in {search_time:.2f} seconds:"
        )
        logging.info(log_entry)
        for obj in result.objects:
            chunk_data = obj.properties
            doc_objs = obj.references.get("document").objects
            if not doc_objs:
                continue
            first_doc = doc_objs[0]
            if "library" not in first_doc.properties or not first_doc.properties["library"]:
                first_doc.properties["library"] = "mzk"
            document_obj = schemas.Document(
                id=first_doc.uuid,
                **first_doc.properties,
            )
            
            chunk = schemas.TextChunkWithDocument(
                id=obj.uuid,
                **chunk_data,
                document_object=document_obj,
                document=first_doc.uuid
            )
            print(chunk)
            chunk.text = chunk.text.replace("-\n", "").replace("\n", " ")
            results.append(chunk)

        # Process with LLM if needed
        if search_request.search_title_generate or search_request.search_summary_generate:
            results = await self._process_with_llm(results, search_request)

        response = schemas.SearchResponse(
            results=results,
            search_request=search_request,
            time_spent=search_time,
            search_log=[log_entry]
        )
        logging.info(f'Response created in {time() - t1:.2f} seconds')
        return response

    async def add_or_get_tag(self, tag_request: schemas.TagReqTemplate) -> str:
        """
        Create a new tag or return existing tag UUID if it matches
        """
        logging.info("In the add or get tag")
        try:
            tag_collection = self.client.collections.get("Tag")
        except Exception:
            # collection does not exist so create it
            tag_collection = await self.client.collections.create(
                name="Tag",
                properties=[
                    {"name": "tag_name", "dataType": "string"},
                    {"name": "tag_shorthand", "dataType": "string"},
                    {"name": "tag_color", "dataType": "string"},
                    {"name": "tag_pictogram", "dataType": "string"},
                    {"name": "tag_definition", "dataType": "string"},
                    {"name": "tag_examples", "dataType": "string"},
                ]
            )
        
        # check if tag with same properties already exists
        filters =(
            Filter.by_property("tag_name").equal(tag_request.tag_name) &
            Filter.by_property("tag_shorthand").equal(tag_request.tag_shorthand)&
            Filter.by_property("tag_color").equal(tag_request.tag_color)
        )
        results = await self.client.collections.get("Tag").query.fetch_objects(
            filters=filters
        )
        existing_tags = results.objects
        
        # check for exact match
        for existing_tag in existing_tags:
            if (existing_tag.properties["tag_name"] == tag_request.tag_name and
                existing_tag.properties["tag_shorthand"] == tag_request.tag_shorthand and
                existing_tag.properties["tag_color"] == tag_request.tag_color and
                existing_tag.properties["tag_pictogram"] == tag_request.tag_pictogram):
                return existing_tag.uuid  # return existing tag UUID
        
        # if no exact match found then create new tag
        new_tag_uuid = await self.client.collections.get("Tag").data.insert(
            properties={
                "tag_name": tag_request.tag_name,
                "tag_shorthand": tag_request.tag_shorthand,
                "tag_color": tag_request.tag_color,
                "tag_pictogram": tag_request.tag_pictogram,
                "tag_definition": tag_request.tag_definition,
                "tag_examples": tag_request.tag_examples
            }
        )
        return new_tag_uuid  
         

    async def tag(self, tag_request: schemas.TagReqTemplate) -> schemas.TagResponse:
        # tags chunks
        try:

            prompt = ChatPromptTemplate.from_template(self.tag_template)
            model = OllamaProxyRunnable(self.ollama_proxy, self.ollama_model)
            chain = prompt | model

            # get the collection
            collection_name = tag_request.collection_name
            weaviate_objects = self.client.collections.get(collection_name)
            
            # query weaviate db for chunks of chosen collection
            query = weaviate_objects.query.fetch_objects(
                return_properties=["text"],  # only return the text field
            )
            results = await query

            # extract text field from each object
            texts = [obj.properties["text"] for obj in results.objects]

            # process with llm and decide if tag belongs to text 
            tags = await chain.abatch([{"tag_name": tag_request.tag_name, "tag_definition": tag_request.tag_definition, "tag_examples": tag_request.tag_examples, "content": text} for text in texts])
            
            # store in weaviate (upload positive tag instances to weaviate)
            positive_responses = re.compile("^(True|Ano|Áno)", re.IGNORECASE)
            
            # check if there are any positive repsonses
            positive = any(positive_responses.search(t) for t in tags)
            if positive:
                tag_uuid = await self.add_or_get_tag(tag_request)
                logging.info("Got past add new object")
                for idx, obj in enumerate(results.objects):
                    if positive_responses.search(tags[idx]): # if the llm response is positive then store the tag data
                        # add the new tag data
                        await weaviate_objects.data.reference_add(
                            from_uuid = obj.uuid,
                            from_property="hasTags",
                            to=tag_uuid
                        )
                        """
                        await weaviate_objects.data.reference.add(
                            from_uuid = obj.uuid,
                            from_property_name="hasTags",
                            to_uuid = tag_uuid,
                            to_class_name = "Tag",)
                        """
                """
                            properties = {
                                "tag": {"tag_name": tag_request.tag_name, "tag_definition": tag_request.tag_definition, "tag_examples": tag_request.tag_examples, "content": obj.properties["text"]}, # TODO remove , "content": obj.properties["text"]
                            }
                """
                
                cfg = await self.client.collections.get("Chunks").config.get()
                logging.info(f"Chunk refs: {[r.name for r in cfg.references]}")

                # check stored TODO remove this part
                from weaviate.classes.query import QueryReference

                # check stored
                weaviate_objects_test = self.client.collections.get(collection_name)

                test_results = await weaviate_objects_test.query.fetch_objects(
                    return_properties=["text"],
                    return_references=QueryReference(
                        link_on="hasTags",
                        return_properties=["tag_name", "tag_shorthand", "tag_color", "tag_pictogram", "tag_definition", "tag_examples"]
                    ),
                    limit=100,
                )

                for obj in test_results.objects:
                    logging.info(f"Chunk {obj.uuid} | text: {obj.properties.get('text','')[:80]}...")

                    # references come under obj.references, not properties
                    tags_ref = obj.references.get("hasTags") if obj.references else None
                    if tags_ref and getattr(tags_ref, "objects", None):
                        for tag_obj in tags_ref.objects:
                            logging.info(
                                f"Tag {tag_obj.uuid} | "
                                f"name={tag_obj.properties.get('tag_name')} | "
                                f"short={tag_obj.properties.get('tag_shorthand')} | "
                                f"color={tag_obj.properties.get('tag_color')} | "
                                f"pic={tag_obj.properties.get('tag_pictogram')} | "
                                f"def={tag_obj.properties.get('tag_definition')} | "
                                f"examples={str(tag_obj.properties.get('tag_examples'))}"
                            )
                    else:
                        logging.info("No tags found")
                """
                weaviate_objects_test = self.client.collections.get(collection_name)
                query_test = weaviate_objects_test.query.fetch_objects()
                test_results = await query_test
                for obj in test_results.objects:
                    logging.info(f"Objects: {obj.uuid}, orig_text {obj.properties["text"]}")
                    logging.info(f"Properties: {obj.properties}")
                    # Check if hasTags reference exists and handle it properly
                    try:
                        
                        for ref in obj.references["hasTags"]:
                                logging.info(f"Tag ref: {ref.uuid}, properties: {ref.properties}")
                    except Exception as e:
                        logging.info(f"No tags found, {e}")
                """
            return {'texts': texts, 'tags': tags}
            
        except Exception as e:
            print(f"Error fetching texts from collection {collection_name}: {e}")
            return []


"""
        test: INFO:root:Objects: 038b29a5-776d-4865-9891-df3f2576e8ea, orig_text Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce. tag: {'tag_name': 'Prezident', 'tag_definition': 'Hlava statu', 'content': 'Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'tag_examples': ['EU Cesko']}
INFO:root:Objects: 0afae9a3-9226-4bae-a3ea-43e6bf05724a, orig_text Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách. tag: None
INFO:root:Objects: 0b8d98fa-749c-4e73-87c9-ddb9e49a830b, orig_text V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě. tag: {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'tag_name': 'Prezident'}
INFO:root:Objects: 453b0a91-07c1-485e-8ed7-a163747e4ea5, orig_text Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor's European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier.. tag: {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', 'tag_name': 'Prezident'}
INFO:root:Objects: 787683f5-4378-4aa2-bf98-89856fc7f839, orig_text "Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista. tag: {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'tag_name': 'Prezident'}
INFO:root:Objects: fc65adff-b1b8-4310-80a0-c93d819bef53, orig_text Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace.. tag: None
Is ok compared:
Results:
1. Ano : Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.
2. Ne : Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.
3. True : V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.
4. Ano : Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor's European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..
5. Ano : "Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.
6. Ne : Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..

        try:
            # Get the collection
            collection_name = "Chunks"
            collection = self.client.collections.get(collection_name)
            
            # Query with filters (if provided)
            query = collection.query.fetch_objects(
                limit=limit,
                return_properties=["text"],  # Only return the "text" field
                # Add filters if provided
                filters=additional_filters if additional_filters else None,
            )
            
            results = await query
            
            # Extract the 'text' field from each object
            texts = [obj.properties["text"] for obj in results.objects]
            return texts
            
        except Exception as e:
            print(f"Error fetching texts from collection {collection_name}: {e}")
            return []
        
        str(self.chunk_col)
        return {'texts': ['test', 'test1'], 'tags': ['tagtest', 'teg_test2']}

INFO:root:Got past add new object
INFO:httpx:HTTP Request: POST http://localhost:8080/v1/objects/Chunks/0b8d98fa-749c-4e73-87c9-ddb9e49a830b/references/hasTags "HTTP/1.1 200 OK"
INFO:httpx:HTTP Request: GET http://localhost:8080/v1/schema/Chunks "HTTP/1.1 200 OK"
INFO:root:Chunk refs: ['document', 'hasTags']
INFO:root:Objects: 038b29a5-776d-4865-9891-df3f2576e8ea, orig_text Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.
INFO:root:Properties: {'text': 'Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'tag': {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'tag_name': 'Prezident'}, 'to_page': '2', 'from_page': '1', 'start_page_id': '87615e80-7370-43a6-832d-ed5970170327'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 0afae9a3-9226-4bae-a3ea-43e6bf05724a, orig_text Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.
INFO:root:Properties: {'text': 'Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.', 'tag': None, 'to_page': '3', 'from_page': '2', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 0b8d98fa-749c-4e73-87c9-ddb9e49a830b, orig_text V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.
INFO:root:Properties: {'text': 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'tag': {'tag_examples': ['EU Cesko'], 'tag_definition': 'Hlava statu', 'content': 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'tag_name': 'Prezident'}, 'to_page': '2', 'from_page': '1', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 453b0a91-07c1-485e-8ed7-a163747e4ea5, orig_text Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor's European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..
INFO:root:Properties: {'text': 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', 'tag': {'tag_examples': ['Beneš, prezident, je v EU'], 'tag_pictogram': 'key', 'tag_shorthand': 'cz', 'tag_color': '#03a9f4', 'tag_definition': 'Stát, krajina kde žijou lidi', 'content': 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', 'tag_name': 'Cesko'}, 'to_page': '5', 'from_page': '4', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: 787683f5-4378-4aa2-bf98-89856fc7f839, orig_text "Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.
INFO:root:Properties: {'text': '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'tag': {'tag_name': 'Cesko', 'tag_pictogram': 'key', 'tag_shorthand': 'cz', 'tag_color': '#03a9f4', 'tag_definition': 'Stát, krajina kde žijou lidi', 'content': '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'tag_examples': ['Beneš, prezident, je v EU']}, 'to_page': '4', 'from_page': '3', 'start_page_id': '5263d30b-12bc-404a-86e3-077a58023d76'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Objects: fc65adff-b1b8-4310-80a0-c93d819bef53, orig_text Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..
INFO:root:Properties: {'text': 'Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..', 'tag': None, 'to_page': '3', 'from_page': '2', 'start_page_id': '87615e80-7370-43a6-832d-ed5970170327'}
INFO:root:No tags found, 'NoneType' object is not subscriptable
INFO:root:Task finished. Response: {'texts': ['Jak informuje náš washingtonský zpravodaj Miroslav Konvalina, Bush v rozhlase uvedl: "V nutnosti odzbrojit Irák jsou Spojené Státy zajedno a Kongres je v této otázce zajedno. Amerika mluví jedním hlasem. Irák musí odzbrojit a podřídit se všem rezolucím OSN, nebo k tomu bude donucen". I přesto, že prezident Bush považuje Irák za naprostou prioritu, řada politických vůdců ve Spojených Státech opakovaně upozorňuje, že na domácím poli by měl Bush svést důležitější bitvy, zejména se stagnující ekonomikou. Demokraté chtějí v následujících dnech před listopadovými kongresovými volbami ostře vystoupit proti republikánskému řízení hospodářství. Demokraté také chtějí svolat ekonomické fórum a vyzvali Bushovi poradce, aby odstoupili. Prezident Bush dává v ekonomice přednost smířlivějšímu tónu a vyzval demokratickou opozici v Kongresu, aby se republikány sjednotila kolem hospodářství tak, jak se to podařilo v případě Irácké rezoluce.', 'Václav Havel: Nepleťte si ekonomiku s účetnictvím Na druhý den byl ve Smetanově síni avizován projev exprezidenta a dramatika Václava Havla. Poselstvím a hlavním tématem jeho slov byla schopnost mladých perspektivních manažerů umění rozlišit zisk spočitatelný od nespočitatelného, ono kulturní dědictví či ztráty, jež nelze vyčíslil v účetního tabulkách.', 'V obsáhlé řeči, ve které se opíral o témata Praha, globalizace, konkurence post sovětských zemí v EU, uvedl, že management budoucnosti by neměl stavět své pilíře na agresivních jedincích a na Darwinově teorii Boje druhů. Běžnému zaměstnanci by se neměl utahovat opasek ve prospěch manažerů. "Je nutné trvale kultivovat lidský kapitál," vyslal jako poselství Jiří Paroubek mladým elitám současnosti. V pondělí na závěr prvního bloku zaujal svým energickým a vyčerpávajícím projevem publicista a spolupředseda poslanecké skupiny Evropského parlamentu a člen komise Evropského parlamentu Daniel Cohn-Bendit. Takřka hodinu mluvil o historickém pozadí Evropy, kterou přirovnával ke krásné bytosti, které se chtějí všichni dotknout, ale zároveň se bojí k ní přiblížit. Do prostoru vznesl i zásadní otázku:"Proč potřebujeme Evropu. Potřebujeme ji vůbec?!" Přemýšlel nad problémem národních identit, nad tím, že žádný stát v Evropě by neměl být víc a že národnost konec konců znamená právě ty pomyslné hranice v Evropě.', 'Věřím ve vás, v mladší generaci, která se bude dívat dál do budoucna, za úzký soudobý horizont." Na Successor\'s European Youth Summit 2006 se sešlo se takřka 400 mladých manažerů z celého světa. Účastníci summitu zastávají v mladém věku významné posty v oblasti obchodu, vědy, výzkumu či umění. V Obecním době na panelových diskuzích debatovali o globalizace, nových teoriích růstu, světové bídě i Evropské unii. Panely vedly osobnosti z tuzemské manažerské špičky: generální ředitel Czechinvest Tomáš Hruda, hlavní ekonom Raiffeisen Bank, člen představenstva Škoda Auto Martin Jahn, bývalý ministr financí Pavel Mertlík, poradce premiéra ČR Valtr Komárek či viceprezident společnosti Microsoft pro Evropu, Blízký východ a Afriku Jan Mühlfeit nebo před velkým sálem promluvili i bývalý československý ministr zahraničních věcí Jiří Dienstbier..', '"Přestat si plést ekonomiku s účetnictvím - to by měl být cíl mladých perspektivních manažerů, kteří budou již brzo řídit hospodářství svých zemí," uvedl mírně skepticky exprezident Václav Havel a dodal, "existuje bezpočet zisků, které nelze žádným sebelepším účetním systémem zjistit, a je i mnoho ztrát, které nelze tímto způsobem zjistit." Města halí postmoderní nic, řekl Havel Havel se zamýšlel i nad konzumní propastí, do které se dostávají lidé a jejich města: "Česká a moravská města obklíčily zvláštní zóny, kde jsou rozcapené jakési veliké jednopodlažní tovární haly, další chrámy konzumu - supermarkety, podivná sídliště, která si hrají na vilky, ale ve skutečnosti jsou anonymní. Jsou zde ohromné skladovací plochy, ohromná parkoviště a mezitím step, step a step. Dohromady to nenazvete ničím Není to pole, ani louka ani les, ani vesnice, ani město. Je to jakési postmoderní nic." Přestože jeho projev měl pesimistickou a posmutnělou dikcí, na závěr tomuto Havel opanoval:"Jsem optimista.', 'Bush požádal zákonodárce o rychlé odhlasování několika ekonomických zákonů, například krytí teroristických hrozeb pojišťovnami. Neexistence této legislativy podle něho zbrzdila nebo znemožnila přes 15 miliard transakcí s nemovitostmi a ve druhém plánu to vedlo ke ztrátě více než 300.000 pracovních příležitostí. Průzkumy veřejného mínění ukazují, že Američané se zajímají více o ekonomiku než o případnou intervenci jejich armády proti Iráku. O Iráku začne otevřeně diskutovat ve středu Rada bezpečnosti OSN. V tomto typu debaty tak budou moci sdělit své stanovisko zástupci všech členských zemí Světové organizace..'], 'tags': ['Ne', 'Ne', 'Ano', 'Ne.', 'Ne', 'Ne']}
INFO:root:Updated ok
"""