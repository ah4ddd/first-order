import yfinance as yf
from curl_cffi import requests

session = requests.Session(impersonate="chrome")
ticker = yf.Ticker("AAPL", session=session)

# Print raw output directly from the engine
print(ticker.news)
