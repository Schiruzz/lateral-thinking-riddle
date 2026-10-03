FROM python:3.12-slim

WORKDIR /app

# dependencies first: this layer is rebuilt only when requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# the game: code, puzzles and page (tests, notebooks and logs stay out)
COPY riddle/ riddle/
COPY puzzles/ puzzles/
COPY static/ static/

# Cloud Run tells the container which port to listen on in $PORT
CMD exec uvicorn riddle.server:app --host 0.0.0.0 --port ${PORT:-8080}