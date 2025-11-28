# 1. Base Image
FROM python:3.11-slim

# 2. Set environment/user
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

# 3. Set Working Directory
WORKDIR $HOME/app

# 4. Copy requirements and install dependencies (still running as root here)
COPY requirements.txt .
# Combine these RUN commands for better performance
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of the application code
# Ensure the files are copied first. The --chown=user is good, but the explicit chown is safer.
COPY . . 

# 6. FIX: Explicitly change ownership to the non-root user (must be run by root)
RUN chown -R user:user $HOME/app 

# 7. Switch to the non-root user BEFORE CMD is run
USER user 

# 8. Define the startup command
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]