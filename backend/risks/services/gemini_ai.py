from django.conf import settings
from google import genai


def generate_ai_mitigation_two_lines(risk):
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""
Write exactly 2 short mitigation lines for this software/project risk.
Use simple words.
No bullets. No numbering.

Title: {risk.title}
Description: {risk.description}
Risk level: {risk.risk_level}
Decision: {risk.risk_decision}
"""

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
    )

    text = (response.text or "").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    if len(lines) >= 2:
        return f"{lines[0]}\n{lines[1]}"
    return text