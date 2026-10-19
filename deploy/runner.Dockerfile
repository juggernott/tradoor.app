FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /opt/tradoor
# Whitelist copies: no workspace state, credentials, datasets or private source.
COPY pyproject.toml README.md LICENSE ./
COPY alphaloop ./alphaloop
RUN pip install --no-cache-dir '.[web,v12]' && useradd --uid 10001 --no-create-home runner
USER 10001:10001
ENTRYPOINT ["python", "-m", "alphaloop.web.private_runner"]
