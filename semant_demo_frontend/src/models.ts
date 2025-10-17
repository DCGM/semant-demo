// TypeScript interfaces generated from Python Pydantic models

export interface SearchRequest {
  query: string;
  limit?: number;
  min_year?: number | null;
  max_year?: number | null;
  min_date?: string | null; // ISO datetime string
  max_date?: string | null; // ISO datetime string
  language?: string | null;
  tag_uuids?: string[] | null;
  positive: boolean;
  automatic: boolean;
}

export interface TagRequest {
  tag_name: string;
  tag_shorthand: string;
  tag_color: string;
  tag_pictogram: string;
  tag_definition: string;
  tag_examples: string[];
  collection_name: string;
}

export interface CollectionRequest {
  collection_name: string;
  user_id: string;
}

export interface TagData {
  tag_uuids: string[];
}

export interface Document {
  id: string; // UUID as string
  library: string;
  title: string;
  subtitle?: string | null;
  partNumber?: number | null;
  partName?: string | null;
  yearIssued?: number | null;
  dateIssued?: string | null; // ISO datetime string
  author?: string | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  url?: string | null;
  public?: string | null;
  documentType?: string | null;
  genre?: string | null;
  placeTerm?: string | null;
}

export interface TextChunk {
  id: string; // UUID as string
  title: string;
  text: string;
  start_page_id: string; // UUID as string
  from_page: number;
  to_page: number;
  end_paragraph: boolean;
  language?: string | null;
  document: string; // UUID as string

   ner_P?: string[] | null; // Person entities
  ner_T?: string[] | null; // Temporal entities
  ner_A?: string[] | null; // Address entities
  ner_G?: string[] | null; // Geographical entities
  ner_I?: string[] | null; // Institution entities
  ner_M?: string[] | null; // Media entities
  ner_O?: string[] | null; // Cultural artifacts

}

export interface TextChunkWithDocument extends TextChunk {
  summary?: string | null;
  document_object: Document;
  query_title: string | null;
  query_summary: string | null;
  automaticTags: TagData[];
  positiveTags: TagData[];
}

interface ChunkTagData {
  chunk_id: string;
  positive_tags_ids: string[];
  automatic_tags_ids: string[];
}

export interface SearchResponse {
  results: TextChunkWithDocument[];
  search_request: SearchRequest;
  time_spent: number;
  search_log: string[];
  tags_result: ChunkTagData[];
}

export interface SummaryResponse {
  summary: string;
  time_spent: number;
}

export interface TaggingResponse {
  texts: string[];
  tagged: string[]; // the llm response if the tag belongs to the chunk
}

export interface TagStartResponse {
  job_started: boolean;
  task_id: string;
  message: string;
}

export interface CreateResponse {
  created: boolean;
  message: string;
}

export enum TagType {
  positive = "positive",
  negative = "negative",
  automatic = "automatic",
}

export interface TaggedChunks {
    tag_uuid : string;
    text_chunk: string;
    chunk_id: string;
    chunk_collection_name: string;
}

export interface GetTaggedChunksResponse {
    chunks_with_tags : TaggedChunks[]
}

export interface TagResult {
  texts: string[];
  tags: string[];
}

export interface CancelTaskResponse {
    message: string;
    taskCanceled: boolean;
}

export interface ApproveTagResponse {
  successful: boolean;
  approved: boolean;
}

export interface RemoveTagsResponse {
  successful: boolean;
}

export interface ProcessedTagData {
  chunk_id: string;
  text: string;
  tag: string;
}

export interface TagData {
    tag_name: string           
    tag_shorthand: string          
    tag_color: string              
    tag_pictogram: string         
    tag_definition: string     
    tag_examples: string[] 
    collection_name: string
    tag_uuid: string
}

export interface GetTagsResponse {
    tags_lst: TagData[]
}

export interface StatusResponse {
  taskId: string;
  status: string;
  result: TagResult;
  all_texts_count: number;
  processed_count: number;
  tag_id: string;
  tag_processing_data: ProcessedTagData[];
}

export enum ApprovedState {
  automatic = 'automatic',
  positive = 'positive',
  negative = 'negative',
}

export interface AnnotationClass {
  short: string
  colorString: string
  textColor: string
  approved: ApprovedState
}

export interface User {
  id: string
  username: string
  full_name: string
  user_type: string
}

export interface Collection {
  id: string
  name: string
  user_id: string
}

export interface GetUserCollectionsResponse {
  collections: Collection[]
  user_id: string
}