# Mainsheet, Claude Code and Vaara in an image OpenShell can run. The workload must not
# run as root, and its working directory is the one place it may write besides /tmp.
FROM node:22-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code

# Dependencies sit outside the working directory: the agent can read them and not change them.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Mainsheet writes instances/ next to its own code, so the code sits inside the working directory.
COPY --chown=node:node . /home/node/mainsheet
RUN pip install --no-cache-dir -e /home/node/mainsheet
# OpenShell starts the shell with its own PATH, so the commands go where that PATH looks.
RUN ln -s /opt/venv/bin/mainsheet* /opt/venv/bin/vaara* /usr/local/bin/

USER node
WORKDIR /home/node
