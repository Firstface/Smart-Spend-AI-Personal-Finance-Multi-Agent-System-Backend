import json

from agents.education.service import answer_question

test_questions = [
    "How can I save money more effectively?",
    "What is an emergency fund?",
    "I spend all my money every month. How should I manage it better?",
    "What stocks should I buy right now?",
    "How do taxes work for freelancers in Singapore?"
]

for q in test_questions:
    print("\n" + "=" * 80)
    print(f"Question: {q}")

    response = answer_question(
        q,
        user_id="b230c1ef-ed77-46bd-aeca-7139f2e0c370"
    )

    print("Status:", response.get("status"))
    print("Answer:", response.get("answer"))
    print("Citations:")
    print(json.dumps(response.get("citations", []), indent=2, ensure_ascii=False))
    print("Retrieval:")
    print(json.dumps(response.get("retrieval", {}), indent=2, ensure_ascii=False))

    if response.get("status") == "refuse":
        print("Refusal type:", response.get("refusal_type"))