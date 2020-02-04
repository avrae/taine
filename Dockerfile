FROM python:3.8-buster

RUN useradd --create-home taine
USER taine
WORKDIR /home/taine

COPY --chown=taine:taine requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt

COPY --chown=taine:taine . .

ENTRYPOINT python bot.py
