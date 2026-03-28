# API server
Serves as the backend API server that interfaces with the LLM (Ollama) and Speech-to-Text (Not implemented yet) services. 

Built with FastAPI and deployed in a Docker container.

## Setup
1. Build and start the Docker container: 
`docker compose up --build`
<br/>
2. Pull the model in Ollama (may take a while depending on the model):
`docker compose exec ollama ollama pull granite4`

    **Note**: GPU access only work for Docker with WSL2. Benchmark: 
    `docker run --rm -it --gpus=all nvcr.io/nvidia/k8s/cuda-sample:nbody nbody -gpu -benchmark`

## Configuration
See `docker-compose.yml` and for environment variables such as API key and model. 

## Routes 
- GET `/health`: checks if the Ollama server is running.
- POST `/generate-str`: takes a prompt and generation parameters, returns generated string from the model.
- POST `/generate-json`: takes a prompt and generation parameters, returns generated JSON from the model (format: json mode).
- WIP POST `/process-context`: take the DOM and current context and return a combined context.
> Route detail definitions and example requests in `api/routes/` folder.

