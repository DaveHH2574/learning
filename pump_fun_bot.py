# bot.py

import os
import time
import json
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from solana.publickey import PublicKey
from solana.rpc.api import Client
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from solana.keypair import Keypair
from pyserum.market import Market
from pyserum.connection import conn
from pyserum.order_book import OrderBook
import asyncio
import logging

# Load environment variables
load_dotenv()

# Initialize Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

# Solana Client
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"  # Change to devnet for testing
solana_client = Client(SOLANA_RPC_URL)

# Load Wallet
SECRET_KEY = json.loads(os.getenv("SECRET_KEY"))
keypair = Keypair.from_secret_key(bytes(SECRET_KEY))
public_key = keypair.public_key

# API Configurations
RUGCHECK_API_URL = 'https://api.rugcheck.xyz/check'  # Hypothetical endpoint
RUGCHECK_API_KEY = os.getenv("RUGCHECK_API_KEY")

GETMONI_API_URL = 'https://api.getmoni.xyz/project'  # Hypothetical endpoint
GETMONI_API_KEY = os.getenv("GETMONI_API_KEY")

# Email Notifications Configuration (Optional)
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")

# Slippage Tolerance
SLIPPAGE_PERCENT = 1  # 1%

# Profit Target
PROFIT_MULTIPLIER = 5  # 5x

# Define the Serum DEX Market Address
MARKET_ADDRESS = os.getenv("MARKET_ADDRESS")  # Replace with actual market address

if not MARKET_ADDRESS:
    logger.error("Serum Market Address not set in .env file.")
    exit(1)

# Initialize Serum Market
serum_connection = conn(SOLANA_RPC_URL)
try:
    market = Market.load(serum_connection, PublicKey(MARKET_ADDRESS))
    logger.info(f"Connected to Serum Market: {MARKET_ADDRESS}")
except Exception as e:
    logger.error(f"Failed to load Serum Market: {e}")
    exit(1)

# In-Memory Storage for Open Positions
open_positions = {}  # Key: token_address, Value: {'initial_price': float, 'amount': float}

# Utility Functions

def send_email(subject, body):
    """
    Sends an email notification.
    Requires configuration of an SMTP server or use of a service like Gmail.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not EMAIL_USER or not EMAIL_PASS or not EMAIL_RECIPIENT:
        logger.warning("Email credentials not set. Skipping email notification.")
        return

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        text = msg.as_string()
        server.sendmail(EMAIL_USER, EMAIL_RECIPIENT, text)
        server.quit()
        logger.info(f"Email sent: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def get_current_time():
    return datetime.utcnow()

def time_since_launch(launch_time):
    """
    Returns the time difference in hours since the token was launched.
    """
    now = get_current_time()
    diff = now - launch_time
    return diff.total_seconds() / 3600  # Convert to hours

async def fetch_new_tokens():
    """
    Fetches new tokens from Pump.fun.
    Placeholder function: Replace with actual API calls or scraping logic.
    """
    try:
        # Example static data; replace with dynamic fetching
        tokens = [
            {
                'name': 'ExampleToken1',
                'contract_address': 'ExampleContractAddress12345',
                'launch_time': get_current_time() - timedelta(hours=6),  # Launched 6 hours ago
                'market_cap': 7500,  # USD
                'has_live_streams': False
            },
            {
                'name': 'ExampleToken2',
                'contract_address': 'ExampleContractAddress67890',
                'launch_time': get_current_time() - timedelta(hours=9),  # Launched 9 hours ago
                'market_cap': 6000,  # USD
                'has_live_streams': False
            },
            {
                'name': 'ExampleToken3',
                'contract_address': 'ExampleContractAddress54321',
                'launch_time': get_current_time() - timedelta(hours=7),  # Launched 7 hours ago
                'market_cap': 8000,  # USD
                'has_live_streams': True
            },
            # Add more tokens as needed
        ]
        logger.info(f"Fetched {len(tokens)} new tokens.")
        return tokens
    except Exception as e:
        logger.error(f"Error fetching new tokens: {e}")
        return []

def check_rug_pull(contract_address):
    """
    Checks if the token is safe using RugCheck API.
    Returns True if safe, False otherwise.
    """
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {RUGCHECK_API_KEY}'
        }
        payload = {
            'contractAddress': contract_address
        }
        response = requests.post(RUGCHECK_API_URL, headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            is_safe = not data.get('isRugPull', False)
            if is_safe:
                logger.info(f"Token {contract_address} is safe.")
            else:
                logger.warning(f"Token {contract_address} is flagged as a rug pull.")
            return is_safe
        else:
            logger.error(f"RugCheck API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception during RugCheck API call: {e}")
        return False

def check_social_media(contract_address):
    """
    Checks if the token has at least one social media account using Getmoni API.
    Returns True if at least one social media account exists, False otherwise.
    """
    try:
        headers = {
            'Authorization': f'Bearer {GETMONI_API_KEY}',
            'Content-Type': 'application/json'
        }
        response = requests.get(f"{GETMONI_API_URL}/{contract_address}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            social_media = data.get('socialMedia', {})
            if social_media and len(social_media) >= 1:
                logger.info(f"Token {contract_address} has social media accounts: {list(social_media.keys())}")
                return True
            else:
                logger.warning(f"Token {contract_address} has no social media accounts.")
                return False
        else:
            logger.error(f"Getmoni API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Exception during Getmoni API call: {e}")
        return False

def get_market_cap(contract_address):
    """
    Fetches the market cap of the token.
    Placeholder function: Replace with actual logic to fetch market cap.
    """
    try:
        # Example static data; replace with dynamic fetching
        # You might use a service like CoinGecko API or integrate with Solana's on-chain data
        # For demonstration, assume the market cap is already provided in the token data
        return None  # Not used in this implementation
    except Exception as e:
        logger.error(f"Error fetching market cap for {contract_address}: {e}")
        return None

async def buy_token(token, amount_sol):
    """
    Buys the specified token with the given amount of SOL, considering 1% slippage.
    """
    try:
        # Fetch the current best bid (buy price)
        bids = market.load_bids()
        best_bid = bids.top_bid()
        if not best_bid:
            logger.warning(f"No bids available for {token['name']}. Cannot buy.")
            return False

        price = best_bid[0]  # Price per token in USDC
        quantity = amount_sol / price  # Number of tokens to buy

        # Calculate slippage
        slippage_amount = quantity * (SLIPPAGE_PERCENT / 100)
        min_quantity = quantity - slippage_amount

        logger.info(f"Buying {quantity:.6f} {token['name']} at price {price} USDC with min quantity {min_quantity:.6f} (1% slippage).")

        # Place a limit buy order on Serum DEX
        txn = Transaction()

        # Create a buy order
        order = market.make_order(
            payer=public_key,
            owner=keypair,
            side='buy',
            limit_price=price,
            max_quantity=quantity,
            order_type='limit',
            client_id=int(time.time())
        )

        txn.add(order)

        # Send the transaction
        response = solana_client.send_transaction(txn, keypair)
        logger.info(f"Buy transaction sent: {response['result']}")

        # Track the position
        open_positions[token['contract_address']] = {
            'initial_price': price,
            'amount': quantity
        }

        send_email(f"Bought {token['name']}", f"Purchased {quantity:.6f} {token['name']} at {price} USDC each. Transaction Signature: {response['result']}")

        return True

    except Exception as e:
        logger.error(f"Error buying token {token['name']}: {e}")
        send_email(f"Buy Failed for {token['name']}", f"Failed to purchase {token['name']}. Error: {e}")
        return False

async def sell_token(token, initial_price, amount_tokens):
    """
    Sells the specified amount of tokens when the price reaches 5x profit.
    """
    try:
        target_price = initial_price * PROFIT_MULTIPLIER

        # Fetch the current best ask (sell price)
        asks = market.load_asks()
        best_ask = asks.top_ask()
        if not best_ask:
            logger.warning(f"No asks available for {token['name']}. Cannot sell.")
            return False

        current_price = best_ask[0]
        if current_price < target_price:
            logger.info(f"Current price {current_price} USDC is below target {target_price} USDC for selling {token['name']}.")
            return False

        # Calculate slippage
        slippage_amount = amount_tokens * (SLIPPAGE_PERCENT / 100)
        min_sol = (current_price * amount_tokens) - (current_price * slippage_amount)

        logger.info(f"Selling {amount_tokens:.6f} {token['name']} at price {current_price} USDC with min SOL {min_sol:.2f} (1% slippage).")

        # Place a limit sell order on Serum DEX
        txn = Transaction()

        # Create a sell order
        order = market.make_order(
            payer=public_key,
            owner=keypair,
            side='sell',
            limit_price=current_price,
            max_quantity=amount_tokens,
            order_type='limit',
            client_id=int(time.time())
        )

        txn.add(order)

        # Send the transaction
        response = solana_client.send_transaction(txn, keypair)
        logger.info(f"Sell transaction sent: {response['result']}")

        # Remove the position from open_positions
        del open_positions[token['contract_address']]

        send_email(f"Sold {token['name']}", f"Sold {amount_tokens:.6f} {token['name']} at {current_price} USDC each. Transaction Signature: {response['result']}")

        return True

    except Exception as e:
        logger.error(f"Error selling token {token['name']}: {e}")
        send_email(f"Sell Failed for {token['name']}", f"Failed to sell {token['name']}. Error: {e}")
        return False

async def monitor_price(token):
    """
    Monitors the token's price and sells when 5x profit is achieved.
    """
    contract_address = token['contract_address']
    initial_price = open_positions[contract_address]['initial_price']
    amount_tokens = open_positions[contract_address]['amount']

    logger.info(f"Monitoring price for {token['name']}: Initial Price = {initial_price} USDC")

    while True:
        try:
            # Fetch the current best ask
            asks = market.load_asks()
            best_ask = asks.top_ask()
            if not best_ask:
                logger.warning(f"No asks available for {token['name']}. Cannot monitor price.")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
                continue

            current_price = best_ask[0]

            logger.info(f"Current price for {token['name']}: {current_price} USDC")

            if current_price >= initial_price * PROFIT_MULTIPLIER:
                # Profit target reached; sell the token
                logger.info(f"Profit target reached for {token['name']}. Initiating sell.")
                await sell_token(token, initial_price, amount_tokens)
                break

            await asyncio.sleep(300)  # Wait 5 minutes before checking again

        except Exception as e:
            logger.error(f"Error monitoring price for {token['name']}: {e}")
            send_email(f"Price Monitoring Error for {token['name']}", f"An error occurred while monitoring price: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retrying

async def monitor_and_trade():
    """
    Main function to monitor tokens and execute buy/sell strategies.
    """
    while True:
        try:
            tokens = await fetch_new_tokens()
            for token in tokens:
                # Verify launch time
                launch_time = token['launch_time']
                age_hours = time_since_launch(launch_time)
                if not (5 <= age_hours <= 10):
                    logger.info(f"Skipping {token['name']} due to launch time {age_hours:.2f} hours.")
                    continue

                # Verify market cap
                if not (5000 <= token['market_cap'] <= 10000):
                    logger.info(f"Skipping {token['name']} due to market cap ${token['market_cap']}.")
                    continue

                # Check for live streams
                if token['has_live_streams']:
                    logger.info(f"Skipping {token['name']} because it has live streams.")
                    continue

                # Check rug pull risk
                if not check_rug_pull(token['contract_address']):
                    logger.info(f"Skipping {token['name']} due to rug pull risk.")
                    continue

                # Check social media presence
                if not check_social_media(token['contract_address']):
                    logger.info(f"Skipping {token['name']} due to lack of social media presence.")
                    continue

                # Proceed to buy the token if not already in open_positions
                if token['contract_address'] in open_positions:
                    logger.info(f"Already holding {token['name']}. Skipping buy.")
                    continue

                # Buy the token
                amount_sol = 0.01  # Define the amount of SOL to spend per purchase
                buy_success = await buy_token(token, amount_sol)
                if buy_success:
                    # Start monitoring the price for profit
                    asyncio.create_task(monitor_price(token))

        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            send_email("Bot Error", f"An error occurred: {e}")

        # Wait before the next monitoring cycle
        logger.info("Sleeping for 10 minutes before next monitoring cycle.")
        await asyncio.sleep(600)  # 10 minutes

def main():
    """
    Entry point of the bot.
    """
    logger.info("🚀 Starting Pump.fun Bot...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(monitor_and_trade())

if __name__ == "__main__":
    main()
