
import csv
from contextlib import contextmanager
from datetime import datetime, timezone
from io import StringIO
import json
import os
import re
import secrets
import traceback

import mysql.connector
import numpy as np
from flask import Flask, jsonify, redirect, request, session, send_from_directory, abort
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from app_config import get_allowed_origins

TOTAL_PROGRAM_WEEKS = 8
MAX_WEEKLY_PASSAGES_PER_CLASS = 3

DB_HOST = os.environ.get("READWISE_DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("READWISE_DB_PORT", "3306"))
DB_USER = os.environ.get("READWISE_DB_USER", "root")
DB_PASSWORD = os.environ.get("READWISE_DB_PASSWORD", "")
DB_NAME = os.environ.get("READWISE_DB_NAME", "readwise_db")
PRESET_AVATAR_PATTERN = re.compile(r"^/(?:[A-Za-z0-9._-]+/)?avatar/[A-Za-z0-9 _().-]+\.svg$")

if not re.fullmatch(r"[A-Za-z0-9_]+", DB_NAME):
    raise RuntimeError("Invalid READWISE_DB_NAME")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_prefix=1)
IS_PRODUCTION = os.environ.get("READWISE_ENV") == "production"

SECRET_KEY = os.environ.get("READWISE_SECRET_KEY")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError("READWISE_SECRET_KEY must be set when READWISE_ENV=production")
    SECRET_KEY = "readwise-dev-secret-change-me"

app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="None" if IS_PRODUCTION else "Lax",
    SESSION_COOKIE_SECURE=IS_PRODUCTION,
)

origins_list = get_allowed_origins(IS_PRODUCTION)

CORS(
    app,
    supports_credentials=True,
    origins=origins_list,
    allow_headers=["Content-Type", "X-Auth-Token", "Authorization"],
)

DB_POOL = None
DB_READY = False

SEED_ADMINS = [
    {"email": "admin@pnhs.edu", "password": "admin123"},
]

SEED_TEACHERS = [
    {"email": "ms.villanueva@pnhs.edu", "password": "teacher123"},
    {"email": "teacher@example.com", "password": "abcd"},
]

SEED_STUDENTS = [
    {"id": "s1", "email": "juan.delacruz@pnhs.edu", "password": "password123", "name": "Juan Dela Cruz", "grade": "7", "section": "MAKADIYOS", "class": "HARD", "pre": 58},
    {"id": "s2", "email": "maria.santos@pnhs.edu", "password": "password123", "name": "Maria Santos", "grade": "7", "section": "MAKADIYOS", "class": "MODERATE", "pre": 72},
    {"id": "s3", "email": "carlo.reyes@pnhs.edu", "password": "password123", "name": "Carlo Reyes", "grade": "7", "section": "MAKADIYOS", "class": "EASY", "pre": 45},
    {"id": "s4", "email": "new.student@pnhs.edu", "password": "password123", "name": "New Student", "grade": "7", "section": "MAKADIYOS", "class": "EASY", "pre": 0},
    {"id": "s5", "email": "lea.garcia@pnhs.edu", "password": "password123", "name": "Lea Garcia", "grade": "7", "section": "Rosal", "class": "MODERATE", "pre": 64},
    {"id": "s6", "email": "paolo.mendoza@pnhs.edu", "password": "password123", "name": "Paolo Mendoza", "grade": "7", "section": "Rosal", "class": "HARD", "pre": 81},
    {"id": "s7", "email": "trisha.navarro@pnhs.edu", "password": "password123", "name": "Trisha Navarro", "grade": "7", "section": "Rosal", "class": "EASY", "pre": 43},
    {"id": "s8", "email": "adrian.lopez@pnhs.edu", "password": "password123", "name": "Adrian Lopez", "grade": "7", "section": "Makahiya", "class": "MODERATE", "pre": 59},
    {"id": "s9", "email": "bea.cortez@pnhs.edu", "password": "password123", "name": "Bea Cortez", "grade": "7", "section": "Makahiya", "class": "HARD", "pre": 74},
    {"id": "s10", "email": "noah.flores@pnhs.edu", "password": "password123", "name": "Noah Flores", "grade": "7", "section": "Makahiya", "class": "EASY", "pre": 0},
    {"id": "s11", "email": "jamie.ong@pnhs.edu", "password": "password123", "name": "Jamie Ong", "grade": "7", "section": "MAKADIYOS", "class": "EASY", "pre": 0},
    {
        "id": "s12",
        "email": "ella.mendoza@pnhs.edu",
        "password": "password123",
        "name": "Ella Mendoza",
        "grade": "7",
        "section": "Jasmin",
        "class": "EASY",
        "pre": 86
    },
    {
        "id": "s13",
        "email": "miguel.ramos@pnhs.edu",
        "password": "password123",
        "name": "Miguel Ramos",
        "grade": "7",
        "section": "Jasmin",
        "class": "MODERATE",
        "pre": 67
    },
    {
        "id": "s14",
        "email": "sofia.bautista@pnhs.edu",
        "password": "password123",
        "name": "Sofia Bautista",
        "grade": "7",
        "section": "Jasmin",
        "class": "HARD",
        "pre": 51
    },
    {
        "id": "s15",
        "email": "nico.villareal@pnhs.edu",
        "password": "password123",
        "name": "Nico Villareal",
        "grade": "7",
        "section": "Jasmin",
        "class": "EASY",
        "pre": 0
    },
    {
        "id": "s16",
        "email": "elaira@pnhs.edu",
        "password": "password123",
        "name": "elle laira",
        "grade": "7",
        "section": "Jasmin",
        "class": "EASY",
        "pre": 0
    },
    {
        "id": "s17",
        "email": "mamfe@pnhs.edu",
        "password": "password123",
        "name": "Nico Villareal",
        "grade": "7",
        "section": "Jasmin",
        "class": "EASY",
        "pre": 0
    }
    ,
     {
        "id": "s18",
        "email": "mamfe1@pnhs.edu",
        "password": "password123",
        "name": "Nico Villareal",
        "grade": "7",
        "section": "Jasmin",
        "class": "EASY",
        "pre": 0
    }
    ,{
        "id": "s19",
        "email": "mamfe2@pnhs.edu",
        "password": "password123",
        "name": "Nico Villareal",
        "grade": "7",
        "section": "Jasmin",
        "class": "EASY",
        "pre": 0
    }
    ,{
            "id": "s20",
            "email": "mamfe334@pnhs.edu",
            "password": "password123",
            "name": "fehablids",
            "grade": "7",
            "section": "ccs",
            "class": "HARD",
            "pre": 0
        }
]

SEED_PASSAGES = [
    {"id": "p1", "title": "The Water Cycle", "genre": "Expository", "label": "EASY", "text": "Water evaporates, condenses into clouds, and returns as rain."},
    {"id": "p2", "title": "The Life of Jose Rizal", "genre": "Narrative", "label": "MODERATE", "text": "Jose Rizal wrote novels that inspired Filipino nationalism."},
    {"id": "p3", "title": "Climate Change and Its Effects", "genre": "Expository", "label": "HARD", "text": "Climate change increases risks like stronger storms and sea-level rise."},
    {"id": "p4", "title": "The Little Prince Summary", "genre": "Narrative", "label": "EASY", "text": "The Little Prince teaches readers about friendship and love."},
    {"id": "p5", "title": "Philippine Biodiversity", "genre": "Expository", "label": "MODERATE", "text": "The Philippines has many endemic species that need protection."},
    {"id": "p6", "title": "Constitutional Rights of Citizens", "genre": "Expository", "label": "HARD", "text": "The Constitution protects rights like due process and free expression."},
    {"id": "p7", "title": "The School Garden", "genre": "Narrative", "label": "EASY", "text": "Our class started a school garden project behind the science building. On the first day, we cleaned the area, removed stones, and prepared planting boxes. We planted tomatoes, pechay, and spring onions in separate rows so we could compare how each plant grows. Every morning before class, two assigned classmates watered the plants while others checked the soil and removed weeds. Our teacher taught us how sunlight, water, and healthy soil help plants grow. After a few weeks, we noticed tiny leaves becoming thicker and greener. We wrote our weekly observations in a garden notebook and measured the height of the plants every Friday. By the second month, we harvested enough vegetables to share with the canteen and bring some home. Through this project, we learned teamwork, patience, and responsibility. We also understood that growing food requires planning, care, and cooperation."},
    {"id": "p8", "title": "A Day at the Library", "genre": "Narrative", "label": "EASY", "text": "Maria visited the school library to complete her science assignment about volcanoes and earthquakes. At first, she felt overwhelmed because there were many shelves and reference books. The librarian guided her to the science section and helped her choose three books and one magazine that matched her topic. Maria read the table of contents first so she could focus on the most useful chapters. She wrote key ideas in her notebook and copied definitions of important terms like crater, magma, and eruption. She also compared two diagrams that explained how tectonic plates move. During break time, she reviewed her notes and organized them into bullet points for her report. Before leaving, she returned the books properly and thanked the librarian for the help. On her way home, Maria felt more confident because she had complete, reliable information. She realized that the library is a helpful place for studying and preparing well-researched school work."},
    {"id": "p9", "title": "Why We Wash Hands", "genre": "Expository", "label": "EASY", "text": "Handwashing is one of the simplest and most effective ways to protect our health. Our hands touch many surfaces every day, such as doorknobs, classroom desks, railings, and gadgets. These surfaces may carry germs that can enter our body when we touch our eyes, nose, or mouth. Washing hands with soap and clean running water helps remove dirt, oil, and harmful microorganisms. Health experts recommend washing before eating, after using the restroom, after coughing or sneezing, and after playing outside. Proper handwashing should last at least twenty seconds and include cleaning between fingers, under nails, and the back of the hands. In schools, regular handwashing can reduce the spread of colds, cough, and stomach-related illnesses, which helps students stay healthy and attend classes consistently. Hand hygiene is a small daily habit, but it has a big impact on personal and community health."},
    {"id": "p10", "title": "The Rice Plant", "genre": "Expository", "label": "EASY", "text": "Farmers prepare the field before planting rice seedlings. The plants grow best with enough sunlight and water. After several months, the grains turn golden and are ready to harvest and dry."},
    {"id": "p11", "title": "Typhoon Preparedness at Home", "genre": "Expository", "label": "MODERATE", "text": "Families can reduce typhoon risks by preparing emergency kits, securing important documents, and identifying safe evacuation routes. Listening to weather bulletins and following local government advisories helps communities respond quickly when storms intensify."},
    {"id": "p12", "title": "The Story of Lapu-Lapu", "genre": "Narrative", "label": "MODERATE", "text": "Lapu-Lapu, a chieftain of Mactan, became known for resisting foreign forces during the Battle of Mactan in 1521. His leadership is remembered as a symbol of courage, local sovereignty, and early resistance in Philippine history."},
    {"id": "p13", "title": "Mangrove Forests and Coastal Protection", "genre": "Expository", "label": "MODERATE", "text": "Mangrove forests protect shorelines by reducing wave energy and helping prevent soil erosion. Their roots also serve as breeding grounds for fish and crabs. Conserving mangroves supports both biodiversity and coastal livelihoods."},
    {"id": "p14", "title": "Digital Citizenship and Online Safety", "genre": "Expository", "label": "HARD", "text": "Responsible digital citizenship involves evaluating online sources, protecting personal data, and communicating respectfully across platforms. Learners should recognize misinformation patterns, report harmful content, and use privacy controls to reduce exposure to cyber threats."},
    {"id": "p15", "title": "Renewable Energy Choices for Communities", "genre": "Expository", "label": "HARD", "text": "Community energy planning requires balancing environmental benefits, infrastructure costs, and long-term reliability. While solar and wind reduce carbon emissions, policy design, grid modernization, and storage technology influence whether transitions remain equitable and sustainable."},
    {"id": "p16", "title": "Constitutional Checks and Balances", "genre": "Expository", "label": "HARD", "text": "Checks and balances distribute governmental authority across branches so no institution can dominate decision-making. Judicial review, legislative oversight, and executive veto powers create procedural friction intended to protect constitutional order and civil liberties."},
]

def seed_mc(difficulty, prompt, options, answer_index):
    return {
        "difficulty": difficulty,
        "type": "multiple_choice" if difficulty == "EASY" else "multiple_choice_harder",
        "prompt": prompt,
        "options": options,
        "answerIndex": answer_index,
    }


def seed_tf(difficulty, prompt, answer_key):
    return {
        "difficulty": difficulty,
        "type": "true_false" if difficulty == "EASY" else "true_false_modified",
        "prompt": prompt,
        "answerKey": answer_key,
    }


def seed_sequence(prompt, answer_keys):
    return {
        "difficulty": "MODERATE",
        "type": "sequence",
        "prompt": prompt,
        "options": list(answer_keys),
        "answerKeys": list(answer_keys),
    }


def seed_identification(prompt, answer_keys):
    return {
        "difficulty": "DIFFICULT",
        "type": "identification",
        "prompt": prompt,
        "answerKeys": list(answer_keys),
    }


def seed_fill_blank(prompt, answer_keys):
    return {
        "difficulty": "DIFFICULT",
        "type": "fill_in_the_blanks",
        "prompt": prompt,
        "answerKeys": list(answer_keys),
    }


def seed_enumeration(prompt, answer_keys):
    return {
        "difficulty": "DIFFICULT",
        "type": "enumeration",
        "prompt": prompt,
        "answerKeys": list(answer_keys),
    }


SEED_ASSESSMENTS = {
    "p1": {"questions": [
        seed_mc("EASY", "What process changes liquid water into water vapor?", ["Condensation", "Evaporation", "Runoff", "Precipitation"], 1),
        seed_tf("EASY", "Clouds form when water vapor cools and condenses.", "true"),
        seed_mc("EASY", "What do we call water that soaks into the ground?", ["Runoff", "Precipitation", "Groundwater", "Fog"], 2),
    ], "shortAnswerPrompt": ""},
    "p2": {"questions": [
        seed_mc("MODERATE", "Where was Jose Rizal born?", ["Manila", "Calamba, Laguna", "Baguio", "Cebu"], 1),
        seed_tf("MODERATE", "Rizal continued some of his studies in Spain.", "true"),
        seed_sequence("Arrange these events from Rizal's life in the order they appear in the passage.", ["Studied at Ateneo Municipal", "Pursued medicine and studies abroad", "Published Noli Me Tangere and El Filibusterismo"]),
    ], "shortAnswerPrompt": ""},
    "p3": {"questions": [
        seed_identification("Which greenhouse gas is specifically named in the passage?", ["carbon dioxide", "co2"]),
        seed_fill_blank("The greenhouse effect traps heat in the ______.", ["atmosphere"]),
        seed_enumeration("Name two climate-related risks mentioned in the passage.", ["sea-level rise", "stronger tropical cyclones"]),
    ], "shortAnswerPrompt": "In your own words, explain one effect of climate change on the Philippines."},
    "p4": {"questions": [
        seed_mc("EASY", "What lesson does the fox teach the little prince?", ["Money solves problems", "One sees clearly only with the heart", "Adults are always right", "Travel is better than friendship"], 1),
        seed_tf("EASY", "The little prince meets the pilot in the desert.", "true"),
        seed_mc("EASY", "What living thing does the little prince care for on his home planet?", ["A tree", "A fox", "A single rose", "A sheep"], 2),
    ], "shortAnswerPrompt": ""},
    "p5": {"questions": [
        seed_mc("MODERATE", "The Philippines is identified as one of how many megadiverse countries?", ["10", "17", "25", "30"], 1),
        seed_tf("MODERATE", "The Philippine eagle is an endemic species mentioned in the passage.", "true"),
        seed_sequence("Arrange these ecosystems in the same order used in the passage.", ["Tropical rainforests", "Mangroves", "Coral reefs"]),
    ], "shortAnswerPrompt": ""},
    "p6": {"questions": [
        seed_identification("Which article of the Constitution contains the Bill of Rights?", ["article iii", "article 3", "iii"]),
        seed_fill_blank("No person shall be deprived of life, liberty, or property without ______ process of law.", ["due", "due process"]),
        seed_enumeration("Name two rights mentioned in the passage.", ["freedom of speech", "right to counsel"]),
    ], "shortAnswerPrompt": "Explain what due process of law means in your own words."},
    "p7": {"questions": [
        seed_mc("EASY", "What vegetables did the class plant in the school garden?", ["Tomatoes and pechay", "Eggplant and corn", "Onions and garlic", "Cabbage and carrots"], 0),
        seed_tf("EASY", "The class harvested the vegetables after two months.", "true"),
        seed_mc("EASY", "Who received some of the harvested vegetables?", ["The principal", "The librarian", "The canteen", "The barangay captain"], 2),
    ], "shortAnswerPrompt": ""},
    "p8": {"questions": [
        seed_mc("EASY", "Why did Maria visit the school library?", ["To find books about volcanoes", "To play games", "To practice singing", "To buy school supplies"], 0),
        seed_tf("EASY", "Maria returned the books before going home.", "true"),
        seed_mc("EASY", "Where did Maria write her important notes?", ["On a poster", "In her notebook", "On the wall", "In a newspaper"], 1),
    ], "shortAnswerPrompt": ""},
    "p9": {"questions": [
        seed_mc("EASY", "What removes dirt and germs from our hands?", ["Soap", "Oil", "Dust", "Paper"], 0),
        seed_tf("EASY", "Clean hands can help prevent stomach sickness.", "true"),
        seed_mc("EASY", "When should we wash our hands?", ["Only after sleeping", "Before eating and after using the restroom", "Only on weekends", "Only after class pictures"], 1),
    ], "shortAnswerPrompt": ""},
    "p10": {"questions": [
        seed_mc("EASY", "What do farmers plant in the field?", ["Rice seedlings", "Mango trees", "Corn cobs", "Coconut shells"], 0),
        seed_tf("EASY", "Rice plants grow best without water.", "false"),
        seed_mc("EASY", "What happens to the grains before harvest?", ["They turn golden", "They become blue", "They disappear", "They float away"], 0),
    ], "shortAnswerPrompt": ""},
    "p11": {"questions": [
        seed_mc("MODERATE", "Which action helps families prepare for stronger storms?", ["Ignoring local warnings", "Preparing emergency kits", "Leaving documents outside", "Waiting for rumors"], 1),
        seed_tf("MODERATE", "Listening to weather bulletins can help communities respond quickly.", "true"),
        seed_sequence("Arrange these preparedness actions in a practical order.", ["Prepare an emergency kit", "Secure important documents", "Review evacuation routes"]),
    ], "shortAnswerPrompt": ""},
    "p12": {"questions": [
        seed_mc("MODERATE", "For what is Lapu-Lapu remembered in the passage?", ["Writing a constitution", "Leading resistance in Mactan", "Serving as governor-general", "Building a Spanish fort"], 1),
        seed_tf("MODERATE", "The passage presents Lapu-Lapu as a symbol of courage and local sovereignty.", "true"),
        seed_sequence("Arrange these events in the order described in the passage.", ["Foreign forces arrived in Mactan", "The Battle of Mactan happened in 1521", "Lapu-Lapu was remembered as a symbol of resistance"]),
    ], "shortAnswerPrompt": ""},
    "p13": {"questions": [
        seed_mc("MODERATE", "What do mangrove roots provide for fish and crabs?", ["A place to dry", "Breeding grounds", "More waves", "Less food"], 1),
        seed_tf("MODERATE", "Mangroves help reduce soil erosion.", "true"),
        seed_sequence("Arrange these mangrove benefits in the same order used in the passage.", ["Reduce wave energy", "Help prevent soil erosion", "Support fish and crab breeding grounds"]),
    ], "shortAnswerPrompt": ""},
    "p14": {"questions": [
        seed_identification("What should students protect when practicing responsible digital citizenship?", ["personal data", "personal information"]),
        seed_fill_blank("Students should use privacy ______ to reduce exposure to cyber threats.", ["controls", "settings"]),
        seed_enumeration("Name two responsible online actions mentioned in the passage.", ["evaluating online sources", "reporting harmful content"]),
    ], "shortAnswerPrompt": "Give one example of how a student can verify online information before sharing it."},
    "p15": {"questions": [
        seed_identification("What kind of technology is named as part of renewable energy transitions?", ["storage technology", "energy storage"]),
        seed_fill_blank("Solar and wind can reduce ______ emissions.", ["carbon", "carbon emissions"]),
        seed_enumeration("Name two factors communities should consider in energy planning.", ["infrastructure costs", "long-term reliability"]),
    ], "shortAnswerPrompt": "Why should communities consider both cost and sustainability when choosing energy sources?"},
    "p16": {"questions": [
        seed_identification("Which branch power can stop a bill through a veto?", ["executive", "executive branch"]),
        seed_fill_blank("Checks and balances are meant to protect constitutional ______.", ["order"]),
        seed_enumeration("Name two examples of checks and balances mentioned in the passage.", ["judicial review", "legislative oversight"]),
    ], "shortAnswerPrompt": "Explain one real-life situation where checks and balances can protect citizens."},
}

QUESTION_TYPES_BY_DIFFICULTY = {
    "EASY": {"multiple_choice", "true_false"},
    "MODERATE": {"multiple_choice_harder", "true_false_modified", "sequence"},
    "DIFFICULT": {"fill_in_the_blanks", "identification", "enumeration"},
    "CUSTOM": {"custom"},
}


def api_ok(data=None, status=200):
    return jsonify({"ok": True, "data": data}), status


def api_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def normalize_class_level(value):
    v = str(value or "").strip().upper()
    if v == "MEDIUM":
        return "MODERATE"
    if v == "DIFFICULT":
        return "HARD"
    return v if v in {"EASY", "MODERATE", "HARD"} else "EASY"


def classify_pre_assessment_level(score):
    try:
        normalized_score = int(score)
    except (TypeError, ValueError):
        normalized_score = 0
    normalized_score = max(0, min(100, normalized_score))
    if normalized_score >= 80:
        return "HARD"
    if normalized_score >= 60:
        return "MODERATE"
    return "EASY"


def normalize_question_difficulty(value):
    level = str(value or "").strip().upper()
    if level == "MEDIUM":
        return "MODERATE"
    if level == "HARD":
        return "DIFFICULT"
    if level in QUESTION_TYPES_BY_DIFFICULTY:
        return level
    return "EASY"


def map_passage_label_to_question_difficulty(label):
    class_level = normalize_class_level(label)
    return "DIFFICULT" if class_level == "HARD" else class_level


def display_question_difficulty(level):
    normalized = normalize_question_difficulty(level)
    return "Difficult" if normalized == "DIFFICULT" else normalized.title()


def normalize_string_list(values):
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def parse_delimited_answers(value, delimiter):
    return [item.strip() for item in str(value or "").split(delimiter) if item.strip()]


def parse_csv_assessment_questions(row, default_question_difficulty):
    questions = []
    for index in range(1, 11):
        prompt = str(row.get(f"q{index}_prompt") or "").strip()
        qtype = str(row.get(f"q{index}_type") or "").strip().lower()
        options_raw = str(row.get(f"q{index}_options") or "").strip()
        answer_index_raw = str(row.get(f"q{index}_answerindex") or "").strip()
        answer_key = str(row.get(f"q{index}_answerkey") or "").strip()
        answer_keys_raw = str(row.get(f"q{index}_answerkeys") or "").strip()

        if not prompt and not qtype and not options_raw and not answer_index_raw and not answer_key and not answer_keys_raw:
            continue

        question = {
            "difficulty": normalize_question_difficulty(default_question_difficulty),
            "type": qtype or "",
            "prompt": prompt,
        }

        if options_raw:
            question["options"] = parse_delimited_answers(options_raw, "|")

        if answer_index_raw:
            try:
                question["answerIndex"] = int(answer_index_raw)
            except (TypeError, ValueError):
                question["answerIndex"] = 0

        if answer_key:
            question["answerKey"] = answer_key

        if answer_keys_raw:
            delimiter = "|" if "|" in answer_keys_raw else ","
            question["answerKeys"] = parse_delimited_answers(answer_keys_raw, delimiter)

        questions.append(question)

    return questions


def normalize_assessment_payload(assessment, passage_label, allow_empty=False):
    payload = assessment if isinstance(assessment, dict) else {}
    raw_questions = payload.get("questions") if isinstance(payload.get("questions"), list) else []
    short_answer = str(payload.get("shortAnswerPrompt") or payload.get("shortAnswer") or "").strip()
    expected_difficulty = map_passage_label_to_question_difficulty(passage_label)
    allowed_types = QUESTION_TYPES_BY_DIFFICULTY[expected_difficulty]
    normalized_questions = []

    for index, raw_question in enumerate(raw_questions, start=1):
        question = raw_question if isinstance(raw_question, dict) else {}
        prompt = str(question.get("prompt") or question.get("q") or "").strip()
        if not prompt:
            raise ValueError(f"Question {index} is missing a prompt.")

        difficulty = normalize_question_difficulty(question.get("difficulty") or expected_difficulty)
        if difficulty != expected_difficulty:
            raise ValueError(
                f"Question {index} must use {display_question_difficulty(expected_difficulty)} difficulty."
            )

        question_type = str(question.get("type") or "").strip().lower()
        if not question_type:
            if expected_difficulty == "EASY":
                question_type = "multiple_choice"
            elif expected_difficulty == "MODERATE":
                question_type = "multiple_choice_harder"
            else:
                question_type = "fill_in_the_blanks"

        if question_type not in allowed_types:
            allowed_display = ", ".join(sorted(allowed_types))
            raise ValueError(
                f"Question {index} uses an invalid type for {display_question_difficulty(expected_difficulty)} passages. "
                f"Allowed types: {allowed_display}."
            )

        options = question.get("options") if isinstance(question.get("options"), list) else question.get("opts")
        options = [str(item).strip() for item in options] if isinstance(options, list) else []

        answer_keys = (
            normalize_string_list(question.get("answerKeys"))
            if isinstance(question.get("answerKeys"), list)
            else normalize_string_list(question.get("answer_keys"))
        )
        answer_key = str(question.get("answerKey") or question.get("answer_key") or question.get("answer") or "").strip()
        answer_index = question.get("answerIndex", question.get("ans", 0))
        try:
            answer_index = int(answer_index)
        except (TypeError, ValueError):
            answer_index = 0

        normalized_question = {
            "difficulty": difficulty,
            "type": question_type,
            "prompt": prompt,
            "options": [],
            "answerIndex": 0,
            "answerKey": "",
            "answerKeys": [],
        }

        if question_type in {"multiple_choice", "multiple_choice_harder"}:
            cleaned_options = [item for item in options[:4] if item]
            if len(cleaned_options) != 4:
                raise ValueError(f"Question {index} needs exactly 4 answer options.")
            if answer_index < 0 or answer_index > 3:
                raise ValueError(f"Question {index} must have a valid correct option.")
            normalized_question["options"] = cleaned_options
            normalized_question["answerIndex"] = answer_index
        elif question_type in {"true_false", "true_false_modified"}:
            normalized_question["answerKey"] = "false" if answer_key.lower() == "false" else "true"
            if question_type == "true_false_modified":
                if not answer_keys:
                    answer_keys = parse_delimited_answers(
                        question.get("correctionAnswer") or question.get("correction"),
                        "|",
                    )
                if normalized_question["answerKey"] == "false" and not answer_keys:
                    raise ValueError(
                        f"Question {index} needs the corrected answer for a false statement."
                    )
                normalized_question["answerKeys"] = answer_keys
        elif question_type == "sequence":
            cleaned_options = [item for item in options if item]
            if len(cleaned_options) < 3:
                raise ValueError(f"Question {index} needs at least 3 sequence items.")
            if not answer_keys:
                answer_keys = parse_delimited_answers(answer_key, ",")
            if len(answer_keys) < 3:
                raise ValueError(f"Question {index} needs a complete sequence answer.")
            normalized_question["options"] = cleaned_options
            normalized_question["answerKeys"] = answer_keys
        elif question_type == "enumeration":
            if not answer_keys:
                answer_keys = parse_delimited_answers(answer_key, ",")
            if len(answer_keys) < 2:
                raise ValueError(f"Question {index} needs at least 2 expected answers.")
            normalized_question["answerKeys"] = answer_keys
        else:
            if not answer_keys:
                answer_keys = parse_delimited_answers(answer_key, "|")
            if not answer_keys:
                raise ValueError(f"Question {index} needs at least 1 accepted answer.")
            normalized_question["answerKeys"] = answer_keys

        normalized_questions.append(normalized_question)

    if not normalized_questions and not allow_empty:
        raise ValueError("Add at least 1 complete assessment question.")

    return {"questions": normalized_questions, "shortAnswerPrompt": short_answer}


def normalize_avatar_type(value):
    v = str(value or "initials").strip().lower()
    return v if v in {"initials", "preset", "upload"} else None


def sanitize_avatar_value(avatar_type, value):
    if avatar_type == "initials":
        return None

    avatar_value = str(value or "").strip()
    if not avatar_value:
        raise ValueError("avatarValue is required.")

    if avatar_type == "preset":
        if not PRESET_AVATAR_PATTERN.fullmatch(avatar_value):
            raise ValueError("Invalid preset avatar.")
        return avatar_value

    if avatar_type == "upload":
        if not avatar_value.startswith("data:image/"):
            raise ValueError("Invalid uploaded avatar.")
        if len(avatar_value) > 8_000_000:
            raise ValueError("Uploaded avatar is too large.")
        return avatar_value

    raise ValueError("Invalid avatarType.")


def normalize_week(value):
    try:
        week = int(value)
    except (TypeError, ValueError):
        return 1
    return min(TOTAL_PROGRAM_WEEKS, max(1, week))


def parse_program_start_date(value):
    if hasattr(value, "strftime"):
        return value
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_active_week_from_start(program_start_date):
    start_date = parse_program_start_date(program_start_date)
    today = datetime.now(timezone.utc).date()
    delta_days = (today - start_date).days
    if delta_days <= 0:
        return 1
    computed = (delta_days // 7) + 1
    return min(TOTAL_PROGRAM_WEEKS, max(1, computed))


def get_program_settings(cur):
    cur.execute(
        "SELECT id, program_start_date, manual_override_week, updated_by, updated_at FROM program_settings WHERE id=1"
    )
    row = cur.fetchone()
    if not row:
        return None
    override_week = row.get("manual_override_week")
    active_week = normalize_week(override_week) if override_week is not None else compute_active_week_from_start(row.get("program_start_date"))
    return {
        "programStartDate": row.get("program_start_date").isoformat() if row.get("program_start_date") else None,
        "manualOverrideWeek": int(override_week) if override_week is not None else None,
        "activeWeek": active_week,
        "updatedBy": row.get("updated_by"),
        "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
    }


def count_words(text):
    return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", str(text or "")))


def estimate_minutes(words):
    return max(1, int(np.ceil((words or 0) / 80.0)))


def average_numbers(values):
    cleaned = []
    for value in values:
        if value is None:
            continue
        try:
            cleaned.append(float(value))
        except (TypeError, ValueError):
            continue
    if not cleaned:
        return None
    return int(round(sum(cleaned) / len(cleaned)))


def mysql_config(include_db=True):
    cfg = {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "charset": "utf8mb4",
        "use_unicode": True,
    }
    if include_db:
        cfg["database"] = DB_NAME
    return cfg


@contextmanager
def db_cursor(dictionary=False):
    schema_only = os.environ.get("READWISE_SCHEMA_ONLY") == "1"
    conn = mysql.connector.connect(**mysql_config(True), autocommit=schema_only)
    cur = conn.cursor(dictionary=dictionary)
    try:
        yield conn, cur
        if not schema_only:
            conn.commit()
    except Exception:
        if not schema_only:
            conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def fetch_user_by_id(cur, user_id):
    cur.execute(
        """
        SELECT u.id,u.email,u.role,u.is_active,
               s.id AS student_id,s.full_name,s.grade,s.section,s.class_level,s.pre_score,s.pre_assessment_completed,
               s.avatar_type,s.avatar_value
        FROM users u LEFT JOIN students s ON s.user_id=u.id
        WHERE u.id=%s
        """,
        (user_id,),
    )
    return cur.fetchone()


def get_request_token():
    header_token = str(request.headers.get("X-Auth-Token") or "").strip()
    if header_token:
        return header_token
    auth_header = str(request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()
        if bearer_token:
            return bearer_token
    return None


def current_user():
    uid = session.get("user_id")
    if uid:
        with db_cursor(True) as (_, cur):
            row = fetch_user_by_id(cur, uid)
            if row and row.get("is_active"):
                return row

    token = get_request_token()
    if token:
        with db_cursor(True) as (_, cur):
            cur.execute(
                """
                SELECT u.id,u.email,u.role,u.is_active,
                       s.id AS student_id,s.full_name,s.grade,s.section,
                       s.class_level,s.pre_score,s.pre_assessment_completed,s.avatar_type,s.avatar_value
                FROM auth_tokens t
                JOIN users u ON u.id=t.user_id
                LEFT JOIN students s ON s.user_id=u.id
                WHERE t.token=%s
                """,
                (token,),
            )
            row = cur.fetchone()
            if row and row.get("is_active"):
                return row

    return None


def require_auth():
    user = current_user()
    if not user:
        return None, api_error("Authentication required.", 401)
    return user, None


def require_role(role):
    user, err = require_auth()
    if err:
        return None, err
    if user["role"] != role:
        return None, api_error("Insufficient permissions.", 403)
    return user, None


def serialize_user(row):
    student = None
    if row.get("student_id"):
        student = {
            "id": row["student_id"],
            "name": row.get("full_name"),
            "grade": row.get("grade"),
            "section": row.get("section"),
            "classLevel": row.get("class_level"),
            "preScore": row.get("pre_score"),
            "preAssessmentCompleted": bool(int(row.get("pre_assessment_completed") or 0)),
            "avatarType": row.get("avatar_type") or "initials",
            "avatarValue": row.get("avatar_value") or "",
        }
    return {"id": row["id"], "email": row["email"], "role": row["role"], "student": student}


def parse_json(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return fallback
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def serialize_passage(row):
    confidence = float(row["confidence"]) if row.get("confidence") is not None else None
    return {
        "id": row["id"],
        "title": row["title"],
        "genre": row["genre"],
        "text": row["text"],
        "label": row["label"],
        "words": int(row["words"]),
        "time": int(row["est_minutes"]),
        "confidence": confidence,
        "isDraft": bool(int(row.get("is_draft") or 0)),
    }


def fetch_assessment(cur, passage_id):
    cur.execute("SELECT id, short_answer_prompt FROM assessments WHERE passage_id=%s", (passage_id,))
    a = cur.fetchone()
    if not a:
        return {"questions": [], "shortAnswerPrompt": ""}
    cur.execute(
        """
        SELECT difficulty,type,prompt,options_json,answer_index,answer_key,answer_keys_json
        FROM assessment_questions WHERE assessment_id=%s ORDER BY sort_order,id
        """,
        (a["id"],),
    )
    questions = []
    for q in cur.fetchall():
        questions.append(
            {
                "difficulty": q["difficulty"],
                "type": q["type"],
                "prompt": q["prompt"],
                "options": parse_json(q.get("options_json"), []),
                "answerIndex": int(q.get("answer_index") or 0),
                "answerKey": q.get("answer_key") or "",
                "answerKeys": parse_json(q.get("answer_keys_json"), []),
            }
        )
    return {"questions": questions, "shortAnswerPrompt": a.get("short_answer_prompt") or ""}


def upsert_assessment(cur, passage_id, payload, passage_label, allow_empty=False):
    normalized = normalize_assessment_payload(payload, passage_label, allow_empty=allow_empty)
    questions = normalized["questions"]
    short_answer = normalized["shortAnswerPrompt"]

    cur.execute("SELECT id FROM assessments WHERE passage_id=%s", (passage_id,))
    row = cur.fetchone()
    if row:
        aid = row["id"]
        cur.execute("UPDATE assessments SET short_answer_prompt=%s WHERE id=%s", (short_answer, aid))
        cur.execute("DELETE FROM assessment_questions WHERE assessment_id=%s", (aid,))
    else:
        cur.execute("INSERT INTO assessments (passage_id,short_answer_prompt) VALUES (%s,%s)", (passage_id, short_answer))
        aid = cur.lastrowid

    for i, q in enumerate(questions):
        cur.execute(
            """
            INSERT INTO assessment_questions (
              assessment_id,sort_order,difficulty,type,prompt,options_json,answer_index,answer_key,answer_keys_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                aid,
                i,
                q["difficulty"],
                q["type"],
                q["prompt"],
                json.dumps(q["options"], ensure_ascii=False) if q["options"] else None,
                q["answerIndex"],
                q["answerKey"] or None,
                json.dumps(q["answerKeys"], ensure_ascii=False) if q["answerKeys"] else None,
            ),
        )


def get_weekly_assignments(cur, week):
    out = {"EASY": [], "MODERATE": [], "HARD": []}
    cur.execute("SELECT class_level, passage_id FROM weekly_assignments WHERE week_no=%s ORDER BY id", (week,))
    for row in cur.fetchall():
        out[normalize_class_level(row["class_level"])] += [row["passage_id"]]
    return out


def get_passage_usage_weeks(cur):
    usage = {}
    cur.execute("SELECT passage_id, week_no FROM weekly_assignments ORDER BY week_no, id")
    for row in cur.fetchall():
        usage.setdefault(row["passage_id"], []).append(int(row["week_no"]))
    return usage


def student_row(cur, user):
    sid = user.get("student_id")
    if sid:
        cur.execute("SELECT id, full_name, grade, section, class_level, pre_score, pre_assessment_completed FROM students WHERE id=%s", (sid,))
    else:
        cur.execute("SELECT id, full_name, grade, section, class_level, pre_score, pre_assessment_completed FROM students WHERE user_id=%s", (user["id"],))
    return cur.fetchone()


def pre_assessment_completed(student):
    if not student:
        return False
    return bool(int(student.get("pre_assessment_completed") or 0))


def recommendation_for_score(score):
    normalized_score = int(score or 0)
    if normalized_score >= 80:
        return "HARD", "HARD"
    if normalized_score >= 60:
        return "MODERATE", "MODERATE"
    return "EASY", "EASY"


def fetch_student_progress(cur, student_id):
    cur.execute(
        "SELECT week_no, ROUND(AVG(score_pct)) AS score FROM quiz_attempts WHERE student_id=%s GROUP BY week_no ORDER BY week_no",
        (student_id,),
    )
    rows = cur.fetchall()
    progress = []
    for row in rows:
        score = int(row["score"] or 0)
        recommendation, difficulty = recommendation_for_score(score)
        progress.append(
            {
                "week": int(row["week_no"]),
                "score": score,
                "difficulty": difficulty,
                "recommendation": recommendation,
            }
        )

    if progress:
        return progress

    fallback_progress = {
        "s1": [
            {"week": 1, "score": 55, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 2, "score": 48, "difficulty": "HARD", "recommendation": "Step DOWN to MODERATE"},
            {"week": 3, "score": 65, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 4, "score": 71, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 5, "score": 74, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 6, "score": 78, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
        ],
        "s2": [
            {"week": 1, "score": 70, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 2, "score": 75, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
            {"week": 3, "score": 68, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 4, "score": 72, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 5, "score": 76, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 6, "score": 79, "difficulty": "HARD", "recommendation": "Maintain"},
        ],
        "s3": [
            {"week": 1, "score": 42, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 50, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 55, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
            {"week": 4, "score": 48, "difficulty": "MODERATE", "recommendation": "Step DOWN to EASY"},
            {"week": 5, "score": 57, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 6, "score": 62, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
        ],
        "s4": [
            {"week": 1, "score": 35, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 39, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 44, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 4, "score": 49, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 5, "score": 53, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 6, "score": 58, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
        ],
        "s5": [
            {"week": 1, "score": 63, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 2, "score": 67, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 3, "score": 72, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 4, "score": 78, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
            {"week": 5, "score": 70, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 6, "score": 74, "difficulty": "HARD", "recommendation": "Maintain"},
        ],
        "s6": [
            {"week": 1, "score": 76, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 2, "score": 82, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 3, "score": 79, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 4, "score": 85, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 5, "score": 83, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 6, "score": 87, "difficulty": "HARD", "recommendation": "Maintain"},
        ],
        "s7": [
            {"week": 1, "score": 40, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 47, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 53, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 4, "score": 58, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
            {"week": 5, "score": 52, "difficulty": "MODERATE", "recommendation": "Step DOWN to EASY"},
            {"week": 6, "score": 60, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
        ],
        "s8": [
            {"week": 1, "score": 57, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 2, "score": 61, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 3, "score": 66, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 4, "score": 70, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 5, "score": 73, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 6, "score": 77, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
        ],
        "s9": [
            {"week": 1, "score": 71, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 2, "score": 75, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 3, "score": 80, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 4, "score": 77, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 5, "score": 82, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 6, "score": 84, "difficulty": "HARD", "recommendation": "Maintain"},
        ],
        "s10": [
            {"week": 1, "score": 38, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 43, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 47, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 4, "score": 52, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 5, "score": 59, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
            {"week": 6, "score": 67, "difficulty": "MODERATE", "recommendation": "Maintain"},
        ],
        "s11": [
            {"week": 1, "score": 36, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 41, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 45, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 4, "score": 50, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 5, "score": 55, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
            {"week": 6, "score": 61, "difficulty": "MODERATE", "recommendation": "Maintain"},
        ],
        "s12": [
            {"week": 1, "score": 82, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 85, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 88, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
            {"week": 4, "score": 80, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 5, "score": 83, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 6, "score": 86, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
        ],
        "s13": [
            {"week": 1, "score": 66, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 2, "score": 69, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 3, "score": 73, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
            {"week": 4, "score": 70, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 5, "score": 68, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 6, "score": 74, "difficulty": "HARD", "recommendation": "Maintain"},
        ],
        "s14": [
            {"week": 1, "score": 52, "difficulty": "HARD", "recommendation": "Maintain"},
            {"week": 2, "score": 49, "difficulty": "HARD", "recommendation": "Step DOWN to MODERATE"},
            {"week": 3, "score": 63, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 4, "score": 58, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 5, "score": 61, "difficulty": "MODERATE", "recommendation": "Maintain"},
            {"week": 6, "score": 65, "difficulty": "MODERATE", "recommendation": "Step UP to HARD"},
        ],
        "s15": [
            {"week": 1, "score": 34, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 2, "score": 39, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 3, "score": 44, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 4, "score": 49, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 5, "score": 54, "difficulty": "EASY", "recommendation": "Maintain"},
            {"week": 6, "score": 60, "difficulty": "EASY", "recommendation": "Step UP to MODERATE"},
        ],
    }
    return fallback_progress.get(str(student_id), [])


def fetch_teacher_student_summaries(cur):
    cur.execute(
        """
        SELECT s.id,s.full_name,s.grade,s.section,s.class_level,s.pre_score,s.pre_assessment_completed,u.email
        FROM students s
        JOIN users u ON u.id=s.user_id
        ORDER BY s.full_name ASC
        """
    )
    students = []
    for row in cur.fetchall():
        progress = fetch_student_progress(cur, row["id"])
        latest = progress[-1] if progress else None
        cur.execute(
            "SELECT COUNT(*) AS total FROM quiz_attempts WHERE student_id=%s AND short_answer_text IS NOT NULL AND teacher_score IS NULL",
            (row["id"],),
        )
        pending_reviews = int(cur.fetchone()["total"] or 0)
        students.append(
            {
                "id": row["id"],
                "name": row["full_name"],
                "email": row["email"],
                "grade": row["grade"],
                "section": row["section"],
                "classLevel": row["class_level"],
                "preScore": int(row["pre_score"] or 0),
                "preAssessmentCompleted": bool(int(row["pre_assessment_completed"] or 0)),
                "latestScore": latest["score"] if latest else None,
                "latestWeek": latest["week"] if latest else None,
                "latestRecommendation": latest["recommendation"] if latest else None,
                "latestDifficulty": latest["difficulty"] if latest else None,
                "recentScores": [item["score"] for item in progress[-2:]],
                "progress": progress,
                "pendingReviewCount": pending_reviews,
            }
        )
    return students


def get_stagnation_details(progress):
    if len(progress) < 2:
        return False, ""

    previous = progress[-2]
    latest = progress[-1]
    if int(latest["score"]) > int(previous["score"]):
        return False, ""

    return (
        True,
        f"No improvement from Week {previous['week']} ({previous['score']}%) "
        f"to Week {latest['week']} ({latest['score']}%)."
    )


def build_report_status(student, is_stagnant):
    if not student["preAssessmentCompleted"]:
        return "Pre-Assessment Pending", "hard"
    if student["latestScore"] is None:
        return "Awaiting Weekly Submission", "primary"
    if int(student["latestWeek"] or 0) >= TOTAL_PROGRAM_WEEKS:
        return f"Week {TOTAL_PROGRAM_WEEKS} Recorded", "success"
    if is_stagnant:
        return "Stagnant", "hard"
    return "Improving", "easy"


def build_teacher_report_summary(cur, active_week):
    students = fetch_teacher_student_summaries(cur)
    report_rows = []
    for student in students:
        is_stagnant, stagnant_reason = get_stagnation_details(student["progress"])
        pre_score = int(student["preScore"] or 0) if student["preAssessmentCompleted"] else None
        latest_score = student["latestScore"]
        improvement = None
        if pre_score is not None and latest_score is not None:
            improvement = int(latest_score) - int(pre_score)
        status_label, status_tone = build_report_status(student, is_stagnant)
        report_rows.append(
            {
                "id": student["id"],
                "name": student["name"],
                "email": student["email"],
                "grade": student["grade"],
                "section": student["section"],
                "classLevel": student["classLevel"],
                "preScore": pre_score,
                "preAssessmentCompleted": student["preAssessmentCompleted"],
                "latestScore": latest_score,
                "latestWeek": student["latestWeek"],
                "latestRecommendation": student["latestRecommendation"],
                "latestDifficulty": student["latestDifficulty"],
                "improvement": improvement,
                "statusLabel": status_label,
                "statusTone": status_tone,
                "isStagnant": is_stagnant,
                "stagnantReason": stagnant_reason,
                "progress": student["progress"],
            }
        )

    completion_base = max(1, len(report_rows) * TOTAL_PROGRAM_WEEKS)
    completion_value = sum(min(TOTAL_PROGRAM_WEEKS, int(student["latestWeek"] or 0)) for student in report_rows)
    completion_percent = int(round((completion_value / completion_base) * 100)) if report_rows else 0
    stagnant_students = [student for student in report_rows if student["isStagnant"]]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "activeWeek": normalize_week(active_week),
        "studentCount": len(report_rows),
        "preAverage": average_numbers(
            student["preScore"] for student in report_rows if student["preAssessmentCompleted"]
        ),
        "currentAverage": average_numbers(student["latestScore"] for student in report_rows),
        "completionPercent": completion_percent,
        "stagnantCount": len(stagnant_students),
        "stagnantStudents": stagnant_students,
        "students": report_rows,
    }


def fetch_pending_short_answer(cur, student_id):
    cur.execute(
        """
        SELECT qa.passage_id,qa.short_answer_text,qa.submitted_at,p.title,p.label,a.short_answer_prompt
        FROM quiz_attempts qa
        JOIN passages p ON p.id=qa.passage_id
        LEFT JOIN assessments a ON a.passage_id=qa.passage_id
        WHERE qa.student_id=%s
          AND qa.short_answer_text IS NOT NULL
          AND qa.teacher_score IS NULL
        ORDER BY qa.submitted_at DESC
        LIMIT 1
        """,
        (student_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "passageId": row["passage_id"],
        "passageTitle": row["title"],
        "label": row["label"],
        "prompt": row.get("short_answer_prompt") or "",
        "response": row.get("short_answer_text") or "",
        "submittedAt": row["submitted_at"].isoformat() if row.get("submitted_at") else None,
    }


def fetch_pending_short_answers(cur, student_id):
    cur.execute(
        """
        SELECT qa.id,qa.passage_id,qa.week_no,qa.short_answer_text,qa.submitted_at,
               p.title,p.label,a.short_answer_prompt
        FROM quiz_attempts qa
        JOIN passages p ON p.id=qa.passage_id
        LEFT JOIN assessments a ON a.passage_id=qa.passage_id
        WHERE qa.student_id=%s
          AND qa.short_answer_text IS NOT NULL
          AND qa.teacher_score IS NULL
        ORDER BY qa.submitted_at DESC, qa.id DESC
        """,
        (student_id,),
    )
    rows = cur.fetchall()
    items = []
    for row in rows:
        items.append(
            {
                "attemptId": int(row["id"]),
                "passageId": row["passage_id"],
                "passageTitle": row["title"],
                "week": int(row["week_no"]),
                "label": row["label"],
                "prompt": row.get("short_answer_prompt") or "",
                "response": row.get("short_answer_text") or "",
                "submittedAt": row["submitted_at"].isoformat() if row.get("submitted_at") else None,
            }
        )
    return items
def init_database():
    global DB_READY

    conn = None

    # Wait for Railway MySQL to become available
    for attempt in range(10):
        try:
            conn = mysql.connector.connect(
                **mysql_config(False),
                connection_timeout=30,
                autocommit=False
            )
            break
        except Exception as exc:
            print(f"Database unavailable (attempt {attempt+1}/10): {exc}")
            time.sleep(3)

    if conn is None:
        return False

    try:
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
        cur.close()
        conn.close()

        if os.environ.get("READWISE_SCHEMA_ONLY") != "1":
            run_migrations()

        with db_cursor(True) as (_, cur):
            schema = [
            """CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY,email VARCHAR(255) UNIQUE NOT NULL,password_hash VARCHAR(255) NOT NULL,role ENUM('teacher','student','admin') NOT NULL,is_active TINYINT(1) NOT NULL DEFAULT 1,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """ALTER TABLE users MODIFY COLUMN role ENUM('teacher','student','admin') NOT NULL""",
            """CREATE TABLE IF NOT EXISTS program_settings (id TINYINT PRIMARY KEY,program_start_date DATE NOT NULL,manual_override_week TINYINT NULL,updated_by INT NULL,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,CONSTRAINT chk_program_settings_id CHECK (id=1),FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS auth_tokens (id BIGINT AUTO_INCREMENT PRIMARY KEY,user_id INT NOT NULL,token VARCHAR(128) UNIQUE NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,INDEX idx_auth_tokens_user (user_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS students (id VARCHAR(20) PRIMARY KEY,user_id INT UNIQUE NOT NULL,full_name VARCHAR(255) NOT NULL,grade VARCHAR(20) NOT NULL,section VARCHAR(100) NOT NULL,class_level ENUM('EASY','MODERATE','HARD') NOT NULL DEFAULT 'EASY',pre_score INT NOT NULL DEFAULT 0,pre_assessment_completed TINYINT(1) NOT NULL DEFAULT 0,pre_assessment_completed_at TIMESTAMP NULL,avatar_type ENUM('initials','preset','upload') NOT NULL DEFAULT 'initials',avatar_value MEDIUMTEXT NULL,FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS student_level_progressions (id BIGINT AUTO_INCREMENT PRIMARY KEY,student_id VARCHAR(20) NOT NULL,week_no TINYINT NOT NULL,previous_level ENUM('EASY','MODERATE','HARD') NOT NULL,new_level ENUM('EASY','MODERATE','HARD') NOT NULL,average_score INT NOT NULL,recommendation VARCHAR(30) NOT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,UNIQUE KEY uniq_student_progression_week (student_id,week_no),FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS passages (id VARCHAR(20) PRIMARY KEY,title VARCHAR(255) NOT NULL,genre VARCHAR(100) NOT NULL,text MEDIUMTEXT NOT NULL,label ENUM('EASY','MODERATE','HARD') NOT NULL,words INT NOT NULL,est_minutes INT NOT NULL,confidence DECIMAL(5,2) NULL,is_draft TINYINT(1) NOT NULL DEFAULT 0,created_by INT NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS assessments (id INT AUTO_INCREMENT PRIMARY KEY,passage_id VARCHAR(20) UNIQUE NOT NULL,short_answer_prompt TEXT NULL,FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS assessment_questions (id INT AUTO_INCREMENT PRIMARY KEY,assessment_id INT NOT NULL,sort_order INT NOT NULL DEFAULT 0,difficulty ENUM('EASY','MODERATE','DIFFICULT','CUSTOM') NOT NULL DEFAULT 'EASY',type VARCHAR(60) NOT NULL,prompt TEXT NOT NULL,options_json JSON NULL,answer_index INT NULL,answer_key VARCHAR(255) NULL,answer_keys_json JSON NULL,FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,INDEX idx_q_sort (assessment_id, sort_order)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS weekly_assignments (id INT AUTO_INCREMENT PRIMARY KEY,week_no TINYINT NOT NULL,class_level ENUM('EASY','MODERATE','HARD') NOT NULL,passage_id VARCHAR(20) NOT NULL,UNIQUE KEY uniq_assign (week_no,class_level,passage_id),FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS passage_completions (id BIGINT AUTO_INCREMENT PRIMARY KEY,student_id VARCHAR(20) NOT NULL,week_no TINYINT NOT NULL,passage_id VARCHAR(20) NOT NULL,completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,UNIQUE KEY uniq_complete (student_id,week_no,passage_id),FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS quiz_attempts (id BIGINT AUTO_INCREMENT PRIMARY KEY,student_id VARCHAR(20) NOT NULL,passage_id VARCHAR(20) NOT NULL,week_no TINYINT NOT NULL,score_pct INT NOT NULL DEFAULT 0,correct_count INT NOT NULL DEFAULT 0,total_count INT NOT NULL DEFAULT 0,difficulty_rating TINYINT NULL,short_answer_text TEXT NULL,reading_time VARCHAR(20) NULL,responses_json JSON NULL,teacher_score TINYINT NULL,teacher_feedback TEXT NULL,teacher_scored_by INT NULL,teacher_scored_at TIMESTAMP NULL,submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE,FOREIGN KEY (teacher_scored_by) REFERENCES users(id) ON DELETE SET NULL,INDEX idx_progress (student_id, week_no),UNIQUE KEY uniq_student_passage_week (student_id, passage_id, week_no)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS student_reading_sessions (id BIGINT AUTO_INCREMENT PRIMARY KEY,event_id VARCHAR(120) NOT NULL,student_id VARCHAR(20) NOT NULL,passage_id VARCHAR(20) NOT NULL,week_no TINYINT NOT NULL,reading_seconds INT NOT NULL DEFAULT 0,formatted_time VARCHAR(20) NULL,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,UNIQUE KEY uniq_reading_event (event_id),INDEX idx_reading_student_week (student_id, week_no),FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS student_reading_progress_drafts (id BIGINT AUTO_INCREMENT PRIMARY KEY,student_id VARCHAR(20) NOT NULL,passage_id VARCHAR(20) NOT NULL,week_no TINYINT NOT NULL,reading_seconds INT NOT NULL DEFAULT 0,last_event_id VARCHAR(120) NULL,is_locked TINYINT(1) NOT NULL DEFAULT 0,is_submitted TINYINT(1) NOT NULL DEFAULT 0,completed_at TIMESTAMP NULL,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,UNIQUE KEY uniq_reading_draft (student_id, passage_id, week_no),INDEX idx_reading_draft_student_week (student_id, week_no),FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            # ===== Production relational model (transitional minimal subset for backfill) =====
            # Identity/hierarchy (added first; compatibility-first: no endpoint cutover yet)
            """CREATE TABLE IF NOT EXISTS reading_levels (
                id INT AUTO_INCREMENT PRIMARY KEY,
                code ENUM('EASY','MODERATE','HARD') NOT NULL UNIQUE,
                description VARCHAR(255) NULL,
                threshold_min INT NOT NULL DEFAULT 0,
                threshold_max INT NOT NULL DEFAULT 100
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS teachers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                full_name VARCHAR(255) NOT NULL,
                department VARCHAR(100) NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS classes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                grade_level VARCHAR(20) NOT NULL,
                curriculum_code VARCHAR(20) NOT NULL,
                adviser_teacher_id INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_classes_grade (grade_level),
                FOREIGN KEY (adviser_teacher_id) REFERENCES teachers(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS sections (
                id INT AUTO_INCREMENT PRIMARY KEY,
                class_id INT NOT NULL,
                name VARCHAR(100) NOT NULL,
                school_year INT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_section (class_id, name, school_year),
                FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS reading_sessions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                legacy_quiz_attempt_id BIGINT UNIQUE NULL,
                student_id VARCHAR(20) NOT NULL,
                passage_id VARCHAR(20) NOT NULL,
                week_no TINYINT NOT NULL,
                started_at TIMESTAMP NULL,
                completed_at TIMESTAMP NULL,
                duration_seconds INT NOT NULL DEFAULT 0,
                status ENUM('in_progress','completed') NOT NULL DEFAULT 'in_progress',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_reading_sessions_student_week (student_id, week_no),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS student_answers (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                legacy_quiz_attempt_id BIGINT UNIQUE NULL,
                session_id BIGINT NOT NULL,
                question_id BIGINT NULL,
                answer_payload_json JSON NULL,
                is_correct_nullable TINYINT NULL,
                submitted_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_session_question (session_id, question_id),
                INDEX idx_student_answers_session_question (session_id, question_id),
                FOREIGN KEY (session_id) REFERENCES reading_sessions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS short_answer_responses (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                legacy_quiz_attempt_id BIGINT UNIQUE NULL,
                student_answer_id BIGINT NOT NULL,
                response_text TEXT NOT NULL,
                needs_manual_review TINYINT(1) NOT NULL DEFAULT 0,
                submitted_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_student_answer (student_answer_id),
                FOREIGN KEY (student_answer_id) REFERENCES student_answers(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS short_answer_scores (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                legacy_quiz_attempt_id BIGINT UNIQUE NULL,
                short_answer_response_id BIGINT NOT NULL,
                teacher_id INT NULL,
                score_binary TINYINT NULL,
                feedback TEXT NULL,
                scored_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_short_answer_response (short_answer_response_id),
                FOREIGN KEY (short_answer_response_id) REFERENCES short_answer_responses(id) ON DELETE CASCADE,
                FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS scores (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                legacy_quiz_attempt_id BIGINT UNIQUE NULL,
                session_id BIGINT NOT NULL,
                objective_score_pct INT NULL,
                short_answer_score_pct INT NULL,
                total_score_pct INT NULL,
                computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_session_score (session_id),
                FOREIGN KEY (session_id) REFERENCES reading_sessions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS reading_history (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                student_id VARCHAR(20) NOT NULL,
                session_id BIGINT NULL,
                summary_json JSON NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_reading_history_student_created (student_id, created_at),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES reading_sessions(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS recommendations (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                student_id VARCHAR(20) NOT NULL,
                week_no TINYINT NOT NULL DEFAULT 1,
                source_type VARCHAR(20) NOT NULL DEFAULT 'rule',
                recommendation_text VARCHAR(255) NOT NULL,
                suggested_level_id INT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_recommendation_student_week (student_id, week_no),
                INDEX idx_recommendations_student_created (student_id, created_at),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (suggested_level_id) REFERENCES reading_levels(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS audit_logs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NULL,
                student_id VARCHAR(20) NULL,
                action VARCHAR(80) NOT NULL,
                details JSON NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_audit_user_action (user_id, action),
                INDEX idx_audit_student_created (student_id, created_at),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            # ===== ER Production relational model (questions/choices) =====
            """CREATE TABLE IF NOT EXISTS questions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                passage_id VARCHAR(20) NOT NULL,
                type VARCHAR(60) NOT NULL,
                prompt TEXT NOT NULL,
                sequence_no INT NOT NULL,
                metadata_json JSON NULL,
                INDEX idx_questions_passage_seq (passage_id, sequence_no),
                FOREIGN KEY (passage_id) REFERENCES passages(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

            """CREATE TABLE IF NOT EXISTS choices (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                question_id BIGINT NOT NULL,
                choice_text TEXT NOT NULL,
                is_correct TINYINT(1) NOT NULL DEFAULT 0,
                sequence_no INT NOT NULL DEFAULT 0,
                INDEX idx_choices_question_seq (question_id, sequence_no),
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        ]
            for sql in schema:
                cur.execute(sql)

            if os.environ.get("READWISE_SCHEMA_ONLY") == "1":
                conn.commit()
                cur.close()
                conn.close()
                DB_READY = True
                return True

            # ===== Backfill next identity/hierarchy tables (compatibility-first) =====
            # reading_levels: EASY/MODERATE/HARD with temporary thresholds
            cur.execute("SELECT COUNT(*) AS c FROM reading_levels")
            if int(cur.fetchone()["c"] or 0) == 0:
                cur.execute(
                    """
                    INSERT INTO reading_levels (code, description, threshold_min, threshold_max)
                    VALUES
                      ('EASY','Below 55',0,54),
                      ('MODERATE','55 to 69',55,69),
                      ('HARD','70 and above',70,100)
                    """
                )

        # teachers: 1 row per legacy users(role=teacher)
            cur.execute(
                """
                SELECT COUNT(*) AS c
                FROM teachers t
                JOIN users u ON u.id=t.user_id
                WHERE u.role='teacher'
                """
            )
            # If there are no teachers yet, seed all teacher users.
            if int(cur.fetchone()["c"] or 0) == 0:
                cur.execute(
                    """
                    INSERT INTO teachers (user_id, full_name, department)
                    SELECT
                      u.id AS user_id,
                      -- placeholder full_name: email local-part (or email if no @)
                      CASE
                        WHEN INSTR(u.email,'@')>0 THEN SUBSTRING_INDEX(u.email,'@',1)
                        ELSE u.email
                      END AS full_name,
                      NULL AS department
                    FROM users u
                    WHERE u.role='teacher'
                    """
                )

        # classes & sections: derived from legacy students (grade_level + class_level + section)
        # We'll create:
        # - one class per distinct (grade, class_level)
        # - one section per distinct (grade, class_level, section name)
            cur.execute("SELECT COUNT(*) AS c FROM classes")
            if int(cur.fetchone()["c"] or 0) == 0:
                # Ensure we have at least one teacher to reference adviser_teacher_id (can be NULL)
                cur.execute("SELECT id FROM teachers ORDER BY id DESC LIMIT 1")
                adviser = cur.fetchone()
                adviser_teacher_id = adviser["id"] if adviser else None

                # Create classes
                cur.execute(
                    """
                    INSERT INTO classes (grade_level, curriculum_code, adviser_teacher_id)
                    SELECT
                      s.grade AS grade_level,
                      s.class_level AS curriculum_code,
                      %s AS adviser_teacher_id
                    FROM students s
                    GROUP BY s.grade, s.class_level
                    """,
                    (adviser_teacher_id,),
                )

            # Use current year as placeholder school_year
            cur.execute("SELECT YEAR(CURRENT_DATE()) AS y")
            current_year = int(cur.fetchone()["y"])

            cur.execute(
                """
                INSERT IGNORE INTO sections (class_id, name, school_year)
                SELECT
                  c.id AS class_id,
                  s.section AS name,
                  %s AS school_year
                FROM students s
                JOIN classes c
                  ON c.grade_level=s.grade AND c.curriculum_code=s.class_level
                GROUP BY c.id, s.section
                """,
                (current_year,),
            )

        # ===== End backfill =====

        cur.execute("SELECT id FROM program_settings WHERE id=1")
        if not cur.fetchone():
            cur.execute("SELECT CURRENT_DATE() AS today")
            today = cur.fetchone()["today"]
            cur.execute(
                """
                INSERT INTO program_settings (id, program_start_date, manual_override_week, updated_by)
                VALUES (1, %s, NULL, NULL)
                """,
                (today,),
            )

        cur.execute("SHOW COLUMNS FROM students LIKE 'avatar_type'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE students ADD COLUMN avatar_type ENUM('initials','preset','upload') NOT NULL DEFAULT 'initials' AFTER pre_score"
            )

        cur.execute("SHOW COLUMNS FROM students LIKE 'avatar_value'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE students ADD COLUMN avatar_value MEDIUMTEXT NULL AFTER avatar_type"
            )

        cur.execute("SHOW COLUMNS FROM students LIKE 'pre_assessment_completed'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE students ADD COLUMN pre_assessment_completed TINYINT(1) NOT NULL DEFAULT 0 AFTER pre_score"
            )

        cur.execute("SHOW COLUMNS FROM students LIKE 'pre_assessment_completed_at'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE students ADD COLUMN pre_assessment_completed_at TIMESTAMP NULL AFTER pre_assessment_completed"
            )

        cur.execute("SHOW COLUMNS FROM passages LIKE 'is_draft'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE passages ADD COLUMN is_draft TINYINT(1) NOT NULL DEFAULT 0 AFTER confidence"
            )

        cur.execute("SHOW COLUMNS FROM student_reading_progress_drafts LIKE 'is_locked'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE student_reading_progress_drafts ADD COLUMN is_locked TINYINT(1) NOT NULL DEFAULT 0 AFTER last_event_id"
            )

        cur.execute("SHOW COLUMNS FROM student_reading_progress_drafts LIKE 'completed_at'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE student_reading_progress_drafts ADD COLUMN completed_at TIMESTAMP NULL AFTER is_locked"
            )

        cur.execute("SHOW COLUMNS FROM student_reading_progress_drafts LIKE 'is_submitted'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE student_reading_progress_drafts ADD COLUMN is_submitted TINYINT(1) NOT NULL DEFAULT 0 AFTER is_locked"
            )

        cur.execute("SHOW COLUMNS FROM recommendations LIKE 'week_no'")
        if not cur.fetchone():
            cur.execute(
                "ALTER TABLE recommendations ADD COLUMN week_no TINYINT NOT NULL DEFAULT 1 AFTER student_id"
            )

        cur.execute("SHOW INDEX FROM recommendations WHERE Key_name='uniq_recommendation_student_week'")
        rec_uniq_row = cur.fetchone()
        cur.fetchall()
        if not rec_uniq_row:
            cur.execute(
                """
                DELETE r1 FROM recommendations r1
                JOIN recommendations r2
                  ON r1.student_id = r2.student_id
                 AND r1.week_no = r2.week_no
                 AND r1.id > r2.id
                """
            )
            cur.execute(
                "ALTER TABLE recommendations ADD UNIQUE KEY uniq_recommendation_student_week (student_id, week_no)"
            )

        cur.execute("SHOW INDEX FROM quiz_attempts WHERE Key_name='uniq_student_passage_week'")
        uniq_index_row = cur.fetchone()
        cur.fetchall()
        if not uniq_index_row:
            cur.execute(
                """
                DELETE qa1 FROM quiz_attempts qa1
                JOIN quiz_attempts qa2
                  ON qa1.student_id = qa2.student_id
                 AND qa1.passage_id = qa2.passage_id
                 AND qa1.week_no = qa2.week_no
                 AND qa1.id > qa2.id
                """
            )
            cur.execute(
                "ALTER TABLE quiz_attempts ADD UNIQUE KEY uniq_student_passage_week (student_id, passage_id, week_no)"
            )

        cur.execute("SHOW COLUMNS FROM quiz_attempts LIKE 'teacher_score'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE quiz_attempts ADD COLUMN teacher_score TINYINT NULL AFTER responses_json")

        cur.execute("SHOW COLUMNS FROM quiz_attempts LIKE 'teacher_feedback'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE quiz_attempts ADD COLUMN teacher_feedback TEXT NULL AFTER teacher_score")

        cur.execute("SHOW COLUMNS FROM quiz_attempts LIKE 'teacher_scored_by'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE quiz_attempts ADD COLUMN teacher_scored_by INT NULL AFTER teacher_feedback")

        cur.execute("SHOW COLUMNS FROM quiz_attempts LIKE 'teacher_scored_at'")
        if not cur.fetchone():
            cur.execute("ALTER TABLE quiz_attempts ADD COLUMN teacher_scored_at TIMESTAMP NULL AFTER teacher_scored_by")

        cur.execute(
            "SHOW INDEX FROM quiz_attempts WHERE Key_name='idx_quiz_teacher_scored_by'"
        )
        teacher_idx_row = cur.fetchone()
        cur.fetchall()
        if not teacher_idx_row:
            cur.execute("ALTER TABLE quiz_attempts ADD INDEX idx_quiz_teacher_scored_by (teacher_scored_by)")

        cur.execute(
            """
            SELECT CONSTRAINT_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA=%s
              AND TABLE_NAME='quiz_attempts'
              AND COLUMN_NAME='teacher_scored_by'
              AND REFERENCED_TABLE_NAME='users'
            """,
            (DB_NAME,),
        )
        teacher_fk_row = cur.fetchone()
        cur.fetchall()
        if not teacher_fk_row:
            cur.execute(
                """
                ALTER TABLE quiz_attempts
                ADD CONSTRAINT fk_quiz_attempts_teacher_scored_by
                FOREIGN KEY (teacher_scored_by) REFERENCES users(id) ON DELETE SET NULL
                """
            )

        def upsert_user(email, password, role):
            cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            row = cur.fetchone()
            hashed = generate_password_hash(password)
            if row:
                cur.execute("UPDATE users SET password_hash=%s,role=%s,is_active=1 WHERE id=%s", (hashed, role, row["id"]))
                return row["id"]
            cur.execute("INSERT INTO users (email,password_hash,role,is_active) VALUES (%s,%s,%s,1)", (email, hashed, role))
            return cur.lastrowid

        for admin in SEED_ADMINS:
            upsert_user(admin["email"], admin["password"], "admin")

        for teacher in SEED_TEACHERS:
            upsert_user(teacher["email"], teacher["password"], "teacher")

        for student in SEED_STUDENTS:
            uid = upsert_user(student["email"], student["password"], "student")
            pre_score = int(student["pre"])
            pre_completed = 1 if pre_score > 0 else 0
            cur.execute(
                """
                INSERT INTO students (id,user_id,full_name,grade,section,class_level,pre_score,pre_assessment_completed)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  user_id=VALUES(user_id),
                  full_name=VALUES(full_name),
                  grade=VALUES(grade),
                  section=VALUES(section),
                  class_level=VALUES(class_level),
                  pre_score=VALUES(pre_score),
                  pre_assessment_completed=VALUES(pre_assessment_completed)
                """,
                (student["id"], uid, student["name"], student["grade"], student["section"], normalize_class_level(student["class"]), pre_score, pre_completed),
            )
            if pre_completed:
                cur.execute(
                    "UPDATE students SET pre_assessment_completed_at=COALESCE(pre_assessment_completed_at, NOW()) WHERE id=%s",
                    (student["id"],),
                )

        cur.execute("SELECT id FROM users WHERE email=%s", ("ms.villanueva@pnhs.edu",))
        teacher_id = cur.fetchone()["id"]

        def should_refresh_seed_assessment(passage_id, seed_assessment):
            cur.execute("SELECT id, short_answer_prompt FROM assessments WHERE passage_id=%s", (passage_id,))
            assessment_row = cur.fetchone()
            if not assessment_row:
                return True

            cur.execute("SELECT COUNT(*) AS total FROM assessment_questions WHERE assessment_id=%s", (assessment_row["id"],))
            total_questions = int(cur.fetchone()["total"] or 0)
            has_seed_short_answer = bool(str(seed_assessment.get("shortAnswerPrompt") or "").strip())
            current_short_answer = str(assessment_row.get("short_answer_prompt") or "").strip()

            # Upgrade the original sparse demo seeds (0-1 questions) to the richer seeded library.
            if total_questions <= 1:
                return True
            if has_seed_short_answer and total_questions <= 1 and not current_short_answer:
                return True
            return False

        for p in SEED_PASSAGES:
            words = count_words(p["text"])
            cur.execute(
                "INSERT IGNORE INTO passages (id,title,genre,text,label,words,est_minutes,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (p["id"], p["title"], p["genre"], p["text"], normalize_class_level(p["label"]), words, estimate_minutes(words), teacher_id),
            )
            seed_assessment = SEED_ASSESSMENTS.get(p["id"], {"questions": []})
            if should_refresh_seed_assessment(p["id"], seed_assessment):
                upsert_assessment(cur, p["id"], seed_assessment, p["label"])

        cur.execute("SELECT COUNT(*) AS total FROM weekly_assignments")
        if int(cur.fetchone()["total"]) == 0:
            by_class = {
                "EASY": [p["id"] for p in SEED_PASSAGES if normalize_class_level(p["label"]) == "EASY"],
                "MODERATE": [p["id"] for p in SEED_PASSAGES if normalize_class_level(p["label"]) == "MODERATE"],
                "HARD": [p["id"] for p in SEED_PASSAGES if normalize_class_level(p["label"]) == "HARD"],
            }
            for week in range(1, TOTAL_PROGRAM_WEEKS + 1):
                for class_level, ids in by_class.items():
                    for pid in ids[:MAX_WEEKLY_PASSAGES_PER_CLASS]:
                        cur.execute("INSERT IGNORE INTO weekly_assignments (week_no,class_level,passage_id) VALUES (%s,%s,%s)", (week, class_level, pid))

        DB_READY = True
        return True

    except Exception as exc:
        print(f"Database initialization failed: {exc}")
        traceback.print_exc()
        DB_READY = False
        return False

@app.errorhandler(mysql.connector.Error)
def handle_mysql_error(_):
    return api_error("Database operation failed. Check MySQL configuration and service.", 500)


MIGRATION_FILES = [
    "migrations/001_initial_schema.sql",
    "migrations/002_add_operational_support.sql",
    "migrations/003_add_program_and_pre_assessment.sql",
]


def run_migrations():
    if not os.path.exists("migrations"):
        return []
    applied = []
    for migration_file in MIGRATION_FILES:
        if not os.path.exists(migration_file):
            continue
        with open(migration_file, "r", encoding="utf-8") as handle:
            sql = handle.read()
        if not sql.strip():
            continue
        with db_cursor() as (_, cur):
            cur.execute(sql)
        applied.append(migration_file)
    return applied


from routes.auth_routes import auth_bp
from routes.helpers import enforce_csrf_for_state_change
from routes.passage_routes import passage_bp
from routes.student_routes import student_bp
from routes.teacher_routes import teacher_bp
from routes.admin_routes import admin_bp
from routes.status_routes import configure_request_logging, status_bp


@app.before_request
def enforce_state_change_protection():
    error = enforce_csrf_for_state_change()
    if error is not None:
        return error


configure_request_logging(app)
app.register_blueprint(status_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(student_bp)
app.register_blueprint(teacher_bp)
app.register_blueprint(passage_bp)
app.register_blueprint(admin_bp)


def serve_frontend_file(filename):
    allowed_extensions = (".js", ".css", ".html", ".json", ".webmanifest", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico")
    allowed_roots = {
        "login.html",
        "api.js",
        "login.js",
        "runtime-config.js",
    }
    allowed_directories = (
        "stylesheets/",
        "pages/",
        "assets/",
        "image/",
        "avatar/",
    )

    normalized_filename = filename.replace("\\", "/")
    if normalized_filename.startswith("/"):
        normalized_filename = normalized_filename.lstrip("/")

    if normalized_filename in allowed_roots or any(normalized_filename.startswith(prefix) for prefix in allowed_directories):
        if os.path.splitext(normalized_filename)[1].lower() in allowed_extensions:
            return send_from_directory(os.getcwd(), normalized_filename)

    if os.path.splitext(normalized_filename)[1].lower() in allowed_extensions:
        candidate = os.path.join(os.getcwd(), normalized_filename)
        if os.path.isfile(candidate) and os.path.commonpath([os.getcwd(), candidate]) == os.getcwd():
            return send_from_directory(os.getcwd(), normalized_filename)

    # Allow mapping of top-level HTML paths to the `pages/` directory.
    # e.g. a request for `/student-dashboard.html` will be served from `pages/student-dashboard.html`
    if normalized_filename.endswith(".html"):
        pages_path = os.path.join(os.getcwd(), "pages")
        candidate = os.path.join(pages_path, normalized_filename)
        if os.path.isfile(candidate):
            return send_from_directory(pages_path, normalized_filename)

    abort(404)


CLEAN_PAGE_ROUTES = {
    "login": "login.html",
    "student-dashboard": "pages/student-dashboard.html",
    "student-reading": "pages/student-reading.html",
    "student-profile": "pages/student-profile.html",
    "student-progress": "pages/student-progress.html",
    "student-results": "pages/student-results.html",
    "student-passage": "pages/student-passage.html",
    "student-pre-assessment": "pages/student-pre-assessment.html",
    "student-questions": "pages/student-questions.html",
    "teacher-dashboard": "pages/teacher-dashboard.html",
    "teacher-passages": "pages/teacher-passages.html",
    "teacher-submit": "pages/teacher-submit.html",
    "teacher-reports": "pages/teacher-reports.html",
    "teacher-students": "pages/teacher-students.html",
    "teacher-score": "pages/teacher-score.html",
    "teacher-student-detail": "pages/teacher-student-detail.html",
    "teacher-student-pending": "pages/teacher-student-pending.html",
    "teacher-recommendations": "pages/teacher-recommendations.html",
    "admin-login": "admin-login.html",
    "admin-dashboard": "pages/admin-dashboard.html",
    "admin-students": "pages/admin-students.html",
    "admin-teachers": "pages/admin-teachers.html",
    "admin-passages": "pages/admin-passages.html",
    "admin-pre-assessment": "pages/admin-pre-assessment.html",
}


def register_clean_page_alias(route_name, file_path):
    def route_alias():
        return send_from_directory(os.getcwd(), file_path)

    def legacy_route_alias():
        query_string = request.query_string.decode("utf-8")
        target = f"/{route_name}"
        if query_string:
            target = f"{target}?{query_string}"
        return redirect(target, code=301)

    app.add_url_rule(f"/{route_name}", endpoint=f"clean_{route_name}", view_func=route_alias)
    app.add_url_rule(f"/{route_name}.html", endpoint=f"legacy_{route_name}", view_func=legacy_route_alias)


for route_name, file_path in CLEAN_PAGE_ROUTES.items():
    register_clean_page_alias(route_name, file_path)


@app.route("/<path:filename>")
def frontend_static(filename):
    return serve_frontend_file(filename)


# Database initialization is explicit and should be performed by a separate bootstrap step,
# such as running `python seed_db.py` locally. This keeps app startup lightweight and avoids
# accidental schema changes on every run.

if __name__ == "__main__":
    print(f"Connected to MySQL database '{DB_NAME}' on {DB_HOST}:{DB_PORT}")
    app.run(debug=True, host="127.0.0.1", port=5000)
