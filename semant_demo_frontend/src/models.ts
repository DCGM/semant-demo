// Raw (snake_case) wire types for code that calls the backend through axios instead of the
// generated client (src/generated/api, camelCase): the search page and the user store. They
// mirror the backend models of the same name (features/search/schemas.py,
// schema/documents.py, users/schemas.py). Use the generated types when a caller moves to the
// generated client; do not add types here for endpoints it already serves.

export interface User {
  id: string; // UUID as string
  email: string;
  username: string | null;
  name: string | null;
  institution: string | null;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

export interface SearchFilterInput {
  id: string;
  min_value?: number | null;
  max_value?: number | null;
  values?: string[] | null;
}

export interface NominalValue {
  user_form: string;
  backend_form: string;
}

export interface SearchFilter {
  id: string;
  type: 'interval' | 'nominal';
  description: string;
  target_property: string;
  min_value?: number | null;
  max_value?: number | null;
  values?: NominalValue[] | null;
}

export interface SearchFiltersResponse {
  filters: SearchFilter[];
}

export interface SearchRequest {
  query: string;
  limit?: number;
  user_collection_id: string | null;
  search_title_generate?: boolean;
  search_summary_generate?: boolean;
  search_results_summary_generate?: boolean;
  type?: 'hybrid' | 'text' | 'vector';
  hybrid_search_alpha?: number;
  filters?: SearchFilterInput[] | null;
  min_year?: number | null;
  max_year?: number | null;
  min_date?: string | null; // ISO datetime string
  max_date?: string | null; // ISO datetime string
  language?: string | null;
  tag_uuids: string[] | null;
  positive: boolean;
  automatic: boolean;
}

export interface Document {
  id: string; // UUID as string
  library?: string | null; // filled in ("mzk") for search hits
  title?: string | null;
  subtitle?: string | null;
  partNumber?: number | string | null;
  partName?: string | null;
  yearIssued?: number | null;
  dateIssued?: string | null; // ISO datetime string
  author?: string[] | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  url?: string | null;
  public?: boolean | null;
  documentType?: string | null;
  keywords?: string[] | null;
  genre?: string | null;
  placeTerm?: string | null;
  placeOfPublication?: string | null;
  editors?: string[] | null;
  seriesName?: string | null;
  edition?: string | null;
  illustrators?: string[] | null;
  translators?: string[] | null;
  redaktors?: string[] | null;
  seriesNumber?: string | null;
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

// Search hit; text is display text (hyphenated line breaks joined), not canonical text.
export interface TextChunkWithDocument extends TextChunk {
  summary?: string | null;
  document_object: Document;
  query_title: string | null;
  query_summary: string | null;
}

export interface SearchResponse {
  results: TextChunkWithDocument[];
  search_request: SearchRequest;
  time_spent: number;
  search_log: string[];
  // Problems that did not prevent the results, e.g. failed optional summaries.
  warnings?: string[];
}

export interface SummaryResponse {
  summary: string;
  time_spent: number;
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
}

export interface ExtendedAnnotationClass {
  short: string
  colorString: string
  textColor: string
  approved: ApprovedState
}
