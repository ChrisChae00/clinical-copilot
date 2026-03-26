# API server
Serves as the backend API server that interfaces with the LLM (Ollama) and Speech-to-Text (Not implemented yet) services. 

Built with FastAPI and deployed in a Docker container.

## Setup
1. Build and start the Docker container: 
`docker compose up --build`
<br/>
2. Pull the model in Ollama (may take a while depending on the model):
`docker compose exec ollama ollama pull llama3.2:1b`

    **Note**: GPU access only work for Docker with WSL2. Benchmark: 
    `docker run --rm -it --gpus=all nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -gpu -benchmark`

## Configuration
See `docker-compose.yml` and for environment variables such as API key and model. 

## Routes
- POST `/generate`: takes a JSON body with a "prompt" field and returns the LLM response.

- GET `/health`: checks if the Ollama server is running.


