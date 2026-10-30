# Retrieval and cited answers

RAG means retrieval augmented generation. Load documents, split them into overlapping chunks, embed the chunks, build an index, retrieve evidence, then compose an answer with citations. This starter uses sparse TF-IDF embeddings with cosine similarity, computed locally using Python's standard library. It does not use neural embeddings or an external vector database.

Chunks preserve a source filename and chunk ID. The offline answer is an extractive evidence summary: it returns passages verbatim with citations. It does not generate a natural language answer through an LLM. If no query terms match the corpus, it abstains.

Evaluate retrieval against a small labeled question set using hit rate at k. This measures whether the expected document was retrieved, not answer quality, groundedness, or production readiness. Larger deployments need separate retrieval and generation evaluations.
