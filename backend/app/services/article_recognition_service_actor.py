"""Private platform service principal for autonomous article recognition.

Never borrow a household user's session, nor claim a human Superuser performed
an automatic proof. HTTP routes must continue to use their own role checks.
"""

SERVICE_ACTOR_ID = "inhuis:internal:article-recognition-v1"


def validate_recognition_actor(actor_id: str, actor_type: str) -> None:
    if not isinstance(actor_id, str) or not actor_id.strip() or actor_type not in {"platform_user", "system_service"}:
        raise ValueError("Een geautoriseerde uitvoerder ontbreekt of is ongeldig.")
    if actor_type == "system_service" and actor_id != SERVICE_ACTOR_ID:
        raise ValueError("Onjuiste interne herkenningsidentiteit.")
    if actor_type == "platform_user" and actor_id == SERVICE_ACTOR_ID:
        raise ValueError("Interne herkenningsservice mag niet als menselijke gebruiker optreden.")
