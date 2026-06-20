FROM python:3.12-slim

WORKDIR /app

#deps first (layer caching - only rebuilds if requirement change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

#uvicorn serves the FASTAPI app; 0.0.0.0 so its reachable from outside container;
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]