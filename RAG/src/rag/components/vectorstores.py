from langchain_chroma import Chroma
from langchain_weaviate import WeaviateVectorStore
import weaviate
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger


class WeaviateWrapper:   
    def __init__(self, host: str, port: int, grpc_port: int, collection_name: str, api_key: Optional[str] = None):
        self.host = host
        self.port = port
        self.grpc_port = grpc_port
        self.collection_name = collection_name
        
        # Create Weaviate client
        client_kwargs = {
            "host": host,
            "port": port,
            "grpc_port": grpc_port
        }
        
        if api_key:
            client_kwargs["auth_client_secret"] = weaviate.AuthApiKey(api_key=api_key)
        
        self._client = weaviate.connect_to_local(**client_kwargs)
        self._collection = self._client.collections.use(collection_name)
        
        logger.info(f"Weaviate connected to {host}:{port}")
    
    async def _get_async_client(self):
        """Get async Weaviate client."""
        if not hasattr(self, '_async_client'):
            # Create async client
            client_kwargs = {
                "host": self.host,
                "port": self.port,
                "grpc_port": self.grpc_port
            }
            
            if hasattr(self, '_api_key') and self._api_key:
                client_kwargs["auth_client_secret"] = weaviate.AuthApiKey(api_key=self._api_key)
            
            self._async_client = weaviate.connect_to_local(**client_kwargs)
            self._async_collection = self._async_client.collections.use(self.collection_name)
        
        return self._async_client, self._async_collection
    
    def is_ready(self) -> bool:
        """Check if Weaviate is ready."""
        return self._client.is_ready()
    
    def query(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Query Weaviate with unified interface."""
        try:
            from weaviate.classes.query import MetadataQuery
            
            # Try near_text first (if vectorizer is configured)
            try:
                response = self._collection.query.near_text(
                    query=query,
                    limit=limit,
                    return_metadata=MetadataQuery(distance=True)
                )
            except Exception as near_text_error:
                logger.warning(f"near_text failed: {near_text_error}")
                # Fallback to bm25 search if vectorizer is not configured
                logger.info("Falling back to bm25 search")
                response = self._collection.query.bm25(
                    query=query,
                    limit=limit,
                    return_metadata=MetadataQuery(score=True)
                )
            
            # Convert to unified format
            results = []
            for obj in response.objects:
                result = {
                    'text': obj.properties.get('text', ''),
                    'metadata': obj.properties.get('metadata', {}),
                    'distance': obj.metadata.distance if obj.metadata else obj.metadata.score if obj.metadata else None,
                    'source': obj.properties.get('source', ''),
                    'source_type': obj.properties.get('source_type', '')
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Weaviate query failed: {e}")
            return []
    
    def similarity_search(self, query: str, k: int = 5, **kwargs) -> List[Any]:
        """Similarity search that returns LangChain Document objects like ChromaDB."""
        try:
            from langchain.schema import Document
            from weaviate.classes.query import MetadataQuery
            
            # Try near_text first (if vectorizer is configured)
            try:
                response = self._collection.query.near_text(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(distance=True)
                )
            except Exception as near_text_error:
                logger.warning(f"near_text failed: {near_text_error}")
                # Fallback to bm25 search if vectorizer is not configured
                logger.info("Falling back to bm25 search")
                response = self._collection.query.bm25(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(score=True)
                )
            
            # Convert to LangChain Document format like ChromaDB
            documents = []
            for obj in response.objects:
                # Extract text content
                text = obj.properties.get('text', '')
                
                # Create metadata dict
                metadata = {
                    'source': obj.properties.get('source', ''),
                    'source_type': obj.properties.get('source_type', ''),
                    'distance': obj.metadata.distance if obj.metadata else obj.metadata.score if obj.metadata else None
                }
                
                # Add any additional properties as metadata
                for key, value in obj.properties.items():
                    if key not in ['text', 'source', 'source_type']:
                        metadata[key] = value
                
                # Create LangChain Document
                doc = Document(page_content=text, metadata=metadata)
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Weaviate similarity_search failed: {e}")
            return []
    
    def similarity_search_with_score(self, query: str, k: int = 5, **kwargs) -> List[tuple]:
        """Similarity search with score to match ChromaDB interface."""
        try:
            from langchain.schema import Document
            from weaviate.classes.query import MetadataQuery
            
            # Try near_text first (if vectorizer is configured)
            try:
                response = self._collection.query.near_text(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(distance=True)
                )
            except Exception as near_text_error:
                logger.warning(f"near_text failed: {near_text_error}")
                # Fallback to bm25 search if vectorizer is not configured
                logger.info("Falling back to bm25 search")
                response = self._collection.query.bm25(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(score=True)
                )
            
            # Convert to (doc, score) format like ChromaDB
            results = []
            for obj in response.objects:
                # Extract text content
                text = obj.properties.get('text', '')
                
                # Create metadata dict
                metadata = {
                    'source': obj.properties.get('source', ''),
                    'source_type': obj.properties.get('source_type', '')
                }
                
                # Add any additional properties as metadata
                for key, value in obj.properties.items():
                    if key not in ['text', 'source', 'source_type']:
                        metadata[key] = value
                
                # Create LangChain Document
                doc = Document(page_content=text, metadata=metadata)
                
                # Use distance/score as score
                score = obj.metadata.distance if obj.metadata else obj.metadata.score if obj.metadata else 0.0
                
                results.append((doc, score))
            
            return results
            
        except Exception as e:
            logger.error(f"Weaviate similarity_search_with_score failed: {e}")
            return []
    
    # Async methods using Weaviate async client
    async def aquery(self, query: str, limit: int = 5, **kwargs) -> List[Dict[str, Any]]:
        """Async query Weaviate using async client."""
        try:
            from weaviate.classes.query import MetadataQuery
            
            # Get async client and collection
            async_client, async_collection = await self._get_async_client()
            
            # Try near_text first (if vectorizer is configured)
            try:
                response = async_collection.query.near_text(
                    query=query,
                    limit=limit,
                    return_metadata=MetadataQuery(distance=True)
                )
            except Exception as near_text_error:
                logger.warning(f"near_text failed: {near_text_error}")
                # Fallback to bm25 search if vectorizer is not configured
                logger.info("Falling back to bm25 search")
                response = async_collection.query.bm25(
                    query=query,
                    limit=limit,
                    return_metadata=MetadataQuery(score=True)
                )
            
            # Convert to unified format
            results = []
            for obj in response.objects:
                result = {
                    'text': obj.properties.get('text', ''),
                    'metadata': obj.properties.get('metadata', {}),
                    'distance': obj.metadata.distance if obj.metadata else obj.metadata.score if obj.metadata else None,
                    'source': obj.properties.get('source', ''),
                    'source_type': obj.properties.get('source_type', '')
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Weaviate async query failed: {e}")
            return []
    
    async def asimilarity_search(self, query: str, k: int = 5, **kwargs) -> List[Any]:
        """Async similarity search that returns LangChain Document objects like ChromaDB."""
        try:
            from langchain.schema import Document
            from weaviate.classes.query import MetadataQuery
            
            # Get async client and collection
            async_client, async_collection = await self._get_async_client()
            
            # Try near_text first (if vectorizer is configured)
            try:
                response = async_collection.query.near_text(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(distance=True)
                )
            except Exception as near_text_error:
                logger.warning(f"near_text failed: {near_text_error}")
                # Fallback to bm25 search if vectorizer is not configured
                logger.info("Falling back to bm25 search")
                response = async_collection.query.bm25(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(score=True)
                )
            
            # Convert to LangChain Document format like ChromaDB
            documents = []
            for obj in response.objects:
                # Extract text content
                text = obj.properties.get('text', '')
                
                # Create metadata dict
                metadata = {
                    'source': obj.properties.get('source', ''),
                    'source_type': obj.properties.get('source_type', ''),
                    'distance': obj.metadata.distance if obj.metadata else obj.metadata.score if obj.metadata else None
                }
                
                # Add any additional properties as metadata
                for key, value in obj.properties.items():
                    if key not in ['text', 'source', 'source_type']:
                        metadata[key] = value
                
                # Create LangChain Document
                doc = Document(page_content=text, metadata=metadata)
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"Weaviate async similarity_search failed: {e}")
            return []
    
    async def asimilarity_search_with_score(self, query: str, k: int = 5, **kwargs) -> List[tuple]:
        """Async similarity search with score to match ChromaDB interface."""
        try:
            from langchain.schema import Document
            from weaviate.classes.query import MetadataQuery
            
            # Get async client and collection
            async_client, async_collection = await self._get_async_client()
            
            # Try near_text first (if vectorizer is configured)
            try:
                response = async_collection.query.near_text(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(distance=True)
                )
            except Exception as near_text_error:
                logger.warning(f"near_text failed: {near_text_error}")
                # Fallback to bm25 search if vectorizer is not configured
                logger.info("Falling back to bm25 search")
                response = async_collection.query.bm25(
                    query=query,
                    limit=k,
                    return_metadata=MetadataQuery(score=True)
                )
            
            # Convert to (doc, score) format like ChromaDB
            results = []
            for obj in response.objects:
                # Extract text content
                text = obj.properties.get('text', '')
                
                # Create metadata dict
                metadata = {
                    'source': obj.properties.get('source', ''),
                    'source_type': obj.properties.get('source_type', '')
                }
                
                # Add any additional properties as metadata
                for key, value in obj.properties.items():
                    if key not in ['text', 'source', 'source_type']:
                        metadata[key] = value
                
                # Create LangChain Document
                doc = Document(page_content=text, metadata=metadata)
                
                # Use distance/score as score
                score = obj.metadata.distance if obj.metadata else obj.metadata.score if obj.metadata else 0.0
                
                results.append((doc, score))
            
            return results
            
        except Exception as e:
            logger.error(f"Weaviate async similarity_search_with_score failed: {e}")
            return []
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection information."""
        try:
            stats = self._collection.aggregate.over_all(total_count=True)
            return {
                'total_count': stats.total_count,
                'collection_name': self.collection_name,
                'store_type': 'Weaviate'
            }
        except Exception as e:
            logger.error(f"Failed to get Weaviate collection info: {e}")
            return {'error': str(e)}
    
    def close(self):
        """Close Weaviate connections."""
        # Close sync client
        if hasattr(self, '_client'):
            try:
                self._client.close()
                logger.info("Weaviate sync connection closed")
            except Exception as e:
                logger.warning(f"Error closing sync client: {e}")
        
        # Close async client
        if hasattr(self, '_async_client'):
            try:
                self._async_client.close()
                logger.info("Weaviate async connection closed")
            except Exception as e:
                logger.warning(f"Error closing async client: {e}")
    
    async def aclose(self):
        """Async close Weaviate connections."""
        # Close sync client
        if hasattr(self, '_client'):
            try:
                self._client.close()
                logger.info("Weaviate sync connection closed")
            except Exception as e:
                logger.warning(f"Error closing sync client: {e}")
        
        # Close async client
        if hasattr(self, '_async_client'):
            try:
                self._async_client.close()
                logger.info("Weaviate async connection closed")
            except Exception as e:
                logger.warning(f"Error closing async client: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()


def get_vectorstore(store_id: str, **kwargs):
    """Get a vector store instance by ID."""
    if store_id == "CHROMA_DB":
        return create_chroma_db(**kwargs)
    elif store_id == "WEAVIATE_DB":
        return create_weaviate_db(**kwargs)
    else:
        raise ValueError(f"Unknown vectorstore: {store_id}")


# Create a simple alias for backward compatibility
class VectorstoreProvider:
    def get(self, store_id: str, **kwargs):
        return get_vectorstore(store_id, **kwargs)

vectorstores = VectorstoreProvider()


def create_chroma_db(**kwargs):
    """Create a ChromaDB vector store."""
    return Chroma(
        persist_directory=kwargs.get('persist_directory'),
        collection_name=kwargs.get('collection_name'),
        embedding_function=kwargs.get('embedding_function')
    )


def create_weaviate_db(**kwargs):
    """Create a Weaviate vector store."""
    # Get Weaviate configuration
    host = kwargs.get('host', '127.0.0.1')
    port = kwargs.get('port', 8089)
    grpc_port = kwargs.get('grpc_port', 50059)
    collection_name = kwargs.get('collection_name', 'Chunks')
    api_key = kwargs.get('api_key')
    
    # Create Weaviate wrapper
    return WeaviateWrapper(
        host=host,
        port=port,
        grpc_port=grpc_port,
        collection_name=collection_name,
        api_key=api_key
    )

