# Each instruction in this file generatalpnes a new layer that gets pushed to your local image cache

FROM tiangolo/uwsgi-nginx-flask:python3.9
#
# Identify the maintainer of an image
LABEL maintainer="jonhall@us.ibm.com"
#
# Install NGINX to test.
RUN rm /bin/sh && ln -s /bin/bash /bin/sh
ENV PATH="/app/.local/bin:${PATH}"
WORKDIR /app

RUN  apt-get update && python3 -m venv /opt/venv && source /opt/venv/bin/activate && adduser worker && usermod -aG sudo worker &&echo "worker ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers && chown worker:worker /app && COPY --chown=worker:worker . /app && pip install -r requirements.txt

CMD ./start-script.sh