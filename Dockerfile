#Use a more modern and stable Python base image
FROM python:3.11-slim-bookworm

#Set environment variables to prevent Python from writing .pyc files and to buffer output
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

#Set the working directory in the container
WORKDIR /app

#Install system dependencies required for mysqlclient
#This is a more robust way to run apt-get in a Dockerfile

RUN apt-get update && apt-get install -y default-libmysqlclient-dev build-essential pkg-config --no-install-recommends && apt-get clean && rm -rf /var/lib/apt/lists/*
#Copy the requirements file into the container
COPY requirements.txt .

#Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

#Copy the rest of the application's code into the container
COPY . .

#xpose port 8000 to the outside world
EXPOSE 8000

#Define the command to run the application using Gunicorn
CMD ["python", "-m", "gunicorn", "--bind", "0.0.0.0:8000", "perfectarchive.wsgi:application"]