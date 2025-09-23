# se a more modern and stable Python base image
FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y default-libmysqlclient-dev build-essential pkg-config --no-install-recommends && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# THIS IS THE NEW STEP
# Run collectstatic to gather all static files into the STATIC_ROOT directory
RUN python manage.py collectstatic --noinput

# Expose port 8000
EXPOSE 8000

# Run the application
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "perfectarchive.wsgi:application"]