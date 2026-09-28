import os
import json
import re

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from hindsight_client import Hindsight
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime


# ==================================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==================================================

load_dotenv()


# ==================================================
# 2. GROQ
# ==================================================

groq_client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)


# ==================================================
# 3. HINDSIGHT
# ==================================================

hindsight_client = Hindsight(
    base_url="https://api.hindsight.vectorize.io",
    api_key=os.getenv("HINDSIGHT_API_KEY")
)

BANK_ID = "elderly-care-demo"


# ==================================================
# 4. FASTAPI
# ==================================================

app = FastAPI()


# ==================================================
# 5. CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ==================================================
# 6. SCHEDULER
# ==================================================

scheduler = BackgroundScheduler()
scheduler.start()


# ==================================================
# 7. REQUEST MODEL
# ==================================================

class ChatRequest(BaseModel):
    message: str


# ==================================================
# 8. CURRENT USER PROFILE
# ==================================================

PROFILE_FILE = "user_profile.json"


def load_profile():

    if not os.path.exists(PROFILE_FILE):
        return {}

    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception:
        return {}


def save_profile(profile):

    with open(
        PROFILE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            profile,
            file,
            indent=4
        )


def update_profile_from_message(message):

    profile = load_profile()

    # ----------------------------------------------
    # NAME
    # ----------------------------------------------

    name_match = re.search(
        r"\bmy name is\s+([A-Za-z][A-Za-z\s'-]*?)(?:\s+now)?[.!?]?$",
        message.strip(),
        re.IGNORECASE
    )

    if name_match:

        name = name_match.group(1).strip()

        # Remove accidental extra words
        name = re.sub(
            r"\s+now$",
            "",
            name,
            flags=re.IGNORECASE
        ).strip()

        if name:
            profile["name"] = name


    # ----------------------------------------------
    # AGE
    # ----------------------------------------------

    age_match = re.search(
        r"\bI\s+am\s+(\d{1,3})\s+years?\s+old\b",
        message,
        re.IGNORECASE
    )

    if age_match:

        age = int(age_match.group(1))

        if 1 <= age <= 120:
            profile["age"] = age


    save_profile(profile)

    return profile


# ==================================================
# 9. HOME
# ==================================================

@app.get("/")
def home():

    return {
        "message": "Elderly AI Companion is running"
    }


# ==================================================
# 10. REMINDER FUNCTION
# ==================================================

def send_reminder(medicine):

    print(
        f"🔔 REMINDER: Time to take {medicine}"
    )


# ==================================================
# 11. CREATE DAILY REMINDER
# ==================================================

def create_daily_reminder(
    medicine,
    hour,
    minute
):

    scheduler.add_job(
        send_reminder,
        "cron",
        hour=hour,
        minute=minute,
        args=[medicine],
        id=f"medicine_{medicine}_{hour}_{minute}",
        replace_existing=True
    )

    print(
        f"✅ Daily reminder created for {medicine} "
        f"at {hour:02d}:{minute:02d}"
    )


# ==================================================
# 12. TEST REMINDER
# ==================================================

@app.post("/test-reminder")
def test_reminder():

    scheduler.add_job(
        send_reminder,
        "date",
        run_date=datetime.now(),
        args=["Metformin"]
    )

    return {
        "message": "Test reminder scheduled successfully"
    }


# ==================================================
# 13. CHAT
# ==================================================

@app.post("/chat")
def chat(request: ChatRequest):

    # ==================================================
    # A. UPDATE CURRENT PROFILE FIRST
    # ==================================================

    current_profile = update_profile_from_message(
        request.message
    )


    # ==================================================
    # B. RECALL HINDSIGHT MEMORY
    # ==================================================

    memory = hindsight_client.recall(
        bank_id=BANK_ID,
        query=request.message
    )

    recalled_memories = "\n".join(
        result.text
        for result in memory.results
    )


    # ==================================================
    # C. FORMAT CURRENT PROFILE
    # ==================================================

    profile_information = ""

    if current_profile:

        profile_information = json.dumps(
            current_profile,
            indent=2
        )

    else:

        profile_information = "No current profile information available."


    # ==================================================
    # D. GROQ RESPONSE
    # ==================================================

    prompt = f"""
You are an elderly-care AI companion.

CURRENT USER PROFILE:
{profile_information}

IMPORTANT:
The CURRENT USER PROFILE is the source of truth for
changeable information such as the user's name and age.

If Hindsight memory contains an older name or age that
conflicts with the CURRENT USER PROFILE, ALWAYS use the
CURRENT USER PROFILE.

Do not mention conflicting old information.

Relevant long-term information remembered from Hindsight:
{recalled_memories}

Current user message:
{request.message}


Your tasks:

1. Use remembered information only when relevant.

2. Use the CURRENT USER PROFILE for the user's current
   name and age.

3. If the user has explicitly changed their name,
   use the new name.

4. Never invent a name, age, medicine, dosage, time,
   or medical instruction.

5. Identify whether the user is simply providing information
   or explicitly asking for a reminder.

6. If the user explicitly asks for a reminder, clearly
   acknowledge the requested medicine, time, and frequency.

7. Never change a doctor's medication instruction.

8. If medication information is missing, ask the user for
   the missing information instead of guessing.

9. When answering questions about food preferences,
   only mention foods the user explicitly said they like
   or dislike.

10. Do not create new food restrictions.

11. Do not turn general medical or nutritional knowledge
    into personal instructions.

12. Clearly distinguish remembered user preferences from
    general suggestions.

13. For normal conversation, be friendly, simple,
    and respectful.

14. Never claim that a reminder was scheduled unless
    the scheduler was actually created successfully.
"""


    response = groq_client.chat.completions.create(

        model="openai/gpt-oss-120b",

        messages=[
            {
                "role": "system",
                "content": (
                    "You are an AI personal-care companion "
                    "for elderly users."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )


    agent_response = (
        response.choices[0]
        .message.content
    )


    # ==================================================
    # E. REMINDER DETECTION
    # ==================================================

    if "remind me" in request.message.lower():

        reminder_extraction = (
            groq_client.chat.completions.create(

                model="openai/gpt-oss-120b",

                messages=[
                    {
                        "role": "system",
                        "content": """
You extract reminder information ONLY
from the user's CURRENT MESSAGE.

IMPORTANT:

- Do NOT use Hindsight memory.
- Do NOT use previous messages.
- Do NOT guess missing information.

The CURRENT MESSAGE must explicitly contain:

1. Medicine name
2. Time
3. Frequency

Return ONLY:

MEDICINE|HOUR|MINUTE|FREQUENCY

Example:

Metformin|8|0|daily

If ANY required information is missing,
return exactly:

INVALID

Example:

Remind me to take my medicine.

must return:

INVALID

Do not add explanations.
"""
                    },
                    {
                        "role": "user",
                        "content": request.message
                    }
                ]
            )
        )


        reminder_data = (
            reminder_extraction
            .choices[0]
            .message
            .content
            .strip()
        )


        # ----------------------------------------------
        # VALID REMINDER
        # ----------------------------------------------

        if reminder_data != "INVALID":

            try:

                medicine, hour, minute, frequency = (
                    reminder_data.split("|")
                )

                hour = int(hour)
                minute = int(minute)


                if frequency.lower() == "daily":

                    create_daily_reminder(
                        medicine,
                        hour,
                        minute
                    )

                    agent_response = (
                        f"Your daily reminder for {medicine} "
                        f"at {hour:02d}:{minute:02d} "
                        f"has been scheduled."
                    )


            except (ValueError, TypeError):

                agent_response = (
                    "I could not understand the reminder details. "
                    "Please provide the medicine name, time, "
                    "and frequency."
                )


        # ----------------------------------------------
        # INVALID REMINDER
        # ----------------------------------------------

        else:

            agent_response = (
                "Sure. Please provide the medicine name, "
                "the time, and how often you want the reminder."
            )


    # ==================================================
    # F. MEMORY EXTRACTION
    # ==================================================

    memory_extraction = (
        groq_client.chat.completions.create(

            model="openai/gpt-oss-120b",

            messages=[
                {
                    "role": "system",
                    "content": """
You are a memory extraction system for an
elderly-care AI companion.

Extract ONLY stable, useful information that
belongs to the USER.

Good Hindsight memories include:

- Food likes
- Food dislikes
- Allergies explicitly stated by the user
- Regular daily routines
- Medication information explicitly stated by the user
- Medication schedules explicitly stated by the user
- Personal-care preferences
- Important long-term habits

Do NOT store:

- Assistant advice
- Assistant suggestions
- Assistant explanations
- Assistant questions
- Assistant offers
- Generic health advice
- Temporary conversation details
- Predictions or assumptions
- Information invented by the assistant
- Duplicate information
- The fact that a reminder was successfully scheduled

IMPORTANT:

Name and age are handled separately by the
CURRENT USER PROFILE system.

Do NOT store the user's name or age in Hindsight.

Only extract facts explicitly provided by the
USER'S CURRENT MESSAGE.

If the current message contains no useful long-term
Hindsight information, return exactly:

NONE

Return only the useful memory.
Do not add explanations.
"""
                },
                {
                    "role": "user",
                    "content": request.message
                }
            ]
        )
    )


    user_memory = (
        memory_extraction
        .choices[0]
        .message
        .content
        .strip()
    )


    # ==================================================
    # G. STORE HINDSIGHT MEMORY
    # ==================================================

    if user_memory != "NONE":

        hindsight_client.retain(
            bank_id=BANK_ID,
            content=user_memory
        )


    # ==================================================
    # H. RETURN RESULT
    # ==================================================

    return {

        "user_message": request.message,

        "agent_response": agent_response,

        "memory_used": recalled_memories,

        "current_profile": current_profile
    }