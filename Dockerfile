# JUST NOTE:
# Docker is a containerization platform that packages an application together
# with its dependencies and userspace environment while sharing
# the host operating system kernel through Linux namespaces
# and cgroups for isolation and resource management.

# Instructions for building an image
# Docker reads this file and creates an image.
# When Docker reads the Dockerfile and builds it:
#    docker build -t myapp .
# Docker creates an image
# This image is now a packaged snapshot
# Docker takes the image and says:
#    Start it.
#    Allocate memory.
#    Create processes.
#    Run python main.py.
# Now application is actually alive.
# That living running thing is A container.

# Dockerfile = source code
# Image = compiled executable
# Container = process running in RAM

# ── Base Image ────────────────────────────────────────────────────────────────
# We start from an official Python image from Docker Hub.
# python:3.12-slim means Python 3.12 on a minimal Debian Linux.
# "slim" removes unnecessary tools, making the image smaller (~150MB vs ~900MB).
# Smaller image = faster deploy, less bandwidth, less attack surface.
FROM python:3.12-slim

# ── Working Directory ─────────────────────────────────────────────────────────
# Sets /app as the current directory inside the container.
# All subsequent COPY and RUN commands work relative to this.
# Also where your app code will live inside the container.
WORKDIR /app

# ── Dependencies — copied first for layer caching ────────────────────────────
# Copy ONLY requirements.txt before copying your code.
# Why: if requirements haven't changed, Docker uses the cached pip install layer.
# Your builds go from 60 seconds to 3 seconds when you only change app code.
COPY requirements.txt .

# Install dependencies.
# --no-cache-dir: don't store pip's download cache inside the image.
# Keeps image smaller. We don't need the cache after installation.
RUN pip install --no-cache-dir -r requirements.txt

# ── Application Code ──────────────────────────────────────────────────────────
# Copy everything else now.
# The dot on the left = everything in your project directory on your machine.
# The dot on the right = /app/ inside the container (our WORKDIR).
# .gitignore is NOT automatically respected — Docker uses .dockerignore instead.
COPY . .

# ── Port ──────────────────────────────────────────────────────────────────────
# Documents that the container listens on port 8000.
# This doesn't actually open the port — it's metadata for docker-compose and Render.
# docker-compose uses this when mapping ports.
EXPOSE 8000

# ── Start Command ─────────────────────────────────────────────────────────────
# The command that runs when a container starts from this image.
# --host 0.0.0.0: CRITICAL. Without this, uvicorn only accepts connections
#                 from localhost INSIDE the container, which means nothing
#                 from outside can reach it. 0.0.0.0 means "accept from anywhere".
# --port 8000: matches the EXPOSE above.
# app.main:app: your FastAPI app object — module path : variable name.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
