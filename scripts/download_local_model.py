"""Download the configured local embedding model before starting the API."""
from app.services.embeddings import download_local_embedding_model


if __name__ == "__main__":
    model_name = download_local_embedding_model()
    print(f"Local embedding model is ready: {model_name}")
    print("Set MODEL_PROVIDER=local-hf before starting the API to use this model.")
