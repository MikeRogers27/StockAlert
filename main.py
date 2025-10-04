import requests
import smtplib
import time
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import statistics
import json
import logging
from logging import Logger
import argparse
from typing import Optional

LOG : Optional[Logger] = None


def logger_setup(loglevel='INFO'):
    global LOG
    LOG = logging.getLogger('StockAlerts')
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)

    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s %(levelname)s:%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            # logging.FileHandler('stockalert.log'),
            logging.StreamHandler()
        ]
    )


def get_sp500_historical():
    """Get S&P 500 3-month historical data with daily caching"""
    cache_file = 'sp500_cache.json'
    
    # Check if cache exists and is less than 1 day old
    if os.path.exists(cache_file):
        cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if cache_age < timedelta(days=1):
            LOG.info("Using cached historical data")
            with open(cache_file, 'r') as f:
                return json.load(f)
    
    LOG.info("Fetching fresh historical data")
    api_key = os.getenv('ALPHA_VANTAGE_API_KEY', 'demo')
    url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=SPY&apikey={api_key}'
    
    response = requests.get(url)
    data = response.json()
    time_series = data['Time Series (Daily)']
    
    three_months_ago = datetime.now() - timedelta(days=90)
    prices = []
    
    for date_str, values in time_series.items():
        date = datetime.strptime(date_str, '%Y-%m-%d')
        if date >= three_months_ago:
            prices.append(float(values['4. close']))
    LOG.info(f"Fetched {len(prices)} historical prices from Alpha Vantage")
    
    # Cache the results
    with open(cache_file, 'w') as f:
        json.dump(prices, f)
    LOG.info("Historical data cached successfully")
    
    return prices

def get_current_price():
    """Get current S&P 500 price"""
    try:
        api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey={api_key}'
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        price = float(data['Global Quote']['05. price'])
        LOG.info(f"Current S&P 500 price: {price}")
        return price
    except Exception as e:
        LOG.error(f"Failed to get current price: {e}")
        raise

def get_threshold_state():
    """Get current threshold state from cache"""
    threshold_file = 'threshold_cache.json'
    default_state = {'threshold_percent': 5.0, 'last_updated': datetime.now().isoformat()}
    
    if not os.path.exists(threshold_file):
        state = default_state
    else:
        with open(threshold_file, 'r') as f:
            state = json.load(f)
    
    # Update threshold daily (increase by 1% until reaching 5%)
    last_updated = datetime.fromisoformat(state['last_updated'])
    if datetime.now() - last_updated >= timedelta(days=1):
        state['threshold_percent'] = min(5.0, state['threshold_percent'] + 1.0)
        state['last_updated'] = datetime.now().isoformat()
        save_threshold_state(state)
        LOG.info(f"Threshold updated to {state['threshold_percent']}%")
    
    return state

def save_threshold_state(state):
    """Save threshold state to cache"""
    with open('threshold_cache.json', 'w') as f:
        json.dump(state, f)

def send_email(current_price, peak_price, drop_percent):
    """Send email notification and update threshold"""
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    recipient_email = os.getenv('RECIPIENT_EMAIL')
    
    if not all([sender_email, sender_password, recipient_email]):
        LOG.warning(f"Email not configured. S&P 500 dropped {drop_percent:.1f}% from peak {peak_price} to {current_price}")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"S&P 500 Alert: {drop_percent:.1f}% Drop from Peak"
        
        body = f"S&P 500 has dropped {drop_percent:.1f}% from 3-month peak of {peak_price:.2f} to current price {current_price:.2f}"
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
                
        LOG.info(f"Alert sent! S&P 500: {current_price} (down {drop_percent:.1f}% from peak).")
    except Exception as e:
        LOG.error(f"Failed to send email: {e}")


def monitor_sp500_peak_drop(check_interval=3600):
    """Monitor S&P 500 for drop from 3-month smoothed peak with dynamic threshold"""
    LOG.info("Starting S&P 500 monitoring with dynamic threshold")
    
    while True:
        try:
            # Get current threshold state
            threshold_state = get_threshold_state()
            threshold_percent = threshold_state['threshold_percent']
            
            # Get historical data and calculate smoothed peak
            historical_prices = get_sp500_historical()
            smoothed_peak = statistics.mean(sorted(historical_prices, reverse=True)[:10])
            
            # Get current price
            current_price = get_current_price()
            current_drop_percent = ((smoothed_peak - current_price) / smoothed_peak) * 100
            current_drop_percent = 5
            
            LOG.info(f"Current: {current_price:.2f}, Peak: {smoothed_peak:.2f}, Drop: {current_drop_percent:.1f}%, Threshold: {threshold_percent:.1f}%")
            
            if current_drop_percent >= threshold_percent:
                LOG.warning(f"Alert triggered! Price dropped {current_drop_percent:.1f}% (threshold: {threshold_percent:.1f}%)")
                send_email(current_price, smoothed_peak, current_drop_percent)
                
                # Update threshold to require 1% further drop for next alert
                new_threshold = current_drop_percent + 1.0
                state = {'threshold_percent': new_threshold, 'last_updated': datetime.now().isoformat()}
                save_threshold_state(state)
                LOG.info(f"New drop threshold saved: {new_threshold:.1f}%")

        except Exception as e:
            LOG.error(f"Monitoring error: {e}")
        
        time.sleep(check_interval)

if __name__ == "__main__":
    logger_setup()
    monitor_sp500_peak_drop()
