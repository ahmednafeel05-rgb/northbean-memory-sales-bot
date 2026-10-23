from google import genai

client = genai.Client(api_key="REDACTED")

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Reply with only: API works"
    )
    print("SUCCESS:", response.text)

except Exception as e:
    print("FAILED:", e)