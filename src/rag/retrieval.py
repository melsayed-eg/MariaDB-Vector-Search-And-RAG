import os
from sentence_transformers import SentenceTransformer
from src.database.search import search_chunks

# Initialize the embedding model (outputs 384 dimensions)
model = SentenceTransformer('all-MiniLM-L6-v2')

def get_context_for_question(user_question, category_filter=None, min_length_bytes=None, limit=5):
    """
    Takes a user question, converts it to a 384-dimension vector,
    and searches the MariaDB vector index for relevant Wikipedia chunks.
    """
    print(f"Generating embedding for question: '{user_question}'")
    
    # 1. Embed the query using all-MiniLM-L6-v2
    # model.encode() returns a numpy array, .tolist() converts it to a standard Python list
    query_embedding = model.encode(user_question).tolist()
    
    # Verify the dimension is exactly 384 as required by the database
    if len(query_embedding) != 384:
        raise ValueError(f"Expected embedding dimension of 384, but got {len(query_embedding)}")

    print("Searching MariaDB vector index...")
    
    # 2. Search the database using the DAL function
    try:
        results = search_chunks(
            query_embedding=query_embedding,
            limit=limit,
            category=category_filter,
            min_length=min_length_bytes
        )
    except Exception as e:
        print(f"Error querying database: {e}")
        return []

    # 3. Format the retrieved context
    if not results:
        print("No matching articles found.")
        return ""

    context_text = "Here is the retrieved context from Wikipedia:\n\n"
    
    for rank, result in enumerate(results, start=1):
        title = result.get('title', 'Unknown Title')
        chunk_text = result.get('chunk_text', '')
        distance = result.get('distance', 'N/A')
        url = result.get('url', '')
        
        context_text += f"[{rank}] Source: {title}\n"
        context_text += f"URL: {url}\n"
        context_text += f"Similarity Distance: {distance}\n"
        context_text += f"Content: {chunk_text}\n\n"
        
    return context_text

# Basic test execution if the script is run directly
if __name__ == "__main__":
    test_question = "How does artificial intelligence impact healthcare?"
    
    # Example 1: Standard semantic search
    print("--- Standard Vector Search ---")
    context = get_context_for_question(test_question)
    print(context)
    
    # Example 2: Hybrid search (Semantic Search + SQL Filter)
    print("--- Hybrid Search (Filtered by Category) ---")
    hybrid_context = get_context_for_question(test_question, category_filter="Computer science")
    print(hybrid_context)
