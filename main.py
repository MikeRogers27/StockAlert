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


def get_historical_prices(asset_type):
    """Get 3-month historical data with daily caching"""
    cache_file = f'{asset_type}_cache.json'
    
    # Check if cache exists and is less than 1 day old
    if os.path.exists(cache_file):
        cache_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
        if cache_age < timedelta(days=1):
            LOG.info(f"Using cached {asset_type} historical data")
            with open(cache_file, 'r') as f:
                return json.load(f)
    
    LOG.info(f"Fetching fresh {asset_type} historical data")
    
    if asset_type == 'sp500':
        api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=SPY&apikey={api_key}'
        response = requests.get(url)
        data = response.json()
        response.raise_for_status()
        time_series = data['Time Series (Daily)']
        
        three_months_ago = datetime.now() - timedelta(days=90)
        prices = []
        for date_str, values in time_series.items():
            date = datetime.strptime(date_str, '%Y-%m-%d')
            if date >= three_months_ago:
                prices.append(float(values['4. close']))
    
    elif asset_type == 'bitcoin':
        api_key = os.getenv('COIN_GECKO_API_KEY')
        headers = {"x-cg-demo-api-key": api_key}
        url = 'https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=90'
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        prices = [price[1] for price in data['prices']]
    
    LOG.info(f"Fetched {len(prices)} {asset_type} historical prices")
    
    # Cache the results
    with open(cache_file, 'w') as f:
        json.dump(prices, f)
    LOG.info(f"{asset_type} historical data cached successfully")
    
    return prices

def get_current_price(asset_type):
    """Get current price for asset"""
    try:
        if asset_type == 'sp500':
            api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
            url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=SPY&apikey={api_key}'
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            price = float(data['Global Quote']['05. price'])
        elif asset_type == 'bitcoin':
            api_key = os.getenv('COIN_GECKO_API_KEY')
            headers = {"x-cg-demo-api-key": api_key}
            url = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd'
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            price = data['bitcoin']['usd']
        
        LOG.info(f"Current {asset_type} price: {price}")
        return price
    except Exception as e:
        LOG.error(f"Failed to get current {asset_type} price: {e}")
        raise


def get_threshold_state(asset_type):
    """Get current threshold state from cache"""
    threshold_file = f'{asset_type}_threshold.json'
    default_state = {'threshold_percent': 5.0, 'last_updated': datetime.now().isoformat()}
    
    if not os.path.exists(threshold_file):
        state = default_state
    else:
        with open(threshold_file, 'r') as f:
            state = json.load(f)
    
    # Update threshold daily (decrease by 1% until reaching 5%)
    last_updated = datetime.fromisoformat(state['last_updated'])
    if datetime.now() - last_updated >= timedelta(days=1):
        state['threshold_percent'] = max(5.0, state['threshold_percent'] - 1.0)
        state['last_updated'] = datetime.now().isoformat()
        save_threshold_state(asset_type, state)
        LOG.info(f"{asset_type} threshold updated to {state['threshold_percent']}%")
    
    return state


def save_threshold_state(asset_type, state):
    """Save threshold state to cache"""
    with open(f'{asset_type}_threshold.json', 'w') as f:
        json.dump(state, f)


def send_notification_email(subject, body):
    """Send notification email"""
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    recipient_email = os.getenv('RECIPIENT_EMAIL')
    
    if not all([sender_email, sender_password, recipient_email]):
        LOG.warning(f"Email not configured. {subject}: {body}")
        return
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        LOG.info(f"Email sent: {subject}")
    except Exception as e:
        LOG.error(f"Failed to send email: {e}")

def send_email(asset_type, current_price, peak_price, drop_percent):
    """Send price drop alert email"""
    asset_name = 'S&P 500' if asset_type == 'sp500' else 'Bitcoin'
    subject = f"{asset_name} Alert: {drop_percent:.1f}% Drop from Peak"
    body = f"{asset_name} has dropped {drop_percent:.1f}% from 3-month peak of {peak_price:.2f} to current price {current_price:.2f}"
    send_notification_email(subject, body)


import threading
stop_event = threading.Event()

def monitor_asset(asset_type, check_interval=3600):
    """Monitor asset for drop from 3-month smoothed peak with dynamic threshold"""
    asset_name = 'S&P 500' if asset_type == 'sp500' else 'Bitcoin'
    LOG.info(f"Starting {asset_name} monitoring with dynamic threshold")
    
    try:
        while not stop_event.is_set():
            # Get current threshold state
            threshold_state = get_threshold_state(asset_type)
            threshold_percent = threshold_state['threshold_percent']
            
            # Get historical data and calculate smoothed peak
            historical_prices = get_historical_prices(asset_type)
            smoothed_peak = statistics.mean(sorted(historical_prices, reverse=True)[:10])
            
            # Get current price
            current_price = get_current_price(asset_type)
            current_drop_percent = ((smoothed_peak - current_price) / smoothed_peak) * 100
            
            LOG.info(f"{asset_name} - Current: {current_price:.2f}, Peak: {smoothed_peak:.2f}, Drop: {current_drop_percent:.1f}%, Threshold: {threshold_percent:.1f}%")
            
            if current_drop_percent >= threshold_percent:
                LOG.warning(f"{asset_name} alert triggered! Price dropped {current_drop_percent:.1f}% (threshold: {threshold_percent:.1f}%)")
                send_email(asset_type, current_price, smoothed_peak, current_drop_percent)
                
                # Update threshold to require 1% further drop for next alert
                new_threshold = current_drop_percent + 1.0
                state = {'threshold_percent': new_threshold, 'last_updated': datetime.now().isoformat()}
                save_threshold_state(asset_type, state)
                LOG.info(f"{asset_name} new drop threshold saved: {new_threshold:.1f}%")
            
            time.sleep(check_interval)
    
    except Exception as e:
        LOG.error(f"{asset_name} monitoring fatal error: {e}")
        send_notification_email(f"StockAlert Error - {asset_name}", f"Fatal error in {asset_name} monitoring: {str(e)}")
        stop_event.set()  # Signal other threads to stop
        raise


if __name__ == "__main__":
    logger_setup()
    
    # Send startup notification
    send_notification_email("StockAlert Started", f"StockAlert monitoring started successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Start monitoring both assets in separate threads
    sp500_thread = threading.Thread(target=monitor_asset, args=('sp500',))
    bitcoin_thread = threading.Thread(target=monitor_asset, args=('bitcoin',))
    
    sp500_thread.start()
    bitcoin_thread.start()
    
    try:
        sp500_thread.join()
        bitcoin_thread.join()
    except KeyboardInterrupt:
        LOG.info("Shutdown requested")
        stop_event.set()
    except Exception as e:
        LOG.error(f"Main thread error: {e}")
        send_notification_email("StockAlert Fatal Error", f"Application encountered fatal error: {str(e)}")
        stop_event.set()
