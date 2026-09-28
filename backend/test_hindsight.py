import os
from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

client = Hindsight(
    base_url="https://api.hindsight.vectorize.io",
    api_key=os.getenv("HINDSIGHT_API_KEY")
)

bank_id = "elderly-care"

client.retain(
    bank_id=bank_id,
    content="The elderly user usually eats idli for breakfast and does not like oats."
)

print("Memory stored successfully!")

memories = client.recall(
    bank_id=bank_id,
    query="What does the elderly user like to eat for breakfast?",
)

print("Recalled memory:")
print(memories)