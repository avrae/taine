# taine
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/7c5174b6f97a4144b2c7a1a826f0bbee)](https://www.codacy.com/app/mommothazaz123/taine?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=avrae/taine&amp;utm_campaign=Badge_Grade)
[![Build Status](https://travis-ci.org/avrae/taine.svg?branch=master)](https://travis-ci.org/avrae/taine)

Taine is the main bot to track Avrae bugs and feature requests in Discord.  

## Requirements

- Python 3.6

## Configuration

Set the following environment variables:

- `DISCORD_TOKEN` - a Discord bot token.
- `GITHUB_TOKEN` - a Github Personal Access Token.
- `GITHUB_REPO` - path to the Github repository, defaults to `avrae/avrae`.

Other configuration is via `constants.py`:

- `OWNER_ID` - the Discord User ID of the bot's owner. Used to check if a user can run owner-only commands.
- `BUG_CHAN` - the Discord Channel ID of the channel to listen for bug reports.
- `DDB_CHAN` - the Discord Channel ID of the channel to listen for D&D Beyond bug reports.
- `FEATURE_CHAN` - the Discord Channel ID of the channel to listen for feature requests.
- `WEB_CHAN` - the Discord Channel ID of the channel FIXME
- `TRACKER_CHAN` - the Discord Channel ID of the channel to post all generated reports.
- `OWNER_GITHUB` - the Github username of FIXME
- `REACTIONS` - a list of Unicode/Discord reactions that the bot will react to reports with.

All constants must be unique.

## Running the bot

1. Create a [virtual environment](https://docs.python.org/3/library/venv.html): `python3 -m venv venv`.
2. Activate the virtual environment: `source venv/bin/activate` on Unix (bash/zsh), `venv\Scripts\activate.bat` on Windows. You need to do this each time you open a new shell/command prompt.
3. Install the required Python packages: `pip install -r requirements.txt`.
4. Run the bot: `python bot.py`

## Pull Requests
I (zhu.exe#4211) try to review PRs in a timely manner. A good PR should be descriptive, unique, and useful. Additionally, code should be readable and conform to PEP-8 standards.
