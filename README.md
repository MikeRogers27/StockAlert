## Setup steps

Create your ssh keys and start agent.

### Clone the repo
    
```
cd ~/src
git clone git@github.com:MikeRogers27/StockAlert.git
```

### Virtual env

Install uv:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Run ```source $HOME/.local/bin/env``` to add to path if required.

Setup a new virtual python env

```
cd StockAlert
uv sync
```

The environment will be created at ~/src/StockAlert/.venv

### Script setup

Create a new file: ~/run-stock-alert.sh

```
#!/bin/bash

# wait to see if we're online
for i in {1..50}; do ping -c1 www.google.com &> /dev/null && break; done

# add ssh credentials
eval "$(ssh-agent -s)"
ssh-add ${HOME}/.ssh/id_github

# get latest changes
cd ${HOME}/src/StockAlert/
git pull

# Get free API key from https://www.alphavantage.co/support/#api-key
export ALPHA_VANTAGE_API_KEY=<API_KEY>

# Get free demo API key from https://www.coingecko.com/
export COIN_GECKO_API_KEY=<API_KEY>

# Email configuration (for Gmail, enable 2FA and use App Password)
export SENDER_EMAIL=<SENDER_EMAIL_ADRESS>
export SENDER_PASSWORD=<GOOGLE_GMAIL_APP_PASSWORD>
export RECIPIENT_EMAIL=<RECIPIENT_EMAIL_ADRESS>

source ${HOME}/venv/StockAlert/.venv/bin/activate
sudo --preserve-env=ALPHA_VANTAGE_API_KEY,SENDER_EMAIL,SENDER_PASSWORD,RECIPIENT_EMAIL /home/pi/src/StockAlert/.venv/bin/python main.py
```

Now change to executable permissions:

```
chmod +x ~/run-stock-alert.sh
```

### Install as service

Create the log dir

```
mkdir ~/logs
```

Make a service configuration file

```
sudo nano /lib/systemd/system/stockalert.service
```

with this contents

```
[Unit]
Description=Stock Alert Runner
Wants=network.service
Requires=rpcbind.service network-online.target
After=multi-user.target network.target network-online.target

[Service]
Type=idle
ExecStart=/home/pi/run-stock-alert.sh
User=pi
Group=pi
StandardOutput=append:/home/pi/logs/stockalert.log
StandardError=append:/home/pi/logs/stockalert_err.log

[Install]
WantedBy=multi-user.target
```

Then enable the service
    
```
sudo systemctl daemon-reload
sudo systemctl enable stockalert.service
sudo reboot
```

Commands use disable, start, stop etc

```
sudo systemctl start stockalert.service
```

## Gmail App Password Setup:

* Go to My account settings: https://myaccount.google.com/
* Make sure 2FA is enabled
* Search for "App Passwords"
* Add a new password for "StockAlerts"
* Copy and add to ENV

## CoinGecko API key

* Go to https://www.coingecko.com/
* Sign up for the demo api by registering an account and visiting:
    https://www.coingecko.com/en/developers/dashboard
