import google.generativeai as genai
import PIL.Image
import json

# Replace with your actual API Key
genai.configure(api_key="YOUR_GEMINI_API_KEY")

# 1. Setup the model with System Instructions for better accuracy
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config={"response_mime_type": "application/json"},
    system_instruction="You are a data extraction tool. You only output valid JSON. Extract market item names, prices, and price change percentages from the provided image."
)

def extract_market_data(image_path):
    img = PIL.Image.open(image_path)
    
    # Simple prompt - the System Instruction handles the logic
    prompt = """
    Return a JSON object with:
    - 'items': a list of objects containing 'name', 'price' (integer), and 'change' (string).
    - 'timer': the 'Next Price In' value as a string.
    """

    try:
        response = model.generate_content([prompt, img])
        # Because we set response_mime_type, we don't need to strip ```json anymore
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# Execute
data = extract_market_data('market_screenshot.png')
print(json.dumps(data, indent=2))