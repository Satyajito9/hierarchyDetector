FROM python:3.11-slim

# Pass with: docker build --build-arg APP_VERSION=$(cat VERSION) -t hierarchydetector:$(cat VERSION) .
ARG APP_VERSION=0.0.0
LABEL org.opencontainers.image.version="${APP_VERSION}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VERSION ./VERSION
COPY hierarchy_detector ./hierarchy_detector
COPY app.py ./

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
