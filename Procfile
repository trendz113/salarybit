web: gunicorn server_railway:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 4 --timeout 200 --max-requests 100 --max-requests-jitter 10
