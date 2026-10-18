FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH HF_HOME=/home/user/hf PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# Same LeRobot commit as the robot's venv (pyproject.toml, 0.6.2 is not on PyPI): the processors
# (normalization, tokenizer) must match.
RUN pip install --no-cache-dir --user \
    "lerobot[pi] @ git+https://github.com/huggingface/lerobot.git@146d8474932c8b566717eb2738ba459337ab71c4" \
    "fastapi<1" "uvicorn[standard]" pillow
COPY --chown=user server.py .

EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
