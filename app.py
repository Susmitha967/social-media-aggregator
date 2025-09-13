import requests
import time
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# List of Bearer Tokens for rotation
BEARER_TOKENS = [
   
]

# Function to get user ID by username
def get_user_id(username, token):
    url = f'https://api.twitter.com/2/users/by/username/{username}'
    headers = {'Authorization': f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print(response.json())  
        return response.json()['data']['id']
    except requests.exceptions.RequestException as e:
        print(f"Error getting user ID: {e}")
        return None

# Function to fetch tweets with proper token rotation
def fetch_tweets_with_retry(user_id, retries=3, delay=10):
    params = {'max_results': 35, 'tweet.fields': 'created_at,id,text'}
    all_tokens_exhausted = False

    while not all_tokens_exhausted:
        all_tokens_exhausted = True  # Assume all tokens exhausted unless we find one that works
        for token in BEARER_TOKENS:
            for attempt in range(retries):
                url = f'https://api.twitter.com/2/users/{user_id}/tweets'
                headers = {'Authorization': f"Bearer {token}"}
                try:
                    response = requests.get(url, headers=headers, params=params)
                    
                    # If successful, return data
                    if response.status_code == 200:
                        return response.json().get('data', [])

                    # If rate limit is hit, log and switch to the next token
                    elif response.status_code == 429:
                        reset_time = int(response.headers.get("x-rate-limit-reset", time.time() + delay))
                        retry_in = reset_time - int(time.time())
                        print(f"Rate limit reached for token. Switching to next token. Next token wait: {retry_in} seconds.")
                        time.sleep(1)  # Small pause before trying the next token
                        break  # Try next token

                    else:
                        print(f"HTTP error: {response.status_code}")
                        return {"error": "api_error"}

                except requests.exceptions.RequestException as e:
                    print(f"Error fetching tweets: {e}")
                    return {"error": "network_error"}

                # Exponential backoff for retries on same token
                time.sleep(delay * (2 ** attempt))
                
            # If we didn't hit rate limit or other error, then at least one token is available
            all_tokens_exhausted = False

        # If we went through all tokens and hit rate limits, wait for reset time of the first token
        if all_tokens_exhausted:
            reset_time = int(response.headers.get("x-rate-limit-reset", time.time() + delay))
            retry_in = reset_time - int(time.time())
            print(f"All tokens exhausted. Waiting {retry_in} seconds before retrying with first token.")
            time.sleep(retry_in)
    
    return {"error": "timeout"}

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/get_tweets', methods=['POST'])
def get_tweets():
    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({"error": "Username is required"}), 400

    # Rotate through tokens for the initial user ID lookup as well
    user_id = None
    for token in BEARER_TOKENS:
        user_id = get_user_id(username, token)
        if user_id:
            break
    if not user_id:
        return jsonify({"error": "User not found"}), 404

    # Fetch tweets with rotated tokens
    tweets = fetch_tweets_with_retry(user_id)
    if isinstance(tweets, dict) and "error" in tweets:
        return jsonify({"error": "API error occurred"}), 500

    # Return tweet data
    tweet_data = [
        {
            'id': tweet['id'],
            'text': tweet.get('text', ''),
            'created_at': tweet['created_at'],
            'username': username
        } for tweet in tweets
    ]
    return jsonify(tweet_data)

if __name__ == '__main__':
    app.run(debug=True)
