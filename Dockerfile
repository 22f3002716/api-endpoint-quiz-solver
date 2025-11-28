FROM python:3.11-slim

# Create the same UID (1000) that Spaces uses when running your container
RUN useradd -m -u 1000 user

# Install Python dependencies before copying the entire source tree
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app and switch to the non-root user
COPY --chown=user . .
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH

# 6. FIX: Explicitly ensure the non-root user owns the app directory
# This step gives the 'user' ID 1000 the right to create files like logs.
# -R means recursive, applying to all files/folders inside $HOME/app.
RUN chown -R user:user $HOME/app

EXPOSE 7860

ENV MY_SETTING=default_value

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]