# RestaurantIQ

A runnable college-project prototype for restaurant popularity, review sentiment, survival-risk estimates, recommendations, and comparison.

## Run on Windows 11
1. Install Python 3.10+.
2. Extract this folder.
3. Open Command Prompt inside the `RestaurantIQ` folder.
4. Run:
   ```
   py -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
5. Open http://127.0.0.1:8000

This prototype uses a local SQLite database created automatically. Predictions are rule-based demo estimates, not validated business forecasts. Review sentiment uses VADER when installed, with a basic fallback.
