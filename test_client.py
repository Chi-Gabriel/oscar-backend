# File: test_client.py

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables (optional, but good practice if you need config here)
load_dotenv()

# --- Configuration ---
# Make sure your Flask app is running!
BASE_URL = "http://127.0.0.1:5000" # Default Flask dev server address
CHAT_ENDPOINT = f"{BASE_URL}/api/chat/"

# --- Optional Context (Modify as needed for testing) ---
TEST_LOCATION = "Ibadan, Nigeria"
TEST_NPK = "N:20,P:15,K:10"
TEST_DATE = "2024-07-26"
# --- End Configuration ---

# File: test_client.py
# ... (keep existing imports and config) ...

RECOMMEND_ENDPOINT = f"{BASE_URL}/api/recommend/crops" # Add endpoint URL

def test_recommendations(location):
     """Tests the recommendation endpoint."""
     print(f"\nRequesting recommendations for: '{location}'...")
     payload = {"location": location}
     try:
         response = requests.post(RECOMMEND_ENDPOINT, json=payload)
         response.raise_for_status()
         data = response.json()

         if "error" in data:
             print(f"Backend Error: {data['error']}")
         else:
             recs = data.get("recommendations")
             if recs:
                 print("\n--- Crop Recommendations ---")
                 for crop, details in recs.items():
                     print(f"\nCrop: {crop}")
                     print(f"  Description: {details.get('description', 'N/A')}")
                     print(f"  Survivability: {details.get('survivability', 'N/A')}%")
                     print(f"  Challenges: {details.get('challenges', [])}")
                     print(f"  Reasons: {details.get('reasons', [])}")
                 print("-" * 26)
                 print(f"[Tokens: Input={data.get('_input_tokens', 0)}, Output={data.get('_output_tokens', 0)}]")
             else:
                 print("[No recommendations found in response]")

     except requests.exceptions.RequestException as e:
         print(f"\n[Request Error] Could not connect or communicate with the backend: {e}")
     except json.JSONDecodeError:
         print("\n[Error] Failed to decode JSON response from the backend.")
         print(f"Raw response text: {response.text[:200]}...")
     except Exception as e:
         print(f"\n[Unexpected Error]: {e}")


def main():
    """Runs the interactive chat test client."""
    print("Kapricorn Test Client")
    print("Commands:")
    print("  <your message> - Send chat message")
    print("  recommend <location> - Get crop recommendations (e.g., recommend Ames, Iowa)")
    print("  toggle_pro - Switch between free/pro chat model")
    print("  quit - Exit")
    print("-" * 30)

    chat_history = []
    use_pro_model = False

    while True:
        user_input = input("Enter command or message: ")
        user_input_lower = user_input.lower()

        if user_input_lower == 'quit':
            break
        elif user_input_lower == 'toggle_pro':
             use_pro_model = not use_pro_model
             print(f"[System] Pro model {'enabled' if use_pro_model else 'disabled'}. Next chat message will use this setting.")
             continue
        elif user_input_lower.startswith('recommend '):
             location_part = user_input[len('recommend '):].strip()
             if location_part:
                 test_recommendations(location_part)
             else:
                 print("[Usage] recommend <location description>")
             print("-" * 30)
             continue # Go back to prompt after recommendation test
        elif not user_input: # Handle empty input
             continue

        # --- Existing Chat Logic ---
        print(f"You: {user_input}") # Echo user chat message
        payload = {
            "message": user_input,
            "history": chat_history,
            "use_pro_model": use_pro_model,
            "location": TEST_LOCATION,
            "npk": TEST_NPK,
            "date": TEST_DATE,
        }

        try:
            response = requests.post(CHAT_ENDPOINT, json=payload)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                print(f"Backend Error: {data['error']}")
            else:
                ai_response = data.get("response", "[No response text found]")
                classification = data.get("classification", "N/A")
                visuals = data.get("visuals_data")

                print(f"\nOscar: {ai_response}")
                print(f"[Classification: {classification}]")

                if visuals:
                    print("[Visuals Data Received]:")
                    print(json.dumps(visuals, indent=2))
                    print("-" * 20)

                chat_history = data.get("history", [])

        # ... (keep existing error handling for chat) ...
        except requests.exceptions.RequestException as e:
            print(f"\n[Request Error] Could not connect or communicate with the backend: {e}")
        except json.JSONDecodeError:
             print("\n[Error] Failed to decode JSON response from the backend.")
             print(f"Raw response text: {response.text[:200]}...")
        except Exception as e:
            print(f"\n[Unexpected Error]: {e}")

        print("-" * 30)

if __name__ == "__main__":
    main()