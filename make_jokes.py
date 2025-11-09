import requests
import json
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Thread-safe lock for writing to file
file_lock = threading.Lock()

def fetch_jokes_for_category(model, category):
    """Fetch 3 jokes for a given model and category."""
    jokes = []
    for _ in range(3):
        try:
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": "",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Make a '{category}' joke."
                        }
                    ]
                }
            )
            jokes.append(response.json()['choices'][0]['message']['content'])
        except Exception as e:
            jokes.append(f"Error: {e}")
    return category, jokes

def process_model(model, categories, data):
    """Process all categories for a single model."""
    data[model] = {}
    
    # Process categories for this model (could be parallelized further if needed)
    for category in categories:
        category_name, jokes = fetch_jokes_for_category(model, category)
        data[model][category_name] = jokes
    
    print(f"Completed: {model}")
    print(data[model])
    
    # Thread-safe file writing
    with file_lock:
        with open('jokes.json', 'w', encoding="utf-8") as json_file:
            json.dump(data, json_file, indent=4, ensure_ascii=False)
    
    return model

# Load models and categories
with open('models.csv', 'r', encoding="utf-8") as csv_file:
    csv_content = csv.reader(csv_file, delimiter=',')
    models = [i[0] for i in csv_content]

with open('categories.csv', 'r', encoding="utf-8") as csv_file:
    csv_content = csv.reader(csv_file, delimiter=',')
    categories = [i[0] for i in csv_content]

# Shared data dictionary
data = {}

# Process models in parallel
max_workers = 5  # Adjust based on API rate limits
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(process_model, model, categories, data): model 
               for model in models}
    
    for future in as_completed(futures):
        model = futures[future]
        try:
            future.result()
        except Exception as e:
            print(f"Model {model} generated an exception: {e}")

print("All models processed!")