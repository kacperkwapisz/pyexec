# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container
WORKDIR /app

# Copy the new base requirements file and install the packages for the execution env
COPY src/pyexec/base-requirements.txt /app/base-requirements.txt
RUN pip install --no-cache-dir -r /app/base-requirements.txt

# Copy the application's requirements file and install its dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the application code
COPY src/ /app/src
COPY pyproject.toml .

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application with Gunicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "--bind", "0.0.0.0:8000", "pyexec.main:app"]